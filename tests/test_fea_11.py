"""
TEST SUITE SUMMARY (what this file proves)

These tests are designed to lock down the *contract surface* of `modSlope5`:

1) Correctness of the math
   - `modSlope5` returns TP(newest) - TP(oldest), where TP=(H+L+C)/3.
   - Handles positive, zero, and negative slopes.

2) Input shape contract
   - Requires *exactly* 5 bars. Anything else must raise FeatureContractError.

3) Per-bar OHLC invariant contract
   - For every bar: High >= Low, High >= Close, Low <= Close.
   - Failure must raise FeatureContractError and include the failing bar index in the message.

4) Type coercion expectations
   - Values are cast via float(...), so numeric strings are accepted.
   - Truly non-numeric values cause a ValueError (from float conversion), not FeatureContractError.

5) Helper function behavior (optional but useful)
   - `_typical_price` matches its definition.
   - `_validate_bar_invariants` accepts boundary equalities and rejects violations.

6) Edge-case reality checks (NaN/Inf)
   - NaN should fail invariants (comparisons become False) -> FeatureContractError.
   - Inf can pass invariants and make the output Inf. This test documents that behavior
     (so nobody gets surprised in live trading).

If you later decide that NaN/Inf should be explicitly rejected, these tests should be updated
to enforce that policy. Right now they document the current behavior.
"""

import math
import pytest
from dataclasses import dataclass

# ------------------------------------------------------------------------------
# IMPORTANT: Update this import path to match your file/module name.
# Example: if your code is in `features/mod_slope5.py`, use:
#   from features.mod_slope5 import ...
# ------------------------------------------------------------------------------
from feat_files.mod_slope5 import (
    modSlope5,
    FeatureContractError,
    _typical_price,
    _validate_bar_invariants,
)


# ------------------------------------------------------------------------------
# Test scaffolding: simple concrete Bar implementation
# ------------------------------------------------------------------------------
# Why:
# - The production code accepts any "BarLike" object (duck typing) with .high/.low/.close.
# - For tests, we want an explicit, minimal object that is easy to construct and read.
# - dataclass(frozen=True) gives immutability (no accidental mutation inside tests).
#   Immutability matters because your real pipeline likely treats bars as read-only facts.
# ------------------------------------------------------------------------------
@dataclass(frozen=True)
class Bar:
    high: float
    low: float
    close: float


def mkbar(h, l, c) -> Bar:
    """
    Tiny factory to reduce repetition in test bodies.

    Why:
    - Keeps each test focused on *what* it checks, not repetitive constructor syntax.
    - Makes it easy to swap Bar implementation later without rewriting tests.
    """
    return Bar(high=h, low=l, close=c)


def valid_5bars():
    """
    Returns a canonical valid 5-bar sequence ordered oldest -> newest.

    Why:
    - Most tests need a "known good baseline" and then tweak one element.
    - Fixing a standard baseline reduces cognitive load and improves test reliability.
    """
    return [
        mkbar(10, 8, 9),
        mkbar(11, 9, 10),
        mkbar(12, 10, 11),
        mkbar(13, 11, 12),
        mkbar(14, 12, 13),
    ]


# ==============================================================================
# 1) Core correctness tests (math and sign)
# ==============================================================================


def test_modSlope5_returns_tp_newest_minus_tp_oldest():
    """
    Proves the main equation is correct.

    Why:
    - This is the primary feature definition: TP(newest) - TP(oldest).
    - If this fails, the feature is wrong even if all contracts pass.
    """
    bars = valid_5bars()

    # We compute the expected result explicitly (no helper reuse)
    # so the test doesn't "agree with itself" by calling the same functions.
    tp_old = (10 + 8 + 9) / 3.0
    tp_new = (14 + 12 + 13) / 3.0

    assert modSlope5(bars) == pytest.approx(tp_new - tp_old)


