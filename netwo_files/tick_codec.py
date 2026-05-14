"""
tick_codec.py
=============

Transport <-> typed Tick conversions for the tick data pipeline.

Flow context
------------
tcp_to_redis_ticks.py pushes raw CSV lines to Redis as:
    {"raw_tick": "AAPL,1260513,34200,5000.25,5000.25,100,50,1234"}

tick_validator.py reads from that raw stream and calls this module to:
    1) Extract the raw_tick field
    2) Split and cast the CSV
    3) Validate via tick_contract.py
    4) Encode back to fields for the validated stream

Function Summary
----------------
1) TickDecodeError                    -- raised when CSV or Redis fields cannot be cast/parsed
2) _as_str(x)                         -- bytes -> str utility for Redis field decoding
3) XReadTickBatch                     -- frozen dataclass: ticks list + last_ids dict
4) parse_raw_tick_line(line)          -- CSV str -> typed Tick (cast + validate via tick_contract)
5) tick_from_redis_fields(fields)     -- Redis validated stream fields -> typed Tick
6) tick_to_redis_fields(tick)         -- typed Tick -> canonical string fields for Redis xadd
7) parse_xread_raw_ticks(result)      -- XREAD from raw stream -> list of (entry_id, raw_line) pairs
8) parse_xread_to_ticks(result)       -- XREAD from validated stream -> XReadTickBatch(ticks, last_ids)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

from netwo_files.tick_contract import Tick, validate_tick


@dataclass(frozen=True)
class XReadTickBatch:
    """Result of parsing a validated tick XREAD payload."""
    ticks:    List[Tick]
    last_ids: Dict[str, str]


# ============================================================
# Errors
# ============================================================

class TickDecodeError(ValueError):
    """
    Raised when casting/parsing fails before contract checks.
    DecodeError: "I couldn't even parse it" (e.g. float("abc"))
    TickContractError: "I parsed it but it violates invariants"
    """
    pass


# ============================================================
# Utilities
# ============================================================

def _as_str(x: Any) -> str:
    if isinstance(x, bytes):
        return x.decode("utf-8", errors="strict")
    return str(x)


# ============================================================
# TCP path: raw CSV -> Tick
# ============================================================

def parse_raw_tick_line(line: str) -> Tick:
    """
    Parse and validate a raw CSV tick line.

    Expected schema (8 fields):
      symbol,date,time_s,high,low,up,down,bar_num
    """
    parts = [p.strip() for p in line.strip().split(",")]
    if len(parts) != 8:
        raise TickDecodeError(f"expected 8 fields, got {len(parts)}")

    try:
        t = Tick(
            symbol=parts[0],
            date=int(parts[1]),
            time_s=int(parts[2]),
            high=float(parts[3]),
            low=float(parts[4]),
            up=int(parts[5]),
            down=int(parts[6]),
            bar_num=int(parts[7]),
        )
    except Exception as e:
        raise TickDecodeError(f"type casting failed: {e}") from e

    validate_tick(t)
    return t


# ============================================================
# Redis validated stream: fields -> Tick
# ============================================================

def tick_from_redis_fields(fields: Mapping[Any, Any]) -> Tick:
    """
    Decode Redis validated stream fields into a typed Tick.
    """
    f: Dict[str, str] = {_as_str(k): _as_str(v) for k, v in fields.items()}

    required = ["symbol", "date", "time", "high", "low", "up", "down", "bar_num"]
    missing = [k for k in required if k not in f]
    if missing:
        raise TickDecodeError(f"missing fields: {missing}")

    try:
        t = Tick(
            symbol=f["symbol"],
            date=int(f["date"]),
            time_s=int(f["time"]),
            high=float(f["high"]),
            low=float(f["low"]),
            up=int(f["up"]),
            down=int(f["down"]),
            bar_num=int(f["bar_num"]),
        )
    except Exception as e:
        raise TickDecodeError(f"type casting failed: {e}") from e

    validate_tick(t)
    return t


# ============================================================
# Redis validated stream: Tick -> fields
# ============================================================

def tick_to_redis_fields(t: Tick) -> Dict[str, str]:
    """
    Encode a typed Tick into Redis Stream fields for the validated stream.
    """
    validate_tick(t)
    return {
        "symbol":  t.symbol,
        "date":    f"{t.date:07d}",
        "time":    str(t.time_s),
        "high":    repr(t.high),
        "low":     repr(t.low),
        "up":      str(t.up),
        "down":    str(t.down),
        "bar_num": str(t.bar_num),
    }


# ============================================================
# Raw stream XREAD: extract raw_tick lines
# ============================================================

def parse_xread_raw_ticks(xread_result: Any) -> List[Tuple[str, str]]:
    """
    Extract (entry_id, raw_tick_line) pairs from a raw stream XREAD result.

    The raw stream stores: {"raw_tick": "AAPL,1260513,..."}
    This function unwraps the XREAD nesting and returns the raw CSV strings.

    Returns list of (entry_id, raw_line) — does NOT parse or validate.
    """
    if xread_result is None:
        return []

    out: List[Tuple[str, str]] = []

    for stream_block in xread_result:
        _stream_name, entries = stream_block
        for entry_id, fields in entries:
            f = {_as_str(k): _as_str(v) for k, v in fields.items()}
            raw_line = f.get("raw_tick", "")
            out.append((_as_str(entry_id), raw_line))

    return out


# ============================================================
# Validated stream XREAD: fields -> XReadTickBatch
# ============================================================

def parse_xread_to_ticks(xread_result: Any) -> XReadTickBatch:
    """
    Parse redis-py XREAD result from tick_data_validated into typed Ticks.

    Mirrors parse_xread_to_bars from bar_codec.py.
    Returns XReadTickBatch(ticks, last_ids).
    """
    if xread_result is None:
        return XReadTickBatch(ticks=[], last_ids={})

    out: List[Tick] = []
    last_ids: Dict[str, str] = {}

    for stream_block in xread_result:
        raw_stream, entries = stream_block
        stream = _as_str(raw_stream)

        for entry_id, fields in entries:
            t = tick_from_redis_fields(fields)
            out.append(t)
            last_ids[stream] = _as_str(entry_id)

    return XReadTickBatch(ticks=out, last_ids=last_ids)
