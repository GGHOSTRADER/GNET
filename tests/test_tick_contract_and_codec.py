"""
tests/test_tick_contract_and_codec.py
======================================

Unit tests for tick_contract.py and tick_codec.py.
No Redis, no TCP, no I/O — pure function tests only.

Files tested
------------
  netwo_files/tick_contract.py  -- Tick + validate_tick + validate_tick_sequence
  netwo_files/tick_codec.py     -- parse_raw_tick_line + tick_from_redis_fields
                                   tick_to_redis_fields + parse_xread_raw_ticks
                                   parse_xread_to_ticks

Error types
-----------
  TickContractError : parsed/cast OK but invariant violated (high != low, bar_num < 0, etc.)
  TickDecodeError   : could not parse/cast (wrong field count, float("abc"), etc.)

Test Index
----------
CONTRACT
  [01] test_validate_tick_good_passes               -- baseline valid tick passes all invariants
  [02] test_symbol_invalid                          -- rejects empty or non-string symbol
  [03] test_date_invalid_month                      -- rejects month outside [1,12]
  [04] test_date_invalid_day                        -- rejects day outside [1,31]
  [05] test_time_seconds_range                      -- rejects time outside [0, 86399]
  [06] test_high_must_be_positive                   -- rejects high <= 0
  [07] test_low_must_be_positive                    -- rejects low <= 0
  [08] test_high_must_equal_low                     -- rejects high != low (tick invariant)
  [09] test_high_low_type                           -- rejects non-float high or low
  [10] test_up_down_non_negative                    -- rejects negative up or down
  [11] test_up_down_type                            -- rejects non-int up or down
  [12] test_bar_num_non_negative                    -- rejects negative bar_num
  [13] test_tick_sequence_monotonic                 -- enforces bar_num strictly increasing
  [14] test_tick_sequence_reset_allowed             -- allows reset on date or symbol change

CODEC
  [15] test_parse_raw_tick_line_good                -- parses valid CSV into typed Tick
  [16] test_parse_raw_tick_line_bad_field_count     -- rejects CSV with wrong field count
  [17] test_parse_raw_tick_line_cast_error          -- rejects CSV when casting fails
  [18] test_parse_raw_tick_line_contract_error      -- rejects CSV when high != low after casting
  [19] test_tick_from_redis_fields_bytes_ok         -- decodes Redis bytes fields into typed Tick
  [20] test_tick_from_redis_fields_missing_key      -- rejects mapping with missing required key
  [21] test_tick_to_redis_fields_encodes_canonical  -- encodes Tick to canonical string fields
  [22] test_parse_xread_raw_ticks_none_returns_empty -- None yields empty list
  [23] test_parse_xread_raw_ticks_extracts_raw_lines -- extracts raw_tick field from XREAD
  [24] test_parse_xread_to_ticks_none_returns_empty  -- None yields empty XReadTickBatch
  [25] test_parse_xread_to_ticks_happy_path          -- flattens ticks and tracks last_ids
  [26] test_parse_xread_to_ticks_propagates_decode_error   -- propagates TickDecodeError
  [27] test_parse_xread_to_ticks_propagates_contract_error -- propagates TickContractError
"""

import pytest

from netwo_files.tick_contract import Tick, validate_tick, validate_tick_sequence, TickContractError
from netwo_files.tick_codec import (
    parse_raw_tick_line,
    tick_from_redis_fields,
    tick_to_redis_fields,
    parse_xread_raw_ticks,
    parse_xread_to_ticks,
    TickDecodeError,
)


# ============================================================
# Helpers
# ============================================================

def make_tick(**kw) -> Tick:
    """Build a valid Tick. Override any field to test a specific invariant."""
    base = dict(
        symbol="@ES", date=1260125, time_s=36000,
        high=5000.25, low=5000.25,
        up=10, down=5, bar_num=1,
    )
    base.update(kw)
    return Tick(**base)


def make_csv_tick(**kw) -> str:
    """Build a valid CSV tick line. Override any field for negative tests."""
    t = make_tick(**kw)
    return ",".join([
        t.symbol, str(t.date), str(t.time_s),
        str(t.high), str(t.low),
        str(t.up), str(t.down), str(t.bar_num),
    ])


# ============================================================
# CONTRACT tests
# ============================================================

