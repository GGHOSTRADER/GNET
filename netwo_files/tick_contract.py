"""
tick_contract.py
================

Defines the Tick data contract for high-frequency tick data.

Tick vs Bar
-----------
- Tick has 8 fields (no Open, Close, VWAP)
- High == Low always (single price point per tick)
- Same date/bar_num monotonicity rules as bars

Design principles
-----------------
- Pure logic: no IO, no sockets, no Redis
- Deterministic: same input -> same output
- Testable: unit tests can hit this without network setup

Function Summary
----------------
1) TickContractError          -- exception raised when a tick violates the contract
2) _require(cond, msg)        -- validation guard helper, raises TickContractError if cond is False
3) Tick                       -- frozen dataclass holding 8 typed tick fields (no Open/Close/VWAP)
4) validate_tick(t)           -- stateless single-tick validator (types, ranges, high == low)
5) validate_tick_sequence(prev, curr) -- stateful validator: bar_num must strictly increase within same symbol/date
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class TickContractError(ValueError):
    """Raised when a tick violates the declared contract."""
    pass


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise TickContractError(msg)


@dataclass(frozen=True)
class Tick:
    """
    Typed immutable representation of one market tick.

    High == Low because a tick is a single price point,
    not a range like a bar.
    """
    symbol:  str
    date:    int    # YYYMMDD, years since 1900
    time_s:  int    # seconds since midnight (0..86399)
    high:    float  # == low for tick data (single price)
    low:     float  # == high for tick data (single price)
    up:      int    # market buy volume
    down:    int    # market sell volume
    bar_num: int    # tick sequence number


def validate_tick(t: Tick) -> None:
    """Validate a single tick (stateless invariants)."""

    # 1) Symbol
    _require(t.symbol is not None, "symbol must not be null")
    _require(t.symbol != "", "symbol must be non-empty")
    _require(isinstance(t.symbol, str), f"symbol must be str, got {type(t.symbol).__name__}")

    # 2) Date
    _require(t.date >= 0, f"date={t.date} must be >= 0")
    yyy = t.date // 10000
    mm  = (t.date // 100) % 100
    dd  = t.date % 100
    _require(126 <= yyy <= 999, f"date={t.date} invalid: yyy={yyy} not in [126,999]")
    _require(1 <= mm <= 12,     f"date={t.date} invalid: mm={mm} not in [1,12]")
    _require(1 <= dd <= 31,     f"date={t.date} invalid: dd={dd} not in [1,31]")

    # 3) Time
    _require(0 <= t.time_s <= 86399, f"time_s={t.time_s} must be in [0, 86399]")

    # 4) High
    _require(isinstance(t.high, float), f"high must be float, got {type(t.high).__name__}")
    _require(t.high > 0.0, f"high must be > 0, got {t.high}")

    # 5) Low
    _require(isinstance(t.low, float), f"low must be float, got {type(t.low).__name__}")
    _require(t.low > 0.0, f"low must be > 0, got {t.low}")

    # Key tick invariant: single price point
    _require(t.high == t.low, f"high must equal low for tick data: high={t.high} low={t.low}")

    # 6) Up
    _require(isinstance(t.up, int), f"up must be int, got {type(t.up).__name__}")
    _require(t.up >= 0, f"up must be >= 0, got {t.up}")

    # 7) Down
    _require(isinstance(t.down, int), f"down must be int, got {type(t.down).__name__}")
    _require(t.down >= 0, f"down must be >= 0, got {t.down}")

    # 8) Bar number
    _require(isinstance(t.bar_num, int), f"bar_num must be int, got {type(t.bar_num).__name__}")
    _require(t.bar_num >= 0, f"bar_num must be >= 0, got {t.bar_num}")


def validate_tick_sequence(prev: Optional[Tick], curr: Tick) -> None:
    """
    Validate stateful invariant: bar_num must strictly increase
    within the same symbol and date.
    """
    validate_tick(curr)
    if prev is None:
        return

    if prev.symbol == curr.symbol and prev.date == curr.date:
        _require(
            curr.bar_num > prev.bar_num,
            f"bar_num must strictly increase: prev={prev.bar_num} curr={curr.bar_num}",
        )
