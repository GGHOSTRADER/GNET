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
Global (done before any feature calcs):
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
Your parse_xread_to_bars() returns XReadBatch(bars=..., last_ids=...).
It does NOT return entries/fields. Therefore:
- The only place to validate "len(fields)==11" is on the RAW xread output
  (before calling parse_xread_to_bars). This module does that.

If any import names differ in your repo, fix ONLY the imports, not the logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple
from collections import deque
import math

# ---------------------------------------------------------------------
# Required config import (as per your instruction)
# ---------------------------------------------------------------------
from config.setting import REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME

# ---------------------------------------------------------------------
# Required infrastructure import (as per your contract)
# ---------------------------------------------------------------------
from netwo_files.redis_tool import get_redis_connection

# ---------------------------------------------------------------------
# Required codec imports (as per your contract)
# ---------------------------------------------------------------------
from netwo_files.bar_codec import (
    parse_xread_to_bars,
    XReadBatch,
    XReadShapeError,
    DecodeError,
)

# ============================================================
# Errors
# ============================================================


class GlobalContractError(ValueError):
    """Raised when a global invariant (bar validity / continuity) is violated."""


class FeatureContractError(ValueError):
    """Raised when a feature-level invariant is violated."""


def _require(cond: bool, msg: str) -> None:
    """
    Contract helper that is ALWAYS active in production.
    (Unlike assert, which can be disabled with -O.)
    """
    if not cond:
        raise GlobalContractError(msg)


def _require_feature(cond: bool, msg: str) -> None:
    """Same pattern as _require, but for feature invariants."""
    if not cond:
        raise FeatureContractError(msg)


# ============================================================
# RAW XREAD shape helpers (for len(fields)==11 live test)
# ============================================================


def iter_raw_xread_entries(
    xread_result: Any,
) -> Iterator[Tuple[str, Mapping[Any, Any]]]:
    """
    Extract raw (entry_id, fields_mapping) from redis-py XREAD output.

    Why this exists:
    - Your live test #1 requires validating len(fields)==11.
    - Your parser parse_xread_to_bars() *consumes* fields and returns Bars,
      so the raw field-count check must run BEFORE parsing.

    Expected redis-py shape (typical):
      [
        (stream_name, [
            (entry_id, {field: value, ...}),
            ...
        ]),
        ...
      ]

    This helper does NOT decode bytes/str.
    It only safely iterates and yields (entry_id, fields).
    Structural issues are raised as GlobalContractError (adapter-level).
    """
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
    """
    Live test #1:
      len(xread Redis data) == 11

    Interpreted as:
      For each raw XREAD entry, the field map has 11 keys (columns).
    """
    _require(raw_len == 11, f"Expected 11 fields per bar, got {raw_len}.")


# ============================================================
# Typed bar invariants (live tests #2.x)
# ============================================================


