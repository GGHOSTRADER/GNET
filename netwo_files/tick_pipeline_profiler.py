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


@dataclass(frozen=True)
class PipelineTimes:
    tcp_received_ms: float | None = None
    raw_published_ms: float | None = None
    validator_received_ms: float | None = None
    validated_published_ms: float | None = None
    feature_published_ms: float | None = None
    snapshot_started_ms: float | None = None
    snapshot_finished_ms: float | None = None


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
    """Collect exact-hop samples using propagated Redis provenance IDs."""
    raw_by_id: dict[str, PipelineTimes] = {}
    for entry_id, raw_fields in redis_client.xrevrange(
        REDIS1_TICK_RAW_STREAM, count=count
    ):
        fields = _fields(raw_fields)
        tcp_ns = fields.get("tcp_received_ns")
        raw_by_id[_text(entry_id)] = PipelineTimes(
            tcp_received_ms=float(tcp_ns) / 1_000_000 if tcp_ns else None,
            raw_published_ms=_stream_id_ms(entry_id),
        )

    samples: list[PipelineTimes] = []
    for entry_id, raw_fields in redis_client.xrevrange(
        REDIS1_TICK_VALIDATED_STREAM, count=count
    ):
        fields = _fields(raw_fields)
        raw_entry_id = fields.get("raw_entry_id")
        if not raw_entry_id:
            continue
        existing = raw_by_id.get(raw_entry_id)
        if existing is None:
            continue
        validator_ns = fields.get("validator_received_ns")
        samples.append(PipelineTimes(
            tcp_received_ms=existing.tcp_received_ms,
            raw_published_ms=existing.raw_published_ms,
            validator_received_ms=(
                float(validator_ns) / 1_000_000 if validator_ns else None
            ),
            validated_published_ms=_stream_id_ms(entry_id),
        ))

    for entry_id, raw_fields in redis_client.xrevrange(
        REDIS1_FEATURES_VP_STREAM, count=count
    ):
        fields = _fields(raw_fields)
        try:
            source_validated_ms = float(fields["source_validated_published_ms"])
        except (KeyError, ValueError):
            continue
        tcp_ns = fields.get("source_tcp_received_ns")
        validator_ns = fields.get("source_validator_received_ns")
        started_ns = fields.get("snapshot_started_ns")
        finished_ns = fields.get("snapshot_finished_ns")
        raw_source = raw_by_id.get(fields.get("source_raw_entry_id", ""))
        samples.append(
            PipelineTimes(
                tcp_received_ms=(
                    float(tcp_ns) / 1_000_000 if tcp_ns else None
                ),
                raw_published_ms=(
                    raw_source.raw_published_ms if raw_source else None
                ),
                validator_received_ms=(
                    float(validator_ns) / 1_000_000 if validator_ns else None
                ),
                validated_published_ms=source_validated_ms,
                feature_published_ms=_stream_id_ms(entry_id),
                snapshot_started_ms=(
                    float(started_ns) / 1_000_000 if started_ns else None
                ),
                snapshot_finished_ms=(
                    float(finished_ns) / 1_000_000 if finished_ns else None
                ),
            )
        )
    return samples


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
        "GNET tick pipeline latency — exact propagated Redis provenance",
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
            "latest tick age at VP publish",
            durations("validated_published_ms", "feature_published_ms"),
        ),
        _summary(
            "source TCP -> VP publish age",
            durations("tcp_received_ms", "feature_published_ms"),
        ),
        _summary(
            "VP snapshot calculation",
            durations("snapshot_started_ms", "snapshot_finished_ms"),
        ),
        _summary(
            "VP snapshot start -> Redis",
            durations("snapshot_started_ms", "feature_published_ms"),
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
