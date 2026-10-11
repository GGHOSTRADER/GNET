"""Analyze Pearson/Spearman redundancy among the canonical 13 MA features."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.analyze_vp_correlations import build_pair_report


DEFAULT_INPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/df_features_labeled.csv"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/reports/correlation_13_all"
)


class MACorrelationError(RuntimeError):
    """Raised when canonical MA correlation analysis cannot run safely."""


def load_ma_features(path: Path) -> pd.DataFrame:
    """Load only the canonical 13 features from CSV or Parquet."""
    if not path.is_file():
        raise MACorrelationError(f"MA feature dataset does not exist: {path}")
    columns = list(FEATURE_NAMES)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, usecols=columns)
    elif path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path, columns=columns)
    else:
        raise MACorrelationError("input extension must be .csv or .parquet")
    if frame.empty:
        raise MACorrelationError("MA feature dataset is empty")
    values = frame.to_numpy(dtype=np.float64, copy=False)
    if not np.isfinite(values).all():
        bad = np.argwhere(~np.isfinite(values))[0]
        raise MACorrelationError(
            f"non-finite value at row {int(bad[0])}, feature {columns[int(bad[1])]}"
        )
    return frame


def analyze(
    input_path: Path,
    output_root: Path,
    *,
    high_threshold: float = 0.90,
    severe_threshold: float = 0.95,
) -> dict[str, object]:
    """Write the same correlation report contract used for canonical VP."""
    if not 0.0 < high_threshold <= severe_threshold <= 1.0:
        raise MACorrelationError(
            "thresholds must satisfy 0 < high_threshold <= severe_threshold <= 1"
        )
    frame = load_ma_features(input_path)
    standard_deviation = frame.std(ddof=0)
    constant_features = standard_deviation[standard_deviation == 0.0].index.tolist()
    variable_frame = frame.drop(columns=constant_features)
    if variable_frame.shape[1] < 2:
        raise MACorrelationError("fewer than two non-constant features are available")

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
        "input": str(input_path),
        "rows": len(frame),
        "canonical_features": len(FEATURE_NAMES),
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
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--high-threshold", type=float, default=0.90)
    parser.add_argument("--severe-threshold", type=float, default=0.95)
    return parser


def main() -> None:
    args = _parser().parse_args()
    summary = analyze(
        args.input,
        args.output,
        high_threshold=args.high_threshold,
        severe_threshold=args.severe_threshold,
    )
    print(
        "MA correlation analysis complete: "
        f"{summary['rows']:,} rows, {summary['analyzed_features']} features, "
        f"{summary['severe_pairs']} severe pairs, {summary['high_pairs']} high pairs."
    )


if __name__ == "__main__":
    main()
