"""Build engineered OHLCV bars by counting imported tick/volume source bars.

This is a bar-construction command, not an execution replay. Source-row IDs
are not tick-event IDs and must not be fed into the tick executor as such.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


HEADER = ("Date", "Time", "Open", "High", "Low", "Close", "Up", "Down")
OUTPUT_SCHEMA = pa.schema([
    ("session", pa.string()),
    *[(key, pa.int64()) for key in ("first_source_close_ns", "end_ns", "first_source_row",
                                   "last_source_row", "source_bar_count")],
    *[(key, pa.float64()) for key in ("open", "high", "low", "close")],
    *[(key, pa.int64()) for key in ("up", "down", "volume")],
    ("complete", pa.bool_()),
])


def read_source_rows(path, timezone, source_kind, source_size):
    """Stream validated OHLCV rows in file order, including tied timestamps."""
    previous = None
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != HEADER:
            raise ValueError(f"expected exact CSV header: {','.join(HEADER)}")
        for source_row, row in enumerate(reader, start=2):
            try:
                day, clock = row["Date"], row["Time"]
                if (len(day) != 10 or day[2] != "/" or day[5] != "/" or
                        len(clock) != 8 or clock[2] != ":" or clock[5] != ":" or None in row):
                    raise ValueError("use MM/DD/YYYY and HH:MM:SS with exactly eight columns")
                stamp = datetime(int(day[6:]), int(day[:2]), int(day[3:5]),
                                 int(clock[:2]), int(clock[3:5]), int(clock[6:]))
                ns = int(pd.Timestamp(stamp).tz_localize(timezone, ambiguous="raise", nonexistent="raise").value)
                if previous is not None and ns < previous:
                    raise ValueError("source timestamps must be chronological")
                previous = ns
                o, h, low, c = [float(row[key]) for key in HEADER[2:6]]
                if not all(math.isfinite(x) and x > 0 and abs(x * 4 - round(x * 4)) < 1e-7
                           for x in (o, h, low, c)):
                    raise ValueError("prices must be finite positive ES quarter-point prices")
                if low > min(o, c) or h < max(o, c) or low > h:
                    raise ValueError("invalid OHLC ordering")
                if source_kind == "tick" and source_size == 1 and not o == h == low == c:
                    raise ValueError("a one-tick source row must have equal OHLC")
                up, down = int(row["Up"]), int(row["Down"])
                if min(up, down) < 0:
                    raise ValueError("Up and Down must be nonnegative integers")
                session = (stamp.date() + timedelta(days=int(stamp.hour >= 18))).isoformat()
                yield {"session": session, "end_ns": ns, "source_row": source_row,
                       "open": o, "high": h, "low": low, "close": c,
                       "up": up, "down": down, "volume": up + down}
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                raise ValueError(f"{path}: row {source_row}: {exc}") from exc


class SourceBarGroup:
    """Count source rows, never price ticks or a traded-volume threshold."""

    def __init__(self, size):
        if type(size) is not int or size < 1:
            raise ValueError("group size must be a positive integer")
        self.size = size
        self.pending = None

    def push(self, row):
        finished = []
        if self.pending is not None and self.pending["session"] != row["session"]:
            finished.append(self.finish())
        if self.pending is None:
            self.pending = {"session": row["session"], "first_source_close_ns": row["end_ns"],
                            "end_ns": row["end_ns"], "first_source_row": row["source_row"],
                            "last_source_row": row["source_row"], "source_bar_count": 0,
                            "open": row["open"], "high": row["high"], "low": row["low"],
                            "close": row["close"], "up": 0, "down": 0, "volume": 0,
                            "complete": False}
        bar = self.pending
        bar["end_ns"] = row["end_ns"]
        bar["last_source_row"] = row["source_row"]
        bar["high"] = max(bar["high"], row["high"])
        bar["low"] = min(bar["low"], row["low"])
        bar["close"] = row["close"]
        for key in ("up", "down", "volume"):
            bar[key] += row[key]
        bar["source_bar_count"] += 1
        if bar["source_bar_count"] == self.size:
            bar["complete"] = True
            finished.append(self.finish())
        return finished

    def finish(self):
        bar, self.pending = self.pending, None
        return bar


def build_source_bars(input_path, output, *, source_kind, source_size, groups, timezone="America/New_York"):
    if source_kind not in ("tick", "volume") or type(source_size) is not int or source_size < 1:
        raise ValueError("source kind must be tick/volume and source size a positive integer")
    if not groups or len(set(groups)) != len(groups):
        raise ValueError("choose distinct positive group sizes")
    states = {size: SourceBarGroup(size) for size in groups}
    ZoneInfo(timezone)
    input_path, output = Path(input_path).resolve(strict=True), Path(output).resolve()
    before = input_path.stat()
    output.mkdir(parents=True, exist_ok=False)
    (output / "INCOMPLETE.txt").write_text("Bar construction has not completed.\n", encoding="utf-8")
    buffers = {size: [] for size in groups}
    counts = {size: {"total": 0, "complete": 0, "partial": 0} for size in groups}
    writers = {}
    rows = 0
    try:
        for size in groups:
            name = f"aggregated_{source_kind}_src{source_size}_n{size}.parquet"
            writers[size] = pq.ParquetWriter(output / name, OUTPUT_SCHEMA, compression="zstd")

        def emit(size, bar):
            if bar is None:
                return
            buffers[size].append(bar)
            counts[size]["total"] += 1
            counts[size]["complete" if bar["complete"] else "partial"] += 1
            if len(buffers[size]) >= 2048:
                writers[size].write_table(pa.Table.from_pylist(buffers[size], schema=OUTPUT_SCHEMA))
                buffers[size].clear()

        for row in read_source_rows(input_path, timezone, source_kind, source_size):
            rows += 1
            for size, state in states.items():
                for bar in state.push(row):
                    emit(size, bar)
        if rows == 0:
            raise ValueError("source export is empty")
        for size, state in states.items():
            emit(size, state.finish())
            if buffers[size]:
                writers[size].write_table(pa.Table.from_pylist(buffers[size], schema=OUTPUT_SCHEMA))
        after = input_path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("input changed during construction")
    finally:
        for writer in writers.values():
            writer.close()
    manifest = {"schema_version": 1, "input": str(input_path), "input_bytes": before.st_size,
                "input_mtime_ns": before.st_mtime_ns, "source_kind": source_kind,
                "source_size": source_size, "group_sizes": groups, "source_rows": rows,
                "timezone": timezone, "timestamp_storage": "UTC nanoseconds",
                "operation": "count_source_bars", "bar_counts": counts,
                "boundary": "ES session changes at 18:00 source-local time; no cross-session grouping",
                "source_timestamp_semantics": "exported source-bar close timestamp",
                "limitations": "No within-source-bar price path or tick-event mapping is inferred. "
                "Complete means N source rows, assuming exported rows are completed source bars. "
                "Use one audited price vintage per input file."}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "INCOMPLETE.txt").unlink()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-kind", required=True, choices=("tick", "volume"))
    parser.add_argument("--source-size", required=True, type=int)
    parser.add_argument("--groups", required=True, type=int, nargs="+")
    parser.add_argument("--timezone", default="America/New_York")
    args = parser.parse_args()
    result = build_source_bars(args.input, args.output, source_kind=args.source_kind,
                               source_size=args.source_size, groups=args.groups, timezone=args.timezone)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
