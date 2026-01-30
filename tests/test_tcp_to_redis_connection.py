# tests/test_bar_contract_and_codec.py
"""
tests/test_bar_contract_and_codec.py
====================================

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

What we test (and why)
----------------------
Your design has two modules:

1) bar_contract.py
   - Bar dataclass (typed representation)
   - validate_bar(bar): stateless invariants (single bar)
   - validate_sequence(prev, curr): stateful invariant (bar_num monotonic)

2) bar_codec.py
   - parse_csv_line(line): decode TCP CSV -> cast -> validate -> Bar
   - bar_from_redis_fields(fields): decode Redis bytes/strings -> cast -> validate -> Bar

Therefore tests are grouped as:

A) Contract tests
   - Each invariant passes on good input
   - Each invariant fails when we violate it intentionally

B) Codec tests
   - Good CSV -> typed Bar
   - Bad CSV -> DecodeError or ContractError
   - Good Redis fields -> typed Bar
   - Missing/invalid Redis fields -> DecodeError

Important distinction: DecodeError vs ContractError
---------------------------------------------------
DecodeError: you couldn't even interpret the transport (wrong column count, non-numeric text)
ContractError: you could interpret it, but it violates invariants (open <= 0, high < open, etc.)

This distinction matters operationally:
- DecodeError typically means malformed line / corruption / version mismatch
- ContractError means the data is "well-formed" but logically invalid for your domain
"""

import pytest

from netwo_files.bar_contract import Bar, validate_bar, validate_sequence, ContractError
from netwo_files.bar_codec import parse_csv_line, bar_from_redis_fields, DecodeError


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


def test_validate_bar_good_passes():
    """
    Test type: Negative

    Why this test exists
    --------------------
    Before testing failures, we prove the baseline valid object passes.
    If this fails, every other test is meaningless because the "control" case is broken.
    """
    validate_bar(make_bar())


@pytest.mark.parametrize("bad_symbol", ["", None, 3, 10.2])
def test_symbol_invalid(bad_symbol):
    """
    Test type: Negative

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


def test_date_invalid_month():
    """
    Test type: Negative

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


def test_date_invalid_day():
    """
    Test type: Negative

    Contract rule:
      day must be in [1,31] (basic structural day validation)

    We intentionally craft day=32:
      1260132 -> yyy=126, mm=01, dd=32
    """
    with pytest.raises(ContractError, match="dd="):
        validate_bar(make_bar(date=1260132))


@pytest.mark.parametrize("t", [-1, 86400])
def test_time_seconds_range(t):
    """
    Test type: Negative

    Contract rule:
      time_s must be in [0, 86399]

    Why test -1 and 86400
    ---------------------
    - -1 catches negative or uninitialized values
    - 86400 catches off-by-one errors (exactly one second after the day ends)
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(time_s=t))


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_prices_must_be_positive(field):
    """
    Test type: Negative

    Contract rule:
      open/high/low/close must be > 0 (non-zero positive)

    Why parametrize
    ---------------
    This is the same rule applied to 4 different fields.
    Parametrization keeps tests consistent and avoids copy-paste.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(**{field: 0.0}))


def test_high_ge_open():
    """
    Test type: Negative

    Contract rule:
      high must be >= open

    Why test this specific relationship
    -----------------------------------
    This is a fundamental market invariant per bar; downstream volatility
    features can break if violated.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(open=100.0, high=99.9))


# 🟩 ADDED
@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_OHLC_type(field):
    """
    Test type: Negative

    Contract rule:
      Open , High , Low, Close are instance of float

    Why parametrize
    ---------------
    This is the same rule applied to 4 different fields.
    Parametrization keeps tests consistent and avoids copy-paste.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(**{field: "banana"}))


def test_open_ge_low():
    """
    Test type: Negative

    Contract rule:
      open must be >= low

    Again: ensures consistent OHLC relationship.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(open=99.0, low=99.5))


def test_close_within_low_high():
    """
    Test type: Negative

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


@pytest.mark.parametrize("field", ["up", "down"])
def test_up_down_non_negative(field):
    """
    Test type: Negative

    Contract rule:
      up/down must be >= 0

    Why it matters
    --------------
    Negative counts indicate upstream encoding bugs or misinterpretation of fields.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(**{field: -1}))


# 🟩 ADDED
@pytest.mark.parametrize("field", ["up", "down"])
def test_up_down_type(field):
    """
    Test type: Negative

    Contract rule:
      up/down type must be int

    Why it matters
    --------------
    non int numbers are not volume
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(**{field: 2.34}))


def test_vwap_non_negative():
    """
    Test type: Negative

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


def test_bar_num_non_negative():
    """
    Test type: Negative

    Contract rule:
      bar_num must be >= 0

    Why it matters
    --------------
    Negative bar numbers usually indicate uninitialized values or session bugs.
    """
    with pytest.raises(ContractError):
        validate_bar(make_bar(bar_num=-1))


def test_sequence_monotonic_same_symbol_date():
    """
    Test type: Mixed (Positive + Negative)

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


def test_sequence_reset_allowed_new_date_or_symbol():
    """
    Test type: Positive

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


def test_parse_csv_line_good():
    """
    Test type: Positive

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


def test_parse_csv_line_bad_field_count():
    """
    Test type: Negative

    parse_csv_line contract:
      must have exactly 11 fields

    Why test this
    -------------
    Your TCP buffer split and transport can produce partial lines or corruption.
    This ensures you fail fast and clearly.
    """
    with pytest.raises(DecodeError):
        parse_csv_line("a,b,c")


def test_parse_csv_line_cast_error():
    """
    Test type: Negative

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


def test_parse_csv_line_contract_error():
    """
    Test type: Negative

    parse_csv_line should raise ContractError when data casts fine
    but violates invariants.

    Example:
      open = -1.0  (casts to float fine, but violates open > 0)
    """
    line = make_csv(open=-1.0)
    with pytest.raises(ContractError):
        parse_csv_line(line)


def test_bar_from_redis_fields_bytes_ok():
    """
    Test type: Positive

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


def test_bar_from_redis_fields_missing_key():
    """
    Test type: Negative

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
