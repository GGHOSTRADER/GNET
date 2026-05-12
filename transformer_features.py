"""
transformer_features_pipeline.py
=================================

Clean architecture transformer feature pipeline (Redis -> Bars -> Features).

Mirrors feat_eng_1.py in structure. No pandas, no talib, no CSV.
All features computed from a rolling deque of typed Bars read from Redis1.

Layering
--------
- Adapter / Infrastructure (I/O):
    - Reads from Redis1 using redis-py xread
    - Uses get_redis_connection(host, port, stream_name)
    - Imports config from config.setting

- Application / Orchestration:
    - Builds rolling window of 60 bars (max window required)
    - Emits FeaturePoint records

- Domain (Pure):
    - All feature functions are pure: no I/O, no globals, no mutation
    - parse_xread_to_bars() is PURE (from bar_codec.py)
    - Validations use _require / _require_feature (always active)

Features emitted
----------------
  parkinson_vol_{5,15,30}  -- High/Low Parkinson volatility estimator
  ofi_{5,15,30}            -- Order Flow Imbalance (Up - Down) rolling sum
  volume_percentile        -- Rank of current bar volume in last 60 bars (0-1)
  volume_momentum          -- Volume % change vs 5 bars ago
  amihud_illiquidity       -- |log_return| / volume (price impact per unit vol)
  vwap_distance            -- (close - vwap) / ATR(14)
  minutes_since_open       -- Minutes elapsed since 09:30
  is_first_last_30min      -- 1 if in first or last 30 min of session

Window requirements
-------------------
  volume_percentile : 60 bars  (largest -> governs when we start emitting)
  parkinson_vol_30  : 30 bars
  ofi_30            : 30 bars
  atr (for vwap_d.) : 15 bars  (14 TR values -> 15 bars)
  volume_momentum   : 6 bars   (current + 5 ago)
  amihud            : 2 bars   (current + prev close)

Contract compliance
-------------------
1) Connect to Redis using get_redis_connection from netwo_files.redis_tool
2) xread from redis, parse with parse_xread_to_bars from netwo_files.bar_codec
3) Validate raw field count == 11 BEFORE parsing
4) Validate typed Bar invariants + bar_num continuity
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Iterator, List, Mapping, Optional, Sequence, Tuple

from config.setting import REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME
from netwo_files.redis_tool import get_redis_connection
from netwo_files.bar_codec import (
    parse_xread_to_bars,
    XReadBatch,
    XReadShapeError,
    DecodeError,
)

# ============================================================
# Errors
# ============================================================

_OPEN_S = 9 * 3600 + 30 * 60   # 09:30:00 in seconds since midnight = 34200
_CLOSE_S = 16 * 3600            # 16:00:00 = 57600
_WINDOW = 60                    # largest rolling window (volume_percentile)


class GlobalContractError(ValueError):
    """Raised when a global invariant (bar validity / continuity) is violated."""


class FeatureContractError(ValueError):
    """Raised when a feature-level invariant is violated."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise GlobalContractError(msg)


def _require_feature(cond: bool, msg: str) -> None:
    if not cond:
        raise FeatureContractError(msg)


# ============================================================
# RAW XREAD shape helpers (live test #1: len(fields) == 11)
# ============================================================


def iter_raw_xread_entries(
    xread_result: Any,
) -> Iterator[Tuple[str, Mapping[Any, Any]]]:
    """Yield (entry_id, fields_mapping) from raw redis-py XREAD output."""
    if xread_result is None:
        return

    _require(
        isinstance(xread_result, list),
        f"XREAD result must be list, got {type(xread_result).__name__}",
    )

    for i, stream_block in enumerate(xread_result):
        _require(
            isinstance(stream_block, (tuple, list)) and len(stream_block) == 2,
            f"XREAD item[{i}] must be (stream, entries)",
        )
        _raw_stream, entries = stream_block
        _require(isinstance(entries, list), f"XREAD entries item[{i}] must be list")

        for j, entry in enumerate(entries):
            _require(
                isinstance(entry, (tuple, list)) and len(entry) == 2,
                f"XREAD entry[{i}][{j}] must be (id, fields)",
            )
            entry_id, fields = entry
            _require(
                isinstance(fields, Mapping),
                f"XREAD fields for entry[{i}][{j}] must be Mapping",
            )
            yield (str(entry_id), fields)