# [01]
def test_validate_tick_good_passes():
    """Positive — baseline valid tick passes all invariants."""
    validate_tick(make_tick())


# [02]
@pytest.mark.parametrize("bad_symbol", ["", None, 3, 10.2])
def test_symbol_invalid(bad_symbol):
    """Negative — rejects empty or non-string symbol."""
    with pytest.raises(TickContractError):
        validate_tick(make_tick(symbol=bad_symbol))  # type: ignore


# [03]
def test_date_invalid_month():
    """Negative — rejects month outside [1,12]. 1261325 -> mm=13."""
    with pytest.raises(TickContractError, match="mm="):
        validate_tick(make_tick(date=1261325))


# [04]
def test_date_invalid_day():
    """Negative — rejects day outside [1,31]. 1260132 -> dd=32."""
    with pytest.raises(TickContractError, match="dd="):
        validate_tick(make_tick(date=1260132))


# [05]
@pytest.mark.parametrize("t", [-1, 86400])
def test_time_seconds_range(t):
    """Negative — rejects time outside [0, 86399]."""
    with pytest.raises(TickContractError):
        validate_tick(make_tick(time_s=t))


# [06]
def test_high_must_be_positive():
    """Negative — rejects high <= 0."""
    with pytest.raises(TickContractError):
        validate_tick(make_tick(high=0.0, low=0.0))


# [07]
def test_low_must_be_positive():
    """Negative — rejects low <= 0."""
    with pytest.raises(TickContractError):
        validate_tick(make_tick(low=0.0, high=0.0))


# [08]
def test_high_must_equal_low():
    """Negative — rejects high != low. Core tick invariant: single price point."""
    with pytest.raises(TickContractError, match="high must equal low"):
        validate_tick(make_tick(high=5001.0, low=5000.0))


# [09]
@pytest.mark.parametrize("field", ["high", "low"])
def test_high_low_type(field):
    """Negative — rejects non-float high or low."""
    with pytest.raises(TickContractError):
        validate_tick(make_tick(**{field: "banana"}))  # type: ignore


# [10]
@pytest.mark.parametrize("field", ["up", "down"])
def test_up_down_non_negative(field):
    """Negative — rejects negative up or down."""
    with pytest.raises(TickContractError):
        validate_tick(make_tick(**{field: -1}))


# [11]
@pytest.mark.parametrize("field", ["up", "down"])
def test_up_down_type(field):
    """Negative — rejects non-int up or down."""
    with pytest.raises(TickContractError):
        validate_tick(make_tick(**{field: 1.5}))  # type: ignore


# [12]
def test_bar_num_non_negative():
    """Negative — rejects negative bar_num."""
    with pytest.raises(TickContractError):
        validate_tick(make_tick(bar_num=-1))


# [13]
def test_tick_sequence_monotonic():
    """Mixed — bar_num must strictly increase within same symbol/date."""
    prev = make_tick(bar_num=10)
    validate_tick_sequence(prev, make_tick(bar_num=11))
    with pytest.raises(TickContractError):
        validate_tick_sequence(prev, make_tick(bar_num=10))


# [14]
def test_tick_sequence_reset_allowed():
    """Positive — bar_num reset allowed on new date or new symbol."""
    prev = make_tick(symbol="@ES", date=1260125, bar_num=100)
    validate_tick_sequence(prev, make_tick(symbol="@ES", date=1260126, bar_num=1))
    validate_tick_sequence(prev, make_tick(symbol="@NQ", date=1260125, bar_num=1))


# ============================================================
# CODEC tests
# ============================================================

# [15]
def test_parse_raw_tick_line_good():
    """Positive — parses valid CSV into typed Tick with correct types."""
    t = parse_raw_tick_line(make_csv_tick())
    assert isinstance(t.symbol, str)
    assert isinstance(t.date, int)
    assert isinstance(t.time_s, int)
    assert isinstance(t.high, float)
    assert isinstance(t.low, float)
    assert isinstance(t.up, int)
    assert isinstance(t.down, int)
    assert isinstance(t.bar_num, int)


# [16]
def test_parse_raw_tick_line_bad_field_count():
    """Negative — rejects CSV with wrong number of fields."""
    with pytest.raises(TickDecodeError):
        parse_raw_tick_line("a,b,c")


