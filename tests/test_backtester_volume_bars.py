import numpy as np
import pytest

from backtester.bars import aggregate
from backtester.config import BarSpec
from backtester.signals import generate_signals


def bars_for(volumes, size, times=None):
    length = len(volumes)
    if times is None:
        times = np.arange(length, dtype=np.int64)
    return aggregate(times, 6000 + np.arange(length) * .25, np.asarray(volumes),
                     BarSpec("volume", size), 0, 100, 20)


def test_volume_threshold_overshoot_no_split_or_carry():
    bars = bars_for([3, 8, 2, 7, 1, 4], 10)
    assert [b["volume"] for b in bars] == [11, 10, 4]
    assert [b["tick_count"] for b in bars] == [2, 3, 1]
    assert [b["complete"] for b in bars] == [True, True, False]
    assert [(b["first_event"], b["last_event"]) for b in bars] == [(20, 21), (22, 24), (25, 25)]
    assert bars[0]["open"] == 6000 and bars[0]["close"] == 6000.25


def test_large_tick_and_zero_volume_never_invent_ticks():
    bars = bars_for([0, 25, 0, 0, 10], 10)
    assert [b["volume"] for b in bars] == [25, 10]
    assert [b["tick_count"] for b in bars] == [2, 3]
    assert all(b["complete"] for b in bars)
    zero = bars_for([0, 0], 10)
    assert len(zero) == 1 and not zero[0]["complete"]


def test_volume_signal_cannot_enter_on_threshold_event_even_same_timestamp():
    class AlwaysEnter:
        def on_bar(self, bar):
            return True
    times = np.zeros(4, dtype=np.int64)
    bars = bars_for([5, 5, 10, 1], 10, times)
    signals = generate_signals(bars, BarSpec("volume", 10), times, 20, AlwaysEnter())
    assert [s["entry_event"] for s in signals] == [22, 23]
    assert all(s["entry_event"] > s["available_after_event"] for s in signals)


def test_volume_partial_not_carried_across_sessions():
    assert not bars_for([6], 10)[0]["complete"]
    assert not bars_for([6], 10)[0]["complete"]


def test_volume_empty_and_parameter_validation():
    assert bars_for([], 10) == []
    with pytest.raises(ValueError):
        BarSpec("volume", 0)
    with pytest.raises(ValueError):
        BarSpec("volume", 1.5)
