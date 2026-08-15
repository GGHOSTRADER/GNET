"""
volume_profile.py
=================

Clean architecture Volume Profile pipeline (Redis -> Bars -> Volume Profile).

Design: stateful incremental profile
--------------------------------------
Grid is pre-allocated at session start centered on the first bar's close.
Each subsequent bar does a single:

    profile[index] += volume   (one C op, no rebuild)

Grid extension only happens if price breaks outside the pre-allocated range.
Extension adds 15% of range_ticks in the direction of the break.

Parameters
----------
tick_size   : price increment per level (e.g. 0.25 for ES futures)
range_ticks : total number of ticks pre-allocated at session start
              e.g. 400 ticks @ 0.25 = 100 price points = ±50 from open

Layering
--------
  Adapter     : Redis XREAD -> parse_xread_to_ticks -> typed Ticks (no re-validation)
  Domain      : stateful profile, pure numpy ops
  Application : session lifecycle + streaming orchestration

Snapshot cadence
----------------
_update() runs on every tick (O(1), always). _snapshot() -- which derives POC,
Value Area, and all derived features below -- only runs when
`tick.time_s % snapshot_interval_s == snapshot_interval_s - 1`, i.e. once per
bar, 1 second before bar close. snapshot_interval_s defaults to 30 (matches a
30-second bar) and is injectable to match any bar length.

Function Summary
----------------
1)  VolumeProfileError               -- raised when volume profile domain invariants are violated
2)  _require_vp(cond, msg)           -- validation guard for domain invariants
3)  _find_poc(profile, levels)       -- pure: np.argmax -> (poc_price, poc_volume)
4)  _find_value_area(profile, levels)-- pure: np.argsort + cumsum -> (val, vah) at 70% coverage
5)  _compute_derived_features(...)   -- pure: POC distance/concentration, VA width/position,
                                         vol_above_poc_ratio, profile entropy + kurtosis, POC migration
6)  VolumeProfileResult              -- dataclass: full profile snapshot emitted once per bar
7)  _SessionState                    -- dataclass: live pre-allocated profile array + metadata
8)  _init_session(bar, tick_size, range_ticks) -- pre-allocate profile array centered on first tick
9)  _update(state, bar)              -- O(1) incremental update: profile[index] += volume, extends grid if needed
10) _snapshot(state)                 -- derive price_levels, POC, VA + derived features, return VolumeProfileResult
11) stream_ticks_from_redis(...)     -- adapter: reads tick_data_validated, yields typed Ticks
12) stream_volume_profile(...)       -- application: session lifecycle, _update per tick, _snapshot once per bar
13) run_publish_loop(tick_size, range_ticks, snapshot_interval_s) -- main loop: publish one snapshot per bar to Redis
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Optional, Tuple

import numpy as np

from config.setting import (
    REDIS1_HOST, REDIS1_PORT, REDIS1_TICK_VALIDATED_STREAM,
    REDIS1_FEATURES_VP_STREAM,
)
from netwo_files.redis_tool import get_redis_connection
from netwo_files.tick_codec import parse_xread_to_ticks, XReadTickBatch

# ============================================================
# Constants
# ============================================================

VALUE_AREA_PCT   = 0.70   # standard 70% value area
EXTENSION_PCT    = 0.15   # extend grid by 15% of range_ticks on boundary break
DEFAULT_RANGE_TICKS = 400 # default pre-allocated range in ticks
DEFAULT_SNAPSHOT_INTERVAL_S = 30  # bar length in seconds -- snapshot fires 1s before each bar close


# ============================================================
# Errors
# ============================================================

class VolumeProfileError(ValueError):
    """Raised when volume profile invariants are violated."""


def _require_vp(cond: bool, msg: str) -> None:
    if not cond:
        raise VolumeProfileError(msg)


# ============================================================
# Pure domain: POC + Value Area (stateless, read-only)
# ============================================================


def _find_poc(profile: np.ndarray, price_levels: np.ndarray) -> Tuple[float, float]:
    """Return (poc_price, poc_volume) — price level with most volume."""
    idx = int(np.argmax(profile))
    return float(price_levels[idx]), float(profile[idx])


def _find_value_area(
    profile: np.ndarray,
    price_levels: np.ndarray,
    pct: float = VALUE_AREA_PCT,
) -> Tuple[float, float]:
    """
    Return (val, vah) — price bounds of the 70% value area.
    Selects levels by volume descending via argsort + cumsum (no Python loops).
    """
    total = profile.sum()
    _require_vp(total > 0.0, "Total volume is zero, cannot compute value area.")

    sorted_idx = np.argsort(profile)[::-1]
    cumvol     = np.cumsum(profile[sorted_idx])
    n_needed   = min(int(np.searchsorted(cumvol, pct * total, side="left")) + 1,
                     len(price_levels))

    selected   = sorted_idx[:n_needed]
    return float(price_levels[selected].min()), float(price_levels[selected].max())


def _compute_derived_features(
    profile: np.ndarray,
    price_levels: np.ndarray,
    poc_price: float,
    poc_volume: float,
    value_area_low: float,
    value_area_high: float,
    total_volume: float,
    current_price: float,
    tick_size: float,
    prev_poc_price: Optional[float],
) -> dict:
    """
    Pure: derive POC/VA-adjacent features from the current profile snapshot.
    All distances are expressed in ticks (divide by tick_size) so they are
    scale-free across instruments and price ranges.
    """
    poc_distance      = (current_price - poc_price) / tick_size
    poc_concentration = poc_volume / total_volume if total_volume > 0 else 0.0

    va_range    = value_area_high - value_area_low
    va_width    = va_range / tick_size
    va_position = (current_price - value_area_low) / va_range if va_range > 0 else 0.5

    vol_above_poc_ratio = (
        float(profile[price_levels > poc_price].sum()) / total_volume
        if total_volume > 0 else 0.0
    )

    # Profile entropy: -sum(p * log(p)) over nonzero levels. Low = concentrated, high = diffuse.
    if total_volume > 0:
        p  = profile / total_volume
        nz = p > 0
        profile_entropy = float(-np.sum(p[nz] * np.log(p[nz])))
    else:
        profile_entropy = 0.0

    # Profile kurtosis (excess): peakedness of the volume distribution around its mean price.
    if total_volume > 0:
        mean     = float(np.sum(price_levels * profile) / total_volume)
        variance = float(np.sum(profile * (price_levels - mean) ** 2) / total_volume)
        if variance > 0:
            fourth_moment    = float(np.sum(profile * (price_levels - mean) ** 4) / total_volume)
            profile_kurtosis = fourth_moment / (variance ** 2) - 3.0
        else:
            profile_kurtosis = 0.0
    else:
        profile_kurtosis = 0.0

    # POC migration: how far the POC moved since the previous bar's snapshot, in ticks.
    poc_migration = (
        (poc_price - prev_poc_price) / tick_size if prev_poc_price is not None else 0.0
    )

    return {
        "poc_distance":        poc_distance,
        "poc_concentration":   poc_concentration,
        "va_width":            va_width,
        "va_position":         va_position,
        "vol_above_poc_ratio": vol_above_poc_ratio,
        "profile_entropy":     profile_entropy,
        "profile_kurtosis":    profile_kurtosis,
        "poc_migration":       poc_migration,
    }


# ============================================================
# Output record
# ============================================================


@dataclass
class VolumeProfileResult:
    """
    Snapshot of the volume profile at the time of the latest bar.
    price_levels[i] and volume_at_level[i] are parallel arrays.
    """
    symbol:          str
    date:            int
    bar_num:         int
    tick_size:       float
    range_ticks:     int
    price_levels:    np.ndarray   # (L,) float64
    volume_at_level: np.ndarray   # (L,) float64
    poc_price:       float
    poc_volume:      float
    value_area_low:  float
    value_area_high: float
    total_volume:    float
    n_bars:          int
    extensions:      int          # how many grid extensions happened this session

    # Derived POC features (see _compute_derived_features)
    poc_distance:        float   # (current_price - poc_price) / tick_size
    poc_concentration:   float   # poc_volume / total_volume
    va_width:            float   # (value_area_high - value_area_low) / tick_size
    va_position:         float   # (current_price - value_area_low) / va_range, 0=VAL 1=VAH
    vol_above_poc_ratio: float   # fraction of total_volume traded above poc_price
    profile_entropy:     float   # -sum(p*log(p)); low=concentrated, high=diffuse
    profile_kurtosis:    float   # excess kurtosis of the volume distribution
    poc_migration:       float   # (poc_price - prev_poc_price) / tick_size


# ============================================================
# Stateful session: pre-allocated grid, incremental updates
# ============================================================


@dataclass
class _SessionState:
    """
    Holds the pre-allocated profile array for one trading session.

    profile[i] is the volume accumulated at price_levels[i].
    min_price is the price corresponding to index 0.
    Grid grows (via np.concatenate) only when price breaks a boundary.
    """
    profile:     np.ndarray   # (L,) float64 -- pre-allocated, grows on extension
    min_price:   float        # price at index 0
    tick_size:   float
    range_ticks: int          # original range (used to compute extension size)
    symbol:      str
    date:        int
    bar_num:     int
    n_bars:      int
    extensions:  int          # count of grid extensions this session
    last_price:    float                # most recent tick price, used as "current_price"
    prev_poc_price: Optional[float]     # POC price at the previous snapshot, for poc_migration


def _init_session(bar: Any, tick_size: float, range_ticks: int) -> _SessionState:
    """
    Pre-allocate a grid of range_ticks levels centered on the first bar's close.
    All profile values start at zero.
    """
    _require_vp(tick_size > 0.0, f"tick_size must be > 0, got {tick_size}")
    _require_vp(range_ticks > 0, f"range_ticks must be > 0, got {range_ticks}")

    # Snap first tick price to grid (high == low for tick data)
    snapped   = round(bar.high / tick_size) * tick_size
    half      = (range_ticks // 2) * tick_size
    min_price = snapped - half

    return _SessionState(
        profile=np.zeros(range_ticks + 1, dtype=np.float64),
        min_price=min_price,
        tick_size=tick_size,
        range_ticks=range_ticks,
        symbol=bar.symbol,
        date=bar.date,
        bar_num=bar.bar_num,
        n_bars=0,
        extensions=0,
        last_price=snapped,
        prev_poc_price=None,
    )


def _update(state: _SessionState, bar: Any) -> None:
    """
    Add one bar to the stateful profile. O(1) in the common case.

    Steps
    -----
    1. Snap close to nearest tick
    2. Compute integer index into profile array
    3. If index is within bounds: profile[index] += volume  (single C op)
    4. If index is out of bounds: extend the array by 15% of range_ticks
       in the direction of the break, then add volume
    """
    # high == low for tick data — single price point
    volume  = float(bar.up + bar.down)
    snapped = round(bar.high / state.tick_size) * state.tick_size
    raw_idx = int(round((snapped - state.min_price) / state.tick_size))

    extension = max(1, int(state.range_ticks * EXTENSION_PCT))

    if raw_idx < 0:
        # Price broke below grid floor -- prepend zeros
        n_add = max(extension, -raw_idx)
        state.profile   = np.concatenate(
            [np.zeros(n_add, dtype=np.float64), state.profile]
        )
        state.min_price -= n_add * state.tick_size
        raw_idx         += n_add
        state.extensions += 1

    elif raw_idx >= len(state.profile):
        # Price broke above grid ceiling -- append zeros
        n_add = max(extension, raw_idx - len(state.profile) + 1)
        state.profile = np.concatenate(
            [state.profile, np.zeros(n_add, dtype=np.float64)]
        )
        state.extensions += 1

    state.profile[raw_idx] += volume
    state.bar_num = bar.bar_num
    state.n_bars += 1
    state.last_price = snapped


def _snapshot(state: _SessionState) -> VolumeProfileResult:
    """Build a VolumeProfileResult from current state (read-only)."""
    price_levels = (
        state.min_price
        + np.arange(len(state.profile), dtype=np.float64) * state.tick_size
    )
    poc_price, poc_volume = _find_poc(state.profile, price_levels)
    val, vah = _find_value_area(state.profile, price_levels)
    total_volume = float(state.profile.sum())

    derived = _compute_derived_features(
        profile=state.profile,
        price_levels=price_levels,
        poc_price=poc_price,
        poc_volume=poc_volume,
        value_area_low=val,
        value_area_high=vah,
        total_volume=total_volume,
        current_price=state.last_price,
        tick_size=state.tick_size,
        prev_poc_price=state.prev_poc_price,
    )
    state.prev_poc_price = poc_price

    return VolumeProfileResult(
        symbol=state.symbol,
        date=state.date,
        bar_num=state.bar_num,
        tick_size=state.tick_size,
        range_ticks=state.range_ticks,
        price_levels=price_levels,
        volume_at_level=state.profile.copy(),
        poc_price=poc_price,
        poc_volume=poc_volume,
        value_area_low=val,
        value_area_high=vah,
        total_volume=total_volume,
        n_bars=state.n_bars,
        extensions=state.extensions,
        **derived,
    )


# ============================================================
# Adapter: Redis -> bars (no re-validation)
# ============================================================


def stream_ticks_from_redis(
    *,
    block_ms: int = 100,
    count: int = 500,
    start_id: str = "$",
) -> Iterator[Any]:
    """
    Reads validated ticks from Redis tick_data_validated stream.
    Data is already validated by tick_validator.py — just read and cast.
    """
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_TICK_VALIDATED_STREAM)
    last_id = start_id

    while True:
        xread_result = r.xread({REDIS1_TICK_VALIDATED_STREAM: last_id}, count=count, block=block_ms)
        batch: XReadTickBatch = parse_xread_to_ticks(xread_result)
        if not batch.ticks:
            continue
        last_id = batch.last_ids[REDIS1_TICK_VALIDATED_STREAM]
        yield from batch.ticks


# ============================================================
# Application: session lifecycle + streaming
# ============================================================


def stream_volume_profile(
    tick_size: float = 0.25,
    range_ticks: int = DEFAULT_RANGE_TICKS,
    snapshot_interval_s: int = DEFAULT_SNAPSHOT_INTERVAL_S,
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[VolumeProfileResult]:
    """
    Consume ticks from Redis, update the profile on every tick, and emit a
    VolumeProfileResult once per bar (1 second before bar close).

    Parameters
    ----------
    tick_size   : price increment per level (e.g. 0.25 for ES futures)
    range_ticks : number of ticks to pre-allocate at session start.
                  e.g. 400 ticks @ 0.25 = ±50 points around session open.
                  If price breaks the boundary, 15% of range_ticks is added
                  in the direction of the break.
    snapshot_interval_s : bar length in seconds. A snapshot (POC, VA, and all
                  derived features) is computed when
                  `tick.time_s % snapshot_interval_s == snapshot_interval_s - 1`,
                  i.e. once per bar, matching the live bar pipeline.

    Session resets on date change (new trading day).
    _update() is O(1) on every tick -- single profile[index] += volume.
    Grid extension (np.concatenate) only on boundary break.
    """
    state: Optional[_SessionState] = None

    for tick in stream_ticks_from_redis(block_ms=block_ms, count=count, start_id=start_id):

        # New session or first tick
        if state is None or tick.date != state.date:
            state = _init_session(tick, tick_size, range_ticks)

        _update(state, tick)

        if tick.time_s % snapshot_interval_s == snapshot_interval_s - 1:
            yield _snapshot(state)


# ============================================================
# Smoke loop
# ============================================================


def _vp_result_to_redis_fields(vp: VolumeProfileResult) -> dict:
    """
    Encode scalar VolumeProfileResult fields for Redis xadd.
    Arrays (price_levels, volume_at_level) are excluded — too large for a stream field.
    Downstream consumers receive the key scalars: POC, VA, totals.
    """
    return {
        "symbol":          vp.symbol,
        "date":            str(vp.date),
        "bar_num":         str(vp.bar_num),
        "tick_size":       repr(vp.tick_size),
        "range_ticks":     str(vp.range_ticks),
        "poc_price":       repr(vp.poc_price),
        "poc_volume":      repr(vp.poc_volume),
        "value_area_low":  repr(vp.value_area_low),
        "value_area_high": repr(vp.value_area_high),
        "total_volume":    repr(vp.total_volume),
        "poc_distance":        repr(vp.poc_distance),
        "poc_concentration":   repr(vp.poc_concentration),
        "va_width":            repr(vp.va_width),
        "va_position":         repr(vp.va_position),
        "vol_above_poc_ratio": repr(vp.vol_above_poc_ratio),
        "profile_entropy":     repr(vp.profile_entropy),
        "profile_kurtosis":    repr(vp.profile_kurtosis),
        "poc_migration":       repr(vp.poc_migration),
    }


def run_publish_loop(
    tick_size: float = 0.25,
    range_ticks: int = DEFAULT_RANGE_TICKS,
    snapshot_interval_s: int = DEFAULT_SNAPSHOT_INTERVAL_S,
) -> None:
    """
    Main loop: compute volume profile and push one snapshot per bar to Redis.
    Writes to stream: features_volume_profile
    Also prints to stdout for monitoring.
    """
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_FEATURES_VP_STREAM)

    for vp in stream_volume_profile(
        tick_size=tick_size,
        range_ticks=range_ticks,
        snapshot_interval_s=snapshot_interval_s,
    ):
        r.xadd(
            REDIS1_FEATURES_VP_STREAM,
            _vp_result_to_redis_fields(vp),
            maxlen=50_000,
            approximate=True,
        )
        print(
            f"{vp.symbol} date={vp.date} bar={vp.bar_num} bars={vp.n_bars} "
            f"tick={vp.tick_size} range={vp.range_ticks} "
            f"POC={vp.poc_price:.2f} ({vp.poc_volume:.0f}) "
            f"VA=[{vp.value_area_low:.2f} - {vp.value_area_high:.2f}] "
            f"TotalVol={vp.total_volume:.0f} "
            f"GridLevels={len(vp.price_levels)} Extensions={vp.extensions} | "
            f"poc_dist={vp.poc_distance:.2f} poc_conc={vp.poc_concentration:.3f} "
            f"va_width={vp.va_width:.2f} va_pos={vp.va_position:.2f} "
            f"vol_above={vp.vol_above_poc_ratio:.3f} "
            f"entropy={vp.profile_entropy:.3f} kurt={vp.profile_kurtosis:.2f} "
            f"poc_mig={vp.poc_migration:.2f}"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Volume Profile Pipeline")
    parser.add_argument("--tick-size",   type=float, default=0.25,              help="Price increment per level (default: 0.25)")
    parser.add_argument("--range-ticks", type=int,   default=DEFAULT_RANGE_TICKS, help="Ticks to pre-allocate at session start (default: 400)")
    parser.add_argument("--snapshot-interval-s", type=int, default=DEFAULT_SNAPSHOT_INTERVAL_S,
                         help="Bar length in seconds -- snapshot fires 1s before each bar close (default: 30)")
    args = parser.parse_args()

    run_publish_loop(
        tick_size=args.tick_size,
        range_ticks=args.range_ticks,
        snapshot_interval_s=args.snapshot_interval_s,
    )
