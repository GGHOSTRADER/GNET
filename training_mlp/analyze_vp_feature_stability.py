"""Quantitative fold-stability and ablation analysis for VP32 and MA13+VP32.

Selection uses only the purged CPCV development sample.  The later chronological
confirmation segment is deliberately excluded from every calculation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from math import comb
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from training_mlp.analyze_pwf_trading import trade_statistics
from training_mlp.compare_purged_feature_sets import feature_sets, load_comparison_frame
from training_mlp.cpcv_hyperparameter_search import _joined_pnl, split_development_holdout
from training_mlp.evaluate_vp_logistic import select_threshold
from training_mlp.validation import CombinatorialPurgedCrossValidation, EventIntervals


DEFAULT_INPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/"
    "ma2cross_esu26_closed_bar_canonical_vp45_common_through_2026-08-14.parquet"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/reports/"
    "vp_feature_stability_2026-09-29"
)
CONTRACTS = ("vp_32", "ma_vp_45")


@dataclass(frozen=True)
class Config:
    n_groups: int = 6
    n_test_groups: int = 2
    embargo_pct: float = 0.01
    holdout_fraction: float = 0.15
    threshold_min: float = 0.35
    threshold_max: float = 0.65
    threshold_step: float = 0.025
    minimum_approval_rate: float = 0.10
    max_iter: int = 10_000
    permutation_repeats: int = 20
    seed: int = 42
    sign_consistency_min: float = 0.75
    positive_split_fraction_min: float = 0.60
    minimum_passes: int = 3


@dataclass(frozen=True)
class ModelSpec:
    c: float
    l1_ratio: float


SELECTED_SPECS = {
    "vp_32": ModelSpec(c=0.01, l1_ratio=0.0),
    "ma_vp_45": ModelSpec(c=0.01, l1_ratio=0.25),
}


def make_model(spec: ModelSpec, seed: int) -> Pipeline:
    """Return the fixed regularized logistic model selected previously by CPCV."""
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=spec.c,
                    l1_ratio=spec.l1_ratio,
                    solver="saga",
                    class_weight="balanced",
                    max_iter=10_000,
                    tol=1e-5,
                    random_state=seed,
                ),
            ),
        ]
    )


def complete_path_auc(
    values: np.ndarray,
    labels: np.ndarray,
    splits: list,
    groups: list[np.ndarray],
    spec: ModelSpec,
    seed: int,
) -> tuple[float, np.ndarray]:
    """Return median complete-path AUC and all assembled CPCV path AUCs."""
    n_paths = comb(len(groups) - 1, 1)
    probabilities = np.full((n_paths, len(labels)), np.nan, dtype=np.float64)
    for split in splits:
        model = make_model(spec, seed + split.split_id)
        model.fit(values[split.train_indices], labels[split.train_indices])
        predicted = model.predict_proba(values[split.test_indices])[:, 1]
        by_index = dict(zip(split.test_indices.tolist(), predicted.tolist()))
        for group_id, path_id in split.path_assignments.items():
            for event_index in groups[group_id]:
                probabilities[path_id, event_index] = by_index[int(event_index)]
    if np.isnan(probabilities).any():
        raise RuntimeError("CPCV path assembly left missing predictions")
    aucs = np.asarray([roc_auc_score(labels, row) for row in probabilities])
    return float(np.median(aucs)), aucs


def analyze_contract(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    splits: list,
    groups: list[np.ndarray],
    spec: ModelSpec,
    config: Config,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Measure four independent indicators of feature stability."""
    values = frame.loc[:, list(columns)].to_numpy(dtype=np.float64)
    labels = frame["Label"].to_numpy(dtype=np.int64)
    baseline_median, baseline_paths = complete_path_auc(
        values, labels, splits, groups, spec, config.seed
    )
    coefficient_values = {name: [] for name in columns}
    permutation_values = {name: [] for name in columns}
    univariate_values = {name: [] for name in columns}
    rng = np.random.default_rng(config.seed)
    for split in splits:
        train = split.train_indices
        test = split.test_indices
        model = make_model(spec, config.seed + split.split_id)
        model.fit(values[train], labels[train])
        probability = model.predict_proba(values[test])[:, 1]
        baseline_split_auc = roc_auc_score(labels[test], probability)
        coefficient = model.named_steps["model"].coef_[0]
        for feature_index, feature in enumerate(columns):
            coefficient_values[feature].append(float(coefficient[feature_index]))
            decreases: list[float] = []
            for _ in range(config.permutation_repeats):
                permuted = values[test].copy()
                permuted[:, feature_index] = rng.permutation(permuted[:, feature_index])
                permuted_auc = roc_auc_score(
                    labels[test], model.predict_proba(permuted)[:, 1]
                )
                decreases.append(baseline_split_auc - permuted_auc)
            permutation_values[feature].append(float(np.mean(decreases)))
            univariate = make_model(ModelSpec(c=1.0, l1_ratio=0.0), config.seed)
            univariate.fit(values[train, feature_index : feature_index + 1], labels[train])
            univariate_probability = univariate.predict_proba(
                values[test, feature_index : feature_index + 1]
            )[:, 1]
            univariate_values[feature].append(
                float(roc_auc_score(labels[test], univariate_probability))
            )
    rows: list[dict[str, object]] = []
    for feature_index, feature in enumerate(columns):
        reduced = np.delete(values, feature_index, axis=1)
        reduced_median, _ = complete_path_auc(
            reduced, labels, splits, groups, spec, config.seed + 10_000 + feature_index
        )
        coefficients = np.asarray(coefficient_values[feature])
        permutations = np.asarray(permutation_values[feature])
        univariate = np.asarray(univariate_values[feature])
        nonzero = np.abs(coefficients) > 1e-10
        nonzero_coefficients = coefficients[nonzero]
        if len(nonzero_coefficients):
            positive = float(np.mean(nonzero_coefficients > 0))
            negative = float(np.mean(nonzero_coefficients < 0))
            sign_consistency = max(positive, negative)
            dominant_sign = 1 if positive >= negative else -1
        else:
            sign_consistency = 0.0
            dominant_sign = 0
        permutation_pass = bool(
            np.median(permutations) > 0
            and np.mean(permutations > 0) >= config.positive_split_fraction_min
        )
        ablation_delta = baseline_median - reduced_median
        ablation_pass = bool(ablation_delta > 0)
        sign_pass = bool(
            np.mean(nonzero) >= config.positive_split_fraction_min
            and sign_consistency >= config.sign_consistency_min
        )
        univariate_pass = bool(
            np.median(univariate) > 0.5
            and np.mean(univariate > 0.5) >= config.positive_split_fraction_min
        )
        passes = sum((permutation_pass, ablation_pass, sign_pass, univariate_pass))
        rows.append(
            {
                "feature": feature,
                "baseline_path_auc_median": baseline_median,
                "coefficient_median": float(np.median(coefficients)),
                "coefficient_nonzero_fraction": float(np.mean(nonzero)),
                "dominant_sign": dominant_sign,
                "sign_consistency": sign_consistency,
                "permutation_auc_decrease_median": float(np.median(permutations)),
                "permutation_positive_split_fraction": float(np.mean(permutations > 0)),
                "leave_one_out_path_auc_median": reduced_median,
                "leave_one_out_auc_delta": ablation_delta,
                "univariate_split_auc_median": float(np.median(univariate)),
                "univariate_above_random_split_fraction": float(np.mean(univariate > 0.5)),
                "permutation_pass": permutation_pass,
                "ablation_pass": ablation_pass,
                "sign_pass": sign_pass,
                "univariate_pass": univariate_pass,
                "passes": passes,
                "selected": passes >= config.minimum_passes,
            }
        )
    report = pd.DataFrame(rows).sort_values(
        ["passes", "permutation_auc_decrease_median", "leave_one_out_auc_delta"],
        ascending=[False, False, False],
        kind="stable",
    )
    summary = {
        "features": len(columns),
        "baseline_path_auc_median": baseline_median,
        "baseline_path_aucs": baseline_paths.tolist(),
        "selected_features": report.loc[report["selected"], "feature"].tolist(),
        "selected_count": int(report["selected"].sum()),
    }
    return report, summary


