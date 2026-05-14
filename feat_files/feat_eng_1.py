"""
feature_engineering_pipeline.py
===============================

Clean architecture quant feature pipeline (Redis -> Bars -> Features).

Layering
-----------------------------
- Adapter / Infrastructure (I/O):
    - Reads from Redis using redis-py xread
    - Uses get_redis_connection(host, port, stream_name)
    - Imports config from config.setting

- Application / Orchestration:
    - Builds rolling windows
    - Emits FeaturePoint records

- Domain (Pure):
    - parse_xread_to_bars(xread_result) is PURE (given by you, in bar_codec.py)
    - modSlope5 is PURE
    - Validations are explicit (no assert)

Contract compliance
-------------------
Bar consuer / caster (done before any feature calcs):
1) Connect to redis using get_redis_connection from netwo_files.redis_tool.py
   REQUIRED signature used here:
     r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME)

2) xread from redis using redis_client.xread(...)
   Parse with parse_xread_to_bars(xread_result), XReadBatch, XReadShapeError from netwo_files.bar_codec.py

3) Parse/cast via bar_from_redis_fields/_as_str/DecodeError happens inside parse_xread_to_bars


Live tests:
- (1) len(xread Redis data) == 11  [validated on RAW xread fields before parsing]
- (2) Field invariants on typed Bar (symbol/date/time/open/high/low/close/up/down/vwap/bar_num)
- (3) Bar continuity: bar_num[-1] - bar_num[-2] == 1

Internal(per feature):
- modSlope5 over a 5-bar window with invariants.

Important reality check
-----------------------

If any import names differ in your repo, fix ONLY the imports, not the logic.

Function Summary
----------------
1) FeatureContractError              -- raised when a feature-level invariant is violated
2) _require_feature(cond, msg)       -- validation guard for feature invariants
3) modSlope5(bars)                   -- pure: (avg last bar) - (avg first bar) over 5-bar window
4) FeaturePoint                      -- frozen dataclass: symbol/date/time_s/bar_num/modSlope5
5) stream_bars_from_redis(...)       -- adapter: reads validated_bar stream, yields typed Bars
6) stream_feature_points(...)        -- application: builds 5-bar rolling window, yields FeaturePoint
7) run_print_loop()                  -- smoke runner: prints one FeaturePoint line per bar
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Deque, Iterator, Sequence
from collections import deque
import math

from config.setting import REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME
from netwo_files.redis_tool import get_redis_connection
from netwo_files.bar_codec import parse_xread_to_bars

# ============================================================
# Errors
# ============================================================


class FeatureContractError(ValueError):
    """Raised when a feature-level invariant is violated."""


def _require_feature(cond: bool, msg: str) -> None:
    if not cond:
        raise FeatureContractError(msg)


# ============================================================
# Pure feature: modSlope5
# ============================================================


def modSlope5(bars: Sequence[Any]) -> float:
    """
    modSlope5 (PURE)
    ----------------
    Input:
      - bars: window of 5 bars, each must have .high .low .close .bar_num

    Calculation:
      (high[-1] + low[-1] + close[-1])/3 - (high[-5] + low[-5] + close[-5])/3

    Invariants:
      - len(bars) == 5
      - bar_num[-1] - bar_num[-5] == 4
      - continuity within window
      - math.isfinite(output)
    """
    _require_feature(len(bars) == 5, f"E_LEN")

    nums = [b.bar_num for b in bars]
    _require_feature(
        nums[-1] - nums[0] == 4,
        f"E_GAP",
    )
    _require_feature(
        all(nums[i] == nums[i - 1] + 1 for i in range(1, 5)),
        f"window not continuous: {nums}",
    )

    last = bars[-1]
    first = bars[0]

    typical_last = (last.high + last.low + last.close) / 3.0
    typical_first = (first.high + first.low + first.close) / 3.0
    out = typical_last - typical_first

    _require_feature(math.isfinite(out), f"modSlope5 not finite: {out}")
    return float(out)


# ============================================================
# Output record
# ============================================================


@dataclass(frozen=True)
class FeaturePoint:
    """
    Minimal engineered feature payload.

    Keep it small and explicit. Downstream systems can add more fields later.
    """

    symbol: str
    date: int
    time_s: int
    bar_num: int
    modSlope5: float


# ============================================================
# Adapter: Redis -> parse -> bars
# ============================================================


def stream_bars_from_redis(
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[Any]:
    """
    Reads validated bars from Redis1. Data is already validated at ingestion
    (tcp_to_redis_connection.py + bar_codec.py), so we just read and cast.
    """
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME)
    last_id = start_id

    while True:
        xread_result = r.xread({REDIS1_STREAM_NAME: last_id}, count=count, block=block_ms)
        batch = parse_xread_to_bars(xread_result)
        if not batch.bars:
            continue
        last_id = batch.last_ids[REDIS1_STREAM_NAME]
        yield from batch.bars


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
    - consume validated bars
    - build rolling window of 5 bars
    - emit FeaturePoint when window is full
    """
    window: Deque[Any] = deque(maxlen=5)

    for bar in stream_bars_from_redis(
        block_ms=block_ms, count=count, start_id=start_id
    ):
        window.append(bar)
        if len(window) < 5:
            continue

        value = modSlope5(list(window))
        yield FeaturePoint(
            symbol=bar.symbol,
            date=bar.date,
            time_s=bar.time_s,
            bar_num=bar.bar_num,
            modSlope5=value,
        )


# ============================================================
# Minimal runnable smoke loop (optional)
# ============================================================


def run_print_loop() -> None:
    """
    Smoke runner:
    - prints features as they are produced
    """
    for fp in stream_feature_points():
        print(
            f"{fp.symbol} date={fp.date} t={fp.time_s} bar={fp.bar_num} modSlope5={fp.modSlope5}"
        )


if __name__ == "__main__":
    run_print_loop()
