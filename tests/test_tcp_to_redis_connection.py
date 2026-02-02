# tests/test_bar_contract_and_codec.py
"""
tests/test_bar_contract_and_codec.py
====================================

Unit tests (fast)

Files that tests :  bar_contract.py and bar_codec.py
Invariants: Keep only function tests, no Integration tests or End-to-end tests

What exactly is going on:
----
1) Negative tests ensure that invalid data is caught by your contract and codec.
The tests must raise ContractError or DecodeError to pass the test.
ContractError is a user defined types that is in bar_contract.py
DecodeError is a user defined types that is in bar_codec.py

2)Positive tests ensure that valid data passes your contract and codec.
The tests must NOT raise any exceptions to pass the test
must return the assert condition.

Goal
----
This test suite proves that your "contract" and "codec" do what you THINK they do,
without needing TCP sockets or Redis running.

Why you should test these functions
-----------------------------------
You already have a live validator in the TCP server. That is necessary, but it is not sufficient.

$$$$$$$$$$$$$$$
VERY IMPORTANT
$$$$$$$$$$$$$$$
1) Live validation answers: "Is the current incoming data okay right now?"
2) Unit tests answer: "If I change one line in the validator next week, will I silently break rules?"

Trading pipelines fail in the worst way: silently.
This suite is your tripwire.

-------------------------------------------------------------------------------
Test Index (must match body order)
-------------------------------------------------------------------------------
[01] test_validate_bar_good_passes — Valid bar passes all invariants
[02] test_symbol_invalid — Rejects empty or nonstring symbol
[03] test_date_invalid_month — Rejects month outside valid range
[04] test_date_invalid_day — Rejects day outside valid range
[05] test_time_seconds_range — Rejects time outside daily bounds
[06] test_prices_must_be_positive — Rejects nonpositive OHLC price values
[07] test_high_ge_open — Rejects high less than open
[08] test_OHLC_type — Rejects OHLC fields with nonfloat
[09] test_open_ge_low — Rejects open lower than low
[10] test_close_within_low_high — Rejects close outside low-high bounds
[11] test_up_down_non_negative — Rejects negative up or down
[12] test_up_down_type — Rejects up/down fields with nonint
[13] test_vwap_non_negative — Rejects negative VWAP values always
[14] test_bar_num_non_negative — Rejects negative bar_num values always
[15] test_sequence_monotonic_same_symbol_date — Enforces monotonic bar_num within session
[16] test_sequence_reset_allowed_new_date_or_symbol — Allows resets across date or symbol
[17] test_parse_csv_line_good — Parses valid CSV into typed Bar
[18] test_parse_csv_line_bad_field_count — Rejects CSV with wrong fieldcount
[19] test_parse_csv_line_cast_error — Rejects CSV when casting fails
[20] test_parse_csv_line_contract_error — Rejects CSV when invariants violated
[21] test_bar_from_redis_fields_bytes_ok — Decodes Redis bytes fields into Bar
[22] test_bar_from_redis_fields_missing_key — Rejects Redis missing required fields
[23] test__as_str_decodes_bytes_strict_utf8 — Decodes UTF-8 bytes into string
[24] test__as_str_non_bytes_falls_back_to_str — Stringifies non-bytes values consistently always
[25] test_bar_to_redis_fields_encodes_canonical_strings — Encodes bar into canonical strings
[26] test_bar_to_redis_fields_rejects_invalid_bar_via_contract — Rejects invalid bar during encoding
[27] test_parse_xread_to_bars_none_returns_empty_batch — None input yields empty batch
[28] test_parse_xread_to_bars_requires_list_top_level — Rejects XREAD result not list
[29] test_parse_xread_to_bars_rejects_bad_stream_block_shape — Rejects stream block wrong shape
[30] test_parse_xread_to_bars_requires_entries_list — Rejects entries container not list
[31] test_parse_xread_to_bars_rejects_bad_entry_shape — Rejects entry tuple wrong shape
[32] test_parse_xread_to_bars_requires_fields_mapping — Rejects fields not mapping type
[33] test_parse_xread_to_bars_happy_path_multiple_streams_bytes_and_str — Flattens payload, tracks last ids
[34] test_parse_xread_to_bars_propagates_decode_error_from_fields — Propagates DecodeError from bad fields
[35] test_parse_xread_to_bars_propagates_contract_error_from_bar_validation — Propagates ContractError from invalid bar
-------------------------------------------------------------------------------

Important distinction: DecodeError vs ContractError
---------------------------------------------------
DecodeError: you couldn't even interpret the transport (wrong column count, non-numeric text)
ContractError: you could interpret it, but it violates invariants (open <= 0, high < open, etc.)

This distinction matters operationally:
- DecodeError typically means malformed line / corruption / version mismatch
- ContractError means the data is "well-formed" but logically invalid for your domain
- XReadShapeError means the OUTER XREAD payload shape is wrong (nesting/list/tuple/mapping), before field casting even begins
"""

