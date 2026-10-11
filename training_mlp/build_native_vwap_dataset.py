"""Build a comparison dataset from a verified historical per-bar VWAP series.

The canonical bar master and prior labeled dataset remain untouched. The native
export must contain exactly Date, Time, VWAP and cover every master bar.
TradeStation's VWAP quote word does not supply historical values; do not use
its current snapshot as a historical export.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.build_master_dataset import DEFAULT_BARS
from training_mlp.study_pipeline import engineer_features, load_bars


DEFAULT_VWAP = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/vwap_30_tradestation_native.csv"
)
DEFAULT_REFERENCE = Path(
    "training_mlp/strategies/MA2CrossLE/processed/df_features_labeled_master_libb_ts_vwap.csv"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/df_features_labeled_master_libb_ts_native_vwap.csv"
)
NATIVE_COLUMNS = ("Date", "Time", "VWAP")
OTHER_FEATURES = tuple(name for name in FEATURE_NAMES if name != "vwap_distance")


class NativeVwapDatasetError(RuntimeError):
    """The native export cannot support an exact, isolated comparison."""


def native_files(path: Path) -> list[Path]:
    """Accept one CSV or a directory of non-overlapping CSV chunks."""
    files = sorted(path.glob("*.csv")) if path.is_dir() else [path]
    if not files or any(not item.is_file() for item in files):
        raise NativeVwapDatasetError(f"native VWAP CSV not found: {path}")
    return files


def load_native_vwap(path: Path) -> pd.DataFrame:
    """Read a TradeStation bar-close VWAP export with strict timestamp checks."""
    chunks = []
    for item in native_files(path):
        chunk = pd.read_csv(item, encoding="utf-8-sig")
        if set(chunk.columns) != set(NATIVE_COLUMNS):
            raise NativeVwapDatasetError(
                f"{item} must contain exactly {', '.join(NATIVE_COLUMNS)}"
            )
        chunks.append(chunk)
    frame = pd.concat(chunks, ignore_index=True)
    timestamp = pd.to_datetime(
        frame["Date"].astype(str).str.strip()
        + " "
        + frame["Time"].astype(str).str.strip(),
        format="%m/%d/%Y %H:%M:%S",
        errors="coerce",
    )
    value = pd.to_numeric(frame["VWAP"], errors="coerce")
    if timestamp.isna().any() or value.isna().any() or (value <= 0).any():
        raise NativeVwapDatasetError("native export has invalid timestamp or VWAP")
    if timestamp.duplicated().any():
        raise NativeVwapDatasetError("native export has duplicate bar timestamps")
    return pd.DataFrame({"Date/Time": timestamp, "VWAP": value})


def attach_native_vwap(bars: pd.DataFrame, native: pd.DataFrame) -> pd.DataFrame:
    """Require an exact native VWAP match for every canonical master bar."""
    if bars["Date/Time"].duplicated().any():
        raise NativeVwapDatasetError("bar master has duplicate timestamps")
    merged = bars.merge(native, on="Date/Time", how="left", validate="one_to_one")
    if merged["VWAP"].isna().any():
        missing = merged.loc[merged["VWAP"].isna(), "Date/Time"]
        raise NativeVwapDatasetError(
            f"native export is missing {len(missing):,} master bars; "
            f"first missing: {missing.iloc[0]}"
        )
    return merged


def build_native_dataset(
    bars_path: Path, native_path: Path, reference_path: Path
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Replace only the reference dataset's VWAP feature with native values."""
    bars = load_bars(bars_path)
    if bars.empty or bars[["Open", "High", "Low", "Close", "Up", "Down"]].isna().any().any():
        raise NativeVwapDatasetError("bar master is empty or contains invalid values")
    native = load_native_vwap(native_path)
    bars = attach_native_vwap(bars, native)
    features = engineer_features(bars, vwap_column="VWAP")

    reference = pd.read_csv(reference_path)
    required = {"Date/Time", "t1", "Label", *FEATURE_NAMES}
    missing_columns = required - set(reference.columns)
    if missing_columns:
        raise NativeVwapDatasetError(
            f"reference dataset is missing: {', '.join(sorted(missing_columns))}"
        )
    reference["Date/Time"] = pd.to_datetime(reference["Date/Time"], errors="coerce")
    if reference["Date/Time"].isna().any() or reference["Date/Time"].duplicated().any():
        raise NativeVwapDatasetError("reference has invalid or duplicate event timestamps")
    matched = reference.merge(
        features.loc[:, ["Date/Time", *FEATURE_NAMES]],
        on="Date/Time",
        how="left",
        validate="one_to_one",
        suffixes=("", "_native"),
    )
    if matched["vwap_distance_native"].isna().any():
        raise NativeVwapDatasetError("native features are missing for reference events")
    for name in OTHER_FEATURES:
        if not np.allclose(
            matched[name].to_numpy(dtype=float),
            matched[f"{name}_native"].to_numpy(dtype=float),
            rtol=1e-10,
            atol=1e-10,
            equal_nan=True,
        ):
            raise NativeVwapDatasetError(
                f"non-VWAP feature changed: {name}; comparison is not isolated"
            )
    output = reference.copy()
    output["vwap_distance"] = matched["vwap_distance_native"].to_numpy()
    if output.isna().any().any():
        raise NativeVwapDatasetError("output contains missing values")
    summary = {
        "vwap_source": "native_tradestation_export",
        "bars_path": str(bars_path),
        "native_vwap_path": str(native_path),
        "reference_path": str(reference_path),
        "master_bars": len(bars),
        "native_rows": len(native),
        "native_files": [str(item) for item in native_files(native_path)],
        "matched_events": len(output),
        "bar_start": bars["Date/Time"].min().isoformat(),
        "bar_end": bars["Date/Time"].max().isoformat(),
        "native_start": native["Date/Time"].min().isoformat(),
        "native_end": native["Date/Time"].max().isoformat(),
        "changed_vwap_features": int(
            (~np.isclose(
                reference["vwap_distance"].to_numpy(dtype=float),
                output["vwap_distance"].to_numpy(dtype=float),
                rtol=1e-10,
                atol=1e-10,
            )).sum()
        ),
    }
    return output, summary


