"""
tests/test_volume_profile.py
=============================

Unit tests for volume profile pure domain functions.
No Redis, no TCP, no I/O — pure function tests only.

Files tested
------------
  feat_files/volume_profile.py  -- _find_poc + _find_value_area
                                   _init_session + _update + _snapshot

What is tested
--------------
The volume profile is a stateful accumulator. These tests verify:
  - POC always points to the highest volume price level
  - Value area encloses at least 70% of session volume
  - Each tick increments the correct profile index (O(1) update)
  - Grid extends correctly when price breaks above or below bounds
  - Session resets cleanly on date change

Test Index
----------
  [01] test_find_poc_returns_highest_volume_level  -- POC is argmax of profile
  [02] test_find_value_area_covers_70pct           -- VA encloses >= 70% of volume
  [03] test_find_value_area_single_level           -- single level covers 100%
  [04] test_profile_increments_on_each_tick        -- volume accumulates at correct index
  [05] test_profile_total_volume_is_correct        -- total_volume matches sum of tick volumes
  [06] test_profile_extends_grid_above_ceiling     -- extensions counter increases on upside break
  [07] test_profile_extends_grid_below_floor       -- extensions counter increases on downside break
  [08] test_profile_session_resets_on_date_change  -- n_bars resets to 1 on new date
  [09] test_snapshot_price_levels_are_tick_spaced  -- price_levels increment by tick_size
  [10] test_snapshot_arrays_are_parallel           -- price_levels and volume_at_level same length
  [11] test_poc_concentration_single_level         -- single-level profile has concentration == 1.0
  [12] test_poc_distance_sign_and_scale            -- poc_distance is (price-poc)/tick_size, signed
  [13] test_va_position_within_value_area          -- va_position in [0,1] when price inside VA
  [14] test_vol_above_poc_ratio_all_above          -- ratio == 1.0 when all extra volume is above POC
  [15] test_profile_entropy_zero_for_single_level  -- single level has zero entropy (no spread)
  [16] test_poc_migration_zero_on_first_snapshot   -- poc_migration == 0.0 with no prior snapshot
  [17] test_poc_migration_tracks_poc_shift         -- poc_migration reflects POC shift between snapshots
  [18] test_snapshot_gated_by_snapshot_interval    -- stream_volume_profile yields once per bar window
"""

import pytest
import numpy as np
from dataclasses import dataclass

from feat_files.volume_profile import (
    _find_poc,
    _find_value_area,
    _init_session,
    _update,
    _snapshot,
    stream_volume_profile,
)


# ============================================================
# Helper
# ============================================================

@dataclass(frozen=True)
class TickStub:
    """Minimal tick-like object. high == low (single price point)."""
    symbol:  str
    date:    int
    time_s:  int
    high:    float
    low:     float
    up:      int
    down:    int
    bar_num: int


def make_stub(price: float = 5000.0, bar_num: int = 1,
              volume: int = 100, date: int = 1260125) -> TickStub:
    return TickStub(
        symbol="@ES", date=date, time_s=36000,
        high=price, low=price, up=volume, down=0, bar_num=bar_num,
    )


def init_and_update(*stubs, tick_size=0.25, range_ticks=40):
    """Helper: init session on first stub, update with all stubs, return state."""
    state = _init_session(stubs[0], tick_size=tick_size, range_ticks=range_ticks)
    for s in stubs:
        _update(state, s)
    return state


# ============================================================
# Tests
# ============================================================

# [01]
def test_find_poc_returns_highest_volume_level():
    """Positive — POC is the price level with maximum accumulated volume."""
    levels  = np.array([100.0, 100.25, 100.50])
    profile = np.array([200.0, 800.0, 300.0])
    poc_price, poc_volume = _find_poc(profile, levels)
    assert poc_price  == pytest.approx(100.25)
    assert poc_volume == pytest.approx(800.0)


# [02]
def test_find_value_area_covers_70pct():
    """Positive — value area boundaries enclose at least 70% of total volume."""
    levels  = np.array([100.0, 100.25, 100.50, 100.75, 101.0])
    profile = np.array([50.0, 400.0, 400.0, 50.0, 100.0])
    val, vah = _find_value_area(profile, levels)
    total  = profile.sum()
    inside = profile[(levels >= val) & (levels <= vah)].sum()
    assert inside / total >= 0.70