def test_modSlope5_zero_when_oldest_tp_equals_newest_tp():
    """
    Ensures zero slope is produced when oldest TP == newest TP.

    Why:
    - Guards against accidental offset mistakes or sign flips.
    - Also catches subtle floating arithmetic issues if implementation changes.
    """
    bars = [
        mkbar(10, 8, 9),  # oldest
        mkbar(99, 1, 50),  # junk in middle doesn't matter for slope endpoints
        mkbar(5, 4, 4.5),
        mkbar(7, 7, 7),
        mkbar(10, 8, 9),  # newest equal to oldest -> slope should be 0
    ]
    assert modSlope5(bars) == pytest.approx(0.0)


def test_modSlope5_negative_when_newest_tp_lower_than_oldest_tp():
    """
    Confirms slope sign is negative when price declines from oldest to newest.

    Why:
    - This is the fastest way to detect an inverted ordering assumption.
    - If someone accidentally passes newest->oldest and "fixes" code incorrectly,
      this test should fail and force a deliberate decision.
    """
    bars = [
        mkbar(14, 12, 13),  # oldest (higher)
        mkbar(13, 11, 12),
        mkbar(12, 10, 11),
        mkbar(11, 9, 10),
        mkbar(10, 8, 9),  # newest (lower)
    ]
    out = modSlope5(bars)
    assert out < 0


# ==============================================================================
# 2) Input shape contract: must pass exactly 5 bars
# ==============================================================================


@pytest.mark.parametrize("n", [0, 1, 2, 3, 4, 6, 7, 10])
def test_modSlope5_requires_exactly_5_bars(n: int):
    """
    Ensures the function enforces the strongest precondition: len(last5) == 5.

    Why:
    - This is a "hard" contract invariant: anything else is logically invalid.
    - In live pipelines, bad buffering / off-by-one errors are common.
    - We explicitly test multiple wrong lengths to prevent "accidental acceptance."
    """
    bars = [mkbar(10, 8, 9) for _ in range(n)]
    with pytest.raises(FeatureContractError) as e:
        modSlope5(bars)

    # Why check message contents:
    # - When a contract error happens in production, the message is the debug tool.
    # - If messages get refactored away, you lose quick diagnosis.
    assert "Expected 5 bars" in str(e.value)


# ==============================================================================
# 3) Per-bar OHLC invariants: correctness and error reporting
# ==============================================================================


def test_invariant_high_ge_low_violation_raises_with_index():
    """
    Violates high >= low for a single bar and verifies:
      - FeatureContractError is raised
      - message includes the bar index

    Why:
    - Index-in-message is critical for tracing which bar in a live stream is bad.
    - This test forces that observability contract to stay intact.
    """
    bars = valid_5bars()
    bars[2] = mkbar(5, 6, 5.5)  # high < low at idx=2

    with pytest.raises(FeatureContractError) as e:
        modSlope5(bars)

    msg = str(e.value)
    assert "Bar[2]" in msg
    assert "high" in msg and "low" in msg


def test_invariant_high_ge_close_violation_raises_with_index():
    """
    Violates high >= close and verifies the correct error and indexing.

    Why:
    - Close can exceed High due to bad upstream mapping, wrong data feed fields,
      or type parsing mistakes. This catches that quickly.
    """
    bars = valid_5bars()
    bars[1] = mkbar(10, 9, 10.1)  # high < close at idx=1

    with pytest.raises(FeatureContractError) as e:
        modSlope5(bars)

    msg = str(e.value)
    assert "Bar[1]" in msg
    assert "high" in msg and "close" in msg


def test_invariant_low_le_close_violation_raises_with_index():
    """
    Violates low <= close and verifies the correct error and indexing.

    Why:
    - Close below Low indicates corrupt OHLC relationships or swapped fields.
    - Again, message index is non-negotiable for quick diagnosis.
    """
    bars = valid_5bars()
    bars[4] = mkbar(14, 12, 11.9)  # low > close at idx=4

    with pytest.raises(FeatureContractError) as e:
        modSlope5(bars)

    msg = str(e.value)
    assert "Bar[4]" in msg
    assert "low" in msg and "close" in msg


