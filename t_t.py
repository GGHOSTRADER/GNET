"""
modSlope5
=========

Domain-layer pure function (Clean Architecture)
----------------------------------------------

This module defines a single, *pure* domain function: `modSlope5`.

Key idea:
- The function is **domain logic only**: it does not know about Redis, sockets, files, clocks, logging, globals, etc.
- Any parsing/casting/transport validation is assumed to happen **upstream** (your Redis parser/caster contract).

What it computes
----------------
Given a 5-bar window `b` with numeric arrays:
    b.high, b.low, b.close, b.bar_num

Compute:
    avg_last  = (high[-1] + low[-1] + close[-1]) / 3
    avg_first = (high[-5] + low[-5] + close[-5]) / 3
    return avg_last - avg_first

Invariants enforced here (domain contract)
------------------------------------------
1) Buffer length is exactly 5 for all four arrays
2) Endpoints difference: b.bar_num[-1] - b.bar_num[-5] == 4
3) Bar continuity across the 5 bars:
       bar_num[i] == bar_num[i-1] + 1   for i = 1..4
4) Returned value must be a float (not numpy scalar / Decimal, etc.)

Assumptions / Guarantees (boundary clarification)
-------------------------------------------------
Assumptions (true before calling this function):
- Data is already casted to numeric types by the upstream parser/caster layer.
- high/low/close values are already logically validated upstream
  (e.g., no NaNs/infs if that is your system rule, high >= low, etc.).
- `b` represents a coherent 5-bar window (same symbol/timeframe), and is not a mix.

Guarantees (true after successful return):
- If the function returns, it returns a Python `float`.
- No side effects occurred (no I/O, no mutation of inputs, no global state changes).
- If invariants are violated, the function raises a clear exception and does not compute.

Why this is “Clean Architecture”
--------------------------------
- This function depends only on a minimal *shape* of data (a protocol), not on infrastructure.
- Redis is a *data source*, not a domain dependency. The “data dependency” is contractual,
  not a Python import dependency.

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable


# -----------------------------
# Domain Exceptions (stable)
# -----------------------------


class ModSlope5Error(ValueError):
    """
    Base error for modSlope5 contract violations.

    In Clean Architecture terms:
    - This is a domain-level error type.
    - Upstream layers can catch it and decide how to handle it (log, drop bar, alert, etc.)
      without the domain needing to know.
    """

    pass


class BufferLengthError(ModSlope5Error):
    """Raised when the input window is not exactly 5 bars long."""

    pass


class BarContinuityError(ModSlope5Error):
    """Raised when bar_num does not increase by exactly 1 across the 5 bars."""

    pass


class EndpointDifferenceError(ModSlope5Error):
    """Raised when bar_num[-1] - bar_num[-5] is not exactly 4."""

    pass


class OutputTypeError(ModSlope5Error):
    """Raised when the computed output is not a Python float."""

    pass


# -----------------------------
# Input "shape" (Protocol)
# -----------------------------


@runtime_checkable
class BarWindow5(Protocol):
    """
    Structural contract for the 5-bar window object `b`.

    Anything can satisfy this protocol (dataclass, namedtuple, your own Bar buffer class),
    as long as it provides these attributes with Sequence-like behavior:

    - high:    length 5, numeric values
    - low:     length 5, numeric values
    - close:   length 5, numeric values
    - bar_num: length 5, integer-like values that should be consecutive

    IMPORTANT:
    - We intentionally do NOT import your Redis types or your infrastructure types here.
      That would violate dependency direction (domain should not depend on infra).
    """

    high: Sequence[float]
    low: Sequence[float]
    close: Sequence[float]
    bar_num: Sequence[int]


# -----------------------------
# Optional helper for tests/examples
# (Not required by your app, but useful)
# -----------------------------


@dataclass(frozen=True)
class SimpleBarWindow5:
    """
    Minimal, immutable implementation of BarWindow5.

    This is just a convenience container for local testing or examples.
    Your production code can pass in your existing buffer object instead.
    """

    high: Sequence[float]
    low: Sequence[float]
    close: Sequence[float]
    bar_num: Sequence[int]


# -----------------------------
# Internal validations
# -----------------------------


def _require_len_5(name: str, seq: Sequence[object]) -> None:
    """
    Enforce the invariant: the sequence must have length 5.
    """
    # Defensive: Sequence must support len(), which is true for typical buffers/lists/tuples.
    if len(seq) != 5:
        raise BufferLengthError(f"{name} must have length 5, got {len(seq)}.")


def _require_all_buffers_len_5(b: BarWindow5) -> None:
    """
    Enforce that each required buffer is length 5.
    """
    _require_len_5("b.high", b.high)
    _require_len_5("b.low", b.low)
    _require_len_5("b.close", b.close)
    _require_len_5("b.bar_num", b.bar_num)


def _require_endpoint_difference_is_4(bar_nums: Sequence[int]) -> None:
    """
    Enforce: bar_num[-1] - bar_num[-5] == 4

    With length=5, bar_num[-5] is the first element and bar_num[-1] is the last.
    """
    diff = bar_nums[-1] - bar_nums[-5]
    if diff != 4:
        raise EndpointDifferenceError(
            f"Endpoint difference invariant failed: bar_num[-1] - bar_num[-5] must be 4, got {diff} "
            f"(bar_num[-5]={bar_nums[-5]}, bar_num[-1]={bar_nums[-1]})."
        )


def _require_bar_continuity(bar_nums: Sequence[int]) -> None:
    """
    Enforce: bar_nums are strictly consecutive increments of 1 over the 5 bars.

    Equivalent to:
        all(bar_nums[i] == bar_nums[i-1] + 1 for i in range(1, 5))
    """
    for i in range(1, 5):
        expected = bar_nums[i - 1] + 1
        if bar_nums[i] != expected:
            raise BarContinuityError(
                "Bar continuity invariant failed: bar_num must increase by 1 each step. "
                f"At i={i}, expected {expected} from prior {bar_nums[i-1]}, got {bar_nums[i]}. "
                f"Full bar_num={list(bar_nums)}"
            )


# -----------------------------
# Domain Function (pure)
# -----------------------------


def modSlope5(b: BarWindow5) -> float:
    """
    Compute the slope of the last 5 bars using average price difference.

    Parameters
    ----------
    b:
        A 5-bar window object providing:
        - b.high   (Sequence[float], length 5)
        - b.low    (Sequence[float], length 5)
        - b.close  (Sequence[float], length 5)
        - b.bar_num(Sequence[int],   length 5)

    Returns
    -------
    float
        Scalar slope value:
            (avg of last bar) - (avg of first bar)
        where avg(bar) = (high + low + close) / 3.

    Contract / Invariants (enforced)
    --------------------------------
    - Buffer length is exactly 5.
    - bar_num endpoints differ by exactly 4.
    - bar_num is continuous across 5 bars (increment by 1 each bar).
    - Output is a Python float.

    Failure Modes (raised exceptions)
    ---------------------------------
    - BufferLengthError:
        If any buffer length != 5.
    - EndpointDifferenceError:
        If bar_num[-1] - bar_num[-5] != 4.
    - BarContinuityError:
        If bar_num does not increment by 1 at each step.
    - OutputTypeError:
        If the computed value is not an instance of Python float.

    Side Effects
    ------------
    None. This function does not mutate inputs or touch I/O or globals.

    Notes (practical)
    -----------------
    - We assume upstream layers already ensured numeric casting and logical validity of prices.
      This function focuses on *window structure* and *domain calculation*.
    - If you later decide NaN/inf must be rejected here too, that is a domain-policy choice,
      but you told me your upstream contract already handles it—so we keep layering clean.
    """
    # 1) Validate structural invariants (no computation before this point).
    _require_all_buffers_len_5(b)
    _require_endpoint_difference_is_4(b.bar_num)
    _require_bar_continuity(b.bar_num)

    # 2) Perform the domain calculation (still pure).
    avg_last = (b.high[-1] + b.low[-1] + b.close[-1]) / 3.0
    avg_first = (b.high[-5] + b.low[-5] + b.close[-5]) / 3.0
    result = avg_last - avg_first

    # 3) Enforce output type exactly as specified in your contract.
    #    NOTE: Many numeric libs produce numpy.float64, which is *not* `float`.
    #    Your contract explicitly says instance(float), so we enforce it strictly.
    if not isinstance(result, float):
        raise OutputTypeError(
            f"modSlope5 output must be a Python float, got {type(result).__name__}."
        )

    return result