# [03]
def test_find_value_area_single_level():
    """Positive — single price level has 100% of volume, val == vah."""
    levels  = np.array([5000.0])
    profile = np.array([500.0])
    val, vah = _find_value_area(profile, levels)
    assert val == pytest.approx(5000.0)
    assert vah == pytest.approx(5000.0)


# [04]
def test_profile_increments_on_each_tick():
    """Positive — two ticks at same price accumulate their volumes at that level."""
    t1 = make_stub(price=5000.0, bar_num=1, volume=100)
    t2 = make_stub(price=5000.0, bar_num=2, volume=200)
    state = init_and_update(t1, t2)
    vp = _snapshot(state)
    poc_price, poc_volume = _find_poc(vp.volume_at_level, vp.price_levels)
    assert poc_price  == pytest.approx(5000.0, abs=0.01)
    assert poc_volume == pytest.approx(300.0)


# [05]
def test_profile_total_volume_is_correct():
    """Positive — total_volume in snapshot equals sum of all tick volumes."""
    t1 = make_stub(price=5000.0,  bar_num=1, volume=100)
    t2 = make_stub(price=5000.25, bar_num=2, volume=250)
    t3 = make_stub(price=5000.50, bar_num=3, volume=150)
    state = init_and_update(t1, t2, t3)
    vp = _snapshot(state)
    assert vp.total_volume == pytest.approx(500.0)


# [06]
def test_profile_extends_grid_above_ceiling():
    """Positive — extensions counter increases when price breaks above ceiling."""
    t1 = make_stub(price=5000.0, bar_num=1)
    state = _init_session(t1, tick_size=0.25, range_ticks=4)
    _update(state, t1)
    ext_before = state.extensions
    _update(state, make_stub(price=5010.0, bar_num=2))
    assert state.extensions > ext_before


# [07]
def test_profile_extends_grid_below_floor():
    """Positive — extensions counter increases when price breaks below floor."""
    t1 = make_stub(price=5000.0, bar_num=1)
    state = _init_session(t1, tick_size=0.25, range_ticks=4)
    _update(state, t1)
    ext_before = state.extensions
    _update(state, make_stub(price=4990.0, bar_num=2))
    assert state.extensions > ext_before


# [08]
def test_profile_session_resets_on_date_change():
    """Positive — n_bars resets to 1 and date updates when session re-initialises."""
    t1 = make_stub(price=5000.0, bar_num=1, date=1260125)
    state = _init_session(t1, tick_size=0.25, range_ticks=40)
    _update(state, t1)
    assert state.n_bars == 1

    t2 = make_stub(price=5000.0, bar_num=1, date=1260126)
    state = _init_session(t2, tick_size=0.25, range_ticks=40)
    _update(state, t2)
    assert state.n_bars == 1
    assert state.date   == 1260126


# [09]
def test_snapshot_price_levels_are_tick_spaced():
    """Positive — consecutive price_levels differ by exactly tick_size."""
    tick_size = 0.25
    t = make_stub(price=5000.0, bar_num=1)
    state = _init_session(t, tick_size=tick_size, range_ticks=10)
    _update(state, t)
    vp = _snapshot(state)
    diffs = np.diff(vp.price_levels)
    assert np.allclose(diffs, tick_size, atol=1e-9)


# [10]
def test_snapshot_arrays_are_parallel():
    """Positive — price_levels and volume_at_level have the same length."""
    t = make_stub(price=5000.0, bar_num=1)
    state = _init_session(t, tick_size=0.25, range_ticks=40)
    _update(state, t)
    vp = _snapshot(state)
    assert len(vp.price_levels) == len(vp.volume_at_level)


# [11]
def test_poc_concentration_single_level():
    """Positive — a single occupied level has 100% of volume at the POC."""
    t = make_stub(price=5000.0, bar_num=1, volume=100)
    state = init_and_update(t)
    vp = _snapshot(state)
    assert vp.poc_concentration == pytest.approx(1.0)


