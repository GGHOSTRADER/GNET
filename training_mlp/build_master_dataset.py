"""Build an isolated, t1-aware canonical MA research dataset.

The master path deliberately does not use ``pipeline_paths.py`` defaults, so it
cannot overwrite the legacy dataset used to reproduce the deployed model.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.study_pipeline import engineer_features, load_bars, metalabel


DEFAULT_BARS = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/data_30_master.txt"
)
DEFAULT_TRADES = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/trades_30_master.csv"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/df_features_labeled_master.csv"
)
TRADE_HEADER_PREFIX = ("#", "Type", "Date/Time", "Signal")


class MasterDatasetError(RuntimeError):
    """Raised when the master research dataset cannot be built safely."""


@dataclass(frozen=True)
class MasterBuildResult:
    frame: pd.DataFrame
    summary: dict[str, object]


def find_trade_header(path: Path) -> int:
    """Return the zero-based row containing TradeStation's Trades List header."""
    if not path.is_file():
        raise MasterDatasetError(f"trade report does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.reader(handle)):
            normalized = tuple(value.strip() for value in row[:4])
            if normalized == TRADE_HEADER_PREFIX:
                return row_number
    raise MasterDatasetError(
        f"TradeStation Trades List header was not found in {path}"
    )


def load_master_trades(path: Path) -> pd.DataFrame:
    """Load Buy/Sell rows from either a full report or Trades List-only export."""
    header_row = find_trade_header(path)
    frame = pd.read_csv(path, skiprows=header_row)
    required = {"#", "Type", "Date/Time", "Signal", "% Profit"}
    missing = required - set(frame.columns)
    if missing:
        raise MasterDatasetError(
            f"trade report is missing columns: {', '.join(sorted(missing))}"
        )
    frame = frame[frame["Type"].isin(["Buy", "Sell"])].copy()
    if frame.empty:
        raise MasterDatasetError("trade report contains no Buy/Sell rows")
    frame["% Profit"] = (
        frame["% Profit"]
        .astype(str)
        .str.replace(r"[$,%()]", "", regex=True)
        .str.strip()
    )
    frame["% Profit"] = pd.to_numeric(frame["% Profit"], errors="coerce")
    frame["_timestamp"] = pd.to_datetime(
        frame["Date/Time"], errors="coerce", format="mixed"
    )
    return frame.reset_index(drop=True)


def build_master_dataset(
    bars_path: Path,
    trades_path: Path,
    *,
    signal_name: str = "MA2CrossLE",
) -> MasterBuildResult:
    """Calculate canonical features and retain events with exact bar timestamps."""
    bars = load_bars(bars_path)
    if bars.empty:
        raise MasterDatasetError("master bar file contains no valid bars")
    trades = load_master_trades(trades_path)
    labels = metalabel(trades, signal_name)
    features = engineer_features(bars)

    feature_columns = ["Date/Time", *FEATURE_NAMES]
    merged = pd.merge(
        features.loc[:, feature_columns], labels, on="Date/Time", how="inner"
    )
    merged = merged.dropna().sort_values("Date/Time", kind="stable").reset_index(
        drop=True
    )
    if merged.empty:
        raise MasterDatasetError("no labeled entries matched canonical bar features")
    if not merged["Label"].isin([0, 1]).all():
        raise MasterDatasetError("master labels must contain only 0 and 1")
    if (merged["t1"] < merged["Date/Time"]).any():
        raise MasterDatasetError("master dataset contains t1 before entry time")

    bar_end = bars["Date/Time"].max()
    summary: dict[str, object] = {
        "bars": int(len(bars)),
        "bar_start": bars["Date/Time"].min().isoformat(),
        "bar_end": bar_end.isoformat(),
        "completed_labels": int(len(labels)),
        "matched_rows": int(len(merged)),
        "unmatched_labels": int(len(labels) - len(merged)),
        "labels_after_bar_end": int((labels["Date/Time"] > bar_end).sum()),
        "positive_labels": int((merged["Label"] == 1).sum()),
        "negative_labels": int((merged["Label"] == 0).sum()),
        "feature_count": len(FEATURE_NAMES),
        "first_event": merged["Date/Time"].min().isoformat(),
        "last_event": merged["Date/Time"].max().isoformat(),
    }
    return MasterBuildResult(merged, summary)


def write_master_dataset(result: MasterBuildResult, output: Path) -> Path:
    """Atomically write the isolated master CSV and its audit manifest."""
    if output.name == "df_features_labeled.csv":
        raise MasterDatasetError("refusing to overwrite the legacy processed dataset")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    result.frame.to_csv(temporary, index=False)
    os.replace(temporary, output)

    manifest = output.with_suffix(".manifest.json")
    payload = {
        "created_at": datetime.now().astimezone().isoformat(),
        "output": str(output),
        "feature_names": list(FEATURE_NAMES),
        "target_column": "Label",
        "event_end_column": "t1",
        **result.summary,
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=DEFAULT_BARS)
    parser.add_argument("--trades", type=Path, default=DEFAULT_TRADES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--signal-name", default="MA2CrossLE")
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = build_master_dataset(
        args.bars, args.trades, signal_name=args.signal_name
    )
    manifest = write_master_dataset(result, args.output)
    print(
        "Master MA dataset complete: "
        f"{result.summary['matched_rows']:,}/"
        f"{result.summary['completed_labels']:,} labels matched, "
        f"{result.summary['feature_count']} canonical features."
    )
    print(f"Dataset: {args.output}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
