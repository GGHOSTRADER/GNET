from datetime import datetime, timedelta

import numpy as np
import pytest

from training_mlp.validation.event_intervals import (
    EventIntervalError,
    EventIntervals,
    embargo_after_test,
    purge_overlaps,
)


def _times(count: int):
    start = datetime(2026, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def test_event_intervals_require_real_chronological_event_ends():
    starts = _times(3)
    with pytest.raises(EventIntervalError, match="at or after"):
        EventIntervals.from_arrays(starts, [starts[0], starts[0], starts[2]])
    with pytest.raises(EventIntervalError, match="chronological"):
        EventIntervals.from_arrays(starts[::-1], starts[::-1])


def test_purge_removes_all_three_closed_interval_overlap_cases():
    starts = _times(7)
    ends = starts.copy()
    ends[0] = starts[3]  # Ends inside test interval.
    ends[1] = starts[5]  # Envelops the complete test interval.
    events = EventIntervals.from_arrays(starts, ends)

    survivors, purged = purge_overlaps(events, [0, 1, 3, 6], [3, 4])

    assert np.array_equal(survivors, [6])
    assert np.array_equal(purged, [0, 1, 3])


def test_embargo_is_applied_after_each_nonadjacent_test_block():
    result = embargo_after_test([1, 2, 6], n_samples=10, embargo_pct=0.2)
    assert np.array_equal(result, [3, 4, 7, 8])
