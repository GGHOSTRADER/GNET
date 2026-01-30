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

The 4 functions Summary <----------------------------


1) parse_csv_line(line) -> Bar
✅ TCP parser + type caster + validator
Takes a CSV string from TCP
Splits
Casts into int/float
Returns a typed Bar

2) bar_from_redis_fields(fields) -> Bar
✅ Redis parser + type caster + validator
Takes Redis stream dict {bytes:bytes} or {str:str}
Decodes bytes
Casts into int/float
Returns a typed Bar

3) bar_to_redis_fields(bar) -> dict
✅ Redis encoder
Takes a typed Bar
Converts values into canonical strings
Ready for xadd()

4) _as_str(x) -> str
✅ utility decoder
bytes → string helper so Redis decoding is clean
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

from netwo_files.bar_contract import Bar, validate_bar


class DecodeError(ValueError):
    """
    Raised when decoding/casting fails due to bad format.

    Difference vs ContractError:
    ----------------------------
    - DecodeError: "I couldn't even parse/cast it" (e.g., float("abc"))
    - ContractError: "I parsed it, but it violates invariants" (e.g., open <= 0)
    """

    pass


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
