from datetime import datetime, timedelta

import numpy as np

from training_mlp.validation import (
    EventIntervals,
    PurgedWalkForward,
    purged_chronological_holdout,
)


def test_walk_forward_is_expanding_past_only_and_purges_t1_overlap():
    origin = datetime(2026, 1, 1)
    starts = [origin + timedelta(days=index) for index in range(12)]
    ends = starts.copy()
    ends[2] = starts[5]  # This training label reaches first validation group.
    events = EventIntervals.from_arrays(starts, ends)

    splits = list(PurgedWalkForward(n_splits=2, embargo_pct=0.1).split(events))

    assert len(splits) == 2
    assert np.array_equal(splits[0].test_indices, [4, 5, 6, 7])
    assert np.array_equal(splits[0].train_indices, [0, 1, 3])
    assert np.array_equal(splits[0].purged_indices, [2])
    assert splits[0].train_indices.max() < splits[0].test_indices.min()
    assert np.array_equal(splits[1].test_indices, [8, 9, 10, 11])
    assert np.array_equal(splits[1].train_indices, np.arange(8))
    assert splits[1].train_indices.max() < splits[1].test_indices.min()


def test_walk_forward_reports_post_validation_embargo_for_audit():
    origin = datetime(2026, 1, 1)
    starts = [origin + timedelta(days=index) for index in range(12)]
    events = EventIntervals.from_arrays(starts, starts)

    first = next(PurgedWalkForward(n_splits=2, embargo_pct=0.1).split(events))

    assert np.array_equal(first.embargoed_indices, [8])
    assert not np.intersect1d(first.train_indices, first.embargoed_indices).size


def test_chronological_holdout_purges_training_label_crossing_test_boundary():
    origin = datetime(2026, 1, 1)
    starts = [origin + timedelta(days=index) for index in range(10)]
    ends = starts.copy()
    ends[7] = starts[8]
    events = EventIntervals.from_arrays(starts, ends)

    split = purged_chronological_holdout(events, test_size=0.2)

    assert np.array_equal(split.test_indices, [8, 9])
    assert np.array_equal(split.purged_indices, [7])
    assert np.array_equal(split.train_indices, np.arange(7))
