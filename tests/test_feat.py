"""
tests/test_feat.py
==================

Purpose
-------
Contract-focused tests for modSlope5 (pure feature) sourced from feat_eng_1.py.
No Redis, no I/O, uses local test doubles only.

Test Inventory (enumerated, 5-word summaries)
---------------------------------------------
T01 - Valid window returns float
T02 - Fixture returns expected va lue
T03 - Bad length raises E_LEN
T04 - Bad continuity raises E_GAP
T05 - Deterministic and no mutation

Notes
-----
- Imports are setup, not tests.
- Tests assert contract-style error codes (E_LEN, E_GAP).
- Documentation only; execution logic unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import pytest

# ============================================================
# Setup (not tests): stable, static imports
# ============================================================

from feat_files.feat_eng_1 import modSlope5, FeatureContractError as FeatureErr


# ============================================================
# Test doubles (not tests)
# ============================================================


@dataclass(frozen=True)
class BarStub:
    """
    Minimal bar test double.

    Required attributes:
      - high, low, close, bar_num

    Frozen to prevent mutation.
    """

    high: float
    low: float
    close: float
    bar_num: int


def bar(*, n: int, px: float) -> BarStub:
    """
    Deterministic bar factory.

    Typical price:
      (high + low + close)/3 = px + 1/6

    Used to make expected slopes exact.
    """
    return BarStub(high=px + 1.0, low=px - 1.0, close=px + 0.5, bar_num=n)


# ============================================================
# [T01] Valid window returns float
# ============================================================


def test_modSlope5_returns_python_float_positive() -> None:
    """
    [T01] Valid window returns float

    Type:
      Positive

    Intent:
      Verify modSlope5 returns a Python float
      for a valid 5-bar consecutive window.
    """
    bars = [bar(n=i, px=100.0 + (i - 1)) for i in range(1, 6)]
    out = modSlope5(bars)
    assert isinstance(out, float)


# ============================================================
# [T02] Fixture returns expected value
# ============================================================


def test_modSlope5_known_fixture_value_positive() -> None:
    """
    [T02] Fixture returns expected value

    Type:
      Positive

    Fixture:
      bar_num = 1..5
      px      = 100..104

    Expected:
      typical(px) = px + 1/6
      slope = 4.0
    """
    bars = [
        bar(n=1, px=100.0),
        bar(n=2, px=101.0),
        bar(n=3, px=102.0),
        bar(n=4, px=103.0),
        bar(n=5, px=104.0),
    ]
    out = modSlope5(bars)
    assert out == pytest.approx(4.0, rel=0, abs=1e-12)


# ============================================================
# [T03] Bad length raises E_LEN
# ============================================================


def test_modSlope5_len_not_5_raises_E_LEN_negative() -> None:
    """
    [T03] Bad length raises E_LEN

    Type:
      Negative

    Condition:
      len(bars) != 5

    Expected:
      FeatureContractError containing 'E_LEN'.
    """
    bars = [bar(n=1, px=100.0), bar(n=2, px=101.0)]
    with pytest.raises(FeatureErr) as e:
        modSlope5(bars)
    assert "E_LEN" in str(e.value)


# ============================================================
# [T04] Bad continuity raises E_GAP
# ============================================================


def test_modSlope5_non_consecutive_bar_num_raises_E_GAP_negative() -> None:
    """
    [T04] Bad continuity raises E_GAP

    Type:
      Negative

    Condition:
      bar_num sequence is non-consecutive.

    Expected:
      FeatureContractError containing 'E_GAP'.
    """
    bars = [
        bar(n=10, px=100.0),
        bar(n=11, px=101.0),
        bar(n=13, px=102.0),  # continuity break
        bar(n=14, px=103.0),
        bar(n=15, px=104.0),
    ]
    with pytest.raises(FeatureErr) as e:
        modSlope5(bars)
    assert "E_GAP" in str(e.value)


# ============================================================
# [T05] Deterministic and no mutation
# ============================================================


def test_modSlope5_no_mutation_and_deterministic_nonfunctional() -> None:
    """
    [T05] Deterministic and no mutation

    Type:
      Non-functional

    Asserts:
      - Same input yields same output
      - Input BarStub objects remain unchanged
    """
    bars = [bar(n=i, px=200.0 + (i - 1)) for i in range(1, 6)]
    snap = [(b.high, b.low, b.close, b.bar_num) for b in bars]

    out1 = modSlope5(bars)
    out2 = modSlope5(bars)

    assert out1 == out2
    assert snap == [(b.high, b.low, b.close, b.bar_num) for b in bars]