def plot_report(report: pd.DataFrame, model: str, destination: Path) -> None:
    """Plot the two validation-based marginal importance measures."""
    ordered = report.sort_values("permutation_auc_decrease_median").tail(20)
    figure, axes = plt.subplots(1, 2, figsize=(15, 8))
    axes[0].barh(ordered["feature"], ordered["permutation_auc_decrease_median"])
    axes[0].axvline(0, color="black", linewidth=0.8)
    axes[0].set_title("Median validation AUC decrease after permutation")
    axes[0].set_xlabel("AUC decrease")
    ordered_ablation = report.sort_values("leave_one_out_auc_delta").tail(20)
    axes[1].barh(ordered_ablation["feature"], ordered_ablation["leave_one_out_auc_delta"])
    axes[1].axvline(0, color="black", linewidth=0.8)
    axes[1].set_title("Complete-path AUC lost when feature is removed")
    axes[1].set_xlabel("Baseline AUC − leave-one-out AUC")
    figure.suptitle(f"{model} quantitative feature stability (development CPCV only)")
    figure.tight_layout()
    figure.savefig(destination, dpi=160, bbox_inches="tight")
    plt.close(figure)


def evaluate_selected_subset(
    development: pd.DataFrame,
    holdout: pd.DataFrame,
    development_pnl: np.ndarray,
    holdout_pnl: np.ndarray,
    columns: tuple[str, ...],
    splits: list,
    groups: list[np.ndarray],
    spec: ModelSpec,
    config: Config,
) -> list[dict[str, object]]:
    """Evaluate a development-selected subset on the excluded chronology."""
    development_values = development.loc[:, list(columns)].to_numpy(dtype=np.float64)
    holdout_values = holdout.loc[:, list(columns)].to_numpy(dtype=np.float64)
    development_labels = development["Label"].to_numpy(dtype=np.int64)
    holdout_labels = holdout["Label"].to_numpy(dtype=np.int64)
    _, path_aucs = complete_path_auc(
        development_values,
        development_labels,
        splits,
        groups,
        spec,
        config.seed + 20_000,
    )
    n_paths = len(path_aucs)
    path_probabilities = np.full(
        (n_paths, len(development)), np.nan, dtype=np.float64
    )
    for split in splits:
        model = make_model(spec, config.seed + 20_000 + split.split_id)
        model.fit(
            development_values[split.train_indices],
            development_labels[split.train_indices],
        )
        probability = model.predict_proba(
            development_values[split.test_indices]
        )[:, 1]
        by_index = dict(zip(split.test_indices.tolist(), probability.tolist()))
        for group_id, path_id in split.path_assignments.items():
            for event_index in groups[group_id]:
                path_probabilities[path_id, event_index] = by_index[int(event_index)]
    if np.isnan(path_probabilities).any():
        raise RuntimeError("selected-subset CPCV paths contain missing predictions")
    threshold, _ = select_threshold(path_probabilities, development_pnl, config)
    final_model = make_model(spec, config.seed + 30_000)
    final_model.fit(development_values, development_labels)
    holdout_probability = final_model.predict_proba(holdout_values)[:, 1]
    auc = float(roc_auc_score(holdout_labels, holdout_probability))
    rows: list[dict[str, object]] = []
    for threshold_kind, value in (
        ("fixed_0.50", 0.50),
        ("development_selected", threshold),
    ):
        stats = trade_statistics(
            holdout_pnl[holdout_probability >= value], candidates=len(holdout)
        )
        rows.append(
            {
                "threshold_kind": threshold_kind,
                "threshold": value,
                "features": len(columns),
                "feature_names": "|".join(columns),
                "development_path_auc_median": float(np.median(path_aucs)),
                "confirmation_auc": auc,
                **stats,
            }
        )
    return rows