# [17]
def test_parse_raw_tick_line_cast_error():
    """Negative — rejects CSV when a field cannot be cast."""
    with pytest.raises(TickDecodeError):
        parse_raw_tick_line("@ES,1260125,36000,NOT_A_NUMBER,NOT_A_NUMBER,10,5,1")


# [18]
def test_parse_raw_tick_line_contract_error():
    """Negative — rejects CSV when high != low after casting."""
    with pytest.raises(TickContractError):
        parse_raw_tick_line("@ES,1260125,36000,5001.0,5000.0,10,5,1")


# [19]
def test_tick_from_redis_fields_bytes_ok():
    """Positive — decodes Redis bytes fields into typed Tick."""
    fields = {
        b"symbol": b"@ES", b"date": b"1260125", b"time": b"36000",
        b"high": b"5000.25", b"low": b"5000.25",
        b"up": b"10", b"down": b"5", b"bar_num": b"1",
    }
    t = tick_from_redis_fields(fields)
    assert t.symbol == "@ES"
    assert t.high == t.low
    assert isinstance(t.high, float)


# [20]
def test_tick_from_redis_fields_missing_key():
    """Negative — rejects mapping with missing required key."""
    with pytest.raises(TickDecodeError, match="missing fields"):
        tick_from_redis_fields({b"symbol": b"@ES"})


# [21]
def test_tick_to_redis_fields_encodes_canonical():
    """Positive — encodes Tick to canonical string fields with all required keys."""
    f = tick_to_redis_fields(make_tick())
    assert set(f.keys()) == {"symbol", "date", "time", "high", "low", "up", "down", "bar_num"}
    assert isinstance(f["high"], str)
    assert isinstance(f["bar_num"], str)
    assert f["symbol"] == "@ES"


# [22]
def test_parse_xread_raw_ticks_none_returns_empty():
    """Positive — None input yields empty list."""
    assert parse_xread_raw_ticks(None) == []


# [23]
def test_parse_xread_raw_ticks_extracts_raw_lines():
    """Positive — extracts raw_tick field string from XREAD structure."""
    raw_line = "@ES,1260125,36000,5000.25,5000.25,10,5,1"
    payload = [(b"tick_data_raw", [(b"1-0", {b"raw_tick": raw_line.encode()})])]
    result = parse_xread_raw_ticks(payload)
    assert len(result) == 1
    assert result[0][1] == raw_line


# [24]
def test_parse_xread_to_ticks_none_returns_empty():
    """Positive — None yields empty XReadTickBatch."""
    batch = parse_xread_to_ticks(None)
    assert batch.ticks == []
    assert batch.last_ids == {}


# [25]
def test_parse_xread_to_ticks_happy_path():
    """Positive — flattens ticks and tracks last_ids correctly."""
    def fields(bar_num: int) -> dict:
        return {
            b"symbol": b"@ES", b"date": b"1260125", b"time": b"36000",
            b"high": b"5000.25", b"low": b"5000.25",
            b"up": b"10", b"down": b"5",
            b"bar_num": str(bar_num).encode(),
        }
    payload = [(b"tick_data_validated", [(b"1-0", fields(1)), (b"2-0", fields(2))])]
    batch = parse_xread_to_ticks(payload)
    assert len(batch.ticks) == 2
    assert batch.ticks[0].bar_num == 1
    assert batch.ticks[1].bar_num == 2
    assert batch.last_ids == {"tick_data_validated": "2-0"}


# [26]
def test_parse_xread_to_ticks_propagates_decode_error():
    """Negative — propagates TickDecodeError when required fields are missing."""
    payload = [(b"tick_data_validated", [(b"1-0", {b"symbol": b"@ES"})])]
    with pytest.raises(TickDecodeError, match="missing fields"):
        parse_xread_to_ticks(payload)


# [27]
def test_parse_xread_to_ticks_propagates_contract_error():
    """Negative — propagates TickContractError when high != low."""
    payload = [(b"tick_data_validated", [(b"1-0", {
        b"symbol": b"@ES", b"date": b"1260125", b"time": b"36000",
        b"high": b"5001.0", b"low": b"5000.0",
        b"up": b"10", b"down": b"5", b"bar_num": b"1",
    })])]
    with pytest.raises(TickContractError):
        parse_xread_to_ticks(payload)