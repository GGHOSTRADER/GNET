"""Pure first-touch replay for long ES trades.

This is a research price-path proxy, not an exchange execution simulator.
Targets fill at the limit price; stops fill at the first observed trade price
at or below the stop (possibly worse after a gap). A time exit uses the first
observed trade price at or after its deadline. Commission is applied by the
caller, and bid/ask spread, queue position, and slippage are not inferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import isfinite

import numpy as np


ES_TICK_SIZE = 0.25
ES_POINT_VALUE = 50.0


@dataclass(frozen=True)
class ExitPolicy:
    profit_ticks: int
    stop_ticks: int
    max_hold_seconds: int | None

    def __post_init__(self) -> None:
        if self.profit_ticks < 1 or self.stop_ticks < 1:
            raise ValueError("profit and stop must each be at least one tick")
        if self.max_hold_seconds is not None and self.max_hold_seconds < 1:
            raise ValueError("time barrier must be positive")

    @property
    def policy_id(self) -> str:
        hold = "none" if self.max_hold_seconds is None else str(self.max_hold_seconds)
        return f"pt{self.profit_ticks}_sl{self.stop_ticks}_h{hold}"


@dataclass(frozen=True)
class ExitResult:
    reason: str
    timestamp: np.datetime64 | None
    exit_price: float | None
    gross_pnl_usd: float | None
    net_pnl_usd: float | None
    ticks_observed: int
    time_exit_delay_seconds: float | None


def policy_grid(
    profit_ticks: tuple[int, ...],
    stop_ticks: tuple[int, ...],
    hold_seconds: tuple[int, ...],
) -> tuple[ExitPolicy, ...]:
    """Return a deterministic grid of complete three-barrier policies."""
    if not profit_ticks or not stop_ticks or not hold_seconds:
        raise ValueError("each policy dimension must contain at least one value")
    return tuple(
        ExitPolicy(profit, stop, hold)
        for profit, stop, hold in product(
            sorted(set(profit_ticks)), sorted(set(stop_ticks)), sorted(set(hold_seconds))
        )
    )


def replay_long(
    timestamps: np.ndarray,
    prices: np.ndarray,
    *,
    entry_time: np.datetime64,
    entry_price: float,
    policy: ExitPolicy,
    round_trip_cost_usd: float = 6.48,
    include_entry_timestamp: bool = True,
    max_time_exit_delay_seconds: float | None = None,
) -> ExitResult:
    """Replay one long from the entry-bar open, respecting tick row order.

    Tick timestamps may tie. Their original file order resolves price first
    touch within a timestamp. At the time deadline, the time barrier takes
    precedence over a price observation with that same timestamp.
    """
    times = np.asarray(timestamps, dtype="datetime64[ns]")
    values = np.asarray(prices, dtype=np.float64)
    if times.ndim != 1 or values.ndim != 1 or len(times) != len(values):
        raise ValueError("tick times and prices must be equal-length one-dimensional arrays")
    if len(times) and np.any(times[1:] < times[:-1]):
        raise ValueError("tick timestamps must be nondecreasing")
    if not isfinite(entry_price) or entry_price <= 0:
        raise ValueError("entry price must be finite and positive")
    if not isfinite(round_trip_cost_usd) or round_trip_cost_usd < 0:
        raise ValueError("round-trip cost must be finite and nonnegative")
    if max_time_exit_delay_seconds is not None and (
        not isfinite(max_time_exit_delay_seconds) or max_time_exit_delay_seconds < 0
    ):
        raise ValueError("maximum time-exit delay must be finite and nonnegative")
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("tick prices must be finite and positive")

    start = np.datetime64(entry_time, "ns")
    side = "left" if include_entry_timestamp else "right"
    first = int(np.searchsorted(times, start, side=side))
    deadline = (
        None if policy.max_hold_seconds is None
        else start + np.timedelta64(policy.max_hold_seconds, "s")
    )
    target = entry_price + policy.profit_ticks * ES_TICK_SIZE
    stop = entry_price - policy.stop_ticks * ES_TICK_SIZE

    for index in range(first, len(values)):
        timestamp = times[index]
        price = float(values[index])
        if deadline is not None and timestamp >= deadline:
            delay = float((timestamp - deadline) / np.timedelta64(1, "s"))
            if (
                max_time_exit_delay_seconds is not None
                and delay > max_time_exit_delay_seconds
            ):
                return ExitResult(
                    "unavailable_time", timestamp, None, None, None,
                    index - first + 1, delay,
                )
            reason, exit_price = "time", price
        elif price >= target:
            reason, exit_price, delay = "profit", target, None
        elif price <= stop:
            reason, exit_price, delay = "loss", min(price, stop), None
        else:
            continue
        gross = (exit_price - entry_price) * ES_POINT_VALUE
        return ExitResult(
            reason=reason,
            timestamp=timestamp,
            exit_price=exit_price,
            gross_pnl_usd=gross,
            net_pnl_usd=gross - round_trip_cost_usd,
            ticks_observed=index - first + 1,
            time_exit_delay_seconds=delay,
        )

    return ExitResult("censored", None, None, None, None, max(0, len(values) - first), None)


def replay_long_grid(
    timestamps: np.ndarray,
    prices: np.ndarray,
    *,
    entry_time: np.datetime64,
    entry_price: float,
    policies: tuple[ExitPolicy, ...],
    round_trip_cost_usd: float = 6.48,
    include_entry_timestamp: bool = True,
    max_time_exit_delay_seconds: float | None = None,
) -> tuple[ExitResult, ...]:
    """Replay a policy grid with one threshold scan per distinct price level."""
    if not policies:
        raise ValueError("at least one exit policy is required")
    times = np.asarray(timestamps, dtype="datetime64[ns]")
    values = np.asarray(prices, dtype=np.float64)
    if times.ndim != 1 or values.ndim != 1 or len(times) != len(values):
        raise ValueError("tick times and prices must be equal-length one-dimensional arrays")
    if len(times) and np.any(times[1:] < times[:-1]):
        raise ValueError("tick timestamps must be nondecreasing")
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("tick prices must be finite and positive")
    if not isfinite(entry_price) or entry_price <= 0:
        raise ValueError("entry price must be finite and positive")
    if not isfinite(round_trip_cost_usd) or round_trip_cost_usd < 0:
        raise ValueError("round-trip cost must be finite and nonnegative")
    if max_time_exit_delay_seconds is not None and (
        not isfinite(max_time_exit_delay_seconds) or max_time_exit_delay_seconds < 0
    ):
        raise ValueError("maximum time-exit delay must be finite and nonnegative")

    start = np.datetime64(entry_time, "ns")
    first = int(np.searchsorted(
        times, start, side="left" if include_entry_timestamp else "right"
    ))
    times = times[first:]
    values = values[first:]
    sentinel = len(values)
    target_hits: dict[int, int] = {}
    stop_hits: dict[int, int] = {}
    time_hits: dict[int, int] = {}
    for target_ticks in {policy.profit_ticks for policy in policies}:
        positions = np.flatnonzero(values >= entry_price + target_ticks * ES_TICK_SIZE)
        target_hits[target_ticks] = int(positions[0]) if len(positions) else sentinel
    for stop_ticks in {policy.stop_ticks for policy in policies}:
        positions = np.flatnonzero(values <= entry_price - stop_ticks * ES_TICK_SIZE)
        stop_hits[stop_ticks] = int(positions[0]) if len(positions) else sentinel
    for hold in {policy.max_hold_seconds for policy in policies}:
        if hold is not None:
            deadline = start + np.timedelta64(hold, "s")
            time_hits[hold] = int(np.searchsorted(times, deadline, side="left"))

    results: list[ExitResult] = []
    for policy in policies:
        profit_index = target_hits[policy.profit_ticks]
        loss_index = stop_hits[policy.stop_ticks]
        time_index = (
            sentinel if policy.max_hold_seconds is None
            else time_hits[policy.max_hold_seconds]
        )
        index = min(profit_index, loss_index, time_index)
        if index == sentinel:
            results.append(ExitResult("censored", None, None, None, None, sentinel, None))
            continue
        timestamp = times[index]
        if time_index == index:
            reason = "time"
            exit_price = float(values[index])
            deadline = start + np.timedelta64(policy.max_hold_seconds, "s")
            delay = float((timestamp - deadline) / np.timedelta64(1, "s"))
            if (
                max_time_exit_delay_seconds is not None
                and delay > max_time_exit_delay_seconds
            ):
                results.append(ExitResult(
                    "unavailable_time", timestamp, None, None, None,
                    index + 1, delay,
                ))
                continue
        elif profit_index == index:
            reason = "profit"
            exit_price = entry_price + policy.profit_ticks * ES_TICK_SIZE
            delay = None
        else:
            reason = "loss"
            exit_price = min(
                float(values[index]), entry_price - policy.stop_ticks * ES_TICK_SIZE
            )
            delay = None
        gross = (exit_price - entry_price) * ES_POINT_VALUE
        results.append(ExitResult(
            reason, timestamp, exit_price, gross,
            gross - round_trip_cost_usd, index + 1, delay,
        ))
    return tuple(results)
