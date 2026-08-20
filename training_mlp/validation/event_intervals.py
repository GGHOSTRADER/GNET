"""Shared event-interval purging primitives.

Each observation owns an information interval [start_time, end_time]. A
training observation is purged whenever that closed interval overlaps any
validation interval. This is the central leakage rule used by both validation
schemes; row-distance gaps are intentionally unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


class EventIntervalError(ValueError):
    """Raised when event intervals or split parameters are invalid."""


def _datetime_ns(values: Iterable[object], name: str) -> np.ndarray:
    converted = pd.to_datetime(pd.Index(values), errors="coerce")
    if converted.isna().any():
        raise EventIntervalError(f"{name} contains missing or invalid timestamps")
    if converted.tz is not None:
        converted = converted.tz_convert("UTC").tz_localize(None)
    return converted.to_numpy(dtype="datetime64[ns]").astype(np.int64)


@dataclass(frozen=True, slots=True)
class EventIntervals:
    """Chronologically ordered observation start and event-end timestamps."""

    starts_ns: np.ndarray
    ends_ns: np.ndarray

    @classmethod
    def from_arrays(
        cls,
        starts: Iterable[object],
        ends: Iterable[object],
    ) -> "EventIntervals":
        starts_ns = _datetime_ns(starts, "starts")
        ends_ns = _datetime_ns(ends, "ends")
        if len(starts_ns) != len(ends_ns):
            raise EventIntervalError("starts and ends must have equal length")
        if len(starts_ns) < 2:
            raise EventIntervalError("at least two event intervals are required")
        if np.any(starts_ns[1:] < starts_ns[:-1]):
            raise EventIntervalError("event starts must be chronological")
        if np.any(ends_ns < starts_ns):
            raise EventIntervalError("every event end must be at or after its start")
        starts_ns.setflags(write=False)
        ends_ns.setflags(write=False)
        return cls(starts_ns=starts_ns, ends_ns=ends_ns)

    def __len__(self) -> int:
        return len(self.starts_ns)


@dataclass(frozen=True, slots=True)
class ValidationSplit:
    """One leakage-controlled train/test split plus full audit metadata."""

    split_id: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    purged_indices: np.ndarray
    embargoed_indices: np.ndarray
    test_groups: tuple[int, ...] = ()
    path_assignments: Mapping[int, int] = field(default_factory=dict)


def _normalized_indices(indices: Iterable[int], n_samples: int, name: str) -> np.ndarray:
    result = np.asarray(list(indices), dtype=np.int64)
    if result.ndim != 1:
        raise EventIntervalError(f"{name} must be one-dimensional")
    if result.size and (result.min() < 0 or result.max() >= n_samples):
        raise EventIntervalError(f"{name} contains an out-of-range index")
    return np.unique(result)


def _merged_test_intervals(
    events: EventIntervals,
    test_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    ordered = test_indices[np.argsort(events.starts_ns[test_indices], kind="stable")]
    merged_starts: list[int] = []
    merged_ends: list[int] = []
    for index in ordered:
        start = int(events.starts_ns[index])
        end = int(events.ends_ns[index])
        if merged_ends and start <= merged_ends[-1]:
            merged_ends[-1] = max(merged_ends[-1], end)
        else:
            merged_starts.append(start)
            merged_ends.append(end)
    return np.asarray(merged_starts), np.asarray(merged_ends)


def purge_overlaps(
    events: EventIntervals,
    candidate_indices: Iterable[int],
    test_indices: Iterable[int],
) -> tuple[np.ndarray, np.ndarray]:
    """Return surviving candidates and candidates overlapping validation events."""
    candidates = _normalized_indices(candidate_indices, len(events), "candidate_indices")
    tests = _normalized_indices(test_indices, len(events), "test_indices")
    if tests.size == 0:
        raise EventIntervalError("test_indices cannot be empty")
    test_starts, test_ends = _merged_test_intervals(events, tests)
    first_possible = np.searchsorted(
        test_ends, events.starts_ns[candidates], side="left"
    )
    in_range = first_possible < len(test_starts)
    overlaps = np.zeros(len(candidates), dtype=bool)
    positions = np.flatnonzero(in_range)
    overlaps[positions] = (
        test_starts[first_possible[positions]] <= events.ends_ns[candidates[positions]]
    )
    return candidates[~overlaps], candidates[overlaps]


def contiguous_blocks(indices: Iterable[int], n_samples: int) -> list[tuple[int, int]]:
    """Return inclusive index blocks from an arbitrary index collection."""
    normalized = _normalized_indices(indices, n_samples, "indices")
    if normalized.size == 0:
        return []
    split_positions = np.where(np.diff(normalized) > 1)[0] + 1
    return [
        (int(block[0]), int(block[-1]))
        for block in np.split(normalized, split_positions)
    ]


def embargo_after_test(
    test_indices: Iterable[int],
    *,
    n_samples: int,
    embargo_pct: float,
) -> np.ndarray:
    """Return López de Prado observation-count embargoes after test blocks."""
    if not 0.0 <= embargo_pct < 1.0:
        raise EventIntervalError("embargo_pct must satisfy 0 <= embargo_pct < 1")
    embargo_size = int(n_samples * embargo_pct)
    if embargo_size == 0:
        return np.empty(0, dtype=np.int64)
    embargoed: list[int] = []
    for _, block_end in contiguous_blocks(test_indices, n_samples):
        start = block_end + 1
        stop = min(start + embargo_size, n_samples)
        embargoed.extend(range(start, stop))
    return np.unique(np.asarray(embargoed, dtype=np.int64))