import pytest

from netwo_files.bar_contract import Bar, validate_bar, validate_sequence, ContractError
from netwo_files.bar_codec import parse_csv_line, bar_from_redis_fields, DecodeError

# 🟩 ADDED 2026-02-02
from netwo_files.bar_codec import (
    _as_str,
    bar_to_redis_fields,
    parse_xread_to_bars,
    XReadShapeError,
)


def make_bar(**kw) -> Bar:
    """
    Build a VALID Bar by default.

    Why this helper exists
    ----------------------
    Contract tests should be focused: one test should violate ONE rule.
    If every test rewrites 11 fields manually, you'll introduce accidental errors
    and tests become unreadable.

    The default Bar here is valid according to your live format:
    - symbol: "@ES" (non-empty) & type == str
    - date: 1260125 (YYYMMDD, years since 1900)
      126 -> year 2026, 01 -> Jan, 25 -> day 25
    - time_s: 36000 (10:00:00 in seconds)
    - prices: positive and consistent (low <= open <= high; close in [low, high])
    - up/down: non-negative
    - vwap: non-negative
    - bar_num: non-negative

    Each test can override only the field it wants to break.
    """
    base = dict(
        symbol="@ES",
        date=1260125,
        time_s=36000,
        open=100.0,
        high=101.0,
        low=99.5,
        close=100.5,
        up=4,
        down=0,
        vwap=100.2,
        bar_num=26,
    )
    base.update(kw)
    return Bar(**base)


def make_csv(**kw) -> str:
    """
    Build a CSV line matching your TCP schema.

    Why this helper exists
    ----------------------
    parse_csv_line() expects exactly 11 comma-separated fields in a strict order.
    This helper creates a correct CSV string from a valid Bar, then allows
    overriding one field for negative tests (ex: open="NOT_A_NUMBER").

    This avoids writing brittle hard-coded CSV strings in every test.
    """
    b = make_bar(**kw)
    return ",".join(
        [
            b.symbol,
            str(b.date),
            str(b.time_s),
            str(b.open),
            str(b.high),
            str(b.low),
            str(b.close),
            str(b.up),
            str(b.down),
            str(b.vwap),
            str(b.bar_num),
        ]
    )


# -------------------------------------------------------------------
# A) Contract tests (validate_bar / validate_sequence)
# -------------------------------------------------------------------


# [01]
def test_validate_bar_good_passes():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects no exception; baseline control)

    Why this test exists
    --------------------
    Before testing failures, we prove the baseline valid object passes.
    If this fails, every other test is meaningless because the "control" case is broken.
    """
    validate_bar(make_bar())


# [02]
@pytest.mark.parametrize("bad_symbol", ["", None, 3, 10.2])
def test_symbol_invalid(bad_symbol):
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      symbol must not be null and must be non-empty

    Why we test both "" and None
    ----------------------------
    - "" tests empty-string cases from parsing/transport.
    - None tests programmer mistakes or missing values after refactors.
    """
    b = make_bar(symbol=bad_symbol)  # type: ignore
    with pytest.raises(ContractError):
        validate_bar(b)