def test_validate_bar_invariants_allows_equalities():
    """
    Confirms equalities are allowed (high==low==close).

    Why:
    - This is a boundary condition that happens with flat bars or illiquid ticks.
    - Contracts should be strict but not brittle.
    """
    b = mkbar(10, 10, 10)
    _validate_bar_invariants(b, idx=0)  # should not raise


# ==============================================================================
# 4) Type coercion: float(...) casting behavior
# ==============================================================================


def test_accepts_string_numbers_due_to_float_casting():
    """
    Verifies numeric strings are accepted.

    Why:
    - Your implementation calls float(...) on bar fields.
    - In real pipelines, you may decode from TCP/Redis as strings before casting.
    - This test documents and enforces that intended flexibility.
    """

    @dataclass(frozen=True)
    class StrBar:
        high: str
        low: str
        close: str

    bars = [
        StrBar("10", "8", "9"),
        StrBar("11", "9", "10"),
        StrBar("12", "10", "11"),
        StrBar("13", "11", "12"),
        StrBar("14", "12", "13"),
    ]

    out = modSlope5(bars)

    tp_old = (10 + 8 + 9) / 3.0
    tp_new = (14 + 12 + 13) / 3.0
    assert out == pytest.approx(tp_new - tp_old)


def test_non_numeric_values_raise_value_error_from_float_cast():
    """
    Verifies truly non-numeric values raise ValueError (from float conversion).

    Why:
    - The contract code does not wrap float(...) failures into FeatureContractError.
    - That means the expected failure mode is ValueError.
    - This test makes that explicit so callers know what can happen.
    """

    @dataclass(frozen=True)
    class WeirdBar:
        high: str
        low: str
        close: str

    bars = [
        WeirdBar("10", "8", "9"),
        WeirdBar("11", "9", "10"),
        WeirdBar("nope", "10", "11"),  # float("nope") -> ValueError
        WeirdBar("13", "11", "12"),
        WeirdBar("14", "12", "13"),
    ]

    with pytest.raises(ValueError):
        modSlope5(bars)


# ==============================================================================
# 5) Helper functions (optional but useful for faster debugging)
# ==============================================================================


def test_typical_price_matches_definition():
    """
    Validates `_typical_price` implements TP=(H+L+C)/3.

    Why:
    - Helper functions are often refactored; this test keeps it pinned.
    - If modSlope5 changes later to use a different proxy, this test will catch it
      and force an intentional update.
    """
    b = mkbar(12, 6, 9)
    assert _typical_price(b) == pytest.approx((12 + 6 + 9) / 3.0)


# ==============================================================================
# 6) Edge cases: NaN / Inf (document current behavior)
# ==============================================================================


def test_nan_inputs_trigger_contract_error():
    """
    NaN should fail invariants because comparisons with NaN are False.

    Why:
    - This is the real-world behavior of IEEE floats in Python.
    - If NaNs enter the stream, you want a loud, early failure, not silent NaN features.
    - This test ensures NaN doesn't sneak through.
    """
    bars = valid_5bars()
    bars[0] = mkbar(float("nan"), 8, 9)

    with pytest.raises(FeatureContractError):
        modSlope5(bars)


def test_inf_inputs_can_pass_invariants_and_propagate_to_output():
    """
    Inf can satisfy the comparisons and propagate into the output.

    Why:
    - This is a potential live-trading hazard: you may end up with inf features.
    - The current implementation allows it; this test documents that reality.
    - If you decide to reject non-finite values later, change this test accordingly.
    """
    bars = valid_5bars()
    bars[4] = mkbar(float("inf"), 12, 13)

    out = modSlope5(bars)
    assert math.isinf(out)
