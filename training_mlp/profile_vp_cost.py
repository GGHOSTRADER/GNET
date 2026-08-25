"""Profile canonical VP update and snapshot costs on historical tick Parquets."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from feat_files.canonical_volume_profile import VolumeProfileEngine


DEFAULT_INPUT_ROOT = Path("historical_vp/prepared/parquet")
DEFAULT_MANIFEST = Path("historical_vp/features/manifest.json")
DEFAULT_OUTPUT = Path("historical_vp/features/profile/vp_cost_profile.json")


@dataclass(slots=True)
class _Tick:
    symbol: str = "@ES"
    date: int = 0
    time_s: int = 0
    high: float = 0.0
    up: int = 0
    down: int = 0
    bar_num: int = 0


def _packed_date(value: date) -> int:
    return (value.year - 1900) * 10000 + value.month * 100 + value.day


def select_activity_sessions(manifest_path: Path) -> list[str]:
    """Return lowest-, median-, and highest-row sessions."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    partitions = sorted(manifest["partitions"], key=lambda row: row["input_rows"])
    return list(
        dict.fromkeys(
            (
                partitions[0]["session_date"],
                partitions[len(partitions) // 2]["session_date"],
                partitions[-1]["session_date"],
            )
        )
    )


def _load_arrays(path: Path) -> dict[str, np.ndarray]:
    table = pq.read_table(
        path,
        columns=["calendar_date", "time_s", "price", "up", "down", "source_row"],
    )
    calendar_dates = table["calendar_date"].to_pylist()
    packed = np.fromiter(
        (_packed_date(value) for value in calendar_dates),
        dtype=np.int64,
        count=len(calendar_dates),
    )
    return {
        "date": packed,
        "time_s": table["time_s"].to_numpy(zero_copy_only=False),
        "price": table["price"].to_numpy(zero_copy_only=False),
        "up": table["up"].to_numpy(zero_copy_only=False),
        "down": table["down"].to_numpy(zero_copy_only=False),
        "source_row": table["source_row"].to_numpy(zero_copy_only=False),
    }


def _interval_keys(arrays: dict[str, np.ndarray], interval_s: int) -> np.ndarray:
    return arrays["date"] * (86400 // interval_s) + arrays["time_s"] // interval_s


def _three_preview_indices(
    final_indices: np.ndarray,
    interval_keys: np.ndarray,
) -> set[int]:
    """Select three ordered tick proxies per eligible final second."""
    selected: set[int] = set()
    if final_indices.size == 0:
        return selected
    boundaries = np.flatnonzero(np.diff(interval_keys[final_indices])) + 1
    for group in np.split(final_indices, boundaries):
        positions = np.clip(
            np.rint((len(group) - 1) * np.array([0.25, 0.60, 0.90])).astype(int),
            0,
            len(group) - 1,
        )
        selected.update(int(group[position]) for position in np.unique(positions))
    return selected


def _run_policy(
    arrays: dict[str, np.ndarray],
    *,
    policy: str,
    interval_s: int,
    tick_size: float,
    range_ticks: int,
) -> dict[str, float | int | str]:
    engine = VolumeProfileEngine(tick_size=tick_size, range_ticks=range_ticks)
    tick = _Tick()
    keys = _interval_keys(arrays, interval_s)
    final_mask = arrays["time_s"] % interval_s == interval_s - 1
    final_indices = np.flatnonzero(final_mask)
    preview_indices = (
        _three_preview_indices(final_indices, keys) if policy == "three_previews" else set()
    )
    pending_interval: int | None = None
    snapshots = 0
    started = time.perf_counter()
    for index in range(len(arrays["time_s"])):
        current_key = int(keys[index])
        if pending_interval is not None and current_key != pending_interval:
            engine.snapshot(commit=True)
            snapshots += 1
            pending_interval = None

        tick.date = int(arrays["date"][index])
        tick.time_s = int(arrays["time_s"][index])
        tick.high = float(arrays["price"][index])
        tick.up = int(arrays["up"][index])
        tick.down = int(arrays["down"][index])
        tick.bar_num = int(arrays["source_row"][index])
        engine.update(tick)

        if policy == "every_final_tick" and final_mask[index]:
            engine.snapshot(commit=True)
            snapshots += 1
        elif policy == "three_previews" and index in preview_indices:
            engine.snapshot(commit=False)
            snapshots += 1
            pending_interval = current_key
        elif policy == "one_commit" and final_mask[index]:
            pending_interval = current_key

    if pending_interval is not None:
        engine.snapshot(commit=True)
        snapshots += 1
    elapsed = time.perf_counter() - started
    return {
        "policy": policy,
        "ticks": len(arrays["time_s"]),
        "snapshots": snapshots,
        "elapsed_seconds": elapsed,
        "ticks_per_second": len(arrays["time_s"]) / elapsed,
    }


def profile_session(
    path: Path,
    *,
    interval_s: int = 30,
    tick_size: float = 0.25,
    range_ticks: int = 600,
) -> dict[str, object]:
    arrays = _load_arrays(path)
    keys = _interval_keys(arrays, interval_s)
    final_indices = np.flatnonzero(
        arrays["time_s"] % interval_s == interval_s - 1
    )
    boundaries = np.flatnonzero(np.diff(keys[final_indices])) + 1
    counts = np.asarray([len(group) for group in np.split(final_indices, boundaries)])
    policies = [
        _run_policy(
            arrays,
            policy=policy,
            interval_s=interval_s,
            tick_size=tick_size,
            range_ticks=range_ticks,
        )
        for policy in ("update_only", "one_commit", "three_previews", "every_final_tick")
    ]
    baseline = float(policies[0]["elapsed_seconds"])
    for result in policies:
        snapshots = int(result["snapshots"])
        overhead = max(0.0, float(result["elapsed_seconds"]) - baseline)
        result["snapshot_overhead_seconds"] = overhead
        result["estimated_ms_per_snapshot"] = (
            overhead * 1000.0 / snapshots if snapshots else 0.0
        )
    return {
        "session_date": path.parent.name.removeprefix("session_date="),
        "input_path": str(path),
        "ticks": len(arrays["time_s"]),
        "eligible_intervals": len(counts),
        "final_second_ticks": int(counts.sum()),
        "final_ticks_per_interval": {
            "mean": float(counts.mean()),
            "p50": float(np.percentile(counts, 50)),
            "p95": float(np.percentile(counts, 95)),
            "p99": float(np.percentile(counts, 99)),
            "max": int(counts.max()),
        },
        "policies": policies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sessions", nargs="*")
    args = parser.parse_args()
    sessions = args.sessions or select_activity_sessions(args.manifest)
    results = []
    for session in sessions:
        path = args.input_root / f"session_date={session}" / "ticks.parquet"
        result = profile_session(path)
        results.append(result)
        print(
            f"{session}: {result['ticks']:,} ticks, "
            f"{result['final_second_ticks']:,} final-second ticks"
        )
        for policy in result["policies"]:
            print(
                f"  {policy['policy']:<18} {policy['elapsed_seconds']:>8.3f}s "
                f"snapshots={policy['snapshots']:>7,}"
            )
    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "historical_timestamp_precision": "whole_second",
        "three_preview_proxy_quantiles": [0.25, 0.60, 0.90],
        "sessions": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved -> {args.output}")


if __name__ == "__main__":
    main()
