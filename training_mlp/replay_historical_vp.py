"""Replay prepared tick Parquets through the canonical VP feature engine.

The profile is updated on every tick. During the final second of each configured
interval, later ticks replace earlier previews. Only the freshest preview is
committed and written, so temporal features advance once per interval while the
output retains the lowest-latency final-second semantics used live.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from feat_files.canonical_volume_profile import (
    DEFAULT_RANGE_TICKS,
    VOLUME_PROFILE_FEATURE_NAMES,
    VolumeProfileEngine,
)


class HistoricalVPReplayError(RuntimeError):
    """Raised when historical VP feature replay cannot be completed safely."""


@dataclass(slots=True)
class _ReplayTick:
    symbol: str
    date: int
    time_s: int
    high: float
    up: int
    down: int
    bar_num: int


BASE_OUTPUT_FIELDS = (
    "symbol",
    "session_date",
    "snapshot_timestamp",
    "calendar_date",
    "time_s",
    "interval_start_s",
    "interval_end_s",
    "source_row",
    "bar_num",
    "current_price",
    "tick_size",
    "range_ticks",
    "poc_price",
    "poc_volume",
    "value_area_low",
    "value_area_high",
    "total_volume",
    "n_ticks",
    "extensions",
)
OUTPUT_FIELDS = BASE_OUTPUT_FIELDS + VOLUME_PROFILE_FEATURE_NAMES
INPUT_COLUMNS = (
    "timestamp",
    "calendar_date",
    "session_date",
    "time_s",
    "price",
    "up",
    "down",
    "source_row",
)


def _packed_date(value: date) -> int:
    return (value.year - 1900) * 10000 + value.month * 100 + value.day


def discover_session_parquets(input_root: Path) -> list[Path]:
    """Return prepared session partitions in chronological directory order."""
    paths = sorted(input_root.glob("session_date=*/ticks.parquet"))
    if not paths:
        raise HistoricalVPReplayError(
            f"no session Parquets found under {input_root}"
        )
    return paths


def _session_name(path: Path) -> str:
    prefix = "session_date="
    if not path.parent.name.startswith(prefix):
        raise HistoricalVPReplayError(f"invalid session directory: {path.parent}")
    return path.parent.name[len(prefix) :]


def _result_row(
    engine: VolumeProfileEngine,
    *,
    symbol: str,
    session_name: str,
    timestamp: datetime,
    calendar_date: date,
    time_s: int,
    source_row: int,
    interval_s: int,
) -> dict[str, Any]:
    result = engine.snapshot(commit=True)
    state = engine.state
    if state is None:
        raise HistoricalVPReplayError("canonical engine lost its active state")
    interval_start_s = (time_s // interval_s) * interval_s
    row: dict[str, Any] = {
        "symbol": symbol,
        "session_date": session_name,
        "snapshot_timestamp": timestamp,
        "calendar_date": calendar_date,
        "time_s": time_s,
        "interval_start_s": interval_start_s,
        "interval_end_s": (interval_start_s + interval_s) % 86400,
        "source_row": source_row,
        "bar_num": result.bar_num,
        "current_price": state.last_price,
        "tick_size": result.tick_size,
        "range_ticks": result.range_ticks,
        "poc_price": result.poc_price,
        "poc_volume": result.poc_volume,
        "value_area_low": result.value_area_low,
        "value_area_high": result.value_area_high,
        "total_volume": result.total_volume,
        "n_ticks": result.n_bars,
        "extensions": result.extensions,
    }
    row.update(
        {name: float(getattr(result, name)) for name in VOLUME_PROFILE_FEATURE_NAMES}
    )
    return row


def replay_session(
    input_path: Path,
    output_path: Path,
    *,
    symbol: str = "@ES",
    tick_size: float = 0.25,
    range_ticks: int = 600,
    interval_s: int = 30,
    batch_rows: int = 100_000,
    compression: str = "zstd",
) -> dict[str, Any]:
    """Replay one prepared session and write one freshest row per interval."""
    if tick_size <= 0:
        raise HistoricalVPReplayError("tick_size must be positive")
    if range_ticks <= 0 or interval_s <= 0 or batch_rows <= 0:
        raise HistoricalVPReplayError(
            "range_ticks, interval_s, and batch_rows must be positive"
        )

    session_name = _session_name(input_path)
    engine = VolumeProfileEngine(tick_size=tick_size, range_ticks=range_ticks)
    output_rows: list[dict[str, Any]] = []
    input_rows = 0
    pending_key: int | None = None
    pending_metadata: tuple[datetime, date, int, int] | None = None
    started = time.perf_counter()

    parquet_file = pq.ParquetFile(input_path)
    missing = set(INPUT_COLUMNS) - set(parquet_file.schema_arrow.names)
    if missing:
        raise HistoricalVPReplayError(
            f"{input_path} is missing columns: {', '.join(sorted(missing))}"
        )

    tick = _ReplayTick(symbol, 0, 0, 0.0, 0, 0, 0)
    for batch in parquet_file.iter_batches(
        batch_size=batch_rows,
        columns=list(INPUT_COLUMNS),
    ):
        columns = batch.to_pydict()
        for index in range(batch.num_rows):
            timestamp = columns["timestamp"][index]
            calendar_date = columns["calendar_date"][index]
            session_value = columns["session_date"][index].isoformat()
            time_s = int(columns["time_s"][index])
            source_row = int(columns["source_row"][index])
            absolute_interval = (
                calendar_date.toordinal() * 86400 + time_s
            ) // interval_s

            if pending_key is not None and absolute_interval != pending_key:
                if pending_metadata is None:
                    raise HistoricalVPReplayError("missing pending snapshot metadata")
                output_rows.append(
                    _result_row(
                        engine,
                        symbol=symbol,
                        session_name=session_name,
                        timestamp=pending_metadata[0],
                        calendar_date=pending_metadata[1],
                        time_s=pending_metadata[2],
                        source_row=pending_metadata[3],
                        interval_s=interval_s,
                    )
                )
                pending_key = None
                pending_metadata = None

            if session_value != session_name:
                raise HistoricalVPReplayError(
                    f"partition {session_name} contains session {session_value}"
                )

            tick.date = _packed_date(calendar_date)
            tick.time_s = time_s
            tick.high = float(columns["price"][index])
            tick.up = int(columns["up"][index])
            tick.down = int(columns["down"][index])
            tick.bar_num = source_row
            engine.update(tick)
            input_rows += 1

            if time_s % interval_s == interval_s - 1:
                pending_key = absolute_interval
                pending_metadata = (
                    timestamp,
                    calendar_date,
                    time_s,
                    source_row,
                )

    if pending_key is not None and pending_metadata is not None:
        output_rows.append(
            _result_row(
                engine,
                symbol=symbol,
                session_name=session_name,
                timestamp=pending_metadata[0],
                calendar_date=pending_metadata[1],
                time_s=pending_metadata[2],
                source_row=pending_metadata[3],
                interval_s=interval_s,
            )
        )
    if not output_rows:
        raise HistoricalVPReplayError(
            f"{input_path} contains no ticks in a final interval second"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pylist(output_rows)
    table = table.select(list(OUTPUT_FIELDS))
    pq.write_table(table, temporary_path, compression=compression)
    os.replace(temporary_path, output_path)
    elapsed = time.perf_counter() - started
    return {
        "session_date": session_name,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "input_rows": input_rows,
        "feature_rows": len(output_rows),
        "output_bytes": output_path.stat().st_size,
        "first_snapshot": output_rows[0]["snapshot_timestamp"].isoformat(),
        "last_snapshot": output_rows[-1]["snapshot_timestamp"].isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "rows_per_second": round(input_rows / elapsed, 1) if elapsed > 0 else 0.0,
    }


def _worker(payload: tuple[Any, ...]) -> dict[str, Any]:
    return replay_session(
        payload[0],
        payload[1],
        symbol=payload[2],
        tick_size=payload[3],
        range_ticks=payload[4],
        interval_s=payload[5],
        batch_rows=payload[6],
        compression=payload[7],
    )


def _write_manifests(
    output_root: Path,
    results: list[dict[str, Any]],
    *,
    symbol: str,
    tick_size: float,
    range_ticks: int,
    interval_s: int,
    compression: str,
) -> None:
    ordered = sorted(results, key=lambda item: item["session_date"])
    manifest = {
        "format_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "canonical_module": "feat_files.canonical_volume_profile",
        "snapshot_rule": "freshest tick in final interval second; commit once",
        "symbol": symbol,
        "tick_size": tick_size,
        "range_ticks": range_ticks,
        "interval_s": interval_s,
        "compression": compression,
        "sessions": len(ordered),
        "input_rows": sum(item["input_rows"] for item in ordered),
        "feature_rows": sum(item["feature_rows"] for item in ordered),
        "partitions": ordered,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    with (output_root / "manifest_partitions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ordered[0]))
        writer.writeheader()
        writer.writerows(ordered)


def replay_all(
    input_root: Path,
    output_root: Path,
    *,
    symbol: str = "@ES",
    tick_size: float = 0.25,
    range_ticks: int = 600,
    interval_s: int = 30,
    batch_rows: int = 100_000,
    compression: str = "zstd",
    workers: int = 2,
) -> dict[str, Any]:
    """Replay all prepared sessions in parallel and write output manifests."""
    if workers <= 0:
        raise HistoricalVPReplayError("workers must be positive")
    if output_root.exists():
        raise HistoricalVPReplayError(
            f"output already exists: {output_root}. Move it or choose another path."
        )
    inputs = discover_session_parquets(input_root)
    output_root.mkdir(parents=True)
    parquet_root = output_root / "parquet"
    parquet_root.mkdir()
    payloads = []
    for input_path in inputs:
        session_name = _session_name(input_path)
        output_path = (
            parquet_root / f"session_date={session_name}" / "vp_features.parquet"
        )
        payloads.append(
            (
                input_path,
                output_path,
                symbol,
                tick_size,
                range_ticks,
                interval_s,
                batch_rows,
                compression,
            )
        )

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    try:
        with ProcessPoolExecutor(max_workers=min(workers, len(payloads))) as pool:
            futures = {pool.submit(_worker, payload): payload[0] for payload in payloads}
            for completed, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                results.append(result)
                print(
                    f"[{completed}/{len(payloads)}] {result['session_date']} "
                    f"ticks={result['input_rows']} features={result['feature_rows']} "
                    f"rate={result['rows_per_second']} ticks/s"
                )
        _write_manifests(
            output_root,
            results,
            symbol=symbol,
            tick_size=tick_size,
            range_ticks=range_ticks,
            interval_s=interval_s,
            compression=compression,
        )
    except Exception:
        (output_root / "INCOMPLETE.txt").write_text(
            "Historical VP feature replay did not complete.\n", encoding="utf-8"
        )
        raise

    elapsed = time.perf_counter() - started
    summary = {
        "sessions": len(results),
        "input_rows": sum(item["input_rows"] for item in results),
        "feature_rows": sum(item["feature_rows"] for item in results),
        "elapsed_seconds": round(elapsed, 3),
        "workers": min(workers, len(payloads)),
        "output": str(output_root),
    }
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay prepared ticks through canonical VP feature engineering."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("historical_vp") / "prepared" / "parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("historical_vp") / "features",
    )
    parser.add_argument("--symbol", default="@ES")
    parser.add_argument("--tick-size", type=float, default=0.25)
    parser.add_argument("--range-ticks", type=int, default=600)
    parser.add_argument("--interval-s", type=int, default=30)
    parser.add_argument("--batch-rows", type=int, default=100_000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--compression", choices=("zstd", "snappy", "gzip"), default="zstd"
    )
    args = parser.parse_args()
    replay_all(
        args.input,
        args.output,
        symbol=args.symbol,
        tick_size=args.tick_size,
        range_ticks=args.range_ticks,
        interval_s=args.interval_s,
        batch_rows=args.batch_rows,
        compression=args.compression,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
