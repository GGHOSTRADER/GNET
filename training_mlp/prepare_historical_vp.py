"""Prepare TradeStation tick exports for deterministic historical VP replay.

The input files remain immutable. Each row is validated and written once to a
temporary Parquet partition keyed by the ES 18:00 trading-session date. When
two exports contain the same session, exactly one complete session partition
is selected. A JSON manifest and a flat CSV partition manifest record coverage,
checksums, overlap decisions, and validation counters.

Run from the repository root:

    python -m training_mlp.prepare_historical_vp --symbol "@ES"
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import json
from pathlib import Path
import re
import shutil
from time import perf_counter
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq


EXPECTED_COLUMNS = ("Date", "Time", "Open", "High", "Low", "Close", "Up", "Down")
SESSION_START = time(18, 0)
SCHEMA = pa.schema(
    [
        ("timestamp", pa.timestamp("us")),
        ("calendar_date", pa.date32()),
        ("session_date", pa.date32()),
        ("time_s", pa.int32()),
        ("price", pa.float64()),
        ("up", pa.int64()),
        ("down", pa.int64()),
        ("volume", pa.int64()),
        ("source_file", pa.string()),
        ("source_row", pa.int64()),
    ]
)
DEFAULT_RAW_ROOT = Path("historical_vp") / "raw"
DEFAULT_EXPORT_PATTERN = re.compile(r"^volumeprof([1-9][0-9]*)\.txt$")


class HistoricalVPError(ValueError):
    """Raised when a raw export cannot be prepared safely."""


@dataclass
class PartitionStats:
    source_file: str
    session_date: str
    rows: int = 0
    zero_volume_rows: int = 0
    first_timestamp: str = ""
    last_timestamp: str = ""
    sha256: str = ""
    staged_path: str = ""
    parquet_bytes: int = 0


@dataclass
class FileStats:
    source_file: str
    size_bytes: int
    rows: int
    zero_volume_rows: int
    first_timestamp: str
    last_timestamp: str
    sessions: int


def trading_session_date(calendar_day: date, clock: time) -> date:
    """Return the following trading date for ticks at or after 18:00."""
    return calendar_day + timedelta(days=1) if clock >= SESSION_START else calendar_day


def _parse_fixed_date(value: str) -> date:
    """Parse strict MM/DD/YYYY without the per-row cost of strptime()."""
    if len(value) != 10 or value[2] != "/" or value[5] != "/":
        raise ValueError("date must use MM/DD/YYYY")
    return date(int(value[6:10]), int(value[0:2]), int(value[3:5]))


def _parse_fixed_time(value: str) -> time:
    """Parse strict HH:MM:SS without the per-row cost of strptime()."""
    if len(value) != 8 or value[2] != ":" or value[5] != ":":
        raise ValueError("time must use HH:MM:SS")
    return time(int(value[0:2]), int(value[3:5]), int(value[6:8]))


def discover_default_inputs(raw_root: Path = DEFAULT_RAW_ROOT) -> list[Path]:
    """Return volumeprof<number>.txt exports in natural numeric order."""
    matches: list[tuple[int, Path]] = []
    if raw_root.is_dir():
        for path in raw_root.iterdir():
            match = DEFAULT_EXPORT_PATTERN.fullmatch(path.name)
            if path.is_file() and match is not None:
                matches.append((int(match.group(1)), path))
    if not matches:
        raise HistoricalVPError(
            f"no inputs found matching volumeprof<number>.txt in {raw_root}"
        )
    matches.sort(key=lambda item: item[0])
    return [path for _, path in matches]


def _parse_row(row: dict[str, str], source: Path, row_number: int) -> dict:
    try:
        calendar_day = _parse_fixed_date(row["Date"])
        clock = _parse_fixed_time(row["Time"])
        timestamp = datetime.combine(calendar_day, clock)
        prices = [float(row[name]) for name in ("Open", "High", "Low", "Close")]
        up = int(row["Up"])
        down = int(row["Down"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HistoricalVPError(
            f"{source.name}:{row_number}: invalid TradeStation row"
        ) from exc

    if any(price <= 0 for price in prices):
        raise HistoricalVPError(f"{source.name}:{row_number}: price must be positive")
    if len(set(prices)) != 1:
        raise HistoricalVPError(
            f"{source.name}:{row_number}: not a 1-tick row; OHLC values differ"
        )
    if up < 0 or down < 0:
        raise HistoricalVPError(f"{source.name}:{row_number}: volume must be non-negative")

    session_day = trading_session_date(calendar_day, clock)
    return {
        "timestamp": timestamp,
        "calendar_date": calendar_day,
        "session_date": session_day,
        "time_s": clock.hour * 3600 + clock.minute * 60 + clock.second,
        "price": prices[-1],
        "up": up,
        "down": down,
        "volume": up + down,
        "source_file": source.name,
        "source_row": row_number,
    }


def _normalized_digest_row(parsed: dict) -> bytes:
    return (
        f"{parsed['timestamp'].isoformat()}|{parsed['price']!r}|"
        f"{parsed['up']}|{parsed['down']}\n"
    ).encode("ascii")


def _table_from_rows(rows: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=SCHEMA)


def stage_source(
    source: Path,
    staging_root: Path,
    *,
    batch_rows: int,
    compression: str,
) -> tuple[FileStats, list[PartitionStats]]:
    """Validate one source and write source-specific session partitions."""
    source_root = staging_root / source.stem
    source_root.mkdir(parents=True, exist_ok=False)

    partitions: list[PartitionStats] = []
    current_stats: PartitionStats | None = None
    current_session: date | None = None
    writer: pq.ParquetWriter | None = None
    batch: list[dict] = []
    digest = hashlib.sha256()
    previous_timestamp: datetime | None = None
    file_rows = 0
    file_zero_volume = 0
    file_first = ""
    file_last = ""

    def flush() -> None:
        nonlocal batch
        if batch:
            if writer is None:
                raise HistoricalVPError("internal error: missing Parquet writer")
            writer.write_table(_table_from_rows(batch))
            batch = []

    def close_partition() -> None:
        nonlocal writer, current_stats
        if writer is None or current_stats is None:
            return
        flush()
        writer.close()
        current_stats.sha256 = digest.hexdigest()
        current_stats.parquet_bytes = Path(current_stats.staged_path).stat().st_size
        partitions.append(current_stats)
        writer = None
        current_stats = None

    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
                raise HistoricalVPError(
                    f"{source.name}: expected columns {EXPECTED_COLUMNS}, "
                    f"received {tuple(reader.fieldnames or ())}"
                )

            for row_number, row in enumerate(reader, start=2):
                parsed = _parse_row(row, source, row_number)
                timestamp = parsed["timestamp"]
                session_day = parsed["session_date"]
                if previous_timestamp is not None and timestamp < previous_timestamp:
                    raise HistoricalVPError(
                        f"{source.name}:{row_number}: timestamps are not chronological"
                    )
                previous_timestamp = timestamp

                if session_day != current_session:
                    if current_session is not None and session_day < current_session:
                        raise HistoricalVPError(
                            f"{source.name}:{row_number}: session dates moved backwards"
                        )
                    close_partition()
                    current_session = session_day
                    digest = hashlib.sha256()
                    partition_dir = source_root / f"session_date={session_day.isoformat()}"
                    partition_dir.mkdir(parents=True, exist_ok=False)
                    staged_path = partition_dir / "ticks.parquet"
                    writer = pq.ParquetWriter(
                        staged_path,
                        SCHEMA,
                        compression=compression,
                        use_dictionary=("source_file",),
                    )
                    current_stats = PartitionStats(
                        source_file=source.name,
                        session_date=session_day.isoformat(),
                        staged_path=str(staged_path.resolve()),
                    )

                if current_stats is None:
                    raise HistoricalVPError("internal error: partition stats not initialized")
                timestamp_text = timestamp.isoformat(sep=" ")
                current_stats.rows += 1
                current_stats.zero_volume_rows += int(parsed["volume"] == 0)
                if not current_stats.first_timestamp:
                    current_stats.first_timestamp = timestamp_text
                current_stats.last_timestamp = timestamp_text
                digest.update(_normalized_digest_row(parsed))
                batch.append(parsed)

                file_rows += 1
                file_zero_volume += int(parsed["volume"] == 0)
                if not file_first:
                    file_first = timestamp_text
                file_last = timestamp_text
                if len(batch) >= batch_rows:
                    flush()
    finally:
        close_partition()

    if file_rows == 0:
        raise HistoricalVPError(f"{source.name}: export contains no rows")
    return (
        FileStats(
            source_file=source.name,
            size_bytes=source.stat().st_size,
            rows=file_rows,
            zero_volume_rows=file_zero_volume,
            first_timestamp=file_first,
            last_timestamp=file_last,
            sessions=len(partitions),
        ),
        partitions,
    )


def _stage_sources(
    sources: list[Path],
    staging_root: Path,
    *,
    batch_rows: int,
    compression: str,
    workers: int,
) -> tuple[list[FileStats], list[PartitionStats], float]:
    """Stage independent exports sequentially or across worker processes."""
    started = perf_counter()
    results: dict[Path, tuple[FileStats, list[PartitionStats]]] = {}
    worker_count = min(workers, len(sources))

    if worker_count == 1:
        for source in sources:
            print(f"[historical_vp] staging {source.name} ({source.stat().st_size:,} bytes)")
            results[source] = stage_source(
                source,
                staging_root,
                batch_rows=batch_rows,
                compression=compression,
            )
            stats = results[source][0]
            print(
                f"[historical_vp] {source.name}: rows={stats.rows:,} "
                f"sessions={stats.sessions} range={stats.first_timestamp}..{stats.last_timestamp}"
            )
    else:
        print(
            f"[historical_vp] staging {len(sources)} exports with "
            f"{worker_count} worker processes"
        )
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    stage_source,
                    source,
                    staging_root,
                    batch_rows=batch_rows,
                    compression=compression,
                ): source
                for source in sources
            }
            try:
                for future in as_completed(futures):
                    source = futures[future]
                    results[source] = future.result()
                    stats = results[source][0]
                    print(
                        f"[historical_vp] completed {source.name}: rows={stats.rows:,} "
                        f"sessions={stats.sessions} "
                        f"range={stats.first_timestamp}..{stats.last_timestamp}"
                    )
            except Exception:
                for future in futures:
                    future.cancel()
                raise

    file_stats = [results[source][0] for source in sources]
    partitions = [
        partition
        for source in sources
        for partition in results[source][1]
    ]
    return file_stats, partitions, perf_counter() - started


def choose_partition_owners(
    partitions: Iterable[PartitionStats],
) -> list[dict]:
    """Choose exactly one source for each session and record the decision."""
    by_session: dict[str, list[PartitionStats]] = {}
    for partition in partitions:
        by_session.setdefault(partition.session_date, []).append(partition)

    decisions = []
    for session_day, candidates in sorted(by_session.items()):
        candidates.sort(key=lambda item: item.source_file)
        fingerprints = {(item.rows, item.sha256) for item in candidates}
        identical = len(fingerprints) == 1
        if len(candidates) == 1 or identical:
            owner = candidates[0]
            reason = "only_source" if len(candidates) == 1 else "identical_overlap"
        else:
            owner = max(candidates, key=lambda item: (item.rows, item.source_file))
            reason = "conflicting_overlap_preferred_most_rows"

        decisions.append(
            {
                "session_date": session_day,
                "owner": owner.source_file,
                "owner_rows": owner.rows,
                "owner_sha256": owner.sha256,
                "owner_parquet_bytes": owner.parquet_bytes,
                "reason": reason,
                "overlap": len(candidates) > 1,
                "identical_overlap": identical if len(candidates) > 1 else None,
                "candidates": [asdict(item) for item in candidates],
            }
        )

    return decisions


def _conflicting_sessions(decisions: list[dict]) -> list[str]:
    return [
        item["session_date"]
        for item in decisions
        if item["reason"] == "conflicting_overlap_preferred_most_rows"
    ]


def _write_staging_manifest(
    output_root: Path,
    *,
    symbol: str,
    timezone: str,
    compression: str,
    files: list[FileStats],
    partitions: list[PartitionStats],
) -> None:
    payload = {
        "schema_version": 1,
        "symbol": symbol,
        "source_timezone": timezone,
        "compression": compression,
        "files": [asdict(item) for item in files],
        "partitions": [asdict(item) for item in partitions],
    }
    (output_root / "staging_manifest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _finalize_staged(
    output_root: Path,
    *,
    symbol: str,
    timezone: str,
    compression: str,
    files: list[FileStats],
    partitions: list[PartitionStats],
    decisions: list[dict],
) -> dict:
    staging_root = output_root / ".staging"
    parquet_root = output_root / "parquet"
    partition_lookup = {
        (item.session_date, item.source_file): item for item in partitions
    }
    for decision in decisions:
        owner = partition_lookup[(decision["session_date"], decision["owner"])]
        source_dir = Path(owner.staged_path).parent
        target = parquet_root / f"session_date={decision['session_date']}"
        if target.exists():
            raise HistoricalVPError(f"final Parquet partition already exists: {target}")
        shutil.move(str(source_dir), str(target))

    _write_manifests(
        output_root,
        symbol=symbol,
        timezone=timezone,
        compression=compression,
        files=files,
        decisions=decisions,
    )
    shutil.rmtree(staging_root)
    (output_root / "staging_manifest.json").unlink(missing_ok=True)
    (output_root / "overlap_conflicts.json").unlink(missing_ok=True)
    (output_root / "INCOMPLETE.txt").unlink(missing_ok=True)

    overlaps = sum(bool(item["overlap"]) for item in decisions)
    return {
        "status": "complete",
        "files": len(files),
        "input_rows": sum(item.rows for item in files),
        "output_sessions": len(decisions),
        "overlap_sessions": overlaps,
        "output_root": str(output_root),
    }


def _write_manifests(
    output_root: Path,
    *,
    symbol: str,
    timezone: str,
    compression: str,
    files: list[FileStats],
    decisions: list[dict],
) -> None:
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "symbol": symbol,
        "source_timezone": timezone,
        "session_start": "18:00:00",
        "compression": compression,
        "files": [asdict(item) for item in files],
        "partitions": decisions,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    with (output_root / "manifest_partitions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fieldnames = (
            "session_date", "owner", "owner_rows", "owner_sha256",
            "owner_parquet_bytes", "reason", "overlap", "identical_overlap",
        )
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for decision in decisions:
            writer.writerow({name: decision[name] for name in fieldnames})


def prepare(
    sources: list[Path],
    output_root: Path,
    *,
    symbol: str,
    timezone: str = "America/New_York",
    batch_rows: int = 100_000,
    compression: str = "zstd",
    allow_conflicting_overlaps: bool = False,
    workers: int = 1,
) -> dict:
    """Prepare all exports and return a compact execution summary."""
    if output_root.exists():
        raise HistoricalVPError(
            f"output already exists: {output_root}. Choose a new --output path."
        )
    if not sources:
        raise HistoricalVPError("no TradeStation exports were provided")
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise HistoricalVPError(f"missing input files: {', '.join(missing)}")
    if batch_rows <= 0:
        raise HistoricalVPError("batch_rows must be positive")
    if workers <= 0:
        raise HistoricalVPError("workers must be positive")
    source_stems = [source.stem for source in sources]
    if len(source_stems) != len(set(source_stems)):
        raise HistoricalVPError("input filenames must have unique stems")

    output_root.mkdir(parents=True)
    staging_root = output_root / ".staging"
    staging_root.mkdir()
    (output_root / "parquet").mkdir()

    try:
        file_stats, all_partitions, staging_seconds = _stage_sources(
            sources,
            staging_root,
            batch_rows=batch_rows,
            compression=compression,
            workers=workers,
        )

        _write_staging_manifest(
            output_root,
            symbol=symbol,
            timezone=timezone,
            compression=compression,
            files=file_stats,
            partitions=all_partitions,
        )
        decisions = choose_partition_owners(all_partitions)
        conflicts = _conflicting_sessions(decisions)
        if conflicts and not allow_conflicting_overlaps:
            conflict_details = [
                item for item in decisions if item["session_date"] in conflicts
            ]
            (output_root / "overlap_conflicts.json").write_text(
                json.dumps(conflict_details, indent=2), encoding="utf-8"
            )
            joined = ", ".join(conflicts)
            raise HistoricalVPError(
                "overlapping sessions differ: "
                f"{joined}. Staged Parquet was preserved. Inspect "
                "overlap_conflicts.json, then finalize without rereading the raw "
                "files using --resume --allow-conflicting-overlaps."
            )

        summary = _finalize_staged(
            output_root,
            symbol=symbol,
            timezone=timezone,
            compression=compression,
            files=file_stats,
            partitions=all_partitions,
            decisions=decisions,
        )
        total_bytes = sum(item.size_bytes for item in file_stats)
        staging_mib_per_second = (
            total_bytes / (1024 * 1024) / staging_seconds
            if staging_seconds > 0
            else 0.0
        )
        summary["workers"] = min(workers, len(sources))
        summary["staging_seconds"] = round(staging_seconds, 3)
        summary["staging_mib_per_second"] = round(staging_mib_per_second, 3)
    except Exception:
        (output_root / "INCOMPLETE.txt").write_text(
            "Preparation did not complete. Do not use this output.\n",
            encoding="utf-8",
        )
        raise
    return summary


def resume_preparation(
    output_root: Path,
    *,
    allow_conflicting_overlaps: bool = False,
) -> dict:
    """Finalize preserved staging data without rereading raw text exports."""
    staging_manifest = output_root / "staging_manifest.json"
    staging_root = output_root / ".staging"
    if not staging_manifest.is_file() or not staging_root.is_dir():
        raise HistoricalVPError(
            f"no resumable staging data found under {output_root}"
        )
    payload = json.loads(staging_manifest.read_text(encoding="utf-8"))
    files = [FileStats(**item) for item in payload["files"]]
    partitions = [PartitionStats(**item) for item in payload["partitions"]]
    for partition in partitions:
        if not Path(partition.staged_path).is_file():
            raise HistoricalVPError(
                f"staged partition is missing: {partition.staged_path}"
            )

    decisions = choose_partition_owners(partitions)
    conflicts = _conflicting_sessions(decisions)
    if conflicts and not allow_conflicting_overlaps:
        joined = ", ".join(conflicts)
        raise HistoricalVPError(
            f"overlapping sessions still require a decision: {joined}"
        )
    return _finalize_staged(
        output_root,
        symbol=payload["symbol"],
        timezone=payload["source_timezone"],
        compression=payload["compression"],
        files=files,
        partitions=partitions,
        decisions=decisions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate TradeStation ticks, resolve session overlaps, and write Parquet."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help=(
            "Optional input paths. When omitted, all files matching "
            "historical_vp/raw/volumeprof<number>.txt are discovered."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("historical_vp") / "prepared",
    )
    parser.add_argument("--symbol")
    parser.add_argument("--timezone", default="America/New_York")
    parser.add_argument("--batch-rows", type=int, default=100_000)
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of source files to stage in parallel (default: 2).",
    )
    parser.add_argument("--compression", choices=("zstd", "snappy", "gzip"), default="zstd")
    parser.add_argument("--allow-conflicting-overlaps", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Finalize preserved staging data without rereading raw exports.",
    )
    args = parser.parse_args()

    if args.resume:
        summary = resume_preparation(
            args.output,
            allow_conflicting_overlaps=args.allow_conflicting_overlaps,
        )
    else:
        if not args.symbol:
            parser.error("--symbol is required unless --resume is used")
        inputs = args.inputs or discover_default_inputs()
        summary = prepare(
            inputs,
            args.output,
            symbol=args.symbol,
            timezone=args.timezone,
            batch_rows=args.batch_rows,
            compression=args.compression,
            allow_conflicting_overlaps=args.allow_conflicting_overlaps,
            workers=args.workers,
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
