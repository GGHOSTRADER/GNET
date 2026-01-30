from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


# ==========================================================
# Contract Errors
# ==========================================================


class FeatureContractError(ValueError):
    """Raised when feature engineering contract invariants are violated."""


# ==========================================================
# Input Protocol (duck typing)
# ==========================================================


class BarLike(Protocol):
    """
    Bar-like interface required by modSlope5.

    Any object with attributes:
        - high: float
        - low: float
        - close: float
    is acceptable (dataclass, namedtuple, custom class, etc.)
    """

    high: float
    low: float
    close: float


# ==========================================================
# Contract helpers
# ==========================================================


def _require(cond: bool, msg: str) -> None:
    """
    Contract guard.
    Use this instead of assert because asserts can be disabled with -O.
    """
    if not cond:
        raise FeatureContractError(msg)


def _validate_bar_invariants(b: BarLike, *, idx: int) -> None:
    """
    Validate OHLC invariants for a single bar.

    Invariants:
        High >= Low
        High >= Close
        Low  <= Close
    """
    h = float(b.high)
    l = float(b.low)
    c = float(b.close)

    _require(h >= l, f"[modSlope5] Bar[{idx}] invariant violated: high({h}) < low({l})")
    _require(
        h >= c, f"[modSlope5] Bar[{idx}] invariant violated: high({h}) < close({c})"
    )
    _require(
        l <= c, f"[modSlope5] Bar[{idx}] invariant violated: low({l}) > close({c})"
    )


def _typical_price(b: BarLike) -> float:
    """
    Typical price proxy used by this feature.

    TP = (high + low + close) / 3
    """
    return (float(b.high) + float(b.low) + float(b.close)) / 3.0


# ==========================================================
# Feature Contract: modSlope5
# ==========================================================


def modSlope5(last5: Sequence[BarLike]) -> float:
    """
    Feature: modSlope5

    Purpose
    -------
    Measures the slope (price change) across the last 5 bars using typical price.

    Inputs
    ------
    last5:
        Sequence of exactly 5 bars ordered oldest -> newest.
        - last5[0] : bar 4 bars ago (oldest)
        - last5[4] : current bar (newest)

        Each bar must expose:
            .high, .low, .close

    Output
    ------
    float:
        modSlope5 = TP(newest) - TP(oldest)

    Calculation
    -----------
    TP = (high + low + close) / 3

    modSlope5 = TP[4] - TP[0]

    Notes about indexing
    --------------------
    You specified formula:
        TP[0] - TP[4]
    where [0] means "current bar".
    In Python sequences, it's more natural to pass bars ordered oldest->newest,
    so we implement:
        TP(newest) - TP(oldest)

    This gives the exact same slope meaning ("change over 5 bars"),
    but avoids confusion in live pipelines.

    Invariants enforced (per bar)
    -----------------------------
    High >= Low
    High >= Close
    Low <= Close

    Live-trading constraints
    ------------------------
    - no pandas
    - constant time
    - deterministic
    - fast validation
    """
    _require(len(last5) == 5, f"[modSlope5] Expected 5 bars, got {len(last5)}")

    # Validate all bars (cheap: 5 items only)
    for i, b in enumerate(last5):
        _validate_bar_invariants(b, idx=i)

    tp_oldest = _typical_price(last5[0])
    tp_newest = _typical_price(last5[4])

    return tp_newest - tp_oldest
