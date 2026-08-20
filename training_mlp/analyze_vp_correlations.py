"""Analyze redundancy among canonical historical volume-profile features."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from feat_files.canonical_volume_profile import VOLUME_PROFILE_FEATURE_NAMES


DEFAULT_INPUT_ROOT = Path("historical_vp/features/parquet")
DEFAULT_OUTPUT_ROOT = Path("historical_vp/features/correlation")


class VPCorrelationError(RuntimeError):
    """Raised when the correlation dataset cannot be analyzed safely."""


def discover_feature_parquets(input_root: Path) -> list[Path]:
    """Discover chronologically ordered historical VP feature partitions."""
    paths = sorted(input_root.glob("session_date=*/vp_features.parquet"))
    if not paths:
        raise VPCorrelationError(f"no VP feature Parquets found under {input_root}")
    return paths


def load_feature_frame(paths: list[Path]) -> pd.DataFrame:
    """Load only canonical feature columns and enforce finite numeric values."""
    columns = list(VOLUME_PROFILE_FEATURE_NAMES)
    frames = [pd.read_parquet(path, columns=columns) for path in paths]
    frame = pd.concat(frames, ignore_index=True)
    if frame.empty:
        raise VPCorrelationError("historical VP feature dataset is empty")
    values = frame.to_numpy(dtype=np.float64, copy=False)
    if not np.isfinite(values).all():
        bad = np.argwhere(~np.isfinite(values))[0]
        raise VPCorrelationError(
            f"non-finite value at row {int(bad[0])}, feature {columns[int(bad[1])]}"
        )
    return frame


def build_pair_report(
    pearson: pd.DataFrame,
    spearman: pd.DataFrame,
    *,
    high_threshold: float,
    severe_threshold: float,
) -> pd.DataFrame:
    """Create one row per unique feature pair with redundancy classifications."""
    rows: list[dict[str, object]] = []
    names = list(pearson.columns)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            pearson_value = float(pearson.loc[left, right])
            spearman_value = float(spearman.loc[left, right])
            max_absolute = max(abs(pearson_value), abs(spearman_value))
            if max_absolute >= severe_threshold:
                classification = "severe"
            elif max_absolute >= high_threshold:
                classification = "high"
            else:
                classification = "below_threshold"
            rows.append(
                {
                    "feature_a": left,
                    "feature_b": right,
                    "pearson": pearson_value,
                    "abs_pearson": abs(pearson_value),
                    "spearman": spearman_value,
                    "abs_spearman": abs(spearman_value),
                    "max_abs_correlation": max_absolute,
                    "classification": classification,
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["max_abs_correlation", "feature_a", "feature_b"],
        ascending=[False, True, True],
        ignore_index=True,
    )


def analyze(
    input_root: Path,
    output_root: Path,
    *,
    high_threshold: float = 0.90,
    severe_threshold: float = 0.95,
) -> dict[str, object]:
    """Calculate matrices, diagnostics, pair rankings, and a machine-readable summary."""
    if not 0.0 < high_threshold <= severe_threshold <= 1.0:
        raise VPCorrelationError(
            "thresholds must satisfy 0 < high_threshold <= severe_threshold <= 1"
        )
    paths = discover_feature_parquets(input_root)
    frame = load_feature_frame(paths)
    standard_deviation = frame.std(ddof=0)
    constant_features = standard_deviation[standard_deviation == 0.0].index.tolist()
    variable_frame = frame.drop(columns=constant_features)
    if variable_frame.shape[1] < 2:
        raise VPCorrelationError("fewer than two non-constant features are available")

    pearson = variable_frame.corr(method="pearson")
    spearman = variable_frame.corr(method="spearman")
    pairs = build_pair_report(
        pearson,
        spearman,
        high_threshold=high_threshold,
        severe_threshold=severe_threshold,
    )
    diagnostics = pd.DataFrame(
        {
            "feature": frame.columns,
            "count": frame.count().to_numpy(),
            "mean": frame.mean().to_numpy(),
            "std": standard_deviation.to_numpy(),
            "min": frame.min().to_numpy(),
            "max": frame.max().to_numpy(),
            "unique_values": frame.nunique(dropna=False).to_numpy(),
            "is_constant": [name in constant_features for name in frame.columns],
        }
    )

    output_root.mkdir(parents=True, exist_ok=True)
    pearson.to_csv(output_root / "pearson_matrix.csv")
    spearman.to_csv(output_root / "spearman_matrix.csv")
    pairs.to_csv(output_root / "correlation_pairs.csv", index=False)
    pairs[pairs["classification"] != "below_threshold"].to_csv(
        output_root / "high_correlation_pairs.csv", index=False
    )
    diagnostics.to_csv(output_root / "feature_diagnostics.csv", index=False)

    summary: dict[str, object] = {
        "created_at": datetime.now().astimezone().isoformat(),
        "input_root": str(input_root),
        "partitions": len(paths),
        "rows": len(frame),
        "canonical_features": len(VOLUME_PROFILE_FEATURE_NAMES),
        "analyzed_features": variable_frame.shape[1],
        "constant_features": constant_features,
        "high_threshold": high_threshold,
        "severe_threshold": severe_threshold,
        "unique_pairs": len(pairs),
        "high_pairs": int((pairs["classification"] == "high").sum()),
        "severe_pairs": int((pairs["classification"] == "severe").sum()),
        "top_pairs": pairs.head(20).to_dict(orient="records"),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--high-threshold", type=float, default=0.90)
    parser.add_argument("--severe-threshold", type=float, default=0.95)
    return parser


def main() -> None:
    args = _parser().parse_args()
    summary = analyze(
        args.input_root,
        args.output_root,
        high_threshold=args.high_threshold,
        severe_threshold=args.severe_threshold,
    )
    print(
        "VP correlation analysis complete: "
        f"{summary['rows']:,} rows, {summary['analyzed_features']} features, "
        f"{summary['severe_pairs']} severe pairs, {summary['high_pairs']} high pairs."
    )
    print(f"Reports: {args.output_root}")


if __name__ == "__main__":
    main()
