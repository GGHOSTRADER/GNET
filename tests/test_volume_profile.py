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