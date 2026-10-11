"""Canonical MA2CrossLE feature definitions shared by training and live code.

The engine consumes 30-second bars in chronological order. Canonical VWAP is
the ES-session cumulative sum of close * (up + down) / sum(up + down).
An explicit bar mode is retained for separate TradeStation-VWAP experiments.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Deque


FEATURE_NAMES = (
    "parkinson_vol_5", "parkinson_vol_15", "parkinson_vol_30",
    "ofi_5", "ofi_15", "ofi_30",
    "volume_percentile", "volume_momentum",
    "amihud_illiquidity", "vwap_distance",
    "minutes_since_open", "is_first_last_30min", "day_of_week",
)

WINDOW_SIZE = 60
_OPEN_S = 9 * 3600 + 30 * 60
_ES_SESSION_START_ET_S = 18 * 3600


class CanonicalFeatureError(ValueError):
    """Raised when a bar window cannot produce valid canonical features."""


@dataclass(frozen=True)
class FeatureValues:
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
    day_of_week: int


def _actual_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    packed = int(value)
    year = packed // 10000
    if year < 1900:  # TradeStation stores years since 1900 (126 -> 2026).
        year += 1900
    return date(year, (packed // 100) % 100, packed % 100)


def _volume(bar: Any) -> int:
    return int(bar.up) + int(bar.down)


def parkinson_vol(bars: list[Any], window: int) -> float:
    subset = bars[-window:]
    if len(subset) != window:
        raise CanonicalFeatureError(f"parkinson_vol needs {window} bars")
    total = sum(math.log(b.high / b.low) ** 2 for b in subset)
    return float(math.sqrt(total / (4.0 * window * math.log(2.0))))


def order_flow_imbalance(bars: list[Any], window: int) -> float:
    subset = bars[-window:]
    if len(subset) != window:
        raise CanonicalFeatureError(f"ofi needs {window} bars")
    total = sum(_volume(b) for b in subset)
    if total == 0:
        return math.nan
    return float(sum(b.up - b.down for b in subset) / total)


def volume_percentile(bars: list[Any], window: int = WINDOW_SIZE) -> float:
    """Match pandas ``rank(pct=True)`` including average ranks for ties."""
    volumes = [_volume(b) for b in bars[-window:]]
    if len(volumes) != window:
        raise CanonicalFeatureError(f"volume_percentile needs {window} bars")
    current = volumes[-1]
    less = sum(v < current for v in volumes)
    equal = sum(v == current for v in volumes)
    average_rank = less + (equal + 1.0) / 2.0
    return float(average_rank / window)


def volume_momentum(bars: list[Any], periods: int = 5) -> float:
    previous = _volume(bars[-(periods + 1)])
    if previous == 0:
        return math.nan
    return float((_volume(bars[-1]) - previous) / previous)


def amihud_illiquidity(bars: list[Any], window: int = 30) -> float:
    subset = bars[-(window + 1):]
    ratios: list[float] = []
    for previous, current in zip(subset, subset[1:]):
        dollar_volume = current.close * _volume(current)
        if dollar_volume == 0:
            return math.nan
        ratios.append(abs((current.close - previous.close) / previous.close) / dollar_volume)
    return float(sum(ratios) / window)


def average_true_range(bars: list[Any], period: int = 14) -> float:
    subset = bars[-(period + 1):]
    ranges = [
        max(current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close))
        for previous, current in zip(subset, subset[1:])
    ]
    return float(sum(ranges) / period)


def minutes_since_open(time_s: int) -> float:
    return float(max((int(time_s) - _OPEN_S) / 60.0, 0.0))


def session_boundary_flag(time_s: int) -> int:
    minutes = minutes_since_open(time_s)
    return int(minutes <= 30.0 or minutes >= 360.0)


def calculate_features(bars: list[Any], vwap: float) -> FeatureValues:
    if len(bars) != WINDOW_SIZE:
        raise CanonicalFeatureError(f"features need {WINDOW_SIZE} bars, got {len(bars)}")
    current = bars[-1]
    atr = average_true_range(bars)
    if not math.isfinite(vwap) or vwap <= 0:
        raise CanonicalFeatureError(f"invalid VWAP: {vwap!r}")
    vwap_distance = math.nan if atr == 0 else (current.close - vwap) / atr
    return FeatureValues(
        parkinson_vol_5=parkinson_vol(bars, 5),
        parkinson_vol_15=parkinson_vol(bars, 15),
        parkinson_vol_30=parkinson_vol(bars, 30),
        ofi_5=order_flow_imbalance(bars, 5),
        ofi_15=order_flow_imbalance(bars, 15),
        ofi_30=order_flow_imbalance(bars, 30),
        volume_percentile=volume_percentile(bars),
        volume_momentum=volume_momentum(bars),
        amihud_illiquidity=amihud_illiquidity(bars),
        vwap_distance=float(vwap_distance),
        minutes_since_open=minutes_since_open(current.time_s),
        is_first_last_30min=session_boundary_flag(current.time_s),
        day_of_week=_actual_date(current.date).weekday(),
    )


class FeatureEngine:
    """Incremental canonical calculator for chronological bar streams."""

    def __init__(
        self, *, vwap_mode: str = "canonical",
        session_start_s: int = _ES_SESSION_START_ET_S,
    ) -> None:
        if vwap_mode not in {"canonical", "bar"}:
            raise ValueError(f"unknown VWAP mode: {vwap_mode}")
        if not 0 <= session_start_s < 86400:
            raise ValueError(f"invalid session start: {session_start_s}")
        self._vwap_mode = vwap_mode
        self._session_start_s = session_start_s
        self._bars: Deque[Any] = deque(maxlen=WINDOW_SIZE)
        self._date: date | None = None
        self._cumulative_price_volume = 0.0
        self._cumulative_volume = 0

    @property
    def bars_seen(self) -> int:
        return len(self._bars)

    def update(self, bar: Any) -> FeatureValues | None:
        bar_date = _actual_date(bar.date)
        session_date = (
            bar_date + timedelta(days=1)
            if int(bar.time_s) >= self._session_start_s else bar_date
        )
        if session_date != self._date:
            self._date = session_date
            self._cumulative_price_volume = 0.0
            self._cumulative_volume = 0
        volume = _volume(bar)
        self._cumulative_price_volume += float(bar.close) * volume
        self._cumulative_volume += volume
        self._bars.append(bar)

        if len(self._bars) < WINDOW_SIZE:
            return None
        if self._vwap_mode == "bar":
            vwap = float(bar.vwap)
        else:
            vwap = (
                self._cumulative_price_volume / self._cumulative_volume
                if self._cumulative_volume else math.nan
            )
        return calculate_features(list(self._bars), vwap)
