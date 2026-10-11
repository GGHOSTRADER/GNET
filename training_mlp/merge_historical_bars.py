"""Safely merge the base and incremental TradeStation 30-second bar exports.

The module discovers ``data_30_master.txt`` and every
``data_30_update_*.txt`` in the input directory. The legacy ``data_30.txt``
that reproduces the deployed model is deliberately excluded whenever the new
master exists. Exact timestamp/value duplicates are retained once. A shared
timestamp with different OHLC/Up/Down values is written to a conflict report
and aborts the merge. Source exports are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd


DEFAULT_INPUT_DIR = Path("training_mlp/strategies/MA2CrossLE/inputs")
DEFAULT_MASTER = DEFAULT_INPUT_DIR / "data_30_master.txt"
DEFAULT_OUTPUT = DEFAULT_INPUT_DIR / "data_30_master_merged.txt"
REQUIRED_COLUMNS = ("Date", "Time", "Open", "High", "Low", "Close", "Up", "Down")
VALUE_COLUMNS = ("Open", "High", "Low", "Close", "Up", "Down")


class HistoricalBarMergeError(RuntimeError):
    """Raised when historical bar exports cannot be merged safely."""


def discover_bar_exports(input_dir: Path) -> list[Path]:
    """Discover the current master and updates, excluding the legacy base."""
    master = input_dir / "data_30_master.txt"
    legacy = input_dir / "data_30.txt"
    updates = sorted(input_dir.glob("data_30_update_*.txt"))
    base = master if master.is_file() else legacy
    paths = ([base] if base.is_file() else []) + updates
    if not paths:
        raise HistoricalBarMergeError(
            "no data_30_master.txt, legacy data_30.txt, or "
            f"data_30_update_*.txt files found under {input_dir}"
        )
    return paths


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_bar_export(path: Path) -> pd.DataFrame:
    """Load one export and enforce the canonical eight-column bar contract."""
    frame = pd.read_csv(path)
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    extra = set(frame.columns) - set(REQUIRED_COLUMNS)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unexpected: {', '.join(sorted(extra))}")
        raise HistoricalBarMergeError(f"{path} has invalid columns ({'; '.join(details)})")
    frame = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    frame["_timestamp"] = pd.to_datetime(
        frame["Date"].astype(str).str.strip()
        + " "
        + frame["Time"].astype(str).str.strip(),
        format="%m/%d/%Y %H:%M:%S",
        errors="coerce",
    )
    if frame["_timestamp"].isna().any():
        row = int(frame["_timestamp"].isna().idxmax()) + 2
        raise HistoricalBarMergeError(f"{path} has an invalid timestamp at file row {row}")
    for column in VALUE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.loc[:, list(VALUE_COLUMNS)].isna().any().any():
        raise HistoricalBarMergeError(f"{path} contains non-numeric bar values")
    if (frame[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise HistoricalBarMergeError(f"{path} contains non-positive prices")
    if (frame[["Up", "Down"]] < 0).any().any():
        raise HistoricalBarMergeError(f"{path} contains negative Up/Down values")
    invalid_ohlc = (
        (frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1))
        | (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1))
    )
    if invalid_ohlc.any():
        row = int(invalid_ohlc.idxmax()) + 2
        raise HistoricalBarMergeError(f"{path} violates OHLC bounds at file row {row}")
    frame["_source"] = path.name
    frame["_source_row"] = frame.index + 2
    session_day = frame["_timestamp"].dt.normalize() + pd.to_timedelta(
        (frame["_timestamp"].dt.hour >= 18).astype(int), unit="D"
    )
    frame["_session_date"] = session_day.dt.strftime("%Y-%m-%d")
    return frame


def build_session_overlap_report(combined: pd.DataFrame) -> pd.DataFrame:
    """Summarize every 18:00 ES session represented by multiple exports."""
    rows: list[dict[str, object]] = []
    for session_date, session in combined.groupby("_session_date", sort=True):
        sources = sorted(session["_source"].unique())
        if len(sources) < 2:
            continue
        timestamp_sources = session.groupby("_timestamp")["_source"].nunique()
        shared_timestamps = timestamp_sources[timestamp_sources > 1].index
        shared = session[session["_timestamp"].isin(shared_timestamps)]
        distinct_shared = shared.drop_duplicates(
            ["_timestamp", *VALUE_COLUMNS]
        )
        conflicting_timestamps = int(
            distinct_shared.loc[
                distinct_shared.duplicated("_timestamp", keep=False), "_timestamp"
            ].nunique()
        )
        source_rows = {
            source: int((session["_source"] == source).sum()) for source in sources
        }
        source_only = {}
        for source in sources:
            source_times = set(
                session.loc[session["_source"] == source, "_timestamp"]
            )
            other_times = set(
                session.loc[session["_source"] != source, "_timestamp"]
            )
            source_only[source] = len(source_times - other_times)
        rows.append(
            {
                "session_date": session_date,
                "sources": " | ".join(sources),
                "source_rows": json.dumps(source_rows, sort_keys=True),
                "shared_timestamps": int(len(shared_timestamps)),
                "identical_shared_timestamps": int(
                    len(shared_timestamps) - conflicting_timestamps
                ),
                "conflicting_timestamps": int(conflicting_timestamps),
                "source_only_timestamps": json.dumps(source_only, sort_keys=True),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "session_date",
            "sources",
            "source_rows",
            "shared_timestamps",
            "identical_shared_timestamps",
            "conflicting_timestamps",
            "source_only_timestamps",
        ],
    )


def merge_exports(paths: list[Path]) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    """Merge valid exports and return output, summary, and any conflicts."""
    frames = [load_bar_export(path) for path in paths]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(
        ["_timestamp", "_source", "_source_row"], kind="stable"
    ).reset_index(drop=True)
    overlap_report = build_session_overlap_report(combined)
    overlap_records = overlap_report.to_dict(orient="records")

    distinct_values = combined.drop_duplicates(["_timestamp", *VALUE_COLUMNS])
    conflicting_timestamps = distinct_values.loc[
        distinct_values.duplicated("_timestamp", keep=False), "_timestamp"
    ].unique()
    conflicts = combined[combined["_timestamp"].isin(conflicting_timestamps)].copy()
    if not conflicts.empty:
        return combined.iloc[0:0], {
            "overlapping_sessions": int(len(overlap_report)),
            "session_overlaps": overlap_records,
        }, conflicts

    merged = combined.drop_duplicates("_timestamp", keep="first").copy()
    duplicate_rows = len(combined) - len(merged)
    merged = merged.sort_values("_timestamp", kind="stable").reset_index(drop=True)
    if merged["_timestamp"].duplicated().any():
        raise HistoricalBarMergeError("internal error: duplicate timestamps remain")
    summary: dict[str, object] = {
        "source_files": len(paths),
        "input_rows": int(len(combined)),
        "output_rows": int(len(merged)),
        "identical_duplicate_rows_removed": int(duplicate_rows),
        "overlapping_sessions": int(len(overlap_report)),
        "session_overlaps": overlap_records,
        "first_timestamp": merged["_timestamp"].iloc[0].isoformat(),
        "last_timestamp": merged["_timestamp"].iloc[-1].isoformat(),
    }
    return merged, summary, conflicts


def write_merge(paths: list[Path], output: Path) -> dict[str, object]:
    """Write the merged export and manifest, or a conflict report on failure."""
    merged, summary, conflicts = merge_exports(paths)
    output.parent.mkdir(parents=True, exist_ok=True)
    conflict_path = output.with_name(output.stem + "_conflicts.csv")
    overlap_path = output.with_name(output.stem + "_overlap_sessions.csv")
    pd.DataFrame(
        summary.get("session_overlaps", []),
        columns=[
            "session_date",
            "sources",
            "source_rows",
            "shared_timestamps",
            "identical_shared_timestamps",
            "conflicting_timestamps",
            "source_only_timestamps",
        ],
    ).to_csv(overlap_path, index=False)
    if not conflicts.empty:
        conflicts.loc[
            :, ["_timestamp", *VALUE_COLUMNS, "_source", "_source_row"]
        ].to_csv(conflict_path, index=False)
        raise HistoricalBarMergeError(
            f"conflicting overlapping bars found; inspect {conflict_path}"
        )
    if conflict_path.exists():
        conflict_path.unlink()

    temporary = output.with_suffix(output.suffix + ".tmp")
    writable = merged.loc[:, list(REQUIRED_COLUMNS)].copy()
    writable["Date"] = merged["_timestamp"].dt.strftime("%m/%d/%Y")
    writable["Time"] = merged["_timestamp"].dt.strftime("%H:%M:%S")
    writable.to_csv(temporary, index=False)
    os.replace(temporary, output)

    manifest_path = output.with_suffix(".manifest.json")
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "output": str(output),
        "session_overlap_report": str(overlap_path),
        "required_columns": list(REQUIRED_COLUMNS),
        "sources": [
            {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in paths
        ],
        **summary,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        dest="sources",
        help=(
            "explicit source export; repeat for multiple compatible files. "
            "When omitted, automatic base/update discovery is used"
        ),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    paths = args.sources or discover_bar_exports(args.input_dir)
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise HistoricalBarMergeError(
            f"source export does not exist: {missing[0]}"
        )
    manifest = write_merge(paths, args.output)
    print(
        "Historical bar merge complete: "
        f"{manifest['source_files']} files, {manifest['output_rows']:,} rows, "
        f"{manifest['identical_duplicate_rows_removed']:,} duplicates removed."
    )
    print(f"Output: {args.output}")
    print(f"Manifest: {args.output.with_suffix('.manifest.json')}")


if __name__ == "__main__":
    main()
