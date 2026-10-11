"""Evaluate the selected full logistic specifications on old chronological holds."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from feat_files.canonical_volume_profile import VOLUME_PROFILE_FEATURE_NAMES
from training_mlp.analyze_vp_feature_stability import (
    Config,
    ModelSpec,
    evaluate_selected_subset,
)
from training_mlp.cpcv_hyperparameter_search import _joined_pnl, split_development_holdout
from training_mlp.run_old_dataset_feature_studies import load_frame
from training_mlp.validation import CombinatorialPurgedCrossValidation, EventIntervals


ROOT = Path("training_mlp/strategies/MA2CrossLE")
TRADES = ROOT / "inputs/trades_30_libb_2026-04-07.csv"
OUTPUT = ROOT / "reports/old_dataset_logistic_stability_2026-09-30"
CASES = {
    "old_11196_canonical13": (
        ROOT / "processed/ma2cross_old_libb_prior_bar_13.csv",
        tuple(FEATURE_NAMES),
        ModelSpec(c=0.01, l1_ratio=0.25),
        0.0,
    ),
    "old_6444_canonical13_vp32": (
        ROOT / "processed/ma2cross_old_libb_prior_bar_vp45.parquet",
        tuple(FEATURE_NAMES + VOLUME_PROFILE_FEATURE_NAMES),
        ModelSpec(c=0.001, l1_ratio=0.0),
        1.98,
    ),
}


def main() -> None:
    config = Config()
    rows: list[dict[str, object]] = []
    for name, (input_path, columns, spec, additional_cost) in CASES.items():
        frame = load_frame(input_path, columns)
        development, holdout = split_development_holdout(
            frame, config.holdout_fraction
        )
        events = EventIntervals.from_arrays(development["Date/Time"], development["t1"])
        splitter = CombinatorialPurgedCrossValidation(
            n_groups=config.n_groups,
            n_test_groups=config.n_test_groups,
            embargo_pct=config.embargo_pct,
        )
        splits = list(splitter.split(events))
        groups = list(
            np.array_split(np.arange(len(development), dtype=np.int64), config.n_groups)
        )
        development_pnl = _joined_pnl(development, TRADES, additional_cost)
        holdout_pnl = _joined_pnl(holdout, TRADES, additional_cost)
        results = evaluate_selected_subset(
            development,
            holdout,
            development_pnl,
            holdout_pnl,
            columns,
            splits,
            groups,
            spec,
            config,
        )
        rows.extend({"model": name, **result} for result in results)
    destination = OUTPUT / "full_model_confirmation.csv"
    pd.DataFrame(rows).to_csv(destination, index=False)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
