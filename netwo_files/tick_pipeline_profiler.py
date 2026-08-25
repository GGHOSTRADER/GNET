"""Passive latency profiler for the live tick-to-volume-profile pipeline."""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from config.setting import (
    REDIS1_FEATURES_VP_STREAM,
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_TICK_RAW_STREAM,
    REDIS1_TICK_VALIDATED_STREAM,
)
from netwo_files.redis_tool import get_redis_connection
from netwo_files.tick_codec import parse_raw_tick_line


TickKey = tuple[str, int, int, int]


@dataclass(frozen=True)
class PipelineTimes:
    tcp_received_ms: float | None = None
    raw_published_ms: float | None = None
    validator_received_ms: float | None = None
    validated_published_ms: float | None = None
    feature_published_ms: float | None = None


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    return str(value)


def _fields(raw_fields: Mapping[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw_fields.items()}


def _stream_id_ms(entry_id: Any) -> float:
    return float(_text(entry_id).split("-", 1)[0])


def _tick_key(symbol: str, date: int, time_s: int, bar_num: int) -> TickKey:
    return symbol, date, time_s, bar_num


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _summary(label: str, values: Iterable[float]) -> str:
    clean = [value for value in values if value >= 0]
    if not clean:
        return f"{label:<34} n=0"
    return (
        f"{label:<34} n={len(clean):<6} "
        f"p50={_percentile(clean, 0.50):8.3f} ms  "
        f"p95={_percentile(clean, 0.95):8.3f} ms  "
        f"p99={_percentile(clean, 0.99):8.3f} ms  "
        f"max={max(clean):8.3f} ms"
    )


def collect_pipeline_times(redis_client: Any, count: int) -> list[PipelineTimes]:
    """Join recent raw, validated, and VP records by exact tick identity."""
    raw_by_key: dict[TickKey, PipelineTimes] = {}
    for entry_id, raw_fields in redis_client.xrevrange(
        REDIS1_TICK_RAW_STREAM, count=count
    ):
        fields = _fields(raw_fields)
        try:
            tick = parse_raw_tick_line(fields["raw_tick"])
        except (KeyError, ValueError):
            continue
        tcp_ns = fields.get("tcp_received_ns")
        raw_by_key[_tick_key(tick.symbol, tick.date, tick.time_s, tick.bar_num)] = (
            PipelineTimes(
                tcp_received_ms=float(tcp_ns) / 1_000_000 if tcp_ns else None,
                raw_published_ms=_stream_id_ms(entry_id),
            )
        )

    validated_by_key: dict[TickKey, PipelineTimes] = {}
    for entry_id, raw_fields in redis_client.xrevrange(
        REDIS1_TICK_VALIDATED_STREAM, count=count
    ):
        fields = _fields(raw_fields)
        try:
            key = _tick_key(
                fields["symbol"],
                int(fields["date"]),
                int(fields["time"]),
                int(fields["bar_num"]),
            )
        except (KeyError, ValueError):
            continue
        existing = raw_by_key.get(key, PipelineTimes())
        validator_ns = fields.get("validator_received_ns")
        validated_by_key[key] = PipelineTimes(
            tcp_received_ms=existing.tcp_received_ms,
            raw_published_ms=existing.raw_published_ms,
            validator_received_ms=(
                float(validator_ns) / 1_000_000 if validator_ns else None
            ),
            validated_published_ms=_stream_id_ms(entry_id),
        )

    feature_by_bar: dict[tuple[str, int, int], float] = {}
    for entry_id, raw_fields in redis_client.xrevrange(
        REDIS1_FEATURES_VP_STREAM, count=count
    ):
        fields = _fields(raw_fields)
        try:
            key = fields["symbol"], int(fields["date"]), int(fields["bar_num"])
        except (KeyError, ValueError):
            continue
        feature_by_bar.setdefault(key, _stream_id_ms(entry_id))

    joined: list[PipelineTimes] = []
    for key, times in validated_by_key.items():
        feature_ms = feature_by_bar.get((key[0], key[1], key[3]))
        if feature_ms is None:
            continue
        joined.append(
            PipelineTimes(
                tcp_received_ms=times.tcp_received_ms,
                raw_published_ms=times.raw_published_ms,
                validator_received_ms=times.validator_received_ms,
                validated_published_ms=times.validated_published_ms,
                feature_published_ms=feature_ms,
            )
        )
    return joined


def format_report(samples: list[PipelineTimes]) -> str:
    """Format percentile measurements for each observable pipeline hop."""
    def durations(start: str, end: str) -> list[float]:
        result = []
        for sample in samples:
            first = getattr(sample, start)
            last = getattr(sample, end)
            if first is not None and last is not None:
                result.append(last - first)
        return result

    lines = [
        f"GNET tick pipeline latency — {len(samples)} exact VP-producing ticks",
        _summary(
            "TCP line -> raw Redis publish",
            durations("tcp_received_ms", "raw_published_ms"),
        ),
        _summary(
            "raw Redis -> validator starts",
            durations("raw_published_ms", "validator_received_ms"),
        ),
        _summary(
            "validator start -> validated Redis",
            durations("validator_received_ms", "validated_published_ms"),
        ),
        _summary(
            "validated Redis -> VP Redis",
            durations("validated_published_ms", "feature_published_ms"),
        ),
        _summary(
            "TCP line -> VP Redis total",
            durations("tcp_received_ms", "feature_published_ms"),
        ),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5_000)
    parser.add_argument("--refresh-s", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.count <= 0 or args.refresh_s <= 0:
        parser.error("--count and --refresh-s must be positive")

    redis_client = get_redis_connection(
        REDIS1_HOST, REDIS1_PORT, REDIS1_TICK_RAW_STREAM
    )
    while True:
        report = format_report(collect_pipeline_times(redis_client, args.count))
        print("\033[2J\033[H" + report, flush=True)
        if args.once:
            return
        time.sleep(args.refresh_s)


if __name__ == "__main__":
    main()