# [03]
def test_date_invalid_month():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule (for TS YYYMMDD):
      month must be in [1,12]

    We intentionally craft a date with month=13:
      1261325 -> yyy=126, mm=13, dd=25

    Why match "mm=" in error message
    --------------------------------
    You asked for errors to identify the violated field. This ensures the message
    actually points to month, not just a generic "date invalid".
    """
    with pytest.raises(ContractError, match="mm="):
        validate_bar(make_bar(date=1261325))


# [04]
def test_date_invalid_day():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      day must be in [1,31] (basic structural day validation)

    We intentionally craft day=32:
      1260132 -> yyy=126, mm=01, dd=32
    """
    with pytest.raises(ContractError, match="dd="):
        validate_bar(make_bar(date=1260132))


# [05]
@pytest.mark.parametrize("t", [-1, 86400])
def test_time_seconds_range(t):
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      time_s must be in [0, 86399]

    Why test -1 and 86400
    ---------------------
    - -1 catches negative or uninitialized values
    - 86400 catches off-by-one errors (exactly one second after the day ends)
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(time_s=t))


# [06]
@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_prices_must_be_positive(field):
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      open/high/low/close must be > 0 (non-zero positive)

    Why parametrize
    ---------------
    This is the same rule applied to 4 different fields.
    Parametrization keeps tests consistent and avoids copy-paste.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(**{field: 0.0}))


# [07]
def test_high_ge_open():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      high must be >= open

    Why test this specific relationship
    -----------------------------------
    This is a fundamental market invariant per bar; downstream volatility
    features can break if violated.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(open=100.0, high=99.9))


# [08]
@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_OHLC_type(field):
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      Open , High , Low, Close are instance of float

    Why parametrize
    ---------------
    This is the same rule applied to 4 different fields.
    Parametrization keeps tests consistent and avoids copy-paste.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(**{field: "banana"}))


# [09]
def test_open_ge_low():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      open must be >= low

    Again: ensures consistent OHLC relationship.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(open=99.0, low=99.5))


# [10]
def test_close_within_low_high():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      close must be within [low, high]

    We test two directions:
    - close too high
    - close below low

    Why both
    --------
    Ensures we catch violations on both bounds, not just one.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(close=200.0))
    with pytest.raises(ContractError):
        validate_bar(make_bar(close=0.1, low=1.0))


# [11]
@pytest.mark.parametrize("field", ["up", "down"])
def test_up_down_non_negative(field):
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      up/down must be >= 0

    Why it matters
    --------------
    Negative counts indicate upstream encoding bugs or misinterpretation of fields.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(**{field: -1}))


# [12]
@pytest.mark.parametrize("field", ["up", "down"])
def test_up_down_type(field):
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      up/down type must be int

    Why it matters
    --------------
    non int numbers are not volume
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(**{field: 2.34}))


# [13]
def test_vwap_non_negative():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      vwap >= 0

    Why only non-negative
    ---------------------
    Your TCP schema does not include volume, so we cannot recompute VWAP here.
    We enforce only the invariant you declared.

    If you later add volume, you can add a stronger test.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(vwap=-0.01))


# [14]
def test_bar_num_non_negative():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    Contract rule:
      bar_num must be >= 0

    Why it matters
    --------------
    Negative bar numbers usually indicate uninitialized values or session bugs.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(bar_num=-1))


# [15]
def test_sequence_monotonic_same_symbol_date():
    """
    Test type: Mixed (Positive + Negative)
    🟨 ADDED: Mixed (asserts success, then expects error)

    Stateful contract rule:
      bar_num[x] > bar_num[x-1] within same (symbol, date)

    Why this is separate from validate_bar
    --------------------------------------
    You cannot test monotonicity using only one bar. You need at least two.
    """
    prev = make_bar(bar_num=10)
    curr_ok = make_bar(bar_num=11)
    validate_sequence(prev, curr_ok)

    curr_bad = make_bar(bar_num=10)
    with pytest.raises(ContractError):
        validate_sequence(prev, curr_bad)


# [16]
def test_sequence_reset_allowed_new_date_or_symbol():
    """
    Test type: Positive
    🟨 ADDED: Positive (expects no exception; asserts validity)

    Why this test exists
    --------------------
    bar_num monotonicity should not incorrectly fail across:
    - new trading day (date changes)
    - different symbol

    This protects against an overly strict sequence validator.
    """
    prev = make_bar(symbol="@ES", date=1260125, bar_num=100)

    # new date => allow bar_num reset
    curr_new_date = make_bar(symbol="@ES", date=1260126, bar_num=1)
    validate_sequence(prev, curr_new_date)

    # new symbol => allow reset
    curr_new_symbol = make_bar(symbol="@NQ", date=1260125, bar_num=1)
    validate_sequence(prev, curr_new_symbol)