def write_native_dataset(
    frame: pd.DataFrame, summary: dict[str, object], output: Path, *, overwrite: bool
) -> Path:
    """Write only the separate native-VWAP output and its provenance manifest."""
    if "native_vwap" not in output.stem:
        raise NativeVwapDatasetError("output name must include native_vwap")
    protected = {
        DEFAULT_REFERENCE.resolve(),
        DEFAULT_BARS.resolve(),
        Path(summary["bars_path"]).resolve(),
        Path(summary["reference_path"]).resolve(),
        Path(summary["native_vwap_path"]).resolve(),
    }
    if output.resolve() in protected:
        raise NativeVwapDatasetError("refusing to overwrite an input dataset")
    native_path = Path(summary["native_vwap_path"])
    if native_path.is_dir() and output.resolve().is_relative_to(native_path.resolve()):
        raise NativeVwapDatasetError("output cannot be inside the native export directory")
    if output.exists() and not overwrite:
        raise NativeVwapDatasetError(f"output exists; pass --overwrite to replace: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, output)
    fingerprint = hashlib.sha256()
    for item in native_files(Path(summary["native_vwap_path"])):
        fingerprint.update(item.name.encode("utf-8"))
        fingerprint.update(item.read_bytes())
    digest = fingerprint.hexdigest()
    manifest = output.with_suffix(".manifest.json")
    payload = {
        "created_at": datetime.now().astimezone().isoformat(),
        "output": str(output),
        "native_sha256": digest,
        **summary,
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=DEFAULT_BARS)
    parser.add_argument("--native-vwap", type=Path, default=DEFAULT_VWAP)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    frame, summary = build_native_dataset(args.bars, args.native_vwap, args.reference)
    manifest = write_native_dataset(frame, summary, args.output, overwrite=args.overwrite)
    print(f"Native-VWAP dataset: {args.output}")
    print(f"Events: {summary['matched_events']:,}; changed VWAP features: {summary['changed_vwap_features']:,}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
