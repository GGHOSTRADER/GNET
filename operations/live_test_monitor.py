"""Passive evidence recorder for a bounded GNET live-market simulation test.

The monitor never submits orders and never connects to the four GNET TCP
listeners. It observes Redis plus Windows' listening-socket table, which avoids
interfering with the TradeStation DLL clients.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any

import redis

from config.setting import (
    REDIS1_CANDIDATE_STREAM,
    REDIS1_DECISION_STREAM,
    REDIS1_FEATURES_TRANSFORMER_STREAM,
    REDIS1_FEATURES_VP_STREAM,
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_ROUTER_CANDIDATE_GROUP,
    REDIS1_ROUTER_READY_KEY,
    REDIS1_SIGNAL_DECISION_GROUP,
    REDIS1_TICK_RAW_STREAM,
    REDIS1_TICK_VALIDATED_STREAM,
    REDIS1_STREAM_NAME,
)


TCP_PORTS = (9009, 9010, 9011, 9012)
STREAMS = (
    REDIS1_STREAM_NAME,
    REDIS1_TICK_RAW_STREAM,
    REDIS1_TICK_VALIDATED_STREAM,
    REDIS1_FEATURES_TRANSFORMER_STREAM,
    REDIS1_FEATURES_VP_STREAM,
    REDIS1_CANDIDATE_STREAM,
    REDIS1_DECISION_STREAM,
)
EVENT_STREAMS = (REDIS1_CANDIDATE_STREAM, REDIS1_DECISION_STREAM)
HEARTBEAT_COLUMNS = (
    "observed_at",
    "redis_ok",
    "router_ready",
    "port_9009",
    "port_9010",
    "port_9011",
    "port_9012",
    *(f"xlen_{name}" for name in STREAMS),
    "candidate_pending",
    "decision_pending",
)


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _listening_ports() -> set[int]:
    completed = subprocess.run(
        ["netstat.exe", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0:
        return set()
    ports: set[int] = set()
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0].upper() != "TCP":
            continue
        if parts[3].upper() != "LISTENING":
            continue
        try:
            ports.add(int(parts[1].rsplit(":", 1)[1]))
        except (IndexError, ValueError):
            continue
    return ports


def _stream_tail(client: redis.Redis, stream: str) -> str:
    latest = client.xrevrange(stream, count=1)
    return latest[0][0] if latest else "0-0"


def _pending_count(client: redis.Redis, stream: str, group: str) -> int:
    try:
        summary = client.xpending(stream, group)
    except redis.ResponseError:
        return -1
    return int(summary.get("pending", 0))


def _float_field(fields: dict[str, str], name: str) -> float | None:
    value = fields.get(name, "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _new_counters() -> dict[str, Any]:
    return {
        "candidates": 0,
        "decisions": 0,
        "approved": 0,
        "rejected": 0,
        "status_counts": {},
        "router_total_ms": [],
        "inference_ms": [],
    }


def _record_event(
    event_file,
    stream: str,
    entry_id: str,
    fields: dict[str, str],
    counters: dict[str, Any],
) -> None:
    event = {
        "observed_at": _iso_now(),
        "stream": stream,
        "entry_id": entry_id,
        "fields": fields,
    }
    event_file.write(json.dumps(event, sort_keys=True) + "\n")
    event_file.flush()
    if stream == REDIS1_CANDIDATE_STREAM:
        counters["candidates"] += 1
        return
    counters["decisions"] += 1
    if fields.get("approved") == "1":
        counters["approved"] += 1
    else:
        counters["rejected"] += 1
    status = fields.get("status", "missing")
    counts = counters["status_counts"]
    counts[status] = int(counts.get(status, 0)) + 1
    for name in ("router_total_ms", "inference_ms"):
        value = _float_field(fields, name)
        if value is not None:
            counters[name].append(value)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return round(ordered[index], 3)


def _summary(
    run: dict[str, Any],
    counters: dict[str, Any],
    latest_heartbeat: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "started_at": run["started_at"],
        "planned_end_at": run["planned_end_at"],
        "last_updated_at": _iso_now(),
        "simulation_confirmed": True,
        "candidates": counters["candidates"],
        "decisions": counters["decisions"],
        "approved": counters["approved"],
        "rejected": counters["rejected"],
        "status_counts": counters["status_counts"],
        "router_total_ms": {
            "p50": _percentile(counters["router_total_ms"], 0.50),
            "p95": _percentile(counters["router_total_ms"], 0.95),
            "p99": _percentile(counters["router_total_ms"], 0.99),
            "max": round(max(counters["router_total_ms"]), 3)
            if counters["router_total_ms"]
            else None,
        },
        "inference_ms": {
            "p50": _percentile(counters["inference_ms"], 0.50),
            "p95": _percentile(counters["inference_ms"], 0.95),
            "p99": _percentile(counters["inference_ms"], 0.99),
            "max": round(max(counters["inference_ms"]), 3)
            if counters["inference_ms"]
            else None,
        },
        "latest_heartbeat": latest_heartbeat,
    }


def _heartbeat(client: redis.Redis) -> dict[str, Any]:
    listening = _listening_ports()
    row: dict[str, Any] = {
        "observed_at": _iso_now(),
        "redis_ok": 1,
        "router_ready": 1 if client.get(REDIS1_ROUTER_READY_KEY) == "1" else 0,
        **{f"port_{port}": 1 if port in listening else 0 for port in TCP_PORTS},
    }
    for stream in STREAMS:
        row[f"xlen_{stream}"] = client.xlen(stream)
    row["candidate_pending"] = _pending_count(
        client, REDIS1_CANDIDATE_STREAM, REDIS1_ROUTER_CANDIDATE_GROUP
    )
    row["decision_pending"] = _pending_count(
        client, REDIS1_DECISION_STREAM, REDIS1_SIGNAL_DECISION_GROUP
    )
    return row


def run(output_dir: Path, duration_days: float, interval_seconds: int) -> None:
    if duration_days <= 0:
        raise ValueError("duration_days must be positive")
    if interval_seconds < 10:
        raise ValueError("interval_seconds must be at least 10")
    output_dir.mkdir(parents=True, exist_ok=False)
    client = redis.Redis(
        host=REDIS1_HOST,
        port=REDIS1_PORT,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=5,
    )
    if not client.ping():
        raise RuntimeError("Redis did not answer PING")

    started = datetime.now().astimezone()
    planned_end = started + timedelta(days=duration_days)
    registry = Path("model_registry/MA2CrossLE/registry.json").resolve()
    run_record = {
        "run_id": output_dir.name,
        "started_at": started.isoformat(timespec="seconds"),
        "planned_end_at": planned_end.isoformat(timespec="seconds"),
        "duration_days": duration_days,
        "interval_seconds": interval_seconds,
        "simulation_confirmed": True,
        "redis": f"{REDIS1_HOST}:{REDIS1_PORT}",
        "registry_path": str(registry),
        "registry_sha256": _sha256(registry),
        "initial_stream_ids": {
            stream: _stream_tail(client, stream) for stream in EVENT_STREAMS
        },
    }
    _atomic_json(output_dir / "run_manifest.json", run_record)
    last_ids = dict(run_record["initial_stream_ids"])
    counters = _new_counters()
    latest_heartbeat: dict[str, Any] = {}
    next_heartbeat = 0.0

    heartbeat_path = output_dir / "heartbeat.csv"
    events_path = output_dir / "events.jsonl"
    summary_path = output_dir / "summary.json"
    with heartbeat_path.open("w", newline="", encoding="utf-8") as heartbeat_file, events_path.open(
        "a", encoding="utf-8"
    ) as event_file:
        writer = csv.DictWriter(heartbeat_file, fieldnames=HEARTBEAT_COLUMNS)
        writer.writeheader()
        print(f"[live_test] recording to {output_dir}")
        print(f"[live_test] planned end: {planned_end.isoformat(timespec='seconds')}")
        try:
            while datetime.now().astimezone() < planned_end:
                try:
                    results = client.xread(last_ids, count=250, block=1000)
                except redis.RedisError:
                    results = []
                    time.sleep(1)
                for stream, entries in results:
                    for entry_id, fields in entries:
                        last_ids[stream] = entry_id
                        _record_event(event_file, stream, entry_id, fields, counters)
                now = time.monotonic()
                if now < next_heartbeat:
                    continue
                try:
                    latest_heartbeat = _heartbeat(client)
                except (redis.RedisError, subprocess.SubprocessError):
                    listening = _listening_ports()
                    latest_heartbeat = {
                        name: "" for name in HEARTBEAT_COLUMNS
                    }
                    latest_heartbeat.update(
                        {
                            "observed_at": _iso_now(),
                            "redis_ok": 0,
                            **{
                                f"port_{port}": 1 if port in listening else 0
                                for port in TCP_PORTS
                            },
                        }
                    )
                writer.writerow(latest_heartbeat)
                heartbeat_file.flush()
                _atomic_json(
                    summary_path,
                    _summary(run_record, counters, latest_heartbeat),
                )
                next_heartbeat = now + interval_seconds
        except KeyboardInterrupt:
            print("[live_test] stopped by operator")
        finally:
            final = _summary(run_record, counters, latest_heartbeat)
            final["finished_at"] = _iso_now()
            final["completed_full_duration"] = (
                datetime.now().astimezone() >= planned_end
            )
            _atomic_json(summary_path, final)
            print(f"[live_test] final summary: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-days", type=float, default=7.0)
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    run(args.output_dir, args.duration_days, args.interval_seconds)


if __name__ == "__main__":
    main()