def run(input_path: Path, output: Path, config: Config) -> dict[str, object]:
    frame = load_comparison_frame(input_path)
    development, holdout = split_development_holdout(frame, config.holdout_fraction)
    events = EventIntervals.from_arrays(development["Date/Time"], development["t1"])
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=config.n_groups,
        n_test_groups=config.n_test_groups,
        embargo_pct=config.embargo_pct,
    )
    splits = list(splitter.split(events))
    groups = list(np.array_split(np.arange(len(development), dtype=np.int64), config.n_groups))
    contracts = feature_sets()
    development_pnl = _joined_pnl(development, Path(), 0.0)
    holdout_pnl = _joined_pnl(holdout, Path(), 0.0)
    output.mkdir(parents=True, exist_ok=True)
    summaries: dict[str, object] = {}
    selected_evaluations: list[dict[str, object]] = []
    for model in CONTRACTS:
        print(f"Analyzing {model}...", flush=True)
        report, summary = analyze_contract(
            development,
            contracts[model],
            splits,
            groups,
            SELECTED_SPECS[model],
            config,
        )
        report.to_csv(output / f"{model}_feature_stability.csv", index=False)
        plot_report(report, model, output / f"{model}_feature_stability.png")
        summaries[model] = summary
        selected_columns = tuple(summary["selected_features"])
        if selected_columns:
            selected_evaluations.extend(
                {"model": model, **row}
                for row in evaluate_selected_subset(
                    development,
                    holdout,
                    development_pnl,
                    holdout_pnl,
                    selected_columns,
                    splits,
                    groups,
                    SELECTED_SPECS[model],
                    config,
                )
            )
        print(
            f"{model}: baseline AUC={summary['baseline_path_auc_median']:.4f}, "
            f"selected={summary['selected_count']}",
            flush=True,
        )
    pd.DataFrame(selected_evaluations).to_csv(
        output / "selected_subset_confirmation.csv", index=False
    )
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "input": str(input_path),
        "events": len(frame),
        "development_events": len(development),
        "excluded_chronological_events": len(holdout),
        "config": asdict(config),
        "selected_model_specs": {
            key: asdict(value) for key, value in SELECTED_SPECS.items()
        },
        "selection_rule": "at least 3 of 4: positive validation permutation importance, positive leave-one-out complete-path AUC contribution, stable coefficient sign, above-random univariate validation AUC",
        "results": summaries,
        "selected_subset_confirmation": selected_evaluations,
        "confirmation_segment_consulted": False,
        "registry_modified": False,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return result


def main() -> None:
    args = parser().parse_args()
    manifest = run(args.input, args.output, Config())
    print(json.dumps(manifest["results"], indent=2))


if __name__ == "__main__":
    main()
