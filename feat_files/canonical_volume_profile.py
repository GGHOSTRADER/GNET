"""Canonical, transport-independent volume-profile domain engine.

Both live Redis processing and historical Parquet replay must call this module.
It contains no Redis, TCP, filesystem, or clock I/O. Callers provide ordered
tick-like records and decide when to request a snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as calendar_date, timedelta
from typing import Optional, Protocol, Tuple

import numpy as np


VALUE_AREA_PCT = 0.70
EXTENSION_PCT = 0.15
DEFAULT_RANGE_TICKS = 400
SESSION_START_S = 18 * 3600
ACCEPTANCE_RADIUS_TICKS = 4
HVN_MEDIAN_MULTIPLIER = 1.5
LVN_MEDIAN_MULTIPLIER = 0.5
POC_VELOCITY_SNAPSHOTS = 5

VOLUME_PROFILE_FEATURE_NAMES = (
    "poc_distance",
    "poc_concentration",
    "va_width",
    "va_position",
    "vol_above_poc_ratio",
    "profile_entropy",
    "profile_kurtosis",
    "poc_migration",
    "classified_cumulative_delta",
    "classified_delta_ratio",
    "classified_delta_at_poc_ratio",
    "classified_value_area_delta_ratio",
    "classified_delta_above_below_poc",
    "max_abs_delta_price_distance",
    "classified_delta_concentration",
    "recent_classified_delta_ratio",
    "price_classified_delta_divergence",
    "va_expansion_rate",
    "poc_velocity_5",
    "volume_above_vah_ratio",
    "volume_below_val_ratio",
    "profile_skewness",
    "current_price_acceptance_ratio",
    "distance_to_val_ticks",
    "distance_to_vah_ticks",
    "nearest_hvn_distance_ticks",
    "nearest_lvn_distance_ticks",
    "nearest_hvn_strength",
    "nearest_lvn_strength",
    "hvn_count",
    "lvn_count",
    "current_price_in_hvn",
)


class TickLike(Protocol):
    """Minimum record contract consumed by the canonical VP engine."""

    symbol: str
    date: int
    time_s: int
    high: float
    up: int
    down: int
    bar_num: int


class VolumeProfileError(ValueError):
    """Raised when canonical volume-profile invariants are violated."""


def require_volume_profile(condition: bool, message: str) -> None:
    """Raise a domain error when a required invariant is false."""
    if not condition:
        raise VolumeProfileError(message)


def find_poc(
    profile: np.ndarray,
    price_levels: np.ndarray,
) -> Tuple[float, float]:
    """Return the price and volume of the highest-volume level."""
    require_volume_profile(profile.size > 0, "Profile cannot be empty.")
    require_volume_profile(
        profile.shape == price_levels.shape,
        "Profile and price-level arrays must have the same shape.",
    )
    index = int(np.argmax(profile))
    return float(price_levels[index]), float(profile[index])


def find_value_area(
    profile: np.ndarray,
    price_levels: np.ndarray,
    pct: float = VALUE_AREA_PCT,
) -> Tuple[float, float]:
    """Return bounds containing the selected highest-volume fraction."""
    require_volume_profile(profile.size > 0, "Profile cannot be empty.")
    require_volume_profile(
        profile.shape == price_levels.shape,
        "Profile and price-level arrays must have the same shape.",
    )
    require_volume_profile(0.0 < pct <= 1.0, "Value-area pct must be in (0, 1].")
    total = float(profile.sum())
    require_volume_profile(total > 0.0, "Total volume is zero, cannot compute value area.")

    sorted_indices = np.argsort(profile)[::-1]
    cumulative_volume = np.cumsum(profile[sorted_indices])
    levels_needed = min(
        int(np.searchsorted(cumulative_volume, pct * total, side="left")) + 1,
        len(price_levels),
    )
    selected = sorted_indices[:levels_needed]
    return (
        float(price_levels[selected].min()),
        float(price_levels[selected].max()),
    )


def compute_derived_features(
    profile: np.ndarray,
    price_levels: np.ndarray,
    poc_price: float,
    poc_volume: float,
    value_area_low: float,
    value_area_high: float,
    total_volume: float,
    current_price: float,
    tick_size: float,
    previous_poc_price: Optional[float],
) -> dict[str, float]:
    """Derive the canonical eight POC/Value-Area features."""
    require_volume_profile(tick_size > 0.0, "tick_size must be positive")
    poc_distance = (current_price - poc_price) / tick_size
    poc_concentration = poc_volume / total_volume if total_volume > 0 else 0.0

    value_area_range = value_area_high - value_area_low
    value_area_width = value_area_range / tick_size
    value_area_position = (
        (current_price - value_area_low) / value_area_range
        if value_area_range > 0
        else 0.5
    )
    volume_above_poc_ratio = (
        float(profile[price_levels > poc_price].sum()) / total_volume
        if total_volume > 0
        else 0.0
    )

    if total_volume > 0:
        probabilities = profile / total_volume
        nonzero = probabilities > 0
        profile_entropy = float(
            -np.sum(probabilities[nonzero] * np.log(probabilities[nonzero]))
        )
        mean_price = float(np.sum(price_levels * profile) / total_volume)
        variance = float(
            np.sum(profile * (price_levels - mean_price) ** 2) / total_volume
        )
        if variance > 0:
            fourth_moment = float(
                np.sum(profile * (price_levels - mean_price) ** 4) / total_volume
            )
            profile_kurtosis = fourth_moment / (variance**2) - 3.0
        else:
            profile_kurtosis = 0.0
    else:
        profile_entropy = 0.0
        profile_kurtosis = 0.0

    poc_migration = (
        (poc_price - previous_poc_price) / tick_size
        if previous_poc_price is not None
        else 0.0
    )
    return {
        "poc_distance": poc_distance,
        "poc_concentration": poc_concentration,
        "va_width": value_area_width,
        "va_position": value_area_position,
        "vol_above_poc_ratio": volume_above_poc_ratio,
        "profile_entropy": profile_entropy,
        "profile_kurtosis": profile_kurtosis,
        "poc_migration": poc_migration,
    }


def find_volume_nodes(profile: np.ndarray, qualifying_mask: np.ndarray, *, high: bool) -> list[int]:
    """Return one representative index for each contiguous qualifying node."""
    require_volume_profile(
        profile.shape == qualifying_mask.shape,
        "Profile and node mask must have the same shape.",
    )
    qualifying_indices = np.flatnonzero(qualifying_mask)
    if qualifying_indices.size == 0:
        return []
    groups = np.split(
        qualifying_indices,
        np.where(np.diff(qualifying_indices) != 1)[0] + 1,
    )
    representatives: list[int] = []
    for group in groups:
        group_volumes = profile[group]
        offset = int(np.argmax(group_volumes) if high else np.argmin(group_volumes))
        representatives.append(int(group[offset]))
    return representatives


def compute_extended_features(
    state: "VolumeProfileState",
    price_levels: np.ndarray,
    delta_profile: np.ndarray,
    *,
    poc_price: float,
    value_area_low: float,
    value_area_high: float,
    total_volume: float,
) -> dict[str, float]:
    """Compute classified-delta, shape, acceptance, velocity, and node features."""
    profile = state.profile
    tick_size = state.tick_size
    cumulative_delta = float(delta_profile.sum())
    delta_ratio = cumulative_delta / total_volume if total_volume > 0 else 0.0
    poc_index = int(np.argmin(np.abs(price_levels - poc_price)))
    delta_at_poc_ratio = (
        float(delta_profile[poc_index]) / float(profile[poc_index])
        if profile[poc_index] > 0
        else 0.0
    )
    value_area_mask = (price_levels >= value_area_low) & (price_levels <= value_area_high)
    value_area_volume = float(profile[value_area_mask].sum())
    value_area_delta_ratio = (
        float(delta_profile[value_area_mask].sum()) / value_area_volume
        if value_area_volume > 0
        else 0.0
    )
    delta_above = float(delta_profile[price_levels > poc_price].sum())
    delta_below = float(delta_profile[price_levels < poc_price].sum())
    delta_above_below = (
        (delta_above - delta_below) / total_volume if total_volume > 0 else 0.0
    )
    absolute_delta = np.abs(delta_profile)
    total_absolute_delta = float(absolute_delta.sum())
    if total_absolute_delta > 0:
        max_delta_index = int(np.argmax(absolute_delta))
        max_delta_distance = (
            state.last_price - float(price_levels[max_delta_index])
        ) / tick_size
        delta_concentration = float(absolute_delta[max_delta_index]) / total_absolute_delta
    else:
        max_delta_distance = 0.0
        delta_concentration = 0.0

    recent_volume = total_volume - state.prev_snapshot_total_volume
    recent_delta = cumulative_delta - state.prev_snapshot_cumulative_delta
    recent_delta_ratio = recent_delta / recent_volume if recent_volume > 0 else 0.0
    price_change_ticks = (
        (state.last_price - state.prev_snapshot_price) / tick_size
        if state.prev_snapshot_price is not None
        else 0.0
    )
    price_delta_divergence = -price_change_ticks * recent_delta_ratio

    value_area_width = (value_area_high - value_area_low) / tick_size
    va_expansion_rate = (
        value_area_width - state.prev_va_width
        if state.prev_va_width is not None
        else 0.0
    )
    poc_velocity = (
        (poc_price - state.poc_history[-POC_VELOCITY_SNAPSHOTS])
        / tick_size
        / POC_VELOCITY_SNAPSHOTS
        if len(state.poc_history) >= POC_VELOCITY_SNAPSHOTS
        else 0.0
    )

    volume_above_vah_ratio = (
        float(profile[price_levels > value_area_high].sum()) / total_volume
        if total_volume > 0
        else 0.0
    )
    volume_below_val_ratio = (
        float(profile[price_levels < value_area_low].sum()) / total_volume
        if total_volume > 0
        else 0.0
    )
    if total_volume > 0:
        mean_price = float(np.sum(price_levels * profile) / total_volume)
        variance = float(np.sum(profile * (price_levels - mean_price) ** 2) / total_volume)
        profile_skewness = (
            float(np.sum(profile * (price_levels - mean_price) ** 3) / total_volume)
            / (variance**1.5)
            if variance > 0
            else 0.0
        )
    else:
        profile_skewness = 0.0

    acceptance_mask = (
        np.abs(price_levels - state.last_price)
        <= ACCEPTANCE_RADIUS_TICKS * tick_size + tick_size * 1e-9
    )
    current_price_acceptance = (
        float(profile[acceptance_mask].sum()) / total_volume
        if total_volume > 0
        else 0.0
    )

    occupied = profile > 0
    nonzero_volume = profile[occupied]
    median_volume = float(np.median(nonzero_volume)) if nonzero_volume.size else 0.0
    hvn_mask = occupied & (profile >= HVN_MEDIAN_MULTIPLIER * median_volume)
    lvn_mask = occupied & (profile <= LVN_MEDIAN_MULTIPLIER * median_volume)
    hvn_indices = find_volume_nodes(profile, hvn_mask, high=True)
    lvn_indices = find_volume_nodes(profile, lvn_mask, high=False)

    def nearest_node(indices: list[int]) -> tuple[float, float]:
        if not indices or median_volume <= 0:
            return 0.0, 0.0
        nearest = min(
            indices,
            key=lambda index: abs(float(price_levels[index]) - state.last_price),
        )
        distance = (state.last_price - float(price_levels[nearest])) / tick_size
        strength = float(profile[nearest]) / median_volume
        return distance, strength

    nearest_hvn_distance, nearest_hvn_strength = nearest_node(hvn_indices)
    nearest_lvn_distance, nearest_lvn_strength = nearest_node(lvn_indices)
    current_index = int(np.argmin(np.abs(price_levels - state.last_price)))

    return {
        "classified_cumulative_delta": cumulative_delta,
        "classified_delta_ratio": delta_ratio,
        "classified_delta_at_poc_ratio": delta_at_poc_ratio,
        "classified_value_area_delta_ratio": value_area_delta_ratio,
        "classified_delta_above_below_poc": delta_above_below,
        "max_abs_delta_price_distance": max_delta_distance,
        "classified_delta_concentration": delta_concentration,
        "recent_classified_delta_ratio": recent_delta_ratio,
        "price_classified_delta_divergence": price_delta_divergence,
        "va_expansion_rate": va_expansion_rate,
        "poc_velocity_5": poc_velocity,
        "volume_above_vah_ratio": volume_above_vah_ratio,
        "volume_below_val_ratio": volume_below_val_ratio,
        "profile_skewness": profile_skewness,
        "current_price_acceptance_ratio": current_price_acceptance,
        "distance_to_val_ticks": (state.last_price - value_area_low) / tick_size,
        "distance_to_vah_ticks": (value_area_high - state.last_price) / tick_size,
        "nearest_hvn_distance_ticks": nearest_hvn_distance,
        "nearest_lvn_distance_ticks": nearest_lvn_distance,
        "nearest_hvn_strength": nearest_hvn_strength,
        "nearest_lvn_strength": nearest_lvn_strength,
        "hvn_count": float(len(hvn_indices)),
        "lvn_count": float(len(lvn_indices)),
        "current_price_in_hvn": float(bool(hvn_mask[current_index])),
    }


@dataclass
class VolumeProfileResult:
    """Immutable-by-convention snapshot returned by the canonical engine."""

    symbol: str
    date: int
    bar_num: int
    tick_size: float
    range_ticks: int
    price_levels: np.ndarray
    volume_at_level: np.ndarray
    up_volume_at_level: np.ndarray
    down_volume_at_level: np.ndarray
    classified_delta_at_level: np.ndarray
    poc_price: float
    poc_volume: float
    value_area_low: float
    value_area_high: float
    total_volume: float
    n_bars: int
    extensions: int
    poc_distance: float
    poc_concentration: float
    va_width: float
    va_position: float
    vol_above_poc_ratio: float
    profile_entropy: float
    profile_kurtosis: float
    poc_migration: float
    classified_cumulative_delta: float
    classified_delta_ratio: float
    classified_delta_at_poc_ratio: float
    classified_value_area_delta_ratio: float
    classified_delta_above_below_poc: float
    max_abs_delta_price_distance: float
    classified_delta_concentration: float
    recent_classified_delta_ratio: float
    price_classified_delta_divergence: float
    va_expansion_rate: float
    poc_velocity_5: float
    volume_above_vah_ratio: float
    volume_below_val_ratio: float
    profile_skewness: float
    current_price_acceptance_ratio: float
    distance_to_val_ticks: float
    distance_to_vah_ticks: float
    nearest_hvn_distance_ticks: float
    nearest_lvn_distance_ticks: float
    nearest_hvn_strength: float
    nearest_lvn_strength: float
    hvn_count: float
    lvn_count: float
    current_price_in_hvn: float


@dataclass
class VolumeProfileState:
    """Mutable state for one symbol and 18:00-to-17:59 trading session."""

    profile: np.ndarray
    up_profile: np.ndarray
    down_profile: np.ndarray
    min_price: float
    tick_size: float
    range_ticks: int
    symbol: str
    date: int
    session_key: int
    bar_num: int
    n_bars: int
    extensions: int
    last_price: float
    prev_poc_price: Optional[float]
    prev_snapshot_total_volume: float
    prev_snapshot_cumulative_delta: float
    prev_snapshot_price: Optional[float]
    prev_va_width: Optional[float]
    poc_history: list[float]


def next_packed_date(packed: int) -> int:
    """Return the next date in TradeStation's years-since-1900 format."""
    year_offset = packed // 10000
    month = (packed // 100) % 100
    day = packed % 100
    next_day = calendar_date(year_offset + 1900, month, day) + timedelta(days=1)
    return (next_day.year - 1900) * 10000 + next_day.month * 100 + next_day.day


def session_key(packed_date: int, time_s: int) -> int:
    """Map a timestamp to its 18:00-to-17:59 trading-session date."""
    return next_packed_date(packed_date) if time_s >= SESSION_START_S else packed_date


def initialize_profile(
    tick: TickLike,
    tick_size: float,
    range_ticks: int,
) -> VolumeProfileState:
    """Initialize an empty, centered price grid for a new session."""
    require_volume_profile(tick_size > 0.0, f"tick_size must be > 0, got {tick_size}")
    require_volume_profile(range_ticks > 0, f"range_ticks must be > 0, got {range_ticks}")
    snapped_price = round(tick.high / tick_size) * tick_size
    half_range = (range_ticks // 2) * tick_size
    return VolumeProfileState(
        profile=np.zeros(range_ticks + 1, dtype=np.float64),
        up_profile=np.zeros(range_ticks + 1, dtype=np.float64),
        down_profile=np.zeros(range_ticks + 1, dtype=np.float64),
        min_price=snapped_price - half_range,
        tick_size=tick_size,
        range_ticks=range_ticks,
        symbol=tick.symbol,
        date=tick.date,
        session_key=session_key(tick.date, tick.time_s),
        bar_num=tick.bar_num,
        n_bars=0,
        extensions=0,
        last_price=snapped_price,
        prev_poc_price=None,
        prev_snapshot_total_volume=0.0,
        prev_snapshot_cumulative_delta=0.0,
        prev_snapshot_price=None,
        prev_va_width=None,
        poc_history=[],
    )


def update_profile(state: VolumeProfileState, tick: TickLike) -> None:
    """Accumulate one tick, extending the grid only on a boundary break."""
    require_volume_profile(
        tick.symbol == state.symbol,
        "Cannot update a profile with a different symbol.",
    )
    require_volume_profile(
        session_key(tick.date, tick.time_s) == state.session_key,
        "Cannot update a profile with a different trading session.",
    )
    up_volume = float(tick.up)
    down_volume = float(tick.down)
    require_volume_profile(up_volume >= 0.0, "Up volume cannot be negative.")
    require_volume_profile(down_volume >= 0.0, "Down volume cannot be negative.")
    volume = up_volume + down_volume
    snapped_price = round(tick.high / state.tick_size) * state.tick_size
    index = int(round((snapped_price - state.min_price) / state.tick_size))
    extension = max(1, int(state.range_ticks * EXTENSION_PCT))

    if index < 0:
        levels_to_add = max(extension, -index)
        zeros = np.zeros(levels_to_add, dtype=np.float64)
        state.profile = np.concatenate([zeros, state.profile])
        state.up_profile = np.concatenate([zeros.copy(), state.up_profile])
        state.down_profile = np.concatenate([zeros.copy(), state.down_profile])
        state.min_price -= levels_to_add * state.tick_size
        index += levels_to_add
        state.extensions += 1
    elif index >= len(state.profile):
        levels_to_add = max(extension, index - len(state.profile) + 1)
        zeros = np.zeros(levels_to_add, dtype=np.float64)
        state.profile = np.concatenate([state.profile, zeros])
        state.up_profile = np.concatenate([state.up_profile, zeros.copy()])
        state.down_profile = np.concatenate([state.down_profile, zeros.copy()])
        state.extensions += 1

    state.profile[index] += volume
    state.up_profile[index] += up_volume
    state.down_profile[index] += down_volume
    state.date = tick.date
    state.bar_num = tick.bar_num
    state.n_bars += 1
    state.last_price = snapped_price


def snapshot_profile(state: VolumeProfileState) -> VolumeProfileResult:
    """Create a canonical snapshot and advance previous-POC state."""
    price_levels = (
        state.min_price
        + np.arange(len(state.profile), dtype=np.float64) * state.tick_size
    )
    poc_price, poc_volume = find_poc(state.profile, price_levels)
    value_area_low, value_area_high = find_value_area(state.profile, price_levels)
    total_volume = float(state.profile.sum())
    delta_profile = state.up_profile - state.down_profile
    derived = compute_derived_features(
        profile=state.profile,
        price_levels=price_levels,
        poc_price=poc_price,
        poc_volume=poc_volume,
        value_area_low=value_area_low,
        value_area_high=value_area_high,
        total_volume=total_volume,
        current_price=state.last_price,
        tick_size=state.tick_size,
        previous_poc_price=state.prev_poc_price,
    )
    extended = compute_extended_features(
        state,
        price_levels,
        delta_profile,
        poc_price=poc_price,
        value_area_low=value_area_low,
        value_area_high=value_area_high,
        total_volume=total_volume,
    )
    state.prev_poc_price = poc_price
    state.prev_snapshot_total_volume = total_volume
    state.prev_snapshot_cumulative_delta = float(delta_profile.sum())
    state.prev_snapshot_price = state.last_price
    state.prev_va_width = (value_area_high - value_area_low) / state.tick_size
    state.poc_history.append(poc_price)
    if len(state.poc_history) > POC_VELOCITY_SNAPSHOTS:
        state.poc_history.pop(0)
    return VolumeProfileResult(
        symbol=state.symbol,
        date=state.date,
        bar_num=state.bar_num,
        tick_size=state.tick_size,
        range_ticks=state.range_ticks,
        price_levels=price_levels,
        volume_at_level=state.profile.copy(),
        up_volume_at_level=state.up_profile.copy(),
        down_volume_at_level=state.down_profile.copy(),
        classified_delta_at_level=delta_profile.copy(),
        poc_price=poc_price,
        poc_volume=poc_volume,
        value_area_low=value_area_low,
        value_area_high=value_area_high,
        total_volume=total_volume,
        n_bars=state.n_bars,
        extensions=state.extensions,
        **derived,
        **extended,
    )


class VolumeProfileEngine:
    """Convenience engine shared by live and historical ordered tick streams."""

    def __init__(self, tick_size: float = 0.25, range_ticks: int = DEFAULT_RANGE_TICKS):
        require_volume_profile(tick_size > 0.0, "tick_size must be positive")
        require_volume_profile(range_ticks > 0, "range_ticks must be positive")
        self.tick_size = tick_size
        self.range_ticks = range_ticks
        self.state: Optional[VolumeProfileState] = None

    def update(self, tick: TickLike) -> None:
        """Update the current session, resetting automatically when required."""
        tick_session = session_key(tick.date, tick.time_s)
        if (
            self.state is None
            or tick.symbol != self.state.symbol
            or tick_session != self.state.session_key
        ):
            self.state = initialize_profile(tick, self.tick_size, self.range_ticks)
        update_profile(self.state, tick)

    def snapshot(self) -> VolumeProfileResult:
        """Return a snapshot after at least one tick has been processed."""
        require_volume_profile(self.state is not None, "Cannot snapshot before the first tick.")
        return snapshot_profile(self.state)
