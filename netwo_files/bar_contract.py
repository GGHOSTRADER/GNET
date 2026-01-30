# bar_contract.py
"""
bar_contract.py
================

This module defines your TS PROJECT "contract" as code.

Why this exists
---------------
You have two separate problems in your system:

1) TRANSPORT problem:
   - TCP delivers bytes, Redis stores bytes/strings.
   - Those are just containers. They do not guarantee correctness.

2) DATA-CORRECTNESS problem:
   - You need to guarantee each bar respects invariants like:
       open > 0
       close is within [low, high]
       up/down are non-negative

If you mix those problems together (socket code + validation + Redis writes),
your system becomes hard to test and hard to reason about.

So this file is the "truth source" for:
- What a Bar is (typed representation)
- What conditions must always hold (invariants)
- How to validate a single bar (stateless checks)
- How to validate a sequence (stateful check: bar_num monotonicity)

Design principles
-----------------
- Pure logic: no IO, no sockets, no Redis.
- Deterministic: same input -> same output.
- Testable: unit tests can hit this module without network setup.

Function Summary <----------------------------

1) ContractError
✅ Contract violation exception
Used to signal validation failures
Caught by upstream TCP/Redis pipeline
Separates “bad data” from runtime bugs

2) _require(cond, msg) -> None
✅ Validation guard helper
Takes a boolean condition + message
Raises ContractError if condition fails
Keeps validation code readable

3) Bar(...) -> Bar
✅ Typed immutable data container
Holds canonical bar fields (symbol/date/time/OHLC/up/down/vwap/bar_num)
Frozen dataclass prevents mutation bugs
Used as the “truth format” everywhere

4) validate_bar(b: Bar) -> None
✅ Single-bar contract validator (stateless)
Takes a typed Bar
Checks symbol/date/time/OHLC/up/down/vwap/bar_num invariants
Raises ContractError if any rule fails

5) validate_sequence(prev: Optional[Bar], curr: Bar) -> None
✅ Multi-bar contract validator (stateful)
Validates curr first (via validate_bar)
If prev exists and same symbol/date: enforces bar_num strictly increasing
Raises ContractError on sequence violations
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class ContractError(ValueError):
    """
    Raised when a bar violates the declared contract.

    Why a custom exception?
    -----------------------
    - Lets you distinguish "contract violation" from random runtime errors.
    - Your TCP server can catch ContractError and safely drop + log a line.
    """

    pass


def _require(cond: bool, msg: str) -> None:
    """
    Small helper to keep validation readable.

    Why use this instead of 'assert'?
    --------------------------------
    - 'assert' can be disabled with Python optimization flags (-O).
    - You want contract checks ALWAYS active in production.
    """
    if not cond:
        raise ContractError(msg)


@dataclass(frozen=True)
class Bar:
    """
    Typed representation of one bar after decoding/casting.

    Why we need this class
    ----------------------
    Your TCP server receives everything as strings.
    Redis returns everything as bytes/strings.
    But your invariants are numeric comparisons, which only make sense
    after converting to numeric types.

    'frozen=True' means immutable:
    -----------------------------
    - Once created, the bar cannot be changed.
    - Prevents bugs where code mutates a bar after validation.
    - Makes it safe to pass around and cache.
    """

    symbol: str
    date: int  # 6 digits, TS style like 990412 (yy mm dd packed)
    time_s: int  # seconds since midnight (0..86399)
    open: float
    high: float
    low: float
    close: float
    up: int
    down: int
    vwap: float
    bar_num: int


def validate_bar(b: Bar) -> None:
    """
    Validate a single bar (stateless invariants).

    Stateless means:
    ---------------
    We can check these rules using only this bar, without needing
    the previous bar or global context.

    If any rule fails, raise ContractError with a precise message.

    """

    # 1) Symbol
    # Your contract says "value != null".
    # In Python, "null" is None.
    _require(b.symbol is not None, "symbol must not be null")
    _require(b.symbol != "", "symbol must be non-empty")
    # 🟩 ADDED, validates is a string
    _require(
        isinstance(b.symbol, str), f"symbol must be str, got {type(b.symbol).__name__}"
    )

    # 2) Date (YYMMDD packed integer)
    # You stated TS uses "years since 1900" conceptually, but your example
    # shows 990412 which is effectively YYMMDD packed (6 digits).
    #
    # Enforce what is *checkable* at this boundary:
    # - must be an integer
    # - must fit 6 digits
    # - must be non-negative
    # 🟥_require(0 <= b.date <= 999999, "date must be in [0, 999999]")
    # 🟥_require(len(f"{b.date:06d}") == 6, "date must be 6 digits (zero-padded allowed)")

    # 🟩 ADDED
    _require(b.date >= 0, f"date={b.date} must be >= 0")
    yyy = b.date // 10000  # years since 1900
    mm = (b.date // 100) % 100  # month
    dd = b.date % 100  # day
    _require(
        126 <= yyy <= 999,
        f"date={b.date} invalid: yyy={yyy} not in [0,999] (years since 1900)",
    )
    _require(1 <= mm <= 12, f"date={b.date} invalid: mm={mm} not in [1,12]")
    _require(1 <= dd <= 31, f"date={b.date} invalid: dd={dd} not in [1,31]")

    # 3) Time in seconds since midnight
    # Checkable invariant: valid range for a day.
    _require(0 <= b.time_s <= 86399, "time_s must be in [0, 86399]")

    # 4-7) OHLC

    # 🟩 ADDED
    # Type Check
    _require(
        isinstance(b.open, float),
        f"Open must be float, got {type(b.open).__name__}",
    )
    _require(
        isinstance(b.close, float),
        f"Close must be float, got {type(b.open).__name__}",
    )
    _require(
        isinstance(b.low, float),
        f"Low must be float, got {type(b.open).__name__}",
    )
    _require(
        isinstance(b.high, float),
        f"High must be float, got {type(b.open).__name__}",
    )
    # You require these to be non-zero and positive.
    _require(b.open > 0.0, "open must be > 0")
    _require(b.high > 0.0, "high must be > 0")
    _require(b.low > 0.0, "low must be > 0")
    _require(b.close > 0.0, "close must be > 0")

    # Relationship invariants (these matter for downstream features)
    _require(b.high >= b.open, "high must be >= open")
    _require(b.open >= b.low, "open must be >= low")
    _require(b.low <= b.high, "low must be <= high")
    _require(b.low <= b.close <= b.high, "close must be within [low, high]")

    # 8-9) Up/Down: must be non-negative integers
    _require(b.up >= 0, "up must be >= 0")
    _require(b.down >= 0, "down must be >= 0")
    # 🟩 ADDED
    # Up/Down Type
    _require(
        isinstance(b.up, int),
        f"Up must be int, got {type(b.open).__name__}",
    )
    _require(
        isinstance(b.down, int),
        f"Down must be int, got {type(b.open).__name__}",
    )

    # 10) VWAP:
    # Your contract mentions a formula involving volume, but volume is not in your TCP schema.
    # So we can only enforce the invariant you stated: vwap >= 0.
    _require(b.vwap >= 0.0, "vwap must be >= 0")

    # 11) bar_num (single-bar invariant)
    _require(b.bar_num >= 0, "bar_num must be >= 0")


def validate_sequence(prev: Optional[Bar], curr: Bar) -> None:
    """
    Validate stateful invariant(s) involving more than one bar.

    Stateful means:
    --------------
    These rules require looking at "previous bar" and "current bar".

    Your contract:
      bar_number[x] > bar_number[x-1]

    We apply it only if prev and curr are logically in the same session scope:
    - same symbol
    - same date

    Why scope it this way?
    ----------------------
    If the date changes (new trading day) you probably expect bar_num to reset.
    If the symbol changes, sequences are unrelated.
    """
    validate_bar(curr)
    if prev is None:
        return

    if prev.symbol == curr.symbol and prev.date == curr.date:
        _require(
            curr.bar_num > prev.bar_num,
            "bar_num must strictly increase within same symbol/date",
        )
