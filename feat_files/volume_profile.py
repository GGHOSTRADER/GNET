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

Function Summary
----------------
1)  VolumeProfileError               -- raised when volume profile domain invariants are violated
2)  _require_vp(cond, msg)           -- validation guard for domain invariants
3)  _find_poc(profile, levels)       -- pure: np.argmax -> (poc_price, poc_volume)
4)  _find_value_area(profile, levels)-- pure: np.argsort + cumsum -> (val, vah) at 70% coverage
5)  VolumeProfileResult              -- dataclass: full profile snapshot emitted per tick
6)  _SessionState                    -- dataclass: live pre-allocated profile array + metadata
7)  _init_session(bar, tick_size, range_ticks) -- pre-allocate profile array centered on first tick
8)  _update(state, bar)              -- O(1) incremental update: profile[index] += volume, extends grid if needed
9)  _snapshot(state)                 -- derive price_levels from state, call POC + VA, return VolumeProfileResult
10) stream_ticks_from_redis(...)     -- adapter: reads tick_data_validated, yields typed Ticks
11) stream_volume_profile(...)       -- application: session lifecycle, calls _update + _snapshot per tick
12) run_print_loop(tick_size, range_ticks) -- smoke runner: prints one profile line per tick
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


def _snapshot(state: _SessionState) -> VolumeProfileResult:
    """Build a VolumeProfileResult from current state (read-only)."""
    price_levels = (
        state.min_price
        + np.arange(len(state.profile), dtype=np.float64) * state.tick_size
    )
    poc_price, poc_volume = _find_poc(state.profile, price_levels)
    val, vah = _find_value_area(state.profile, price_levels)

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
        total_volume=float(state.profile.sum()),
        n_bars=state.n_bars,
        extensions=state.extensions,
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
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[VolumeProfileResult]:
    """
    Consume bars from Redis and emit an updated VolumeProfileResult on every bar.

    Parameters
    ----------
    tick_size   : price increment per level (e.g. 0.25 for ES futures)
    range_ticks : number of ticks to pre-allocate at session start.
                  e.g. 400 ticks @ 0.25 = ±50 points around session open.
                  If price breaks the boundary, 15% of range_ticks is added
                  in the direction of the break.

    Session resets on date change (new trading day).
    Each bar is O(1) -- single profile[index] += volume.
    Grid extension (np.concatenate) only on boundary break.
    """
    state: Optional[_SessionState] = None

    for tick in stream_ticks_from_redis(block_ms=block_ms, count=count, start_id=start_id):

        # New session or first tick
        if state is None or tick.date != state.date:
            state = _init_session(tick, tick_size, range_ticks)

        _update(state, tick)
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
    }


def run_publish_loop(
    tick_size: float = 0.25,
    range_ticks: int = DEFAULT_RANGE_TICKS,
) -> None:
    """
    Main loop: compute volume profile and push each snapshot to Redis.
    Writes to stream: features_volume_profile
    Also prints to stdout for monitoring.
    """
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_FEATURES_VP_STREAM)

    for vp in stream_volume_profile(tick_size=tick_size, range_ticks=range_ticks):
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
            f"GridLevels={len(vp.price_levels)} Extensions={vp.extensions}"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Volume Profile Pipeline")
    parser.add_argument("--tick-size",   type=float, default=0.25,              help="Price increment per level (default: 0.25)")
    parser.add_argument("--range-ticks", type=int,   default=DEFAULT_RANGE_TICKS, help="Ticks to pre-allocate at session start (default: 400)")
    args = parser.parse_args()

    run_publish_loop(tick_size=args.tick_size, range_ticks=args.range_ticks)