def validate_bar_fields(b: Any) -> None:
    """
    Validate the typed Bar produced by bar_codec.parse_xread_to_bars().

    Assumptions (based on your contract):
    - Bar has attributes:
      symbol(str), date(int), time_s(int), open(float), high(float), low(float),
      close(float), up(int), down(int), vwap(float), bar_num(int)

    If your Bar uses different names (e.g. time vs time_s), fix here.
    """
    # 2.1 Symbol
    _require(b.symbol is not None, "symbol is null")
    _require(
        isinstance(b.symbol, str), f"symbol must be str, got {type(b.symbol).__name__}"
    )
    _require(b.symbol != "", "symbol is empty")

    # 2.2 Date (YYMMDD packed with years since 1900, e.g., 1260412)
    _require(isinstance(b.date, int), f"date must be int, got {type(b.date).__name__}")
    _require(b.date > 1260000, f"date must be > 1260000, got {b.date}")

    mmdd = b.date % 10000
    mm = mmdd // 100
    dd = mmdd % 100
    _require(1 <= mm <= 12, f"month out of range: {mm} derived from date={b.date}")
    _require(1 <= dd <= 31, f"day out of range: {dd} derived from date={b.date}")

    # 2.3 Time seconds since midnight
    _require(
        isinstance(b.time_s, int), f"time_s must be int, got {type(b.time_s).__name__}"
    )
    _require(0 <= b.time_s < 24 * 3600, f"time_s out of range: {b.time_s}")

    # 2.4 Open
    _require(
        isinstance(b.open, float), f"open must be float, got {type(b.open).__name__}"
    )
    _require(b.open > 0.0, f"open must be > 0, got {b.open}")

    # 2.5 High
    _require(
        isinstance(b.high, float), f"high must be float, got {type(b.high).__name__}"
    )
    _require(b.high != 0.0, f"high must be != 0, got {b.high}")
    _require(b.open <= b.high, f"open must be <= high, open={b.open} high={b.high}")

    # 2.6 Low
    _require(isinstance(b.low, float), f"low must be float, got {type(b.low).__name__}")
    _require(b.low != 0.0, f"low must be != 0, got {b.low}")
    _require(b.open >= b.low, f"open must be >= low, open={b.open} low={b.low}")

    # 2.7 Close
    _require(
        isinstance(b.close, float), f"close must be float, got {type(b.close).__name__}"
    )
    _require(b.close != 0.0, f"close must be != 0, got {b.close}")
    _require(
        b.low <= b.close <= b.high,
        f"close must be within [low,high]: low={b.low} close={b.close} high={b.high}",
    )

    # 2.8 Up
    _require(isinstance(b.up, int), f"up must be int, got {type(b.up).__name__}")
    _require(b.up >= 0, f"up must be >= 0, got {b.up}")

    # 2.9 Down
    _require(isinstance(b.down, int), f"down must be int, got {type(b.down).__name__}")
    _require(b.down >= 0, f"down must be >= 0, got {b.down}")

    # 2.10 VWAP
    _require(
        isinstance(b.vwap, float), f"vwap must be float, got {type(b.vwap).__name__}"
    )
    _require(b.vwap >= 0.0, f"vwap must be >= 0, got {b.vwap}")

    # 2.11 Bar number
    _require(
        isinstance(b.bar_num, int),
        f"bar_num must be int, got {type(b.bar_num).__name__}",
    )
    _require(b.bar_num >= 0, f"bar_num must be >= 0, got {b.bar_num}")


def validate_bar_continuity(prev: Any, curr: Any) -> None:
    """
    Live test #3:
      bar_num[-1] - bar_num[-2] == 1
    """
    _require(
        curr.bar_num - prev.bar_num == 1,
        f"bar continuity broken: prev={prev.bar_num}, curr={curr.bar_num}",
    )


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
# Adapter: Redis -> raw XREAD -> parse -> validate -> bars
# ============================================================


def stream_bars_from_redis(
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[Any]:
    """
    Infrastructure adapter:
    - Connect to Redis using configured host/port/stream
    - Read raw XREAD result
    - Validate raw field-count == 11 (live test #1)
    - Parse raw output via parse_xread_to_bars(xread_result) (PURE)
    - Validate typed bar invariants + continuity
    - Yield Bars

    Why adapter owns REDIS1_STREAM_NAME:
    - Your connection signature includes stream_name.
    - This keeps stream identity out of pure feature logic.
    """
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME)

    last_id = start_id
    last_bar: Optional[Any] = None

    while True:
        # 1) SIDE EFFECT: Redis read
        xread_result = r.xread(
            {REDIS1_STREAM_NAME: last_id},
            count=count,
            block=block_ms,
        )

        # 2) RAW live test: validate 11 fields BEFORE parsing
        # If xread_result is empty, iter_raw_xread_entries yields nothing and this does nothing.
        for _entry_id, fields in iter_raw_xread_entries(xread_result):
            validate_xread_field_count(len(fields))

        # 3) PURE parse: raw -> XReadBatch(bars, last_ids)
        try:
            batch: XReadBatch = parse_xread_to_bars(xread_result)
        except (XReadShapeError, DecodeError):
            # Schema break or decoding failure: fail loud
            raise

        if not batch.bars:
            continue

        # 4) Update last_id using parser output
        last_id = batch.last_ids.get(REDIS1_STREAM_NAME)
        _require(
            last_id is not None,
            f"Missing last_id for stream '{REDIS1_STREAM_NAME}' in batch.last_ids",
        )

        # 5) Typed invariants + continuity
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
