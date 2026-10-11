"""Repeat regularized logistic stability studies on the older large datasets."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from math import ceil
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score

from feat_files.canonical_features import FEATURE_NAMES
from feat_files.canonical_volume_profile import VOLUME_PROFILE_FEATURE_NAMES
from training_mlp.analyze_vp_feature_stability import (
    Config,
    ModelSpec,
    analyze_contract,
    evaluate_selected_subset,
    plot_report,
)
from training_mlp.cpcv_hyperparameter_search import _joined_pnl, split_development_holdout
from training_mlp.evaluate_vp_logistic import path_predictions, regularization_grid
from training_mlp.validation import CombinatorialPurgedCrossValidation, EventIntervals


ROOT = Path("training_mlp/strategies/MA2CrossLE")
TRADES = ROOT / "inputs/trades_30_libb_2026-04-07.csv"
OUTPUT = ROOT / "reports/old_dataset_logistic_stability_2026-09-30"
CASES = {
    "old_11196_canonical13": {
        "input": ROOT / "processed/ma2cross_old_libb_prior_bar_13.csv",
        "columns": tuple(FEATURE_NAMES),
        "additional_cost": 0.0,
    },
    "old_6444_canonical13_vp32": {
        "input": ROOT / "processed/ma2cross_old_libb_prior_bar_vp45.parquet",
        "columns": tuple(FEATURE_NAMES + VOLUME_PROFILE_FEATURE_NAMES),
        "additional_cost": 1.98,
    },
}


def load_frame(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_parquet(path)
    required = {"Date/Time", "t1", "Label", *columns}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")
    frame["Date/Time"] = pd.to_datetime(frame["Date/Time"], errors="raise")
    frame["t1"] = pd.to_datetime(frame["t1"], errors="raise")
    frame = frame.sort_values("Date/Time", kind="stable").reset_index(drop=True)
    values = frame.loc[:, list(columns)].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError(f"{path} contains non-finite feature values")
    return frame


def choose_regularization(
    development: pd.DataFrame,
    columns: tuple[str, ...],
    splits: list,
    groups: list[np.ndarray],
    config: Config,
) -> tuple[pd.DataFrame, ModelSpec]:
    labels = development["Label"].to_numpy(dtype=np.int64)
    rows: list[dict[str, object]] = []
    for candidate in regularization_grid():
        paths, _, nonzero = path_predictions(
            development,
            columns,
            splits,
            groups,
            candidate,
            config,
        )
        rows.append(
            {
                "regularization": candidate.name,
                "penalty": candidate.penalty,
                "C": candidate.c,
                "l1_ratio": candidate.l1_ratio,
                "roc_auc_median": float(
                    np.median([roc_auc_score(labels, path) for path in paths])
                ),
                "average_precision_median": float(
                    np.median([average_precision_score(labels, path) for path in paths])
                ),
                "log_loss_median": float(
                    np.median([log_loss(labels, path, labels=[0, 1]) for path in paths])
                ),
                "nonzero_features_median": float(np.median(nonzero)),
            }
        )
    ranking = pd.DataFrame(rows).sort_values(
        ["roc_auc_median", "log_loss_median"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)
    return ranking, select_non_degenerate_spec(ranking, len(columns))


def select_non_degenerate_spec(
    ranking: pd.DataFrame, feature_count: int
) -> ModelSpec:
    """Select the best model retaining at least 10% of candidate features."""
    minimum_nonzero = max(1, ceil(feature_count * 0.10))
    eligible = ranking[
        ranking["nonzero_features_median"] >= minimum_nonzero
    ]
    if eligible.empty:
        raise ValueError(
            f"no regularization candidate retained {minimum_nonzero} features"
        )
    winner = eligible.iloc[0]
    penalty = str(winner["penalty"])
    l1_ratio = {
        "l2": 0.0,
        "l1": 1.0,
        "elasticnet": float(winner["l1_ratio"]),
    }[penalty]
    return ModelSpec(c=float(winner["C"]), l1_ratio=l1_ratio)


def run_case(name: str, definition: dict[str, object], config: Config) -> dict[str, object]:
    input_path = Path(definition["input"])
    columns = tuple(definition["columns"])
    additional_cost = float(definition["additional_cost"])
    frame = load_frame(input_path, columns)
    development, holdout = split_development_holdout(frame, config.holdout_fraction)
    events = EventIntervals.from_arrays(development["Date/Time"], development["t1"])
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=config.n_groups,
        n_test_groups=config.n_test_groups,
        embargo_pct=config.embargo_pct,
    )
    splits = list(splitter.split(events))
    groups = list(np.array_split(np.arange(len(development), dtype=np.int64), config.n_groups))
    destination = OUTPUT / name
    destination.mkdir(parents=True, exist_ok=True)
    print(f"\n{name}: selecting regularization on {len(development):,} events", flush=True)
    ranking_path = destination / "regularization_ranking.csv"
    if ranking_path.is_file():
        ranking = pd.read_csv(ranking_path)
        spec = select_non_degenerate_spec(ranking, len(columns))
    else:
        ranking, spec = choose_regularization(
            development, columns, splits, groups, config
        )
        ranking.to_csv(ranking_path, index=False)
    print(
        f"{name}: C={spec.c:g} l1_ratio={spec.l1_ratio:g}; analyzing {len(columns)} features",
        flush=True,
    )
    report, stability = analyze_contract(
        development, columns, splits, groups, spec, config
    )
    report.to_csv(destination / "feature_stability.csv", index=False)
    plot_report(report, name, destination / "feature_stability.png")
    development_pnl = _joined_pnl(development, TRADES, additional_cost)
    holdout_pnl = _joined_pnl(holdout, TRADES, additional_cost)
    selected = tuple(stability["selected_features"])
    confirmation: list[dict[str, object]] = []
    if selected:
        confirmation = evaluate_selected_subset(
            development,
            holdout,
            development_pnl,
            holdout_pnl,
            selected,
            splits,
            groups,
            spec,
            config,
        )
    pd.DataFrame(confirmation).to_csv(
        destination / "selected_subset_confirmation.csv", index=False
    )
    result = {
        "input": str(input_path),
        "events": len(frame),
        "development_events": len(development),
        "chronological_confirmation_events": len(holdout),
        "date_min": frame["Date/Time"].min().isoformat(),
        "date_max": frame["Date/Time"].max().isoformat(),
        "features": len(columns),
        "additional_round_trip_cost": additional_cost,
        "selected_regularization": asdict(spec),
        "stability": stability,
        "confirmation": confirmation,
    }
    (destination / "manifest.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    config = Config()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = {
        name: run_case(name, definition, config)
        for name, definition in CASES.items()
    }
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "config": asdict(config),
        "round_trip_cost": 6.48,
        "selection_rule": "same predefined 3-of-4 feature-stability rule",
        "results": results,
        "registry_modified": False,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
