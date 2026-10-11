"""Build a leakage-safe MA + volume-profile training dataset.

Each MA event is joined to the freshest canonical VP snapshot at or before its
entry timestamp within the same symbol and 18:00 ES trading session.  ``Label``
remains the target and ``t1`` remains validation metadata; neither join audit
column is part of the model feature contract.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from feat_files.canonical_volume_profile import VOLUME_PROFILE_FEATURE_NAMES


DEFAULT_MA_INPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/df_features_labeled.csv"
)
DEFAULT_VP_ROOT = Path("historical_vp/features/parquet")
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/df_features_labeled_vp.parquet"
)
MA_TIMESTAMP_COLUMN = "Date/Time"
VP_TIMESTAMP_COLUMN = "vp_snapshot_timestamp"
AUDIT_COLUMNS = ("symbol", "session_date", VP_TIMESTAMP_COLUMN, "vp_age_ms")
MODEL_FEATURE_NAMES = FEATURE_NAMES + VOLUME_PROFILE_FEATURE_NAMES


class MAVPMergeError(RuntimeError):
    """Raised when a leakage-safe MA/VP merge cannot be produced."""


@dataclass(frozen=True)
class MergeResult:
    frame: pd.DataFrame
    summary: dict[str, object]


def discover_vp_parquets(input_root: Path) -> list[Path]:
    """Return canonical VP partitions in chronological session order."""
    paths = sorted(input_root.glob("session_date=*/vp_features.parquet"))
    if not paths:
        raise MAVPMergeError(f"no VP feature Parquets found under {input_root}")
    return paths


def es_session_date(timestamps: pd.Series) -> pd.Series:
    """Map naive TradeStation timestamps to the ES session beginning at 18:00."""
    parsed = pd.to_datetime(timestamps, errors="coerce")
    if parsed.isna().any():
        bad_index = parsed[parsed.isna()].index[0]
        raise MAVPMergeError(f"invalid MA timestamp at row {bad_index}")
    calendar_day = parsed.dt.normalize()
    session_day = calendar_day + pd.to_timedelta((parsed.dt.hour >= 18).astype(int), unit="D")
    return session_day.dt.strftime("%Y-%m-%d")


def load_ma_frame(path: Path, *, symbol: str) -> pd.DataFrame:
    """Load and validate the canonical MA event table."""
    if not path.is_file():
        raise MAVPMergeError(f"MA feature file does not exist: {path}")
    frame = pd.read_csv(path)
    required = {MA_TIMESTAMP_COLUMN, "t1", "Label", *FEATURE_NAMES}
    missing = required - set(frame.columns)
    if missing:
        raise MAVPMergeError(
            f"MA feature file is missing columns: {', '.join(sorted(missing))}"
        )
    frame = frame.copy()
    frame[MA_TIMESTAMP_COLUMN] = pd.to_datetime(
        frame[MA_TIMESTAMP_COLUMN], errors="coerce"
    ).astype("datetime64[ns]")
    frame["t1"] = pd.to_datetime(frame["t1"], errors="coerce").astype(
        "datetime64[ns]"
    )
    if frame[[MA_TIMESTAMP_COLUMN, "t1"]].isna().any().any():
        raise MAVPMergeError("MA feature file contains invalid Date/Time or t1 values")
    if not frame["Label"].isin([0, 1]).all():
        raise MAVPMergeError("MA Label must contain only 0 and 1")
    feature_values = frame.loc[:, list(FEATURE_NAMES)].to_numpy(dtype=np.float64)
    if not np.isfinite(feature_values).all():
        raise MAVPMergeError("MA canonical features contain non-finite values")
    frame["symbol"] = symbol
    frame["session_date"] = es_session_date(frame[MA_TIMESTAMP_COLUMN])
    return frame


def load_vp_frame(paths: list[Path]) -> pd.DataFrame:
    """Load the minimum canonical VP join and feature columns."""
    columns = [
        "symbol",
        "session_date",
        "snapshot_timestamp",
        *VOLUME_PROFILE_FEATURE_NAMES,
    ]
    frames = [pd.read_parquet(path, columns=columns) for path in paths]
    frame = pd.concat(frames, ignore_index=True)
    if frame.empty:
        raise MAVPMergeError("historical VP feature dataset is empty")
    frame = frame.rename(columns={"snapshot_timestamp": VP_TIMESTAMP_COLUMN})
    frame[VP_TIMESTAMP_COLUMN] = pd.to_datetime(
        frame[VP_TIMESTAMP_COLUMN], errors="coerce"
    ).astype("datetime64[ns]")
    if frame[VP_TIMESTAMP_COLUMN].isna().any():
        raise MAVPMergeError("VP data contains invalid snapshot timestamps")
    feature_values = frame.loc[:, list(VOLUME_PROFILE_FEATURE_NAMES)].to_numpy(
        dtype=np.float64
    )
    if not np.isfinite(feature_values).all():
        raise MAVPMergeError("VP canonical features contain non-finite values")
    duplicate = frame.duplicated(
        ["symbol", "session_date", VP_TIMESTAMP_COLUMN], keep=False
    )
    if duplicate.any():
        raise MAVPMergeError(
            "VP data contains duplicate symbol/session/snapshot timestamps"
        )
    return frame


def merge_frames(
    ma_frame: pd.DataFrame,
    vp_frame: pd.DataFrame,
    *,
    max_vp_age_s: float = 30.0,
    drop_unmatched: bool = True,
) -> MergeResult:
    """Join each MA event to its freshest same-session non-future VP snapshot."""
    if max_vp_age_s <= 0:
        raise MAVPMergeError("max_vp_age_s must be positive")
    overlap = set(ma_frame.columns) & set(VOLUME_PROFILE_FEATURE_NAMES)
    if overlap:
        raise MAVPMergeError(
            f"MA input already contains VP features: {', '.join(sorted(overlap))}"
        )

    left = ma_frame.sort_values(MA_TIMESTAMP_COLUMN, kind="stable").reset_index(drop=True)
    right = vp_frame.sort_values(VP_TIMESTAMP_COLUMN, kind="stable").reset_index(drop=True)
    merged = pd.merge_asof(
        left,
        right,
        left_on=MA_TIMESTAMP_COLUMN,
        right_on=VP_TIMESTAMP_COLUMN,
        by=["symbol", "session_date"],
        direction="backward",
        tolerance=pd.Timedelta(seconds=max_vp_age_s),
        allow_exact_matches=True,
    )
    matched = merged[VP_TIMESTAMP_COLUMN].notna()
    merged["vp_age_ms"] = (
        merged[MA_TIMESTAMP_COLUMN] - merged[VP_TIMESTAMP_COLUMN]
    ).dt.total_seconds() * 1_000.0
    if (merged.loc[matched, "vp_age_ms"] < 0).any():
        raise MAVPMergeError("future VP leakage detected after backward join")

    unmatched_rows = int((~matched).sum())
    if drop_unmatched:
        merged = merged.loc[matched].copy()
    if merged.empty:
        raise MAVPMergeError("no MA events matched an eligible VP snapshot")

    matched_values = merged.loc[
        merged[VP_TIMESTAMP_COLUMN].notna(), list(VOLUME_PROFILE_FEATURE_NAMES)
    ].to_numpy(dtype=np.float64)
    if matched_values.size and not np.isfinite(matched_values).all():
        raise MAVPMergeError("matched VP feature values contain non-finite values")

    event_metadata = [
        name
        for name in ("entry_time", "net_pnl_at_3_24_per_side")
        if name in merged.columns
    ]
    ordered = [
        MA_TIMESTAMP_COLUMN,
        *FEATURE_NAMES,
        *VOLUME_PROFILE_FEATURE_NAMES,
        *AUDIT_COLUMNS,
        *event_metadata,
        "t1",
        "Label",
    ]
    merged = merged.loc[:, ordered].sort_values(
        MA_TIMESTAMP_COLUMN, kind="stable"
    ).reset_index(drop=True)
    ages = merged["vp_age_ms"].dropna().to_numpy(dtype=np.float64)
    age_percentiles = (
        np.percentile(ages, [50, 95, 99]).tolist()
        if len(ages)
        else [None, None, None]
    )
    summary: dict[str, object] = {
        "input_ma_rows": int(len(ma_frame)),
        "matched_rows": int(len(ages)),
        "unmatched_or_stale_rows": unmatched_rows,
        "match_rate": float(len(ages) / len(ma_frame)),
        "max_vp_age_s": float(max_vp_age_s),
        "ma_features": len(FEATURE_NAMES),
        "vp_features": len(VOLUME_PROFILE_FEATURE_NAMES),
        "model_features": len(MODEL_FEATURE_NAMES),
        "vp_age_ms_p50": age_percentiles[0],
        "vp_age_ms_p95": age_percentiles[1],
        "vp_age_ms_p99": age_percentiles[2],
        "vp_age_ms_max": float(ages.max()) if len(ages) else None,
    }
    return MergeResult(merged, summary)


def build_dataset(
    ma_input: Path,
    vp_root: Path,
    *,
    symbol: str = "@ES",
    max_vp_age_s: float = 30.0,
    drop_unmatched: bool = True,
) -> MergeResult:
    """Load source files and build the leakage-safe combined dataset."""
    ma_frame = load_ma_frame(ma_input, symbol=symbol)
    vp_paths = discover_vp_parquets(vp_root)
    vp_frame = load_vp_frame(vp_paths)
    result = merge_frames(
        ma_frame,
        vp_frame,
        max_vp_age_s=max_vp_age_s,
        drop_unmatched=drop_unmatched,
    )
    summary = {
        "ma_input": str(ma_input),
        "vp_root": str(vp_root),
        "vp_partitions": len(vp_paths),
        "symbol": symbol,
        **result.summary,
    }
    return MergeResult(result.frame, summary)


def write_dataset(result: MergeResult, output: Path) -> Path:
    """Atomically write Parquet/CSV output and its JSON audit manifest."""
    if output.suffix.lower() not in {".parquet", ".csv"}:
        raise MAVPMergeError("output extension must be .parquet or .csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if output.suffix.lower() == ".parquet":
        result.frame.to_parquet(temporary, index=False, compression="zstd")
    else:
        result.frame.to_csv(temporary, index=False)
    os.replace(temporary, output)

    manifest = output.with_suffix(".manifest.json")
    manifest_payload = {
        "created_at": datetime.now().astimezone().isoformat(),
        "output": str(output),
        "model_feature_names": list(MODEL_FEATURE_NAMES),
        "audit_columns": list(AUDIT_COLUMNS),
        "target_column": "Label",
        "event_end_column": "t1",
        **result.summary,
    }
    manifest.write_text(
        json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ma-input", type=Path, default=DEFAULT_MA_INPUT)
    parser.add_argument("--vp-root", type=Path, default=DEFAULT_VP_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--symbol", default="@ES")
    parser.add_argument("--max-vp-age-s", type=float, default=30.0)
    parser.add_argument(
        "--keep-unmatched",
        action="store_true",
        help="retain unmatched rows with null VP fields for diagnostics",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = build_dataset(
        args.ma_input,
        args.vp_root,
        symbol=args.symbol,
        max_vp_age_s=args.max_vp_age_s,
        drop_unmatched=not args.keep_unmatched,
    )
    manifest = write_dataset(result, args.output)
    print(
        "MA + VP merge complete: "
        f"{result.summary['matched_rows']:,}/{result.summary['input_ma_rows']:,} "
        f"events matched, {result.summary['model_features']} model features."
    )
    print(f"Dataset: {args.output}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