# -------------------------------------------------------------------
# B) Codec tests (parse_csv_line / bar_from_redis_fields)
# -------------------------------------------------------------------


# [17]
def test_parse_csv_line_good():
    """
    Test type: Positive
    🟨 ADDED: Positive (asserts returned types correct)

    Why this test exists
    --------------------
    Confirms the TCP decoder:
    - returns a Bar
    - casts types correctly (int/float)

    If types are wrong, your downstream math breaks.
    """
    b = parse_csv_line(make_csv())
    assert isinstance(b.symbol, str)
    assert isinstance(b.date, int)
    assert isinstance(b.time_s, int)
    assert isinstance(b.open, float)
    assert isinstance(b.high, float)
    assert isinstance(b.low, float)
    assert isinstance(b.close, float)
    assert isinstance(b.up, int)
    assert isinstance(b.down, int)
    assert isinstance(b.vwap, float)
    assert isinstance(b.bar_num, int)


# [18]
def test_parse_csv_line_bad_field_count():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects DecodeError raised)

    parse_csv_line contract:
      must have exactly 11 fields

    Why test this
    -------------
    Your TCP buffer split and transport can produce partial lines or corruption.
    This ensures you fail fast and clearly.
    """
    with pytest.raises(DecodeError):
        parse_csv_line("a,b,c")


# [19]
def test_parse_csv_line_cast_error():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects DecodeError raised)

    parse_csv_line should raise DecodeError when types cannot be cast.

    Example:
      open="NOT_A_NUMBER"

    Why this matters
    ----------------
    This distinguishes "malformed transport" from "valid but logically wrong".
    """
    line = make_csv(open="NOT_A_NUMBER")  # type: ignore
    with pytest.raises(DecodeError):
        parse_csv_line(line)


