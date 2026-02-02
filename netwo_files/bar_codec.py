# bar_codec.py
"""
bar_codec.py
============

This module handles "transport <-> typed object" conversions.

Why this exists
---------------
TCP and Redis are transport layers. They typically carry bytes/strings.
Your contract invariants require numeric types (int/float) to compare correctly.

Example problem if you don't cast:
---------------------------------
If bar_num is stored as strings:
  "9" > "10"  -> True   (WRONG because strings compare lexicographically)

So every consumer that does math must reconstruct types.

What this module does
---------------------
1) CSV line (string) -> Bar (typed)  [parse + cast]
2) Redis fields (bytes/str mapping) -> Bar (typed) [decode + cast]
3) Bar (typed) -> Redis fields (canonical strings) [encode]

Important truth about Redis types
---------------------------------
Redis Streams store field values as bytes. There is no type system.
Even if you pass an int/float to redis-py, it gets serialized to bytes.

So the point is NOT that Redis becomes "typed".
The point is:
- you validate correctly before inserting
- you decode + cast consistently when reading
- you standardize encoding for sanity/debugging


The functions Summary <----------------------------

TCP (transport: CSV over TCP)
-----------------------------

1) parse_csv_line(line) -> Bar
✅ TCP parser + type caster + validator
Takes a CSV string from TCP
Splits
Casts into int/float
Returns a typed Bar


General (shared by TCP + Redis)
-------------------------------

2) DecodeError
✅ signals decoding/casting failures due to bad format
Difference vs ContractError:
- DecodeError: "I couldn't even parse/cast it" (e.g., float("abc"))
- ContractError: "I parsed it, but it violates invariants" (e.g., open <= 0)

3) _as_str(x) -> str
✅ utility decoder
bytes → string helper so Redis decoding is clean


Redis (transport: Streams / XREAD)
----------------------------------

4) bar_from_redis_fields(fields) -> Bar
✅ Redis parser + type caster + validator
Takes Redis stream dict {bytes:bytes} or {str:str}
Decodes bytes
Casts into int/float
Returns a typed Bar

5) bar_to_redis_fields(bar) -> dict
✅ Redis encoder
Takes a typed Bar
Converts values into canonical strings
Ready for xadd()


-------------------------------------------------------------------------------
UPDATE: XREAD payload support (pure parsing)
-------------------------------------------------------------------------------

Context
-------
redis-py XREAD does NOT return a flat dict of fields. It returns a nested
transport shape:

    [
      (stream_name, [
          (entry_id, {field: value, ...}),
          ...
      ]),
      ...
    ]

So even though bar_from_redis_fields() already builds a Bar from ONE field map,
you still need an adapter that:
- unwraps the XREAD nesting
- normalizes bytes/str to str
- calls bar_from_redis_fields() for each entry

This adapter must be pure (no Redis client, no I/O) so it can be tested and
used safely inside a Clean Architecture boundary layer.

New components added
--------------------

6) XReadShapeError
✅ signals a malformed XREAD structure
This is intentionally separate from DecodeError:
- XReadShapeError: the OUTER structure is wrong (list/tuple nesting)
- DecodeError: fields exist, but casting/parsing failed (float("abc"), missing key)
- ContractError (from validate_bar): fields parsed, but invariants failed

7) XReadBatch
✅ typed container for parse_xread_to_bars output
- bars: flattened list[Bar]
- last_ids: dict[stream_name -> last entry_id]

8) parse_xread_to_bars(xread_result) -> XReadBatch
✅ XREAD structure parser + Bar builder delegator (pure)
Takes raw output from redis_client.xread(...)
Flattens all entries across streams into list[Bar]
Also returns per-stream "last seen entry id" so the caller can advance offsets


"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from netwo_files.bar_contract import Bar, validate_bar


# #1 --------------------------------------------------------------------------
def parse_csv_line(line: str) -> Bar:
    """
    Parse and validate a CSV bar line.

    Expected schema (11 fields):
      symbol,date,time_s,open,high,low,close,up,down,vwap,bar_num

    What this function guarantees if it returns:
    -------------------------------------------
    - All fields are cast to correct Python types.
    - All contract invariants are validated (via validate_bar).
    - The result is a fully typed Bar ready for math/feature engineering.

    What it does NOT guarantee:
    ---------------------------
    - Any sequence-level invariants (like bar_num monotonicity). That requires
      state across bars, handled elsewhere (validate_sequence).
    """
    parts = [p.strip() for p in line.strip().split(",")]
    if len(parts) != 11:
        raise DecodeError(f"expected 11 fields, got {len(parts)}")

    try:
        b = Bar(
            symbol=parts[0],
            date=int(parts[1]),
            time_s=int(parts[2]),
            open=float(parts[3]),
            high=float(parts[4]),
            low=float(parts[5]),
            close=float(parts[6]),
            up=int(parts[7]),
            down=int(parts[8]),
            vwap=float(parts[9]),
            bar_num=int(parts[10]),
        )
    except Exception as e:
        # If casting fails, it means the line is malformed or corrupted.
        # Example: open="abc"
        raise DecodeError(f"type casting failed: {e}") from e

    # Now enforce your invariants on typed values
    validate_bar(b)
    return b


# #2 --------------------------------------------------------------------------
class DecodeError(ValueError):
    """
    Raised when decoding/casting fails due to bad format.

    Difference vs ContractError:
    ----------------------------
    - DecodeError: "I couldn't even parse/cast it" (e.g., float("abc"))
    - ContractError: "I parsed it, but it violates invariants" (e.g., open <= 0)
    """

    pass


# #3 --------------------------------------------------------------------------
def _as_str(x: Any) -> str:
    """
    Convert Redis-returned bytes (or any value) into a Python str.

    Why needed:
    -----------
    - redis-py often returns bytes for both keys and values.
    - Your code wants to treat them uniformly as strings before casting.
    """
    if isinstance(x, bytes):
        return x.decode("utf-8", errors="strict")
    return str(x)


# #4 --------------------------------------------------------------------------
def bar_from_redis_fields(fields: Mapping[Any, Any]) -> Bar:
    """
    Decode Redis Stream fields into a typed Bar.

    Input shape:
    -----------
    redis-py typically returns something like:
      {b"open": b"100.5", b"up": b"10", ...}

    This function:
    --------------
    1) converts keys/values to strings
    2) checks that all required keys exist
    3) casts strings to correct numeric types
    4) validates invariants via validate_bar
    """
    f: Dict[str, str] = {_as_str(k): _as_str(v) for k, v in fields.items()}

    required = [
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
    ]
    missing = [k for k in required if k not in f]
    if missing:
        raise DecodeError(f"missing fields: {missing}")

    try:
        b = Bar(
            symbol=f["symbol"],
            date=int(f["date"]),
            time_s=int(f["time"]),
            open=float(f["open"]),
            high=float(f["high"]),
            low=float(f["low"]),
            close=float(f["close"]),
            up=int(f["up"]),
            down=int(f["down"]),
            vwap=float(f["vwap"]),
            bar_num=int(f["bar_num"]),
        )
    except Exception as e:
        raise DecodeError(f"type casting failed: {e}") from e

    validate_bar(b)
    return b


# #5 --------------------------------------------------------------------------
def bar_to_redis_fields(b: Bar) -> Dict[str, str]:
    """
    Encode a typed Bar into Redis Stream fields.

    Why encode to *strings* explicitly:
    ----------------------------------
    Redis Streams store bytes anyway.
    Explicit conversion makes encoding predictable and consistent,
    and makes debugging with redis-cli or stream readers easier.

    Canonical encoding choices:
    ---------------------------
    - date: always zero-padded 6 digits (e.g. 990412, 000123)
    - ints: str(int)
    - floats: repr(float) for a stable representation suitable for round-trip

    NOTE:
    -----
    If you want fixed decimals (like 2 dp), you can switch from repr() to format(),
    but that introduces rounding. repr() keeps more precision.
    """
    validate_bar(b)

    return {
        "symbol": b.symbol,
        "date": f"{b.date:06d}",
        "time": str(b.time_s),
        "open": repr(b.open),
        "high": repr(b.high),
        "low": repr(b.low),
        "close": repr(b.close),
        "up": str(b.up),
        "down": str(b.down),
        "vwap": repr(b.vwap),
        "bar_num": str(b.bar_num),
    }


# #6 --------------------------------------------------------------------------
class XReadShapeError(ValueError):
    """
    Raised when the redis-py XREAD structure is not in the expected shape.
    This is different from DecodeError, which is about field casting/parsing.
    """

    pass


# #7 --------------------------------------------------------------------------
@dataclass(frozen=True)
class XReadBatch:
    """
    Typed result of parsing a single XREAD payload (pure).

    bars:
      Flattened Bars in the order they appear in the XREAD payload.

    last_ids:
      Per-stream "last seen id" (the last entry_id observed for that stream),
      useful for the caller to build the next XREAD call.
    """

    bars: list[Bar]
    last_ids: dict[str, str]


# #8 --------------------------------------------------------------------------
def parse_xread_to_bars(xread_result: Any) -> XReadBatch:
    """
    Pure function: Parse redis-py XREAD result into typed Bars using bar_codec.

    Parameters
    ----------
    xread_result:
        Raw output of redis_client.xread(...).

        Typical shape:
          [
            (stream_name, [
                (entry_id, {field: value, ...}),
                ...
            ]),
            ...
          ]

        - stream_name / entry_id / dict keys / dict values may be bytes or str.
        - field maps are decoded/cast by bar_from_redis_fields().

    Returns
    -------
    XReadBatch
        bars: flattened list[Bar]
        last_ids: dict[str, str] mapping stream -> last entry id in this payload

    Raises
    ------
    XReadShapeError:
        If xread_result is malformed structurally.
    DecodeError:
        If a field map exists but cannot be cast/parsed into a Bar.
    ContractError (from validate_bar inside bar_codec):
        If a bar is parseable but violates invariants.
    """
    if xread_result is None:
        return XReadBatch(bars=[], last_ids={})

    if not isinstance(xread_result, list):
        raise XReadShapeError(
            f"XREAD result must be a list, got {type(xread_result).__name__}"
        )

    out: list[Bar] = []
    last_ids: dict[str, str] = {}

    for i, stream_block in enumerate(xread_result):
        if not (isinstance(stream_block, (tuple, list)) and len(stream_block) == 2):
            raise XReadShapeError(f"XREAD item[{i}] must be (stream, entries)")

        raw_stream, entries = stream_block
        stream = _as_str(raw_stream)

        if not isinstance(entries, list):
            raise XReadShapeError(f"XREAD entries for stream '{stream}' must be a list")

        for j, entry in enumerate(entries):
            if not (isinstance(entry, (tuple, list)) and len(entry) == 2):
                raise XReadShapeError(
                    f"XREAD entry[{stream}][{j}] must be (id, fields)"
                )

            raw_id, fields = entry
            entry_id = _as_str(raw_id)

            if not isinstance(fields, Mapping):
                raise XReadShapeError(
                    f"XREAD fields for entry '{entry_id}' must be a mapping"
                )

            # Delegate the real decoding/casting/validation to your existing codec.
            b = bar_from_redis_fields(fields)
            out.append(b)

            # Update last seen id per stream.
            last_ids[stream] = entry_id

    return XReadBatch(bars=out, last_ids=last_ids)