# [12]
def test_poc_distance_sign_and_scale():
    """Positive — poc_distance is (current_price - poc_price) / tick_size."""
    t1 = make_stub(price=5000.0,  bar_num=1, volume=200)  # heavy -> becomes POC
    t2 = make_stub(price=5000.50, bar_num=2, volume=50)   # last tick -> current_price
    state = init_and_update(t1, t2, tick_size=0.25)
    vp = _snapshot(state)
    assert vp.poc_price == pytest.approx(5000.0, abs=0.01)
    assert vp.poc_distance == pytest.approx(2.0)  # (5000.50 - 5000.0) / 0.25


# [13]
def test_va_position_within_value_area():
    """Positive — va_position falls in [0, 1] when current_price is inside the value area."""
    t1 = make_stub(price=5000.00, bar_num=1, volume=400)  # -> becomes VAL and POC
    t2 = make_stub(price=5000.50, bar_num=2, volume=400)  # -> becomes VAH
    t3 = make_stub(price=5000.25, bar_num=3, volume=60)   # last tick -> current_price (midpoint)
    state = init_and_update(t1, t2, t3, tick_size=0.25)
    vp = _snapshot(state)
    assert vp.value_area_low  == pytest.approx(5000.00)
    assert vp.value_area_high == pytest.approx(5000.50)
    assert vp.va_position == pytest.approx(0.5)


# [14]
def test_vol_above_poc_ratio_when_extra_volume_above():
    """Positive — vol_above_poc_ratio equals the fraction of volume above the POC level."""
    t1 = make_stub(price=5000.00, bar_num=1, volume=100)  # POC
    t2 = make_stub(price=5000.50, bar_num=2, volume=50)   # above POC
    state = init_and_update(t1, t2, tick_size=0.25)
    vp = _snapshot(state)
    expected = (vp.total_volume - vp.poc_volume) / vp.total_volume
    assert vp.vol_above_poc_ratio == pytest.approx(expected)
    assert vp.vol_above_poc_ratio == pytest.approx(50.0 / 150.0)


# [15]
def test_profile_entropy_zero_for_single_level():
    """Positive — a single occupied level has zero entropy (no spread)."""
    t = make_stub(price=5000.0, bar_num=1, volume=100)
    state = init_and_update(t)
    vp = _snapshot(state)
    assert vp.profile_entropy == pytest.approx(0.0)


# [16]
def test_poc_migration_zero_on_first_snapshot():
    """Positive — poc_migration is 0.0 when there is no prior snapshot."""
    t = make_stub(price=5000.0, bar_num=1, volume=100)
    state = init_and_update(t)
    vp = _snapshot(state)
    assert vp.poc_migration == pytest.approx(0.0)


# [17]
def test_poc_migration_tracks_poc_shift():
    """Positive — poc_migration reflects the POC shift between consecutive snapshots."""
    t1 = make_stub(price=5000.0, bar_num=1, volume=200)
    state = init_and_update(t1, tick_size=0.25)
    vp1 = _snapshot(state)
    assert vp1.poc_price == pytest.approx(5000.0, abs=0.01)

    # New tick gets a much larger volume 4 ticks above -> POC shifts to 5001.00
    _update(state, make_stub(price=5001.00, bar_num=2, volume=500))
    vp2 = _snapshot(state)
    assert vp2.poc_price == pytest.approx(5001.00, abs=0.01)
    assert vp2.poc_migration == pytest.approx(4.0)  # (5001.00 - 5000.0) / 0.25


# [18]
def test_snapshot_gated_by_snapshot_interval(monkeypatch):
    """Positive — stream_volume_profile yields once per bar (time_s % interval == interval - 1)."""
    ticks = [make_stub(price=5000.0, bar_num=i, volume=10, date=1260125)
             for i in range(61)]
    for i, t in enumerate(ticks):
        ticks[i] = TickStub(
            symbol=t.symbol, date=t.date, time_s=i,
            high=t.high, low=t.low, up=t.up, down=t.down, bar_num=t.bar_num,
        )

    monkeypatch.setattr(
        "feat_files.volume_profile.stream_ticks_from_redis",
        lambda **kwargs: iter(ticks),
    )

    results = list(stream_volume_profile(tick_size=0.25, range_ticks=40, snapshot_interval_s=30))

    # time_s = 0..60 -> fires at time_s = 29 and 59 -> 2 snapshots
    assert len(results) == 2
    assert [vp.n_bars for vp in results] == [30, 60]