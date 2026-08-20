"""Combinatorial Purged Cross-Validation with backtest-path assignments."""

from __future__ import annotations

from itertools import combinations
from math import comb

import numpy as np

from .event_intervals import (
    EventIntervalError,
    EventIntervals,
    ValidationSplit,
    embargo_after_test,
    purge_overlaps,
)


class CombinatorialPurgedCrossValidation:
    """Generate CPCV(N, k) splits and deterministic path membership.

    Each of N chronological groups appears in C(N-1, k-1) test combinations.
    Its successive appearances are assigned to distinct path IDs, allowing
    out-of-sample predictions to be assembled into that many complete paths.
    """

    def __init__(
        self,
        n_groups: int = 6,
        n_test_groups: int = 2,
        embargo_pct: float = 0.01,
    ):
        if n_groups < 2:
            raise EventIntervalError("n_groups must be at least 2")
        if not 1 <= n_test_groups < n_groups:
            raise EventIntervalError(
                "n_test_groups must satisfy 1 <= n_test_groups < n_groups"
            )
        if not 0.0 <= embargo_pct < 1.0:
            raise EventIntervalError("embargo_pct must satisfy 0 <= embargo_pct < 1")
        self.n_groups = n_groups
        self.n_test_groups = n_test_groups
        self.embargo_pct = embargo_pct

    @property
    def n_backtest_paths(self) -> int:
        """Number of complete CPCV paths: C(N-1, k-1)."""
        return comb(self.n_groups - 1, self.n_test_groups - 1)

    def get_n_splits(self) -> int:
        return comb(self.n_groups, self.n_test_groups)

    def split(self, events: EventIntervals):
        """Yield all purged/embargoed combinatorial train/test partitions."""
        if len(events) < self.n_groups:
            raise EventIntervalError("number of events must be at least n_groups")
        groups = np.array_split(np.arange(len(events), dtype=np.int64), self.n_groups)
        all_indices = np.arange(len(events), dtype=np.int64)
        group_occurrences = np.zeros(self.n_groups, dtype=np.int64)

        for split_id, selected in enumerate(
            combinations(range(self.n_groups), self.n_test_groups)
        ):
            test_indices = np.concatenate([groups[group] for group in selected])
            candidate_mask = np.ones(len(events), dtype=bool)
            candidate_mask[test_indices] = False
            candidates = all_indices[candidate_mask]
            surviving, purged = purge_overlaps(events, candidates, test_indices)
            embargoed = embargo_after_test(
                test_indices,
                n_samples=len(events),
                embargo_pct=self.embargo_pct,
            )
            train_indices = np.setdiff1d(
                surviving, embargoed, assume_unique=True
            )
            path_assignments = {
                group: int(group_occurrences[group]) for group in selected
            }
            for group in selected:
                group_occurrences[group] += 1
            if train_indices.size == 0:
                raise EventIntervalError(
                    f"split {split_id} has no training events after purging and embargo"
                )
            yield ValidationSplit(
                split_id=split_id,
                train_indices=train_indices,
                test_indices=test_indices,
                purged_indices=purged,
                embargoed_indices=np.intersect1d(
                    surviving, embargoed, assume_unique=True
                ),
                test_groups=tuple(selected),
                path_assignments=path_assignments,
            )