# [20]
def test_parse_csv_line_contract_error():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects ContractError raised)

    parse_csv_line should raise ContractError when data casts fine
    but violates invariants.

    Example:
      open = -1.0  (casts to float fine, but violates open > 0)
    """
    line = make_csv(open=-1.0)
    with pytest.raises(ContractError):
        parse_csv_line(line)


# [21]
def test_bar_from_redis_fields_bytes_ok():
    """
    Test type: Positive
    🟨 ADDED: Positive (asserts decode and casting)

    Why this test exists
    --------------------
    Redis usually returns bytes for keys and values.
    This test proves the Redis decoder:
    - decodes bytes -> str
    - casts to numeric types
    - returns a valid Bar
    """
    fields = {
        b"symbol": b"@ES",
        b"date": b"1260125",
        b"time": b"36000",
        b"open": b"100.0",
        b"high": b"101.0",
        b"low": b"99.5",
        b"close": b"100.5",
        b"up": b"4",
        b"down": b"0",
        b"vwap": b"100.2",
        b"bar_num": b"26",
    }
    b = bar_from_redis_fields(fields)
    assert b.symbol == "@ES"
    assert b.date == 1260125


# [22]
def test_bar_from_redis_fields_missing_key():
    """
    Test type: Negative
    🟨 ADDED: Negative (expects DecodeError raised)

    Why this test exists
    --------------------
    Streams can contain bad entries:
    - old entries from before contract enforcement
    - future producers writing different schemas
    - manual debug inserts

    The decoder should fail loudly if required fields are missing,
    otherwise you'd get KeyError later or, worse, silently default values.

    We test that missing required keys raises DecodeError with 'missing fields'.
    """
    with pytest.raises(DecodeError, match="missing fields"):
        bar_from_redis_fields({b"symbol": b"@ES"})


# [23] 🟩 ADDED 2026-02-02
def test__as_str_decodes_bytes_strict_utf8():
    """
    Why:
      _as_str is a tiny helper, but it's a boundary sanitizer.
      If it silently accepts garbage bytes, downstream casting errors become confusing.

    We test:
      - valid utf-8 bytes decode cleanly

    🟨 ADDED: Test type: Positive (asserts decoded string)
    """
    assert _as_str(b"@ES") == "@ES"


# [24] 🟩 ADDED 2026-02-02
def test__as_str_non_bytes_falls_back_to_str():
    """
    Why:
      Redis keys/values can sometimes be str already (decode_responses=True),
      and ids/stream names can be non-bytes in mocks.
      This ensures _as_str normalizes consistently.

    🟨 ADDED: Test type: Positive (asserts string conversion)
    """
    assert _as_str("@ES") == "@ES"
    assert _as_str(123) == "123"


# [25] 🟩 ADDED 2026-02-02
def test_bar_to_redis_fields_encodes_canonical_strings():
    """
    Why:
      bar_to_redis_fields() is new and wasn't tested.
      If encoding drifts, round-trips and debugging (redis-cli) get messy.

    We test:
      - required keys exist
      - date encodes as a string
      - numeric values are strings

    🟨 ADDED: Test type: Positive (asserts encoded mapping)
    """
    b = make_bar(date=1260125)  # valid per contract
    f = bar_to_redis_fields(b)

    assert set(f.keys()) == {
        "symbol",
        "date",
        "time",
        "open",
        "high",
        "low",
        "close",
        "up",
        "down",
        "vwap",
        "bar_num",
    }

    # Date should round-trip as the canonical integer string (no truncation)
    assert f["date"] == "1260125"
    assert isinstance(f["date"], str)

    assert isinstance(f["open"], str)
    assert isinstance(f["bar_num"], str)
    assert f["symbol"] == "@ES"


# [26] 🟩 ADDED 2026-02-02
def test_bar_to_redis_fields_rejects_invalid_bar_via_contract():
    """
    Why:
      bar_to_redis_fields() calls validate_bar(b).
      If that call is removed in a refactor, invalid bars could get written to Redis.

    We test:
      - invalid bar triggers ContractError

    🟨 ADDED: Test type: Negative (expects ContractError raised)
    """
    bad = make_bar(open=-1.0)
    with pytest.raises(ContractError):
        bar_to_redis_fields(bad)


# [27] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_none_returns_empty_batch():
    """
    Why:
      Your parser explicitly treats None as "no data yet" and returns empty.
      This is an operationally important behavior (no exceptions during idle polls).

    🟨 ADDED: Test type: Positive (asserts empty output)
    """
    batch = parse_xread_to_bars(None)
    assert batch.bars == []
    assert batch.last_ids == {}


# [28] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_requires_list_top_level():
    """
    Why:
      redis-py XREAD returns a list.
      If a caller passes the wrong thing (mock bug, refactor bug),
      we want a clear XReadShapeError (not random TypeErrors later).

    🟨 ADDED: Test type: Negative (expects XReadShapeError raised)
    """
    with pytest.raises(XReadShapeError, match="must be a list"):
        parse_xread_to_bars("not-a-list")


# [29] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_rejects_bad_stream_block_shape():
    """
    Why:
      Each top-level item must be (stream_name, entries_list).
      If the nesting is wrong, we fail fast with XReadShapeError.

    🟨 ADDED: Test type: Negative (expects XReadShapeError raised)
    """
    with pytest.raises(XReadShapeError, match=r"item\[0\] must be"):
        parse_xread_to_bars([("stream_only",)])


# [30] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_requires_entries_list():
    """
    Why:
      entries must be a list per redis-py shape.

    🟨 ADDED: Test type: Negative (expects XReadShapeError raised)
    """
    with pytest.raises(XReadShapeError, match="must be a list"):
        parse_xread_to_bars([(b"mystream", "not-a-list")])


# [31] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_rejects_bad_entry_shape():
    """
    Why:
      Each entry must be (entry_id, fields_mapping).

    🟨 ADDED: Test type: Negative (expects XReadShapeError raised)
    """
    with pytest.raises(XReadShapeError, match="must be \\(id, fields\\)"):
        parse_xread_to_bars([(b"mystream", [(b"1-0",)])])


# [32] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_requires_fields_mapping():
    """
    Why:
      If fields isn't a mapping, bar_from_redis_fields cannot operate.
      This should be a shape error (outer structure wrong), not DecodeError.

    🟨 ADDED: Test type: Negative (expects XReadShapeError raised)
    """
    with pytest.raises(XReadShapeError, match="must be a mapping"):
        parse_xread_to_bars([(b"mystream", [(b"1-0", ["not", "a", "dict"])])])


# [33] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_happy_path_multiple_streams_bytes_and_str():
    """
    Why:
      This is the *core* purpose of the new adapter:
      - unwrap XREAD nesting
      - normalize bytes/str
      - delegate to bar_from_redis_fields()
      - return flattened bars + per-stream last_ids

    We test:
      - flatten order follows payload order
      - last_ids updated per stream with the last entry id seen

    🟨 ADDED: Test type: Positive (asserts flatten + last_ids)
    """
    xread_payload = [
        (
            b"stream_A",
            [
                (
                    b"1-0",
                    {
                        b"symbol": b"@ES",
                        b"date": b"1260125",
                        b"time": b"36000",
                        b"open": b"100.0",
                        b"high": b"101.0",
                        b"low": b"99.5",
                        b"close": b"100.5",
                        b"up": b"4",
                        b"down": b"0",
                        b"vwap": b"100.2",
                        b"bar_num": b"26",
                    },
                ),
                (
                    b"2-0",
                    {
                        b"symbol": b"@ES",
                        b"date": b"1260125",
                        b"time": b"36001",
                        b"open": b"100.1",
                        b"high": b"101.1",
                        b"low": b"99.6",
                        b"close": b"100.6",
                        b"up": b"5",
                        b"down": b"0",
                        b"vwap": b"100.3",
                        b"bar_num": b"27",
                    },
                ),
            ],
        ),
        (
            "stream_B",
            [
                (
                    "9-0",
                    {
                        "symbol": "@NQ",
                        "date": "1260125",
                        "time": "36000",
                        "open": "200.0",
                        "high": "201.0",
                        "low": "199.5",
                        "close": "200.5",
                        "up": "2",
                        "down": "1",
                        "vwap": "200.2",
                        "bar_num": "10",
                    },
                )
            ],
        ),
    ]

    batch = parse_xread_to_bars(xread_payload)

    assert len(batch.bars) == 3
    assert batch.bars[0].symbol == "@ES"
    assert batch.bars[1].time_s == 36001
    assert batch.bars[2].symbol == "@NQ"

    assert batch.last_ids == {"stream_A": "2-0", "stream_B": "9-0"}


# [34] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_propagates_decode_error_from_fields():
    """
    Why:
      If the OUTER XREAD shape is fine but fields are missing, that's DecodeError,
      not XReadShapeError. This distinction is exactly why you created 2 error types.

    We test:
      - valid XREAD structure
      - missing required bar fields
      - raises DecodeError

    🟨 ADDED: Test type: Negative (expects DecodeError raised)
    """
    payload = [(b"mystream", [(b"1-0", {b"symbol": b"@ES"})])]
    with pytest.raises(DecodeError, match="missing fields"):
        parse_xread_to_bars(payload)


# [35] 🟩 ADDED 2026-02-02
def test_parse_xread_to_bars_propagates_contract_error_from_bar_validation():
    """
    Why:
      If parsing/casting works but invariants fail (open <= 0 etc),
      that must bubble up as ContractError (domain-level invalid bar).

    We test:
      - structure OK
      - casts OK
      - invariant violated => ContractError

    🟨 ADDED: Test type: Negative (expects ContractError raised)
    """
    payload = [
        (
            b"mystream",
            [
                (
                    b"1-0",
                    {
                        b"symbol": b"@ES",
                        b"date": b"1260125",
                        b"time": b"36000",
                        b"open": b"-1.0",  # castable but invalid
                        b"high": b"101.0",
                        b"low": b"99.5",
                        b"close": b"100.5",
                        b"up": b"4",
                        b"down": b"0",
                        b"vwap": b"100.2",
                        b"bar_num": b"26",
                    },
                )
            ],
        )
    ]
    with pytest.raises(ContractError):
        parse_xread_to_bars(payload)
