from collections import Counter
from datetime import datetime, timedelta

import numpy as np

from training_mlp.validation import (
    CombinatorialPurgedCrossValidation,
    EventIntervals,
)


def _events(count: int) -> EventIntervals:
    origin = datetime(2026, 1, 1)
    starts = [origin + timedelta(days=index) for index in range(count)]
    return EventIntervals.from_arrays(starts, starts)


def test_cpcv_generates_all_combinations_and_complete_path_assignments():
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=4, n_test_groups=2, embargo_pct=0.0
    )
    splits = list(splitter.split(_events(12)))

    assert splitter.get_n_splits() == 6
    assert splitter.n_backtest_paths == 3
    assert len(splits) == 6
    appearances = Counter(group for split in splits for group in split.test_groups)
    assert appearances == {0: 3, 1: 3, 2: 3, 3: 3}
    for group in range(4):
        assigned = sorted(
            split.path_assignments[group]
            for split in splits
            if group in split.test_groups
        )
        assert assigned == [0, 1, 2]


def test_cpcv_removes_post_test_embargo_from_training():
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=3, n_test_groups=1, embargo_pct=1 / 6
    )
    first = next(splitter.split(_events(6)))

    assert np.array_equal(first.test_indices, [0, 1])
    assert np.array_equal(first.embargoed_indices, [2])
    assert np.array_equal(first.train_indices, [3, 4, 5])


def test_cpcv_purges_training_label_that_overlaps_test_group():
    origin = datetime(2026, 1, 1)
    starts = [origin + timedelta(days=index) for index in range(6)]
    ends = starts.copy()
    ends[1] = starts[2]
    events = EventIntervals.from_arrays(starts, ends)
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=3, n_test_groups=1, embargo_pct=0.0
    )
    splits = list(splitter.split(events))
    middle_group_split = splits[1]

    assert np.array_equal(middle_group_split.test_indices, [2, 3])
    assert 1 in middle_group_split.purged_indices
    assert 1 not in middle_group_split.train_indices