def validate_xread_field_count(raw_len: int) -> None:
    _require(raw_len == 11, f"Expected 11 fields per bar, got {raw_len}.")


# ============================================================
# Typed bar invariants (live tests #2.x)
# ============================================================


def validate_bar_fields(b: Any) -> None:
    _require(b.symbol is not None, "symbol is null")
    _require(isinstance(b.symbol, str), f"symbol must be str, got {type(b.symbol).__name__}")
    _require(b.symbol != "", "symbol is empty")

    _require(isinstance(b.date, int), f"date must be int, got {type(b.date).__name__}")
    _require(b.date > 1260000, f"date must be > 1260000, got {b.date}")
    mmdd = b.date % 10000
    _require(1 <= mmdd // 100 <= 12, f"month out of range from date={b.date}")
    _require(1 <= mmdd % 100 <= 31, f"day out of range from date={b.date}")

    _require(isinstance(b.time_s, int), f"time_s must be int, got {type(b.time_s).__name__}")
    _require(0 <= b.time_s < 86400, f"time_s out of range: {b.time_s}")

    _require(isinstance(b.open, float), f"open must be float, got {type(b.open).__name__}")
    _require(b.open > 0.0, f"open must be > 0, got {b.open}")

    _require(isinstance(b.high, float), f"high must be float, got {type(b.high).__name__}")
    _require(b.high > 0.0, f"high must be > 0, got {b.high}")
    _require(b.open <= b.high, f"open={b.open} > high={b.high}")

    _require(isinstance(b.low, float), f"low must be float, got {type(b.low).__name__}")
    _require(b.low > 0.0, f"low must be > 0, got {b.low}")
    _require(b.open >= b.low, f"open={b.open} < low={b.low}")

    _require(isinstance(b.close, float), f"close must be float, got {type(b.close).__name__}")
    _require(b.close > 0.0, f"close must be > 0, got {b.close}")
    _require(b.low <= b.close <= b.high, f"close={b.close} not in [low={b.low}, high={b.high}]")

    _require(isinstance(b.up, int), f"up must be int, got {type(b.up).__name__}")
    _require(b.up >= 0, f"up must be >= 0, got {b.up}")

    _require(isinstance(b.down, int), f"down must be int, got {type(b.down).__name__}")
    _require(b.down >= 0, f"down must be >= 0, got {b.down}")

    _require(isinstance(b.vwap, float), f"vwap must be float, got {type(b.vwap).__name__}")
    _require(b.vwap >= 0.0, f"vwap must be >= 0, got {b.vwap}")

    _require(isinstance(b.bar_num, int), f"bar_num must be int, got {type(b.bar_num).__name__}")
    _require(b.bar_num >= 0, f"bar_num must be >= 0, got {b.bar_num}")


def validate_bar_continuity(prev: Any, curr: Any) -> None:
    _require(
        curr.bar_num - prev.bar_num == 1,
        f"bar continuity broken: prev={prev.bar_num}, curr={curr.bar_num}",
    )


# ============================================================
# Pure feature functions
# ============================================================


def _parkinson_vol(bars: Sequence[Any], window: int) -> float:
    """
    Parkinson volatility over `window` bars.
    sigma = sqrt( mean(ln(H/L)^2) / (4 * ln(2)) )
    """
    subset = bars[-window:]
    _require_feature(len(subset) == window, f"parkinson_vol needs {window} bars, got {len(subset)}")
    hl2 = [math.log(b.high / b.low) ** 2 for b in subset]
    sigma2 = sum(hl2) / (window * 4.0 * math.log(2))
    out = math.sqrt(sigma2)
    _require_feature(math.isfinite(out), f"parkinson_vol_{window} not finite: {out}")
    return float(out)


def _ofi(bars: Sequence[Any], window: int) -> float:
    """Order Flow Imbalance: rolling sum of (Up - Down)."""
    subset = bars[-window:]
    _require_feature(len(subset) == window, f"ofi needs {window} bars, got {len(subset)}")
    return float(sum(b.up - b.down for b in subset))


def _volume_percentile(bars: Sequence[Any], window: int = 60) -> float:
    """
    Rank of the current bar's volume among the last `window` bars. Returns [0, 1].
    Uses (rank - 1) / (n - 1) to match pandas rank percent convention.
    """
    subset = bars[-window:]
    _require_feature(len(subset) == window, f"volume_percentile needs {window} bars, got {len(subset)}")
    vols = [b.up + b.down for b in subset]
    current_vol = vols[-1]
    rank = sum(1 for v in vols if v <= current_vol)  # 1..n
    out = float((rank - 1) / (window - 1))
    _require_feature(0.0 <= out <= 1.0, f"volume_percentile out of [0,1]: {out}")
    return out


def _volume_momentum(bars: Sequence[Any], n: int = 5) -> float:
    """
    Volume % change vs n bars ago: (vol_now - vol_prev) / vol_prev.
    Requires at least n+1 bars.
    """
    _require_feature(len(bars) >= n + 1, f"volume_momentum needs {n+1} bars, got {len(bars)}")
    vol_now = bars[-1].up + bars[-1].down
    vol_prev = bars[-(n + 1)].up + bars[-(n + 1)].down
    if vol_prev == 0:
        return 0.0
    return float((vol_now - vol_prev) / vol_prev)


def _amihud_illiquidity(bars: Sequence[Any]) -> float:
    """
    Amihud illiquidity: |log_return| / volume.
    log_return = log(close / prev_close). volume = up + down.
    """
    _require_feature(len(bars) >= 2, f"amihud needs >= 2 bars, got {len(bars)}")
    prev_close = bars[-2].close
    curr = bars[-1]
    _require_feature(prev_close > 0.0, f"prev_close must be > 0, got {prev_close}")
    log_ret = abs(math.log(curr.close / prev_close))
    vol = curr.up + curr.down
    if vol == 0:
        return 0.0
    return float(log_ret / vol)


def _atr(bars: Sequence[Any], period: int = 14) -> float:
    """
    Average True Range over `period` bars.
    True Range = max(H-L, |H-prev_C|, |L-prev_C|).
    Requires period+1 bars (period TR values need period+1 closes).
    """
    _require_feature(len(bars) >= period + 1, f"atr needs {period+1} bars, got {len(bars)}")
    subset = bars[-(period + 1):]
    trs = []
    for i in range(1, len(subset)):
        h = subset[i].high
        l = subset[i].low
        prev_c = subset[i - 1].close
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return float(sum(trs) / len(trs))


def _vwap_distance(bar: Any, atr: float) -> float:
    """(close - vwap) / ATR. Returns 0 if ATR is zero."""
    if atr == 0.0:
        return 0.0
    return float((bar.close - bar.vwap) / atr)


def _minutes_since_open(bar: Any) -> float:
    """Minutes elapsed since 09:30. Clamped to 0 if before open."""
    return float(max((bar.time_s - _OPEN_S) / 60.0, 0.0))


def _is_first_last_30min(bar: Any) -> int:
    """1 if bar is in first 30 min (09:30-10:00) or last 30 min (15:30-16:00) of session."""
    mins = max((bar.time_s - _OPEN_S) / 60.0, 0.0)
    in_first = 0.0 < mins < 31.0
    in_last = 359.0 < mins < 390.0
    return 1 if (in_first or in_last) else 0


# ============================================================
# Output record
# ============================================================


@dataclass(frozen=True)
class FeaturePoint:
    symbol: str
    date: int
    time_s: int
    bar_num: int
    parkinson_vol_5: float
    parkinson_vol_15: float
    parkinson_vol_30: float
    ofi_5: float
    ofi_15: float
    ofi_30: float
    volume_percentile: float
    volume_momentum: float
    amihud_illiquidity: float
    vwap_distance: float
    minutes_since_open: float
    is_first_last_30min: int


# ============================================================
# Adapter: Redis -> raw XREAD -> parse -> validate -> bars
# ============================================================


def stream_bars_from_redis(
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[Any]:
    """
    Infrastructure adapter (mirrors feat_eng_1.py):
    - Connect to Redis1
    - xread with blocking
    - Validate raw field count == 11 (live test #1)
    - Parse with parse_xread_to_bars (pure)
    - Validate typed Bar invariants + bar_num continuity
    - Yield typed Bars
    """
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME)

    last_id = start_id
    last_bar: Optional[Any] = None

    while True:
        xread_result = r.xread(
            {REDIS1_STREAM_NAME: last_id},
            count=count,
            block=block_ms,
        )

        for _entry_id, fields in iter_raw_xread_entries(xread_result):
            validate_xread_field_count(len(fields))

        try:
            batch: XReadBatch = parse_xread_to_bars(xread_result)
        except (XReadShapeError, DecodeError):
            raise

        if not batch.bars:
            continue

        last_id = batch.last_ids.get(REDIS1_STREAM_NAME)
        _require(
            last_id is not None,
            f"Missing last_id for stream '{REDIS1_STREAM_NAME}' in batch.last_ids",
        )

        for bar in batch.bars:
            validate_bar_fields(bar)

            if last_bar is not None:
                validate_bar_continuity(last_bar, bar)

            last_bar = bar
            yield bar


# ============================================================
# Application: rolling window -> feature points
# ============================================================


def stream_feature_points(
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[FeaturePoint]:
    """
    Application orchestration:
    - Consume validated bars from Redis1
    - Build rolling window of 60 bars (largest required window)
    - Emit FeaturePoint once window is full
    """
    window: Deque[Any] = deque(maxlen=_WINDOW)

    for bar in stream_bars_from_redis(block_ms=block_ms, count=count, start_id=start_id):
        window.append(bar)

        if len(window) < _WINDOW:
            continue

        bars = list(window)
        atr = _atr(bars, period=14)

        yield FeaturePoint(
            symbol=bar.symbol,
            date=bar.date,
            time_s=bar.time_s,
            bar_num=bar.bar_num,
            parkinson_vol_5=_parkinson_vol(bars, 5),
            parkinson_vol_15=_parkinson_vol(bars, 15),
            parkinson_vol_30=_parkinson_vol(bars, 30),
            ofi_5=_ofi(bars, 5),
            ofi_15=_ofi(bars, 15),
            ofi_30=_ofi(bars, 30),
            volume_percentile=_volume_percentile(bars, _WINDOW),
            volume_momentum=_volume_momentum(bars, 5),
            amihud_illiquidity=_amihud_illiquidity(bars),
            vwap_distance=_vwap_distance(bar, atr),
            minutes_since_open=_minutes_since_open(bar),
            is_first_last_30min=_is_first_last_30min(bar),
        )


# ============================================================
# Minimal smoke loop
# ============================================================


def run_print_loop() -> None:
    for fp in stream_feature_points():
        print(
            f"{fp.symbol} date={fp.date} t={fp.time_s} bar={fp.bar_num} "
            f"pvol5={fp.parkinson_vol_5:.6f} ofi5={fp.ofi_5:.0f} "
            f"vol_pct={fp.volume_percentile:.3f} amihud={fp.amihud_illiquidity:.8f} "
            f"vwap_d={fp.vwap_distance:.4f} min_open={fp.minutes_since_open:.1f} "
            f"sess_flag={fp.is_first_last_30min}"
        )


if __name__ == "__main__":
    run_print_loop()
