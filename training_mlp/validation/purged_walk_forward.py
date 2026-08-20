"""Purged expanding walk-forward validation using event-end timestamps."""

from __future__ import annotations

import numpy as np

from .event_intervals import (
    EventIntervalError,
    EventIntervals,
    ValidationSplit,
    embargo_after_test,
    purge_overlaps,
)


class PurgedWalkForward:
    """Generate chronological expanding-window splits with interval purging.

    Training always precedes validation, matching live retraining. López de
    Prado's post-test embargo is reported for auditability but cannot remove
    rows from that same fold's past-only training set. Purging remains active
    and removes past events whose labels extend into validation.
    """

    def __init__(self, n_splits: int = 5, embargo_pct: float = 0.01):
        if n_splits < 1:
            raise EventIntervalError("n_splits must be at least 1")
        if not 0.0 <= embargo_pct < 1.0:
            raise EventIntervalError("embargo_pct must satisfy 0 <= embargo_pct < 1")
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct

    def split(self, events: EventIntervals):
        """Yield expanding train/future-validation splits in chronological order."""
        if len(events) < self.n_splits + 1:
            raise EventIntervalError(
                "number of events must be at least n_splits + 1"
            )
        groups = np.array_split(np.arange(len(events), dtype=np.int64), self.n_splits + 1)
        for split_id in range(self.n_splits):
            test_indices = groups[split_id + 1]
            candidates = np.arange(test_indices[0], dtype=np.int64)
            train_indices, purged_indices = purge_overlaps(
                events, candidates, test_indices
            )
            embargoed_indices = embargo_after_test(
                test_indices,
                n_samples=len(events),
                embargo_pct=self.embargo_pct,
            )
            if train_indices.size == 0:
                raise EventIntervalError(
                    f"split {split_id} has no training events after purging"
                )
            yield ValidationSplit(
                split_id=split_id,
                train_indices=train_indices,
                test_indices=test_indices,
                purged_indices=purged_indices,
                embargoed_indices=embargoed_indices,
                test_groups=(split_id + 1,),
            )

    def get_n_splits(self) -> int:
        return self.n_splits


def purged_chronological_holdout(
    events: EventIntervals,
    *,
    test_size: float = 0.10,
) -> ValidationSplit:
    """Reserve the chronological tail and purge training labels overlapping it."""
    if not 0.0 < test_size < 1.0:
        raise EventIntervalError("test_size must satisfy 0 < test_size < 1")
    n_test = max(1, int(len(events) * test_size))
    test_start = len(events) - n_test
    if test_start < 1:
        raise EventIntervalError("test_size leaves no chronological training events")
    test_indices = np.arange(test_start, len(events), dtype=np.int64)
    candidates = np.arange(test_start, dtype=np.int64)
    train_indices, purged_indices = purge_overlaps(
        events, candidates, test_indices
    )
    if train_indices.size == 0:
        raise EventIntervalError("holdout has no training events after purging")
    return ValidationSplit(
        split_id=0,
        train_indices=train_indices,
        test_indices=test_indices,
        purged_indices=purged_indices,
        embargoed_indices=np.empty(0, dtype=np.int64),
    )
