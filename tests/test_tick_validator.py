"""
tests/test_tick_validator.py
=============================

Unit tests for the tick validation pipeline logic.
No Redis, no TCP, no I/O — pure function tests only.

What is tested
--------------
The logic inside tick_validator.py is tested indirectly through the
functions it calls: parse_raw_tick_line + validate_tick_sequence.

This file proves the validator's decision logic:
  - valid raw line -> passes through
  - malformed raw line -> TickDecodeError (drop)
  - castable but invariant-violated line -> TickContractError (drop)
  - sequence break (non-monotonic bar_num) -> TickContractError (drop)
  - sequence reset on date/symbol change -> passes through

Test Index
----------
  [01] test_valid_line_passes_through           -- valid raw CSV produces typed Tick
  [02] test_malformed_line_raises_decode_error  -- bad field count raises TickDecodeError
  [03] test_invalid_invariant_raises_contract   -- high != low raises TickContractError
  [04] test_sequence_break_raises_contract      -- non-monotonic bar_num raises TickContractError
  [05] test_sequence_reset_on_new_date_passes   -- bar_num reset allowed on new date
  [06] test_sequence_reset_on_new_symbol_passes -- bar_num reset allowed on new symbol
  [07] test_none_prev_tick_always_passes        -- first tick with no prev always passes sequence
"""

import pytest

from netwo_files.tick_contract import Tick, validate_tick_sequence, TickContractError
from netwo_files.tick_codec import parse_raw_tick_line, TickDecodeError


# ============================================================
# Helper
# ============================================================

def make_raw_line(symbol="@ES", date=1260125, time_s=36000,
                  high=5000.25, low=5000.25, up=10, down=5, bar_num=1) -> str:
    return f"{symbol},{date},{time_s},{high},{low},{up},{down},{bar_num}"


# ============================================================
# Tests
# ============================================================

# [01]
def test_valid_line_passes_through():
    """Positive — valid raw CSV produces a typed Tick without exceptions."""
    t = parse_raw_tick_line(make_raw_line())
    assert t.symbol == "@ES"
    assert t.high == t.low


# [02]
def test_malformed_line_raises_decode_error():
    """Negative — bad field count raises TickDecodeError (validator drops the line)."""
    with pytest.raises(TickDecodeError):
        parse_raw_tick_line("@ES,1260125,36000")


# [03]
def test_invalid_invariant_raises_contract():
    """Negative — high != low raises TickContractError (validator drops the line)."""
    with pytest.raises(TickContractError):
        parse_raw_tick_line(make_raw_line(high=5001.0, low=5000.0))


# [04]
def test_sequence_break_raises_contract():
    """Negative — non-monotonic bar_num raises TickContractError (validator drops)."""
    prev = parse_raw_tick_line(make_raw_line(bar_num=10))
    curr = parse_raw_tick_line(make_raw_line(bar_num=9))
    with pytest.raises(TickContractError):
        validate_tick_sequence(prev, curr)


# [05]
def test_sequence_reset_on_new_date_passes():
    """Positive — bar_num reset is allowed when date changes (new session)."""
    prev = parse_raw_tick_line(make_raw_line(date=1260125, bar_num=100))
    curr = parse_raw_tick_line(make_raw_line(date=1260126, bar_num=1))
    validate_tick_sequence(prev, curr)


# [06]
def test_sequence_reset_on_new_symbol_passes():
    """Positive — bar_num reset is allowed when symbol changes."""
    prev = parse_raw_tick_line(make_raw_line(symbol="@ES", bar_num=100))
    curr = parse_raw_tick_line(make_raw_line(symbol="@NQ", bar_num=1))
    validate_tick_sequence(prev, curr)


# [07]
def test_none_prev_tick_always_passes():
    """Positive — first tick with no previous always passes sequence check."""
    curr = parse_raw_tick_line(make_raw_line(bar_num=1))
    validate_tick_sequence(None, curr)