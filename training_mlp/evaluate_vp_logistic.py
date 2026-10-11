"""CPCV benchmark of regularized logistic regression on VP32 and MA13+VP32.

The final chronological segment is removed before regularization and decision-
threshold selection.  This is a research benchmark and writes no live model.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import product
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from training_mlp.analyze_pwf_trading import trade_statistics
from training_mlp.compare_purged_feature_sets import feature_sets, load_comparison_frame
from training_mlp.cpcv_hyperparameter_search import (
    _joined_pnl,
    split_development_holdout,
)
from training_mlp.validation import CombinatorialPurgedCrossValidation, EventIntervals


DEFAULT_INPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/"
    "ma2cross_esu26_closed_bar_canonical_vp45_common_through_2026-08-14.parquet"
)
DEFAULT_TRADES = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/"
    "trades_30_libb_2026-06-15_to_2026-09-17.csv"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/reports/"
    "logistic_vp32_vp45_cpcv_2026-09-29"
)
CONTRACTS = ("vp_32", "ma_vp_45")


class LogisticBenchmarkError(RuntimeError):
    """Raised when the controlled logistic benchmark cannot be completed."""


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
    seed: int = 42
    max_iter: int = 10_000


@dataclass(frozen=True)
class Regularization:
    penalty: str
    c: float
    l1_ratio: float | None

    @property
    def name(self) -> str:
        suffix = "" if self.l1_ratio is None else f"_l1r{self.l1_ratio:g}"
        return f"{self.penalty}_C{self.c:g}{suffix}"


def regularization_grid() -> list[Regularization]:
    """Return a deterministic grid spanning strong through weak shrinkage."""
    c_values = (0.001, 0.01, 0.1, 1.0, 10.0, 100.0)
    grid = [Regularization(p, c, None) for p, c in product(("l1", "l2"), c_values)]
    grid.extend(
        Regularization("elasticnet", c, ratio)
        for c, ratio in product(c_values, (0.25, 0.50, 0.75))
    )
    return grid


def make_model(spec: Regularization, config: Config) -> Pipeline:
    """Scale within the training partition and fit a regularized classifier."""
    effective_l1_ratio = {
        "l2": 0.0,
        "l1": 1.0,
        "elasticnet": spec.l1_ratio,
    }[spec.penalty]
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=spec.c,
                    l1_ratio=effective_l1_ratio,
                    solver="saga",
                    class_weight="balanced",
                    max_iter=config.max_iter,
                    random_state=config.seed,
                    tol=1e-5,
                ),
            ),
        ]
    )


def thresholds(config: Config) -> np.ndarray:
    count = int(round((config.threshold_max - config.threshold_min) / config.threshold_step))
    return np.round(config.threshold_min + np.arange(count + 1) * config.threshold_step, 6)


def path_predictions(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    splits: list,
    groups: list[np.ndarray],
    spec: Regularization,
    config: Config,
) -> tuple[np.ndarray, pd.DataFrame, np.ndarray]:
    values = frame.loc[:, list(columns)].to_numpy(dtype=np.float64)
    labels = frame["Label"].to_numpy(dtype=np.int64)
    n_paths = comb(config.n_groups - 1, config.n_test_groups - 1)
    paths = np.full((n_paths, len(frame)), np.nan, dtype=np.float64)
    split_rows: list[dict[str, object]] = []
    nonzero_counts: list[int] = []
    for split in splits:
        model = make_model(spec, config)
        model.fit(values[split.train_indices], labels[split.train_indices])
        probabilities = model.predict_proba(values[split.test_indices])[:, 1]
        coefficient = model.named_steps["model"].coef_[0]
        nonzero_counts.append(int(np.count_nonzero(np.abs(coefficient) > 1e-10)))
        by_index = dict(zip(split.test_indices.tolist(), probabilities.tolist()))
        for group_id, path_id in split.path_assignments.items():
            for event_index in groups[group_id]:
                paths[path_id, event_index] = by_index[int(event_index)]
        split_rows.append(
            {
                "regularization": spec.name,
                "split": split.split_id + 1,
                "train_n": len(split.train_indices),
                "test_n": len(split.test_indices),
                "purged_n": len(split.purged_indices),
                "embargoed_n": len(split.embargoed_indices),
                "roc_auc": roc_auc_score(labels[split.test_indices], probabilities),
                "average_precision": average_precision_score(
                    labels[split.test_indices], probabilities
                ),
                "log_loss": log_loss(
                    labels[split.test_indices], probabilities, labels=[0, 1]
                ),
                "nonzero_features": nonzero_counts[-1],
            }
        )
    if np.isnan(paths).any():
        raise LogisticBenchmarkError("CPCV path assembly left missing predictions")
    return paths, pd.DataFrame(split_rows), np.asarray(nonzero_counts)


def select_threshold(
    probabilities: np.ndarray, pnl: np.ndarray, config: Config
) -> tuple[float, pd.DataFrame]:
    rows: list[dict[str, float]] = []
    for threshold in thresholds(config):
        stats = [
            trade_statistics(pnl[path >= threshold], candidates=len(pnl))
            for path in probabilities
        ]
        rows.append(
            {
                "threshold": float(threshold),
                "approval_rate_median": float(np.median([x["approval_rate"] for x in stats])),
                "net_profit_median": float(np.median([x["net_profit"] for x in stats])),
                "profit_factor_median": float(np.median([x["profit_factor"] for x in stats])),
                "average_trade_median": float(np.median([x["average_trade"] for x in stats])),
                "maximum_drawdown_median": float(np.median([x["maximum_drawdown"] for x in stats])),
            }
        )
    report = pd.DataFrame(rows)
    eligible = report[report["approval_rate_median"] >= config.minimum_approval_rate].copy()
    if eligible.empty:
        eligible = report.copy()
    eligible["score"] = (
        eligible["net_profit_median"].rank(pct=True)
        + eligible["profit_factor_median"].rank(pct=True)
        + eligible["average_trade_median"].rank(pct=True)
        + eligible["maximum_drawdown_median"].rank(pct=True, ascending=False)
    ) / 4.0
    winner = eligible.sort_values(
        ["score", "threshold"], ascending=[False, True], kind="stable"
    ).iloc[0]
    return float(winner["threshold"]), report


def run(frame: pd.DataFrame, trades: Path, output: Path, config: Config) -> None:
    development, holdout = split_development_holdout(frame, config.holdout_fraction)
    development_pnl = _joined_pnl(development, trades, 0.0)
    holdout_pnl = _joined_pnl(holdout, trades, 0.0)
    events = EventIntervals.from_arrays(development["Date/Time"], development["t1"])
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=config.n_groups,
        n_test_groups=config.n_test_groups,
        embargo_pct=config.embargo_pct,
    )
    splits = list(splitter.split(events))
    groups = list(np.array_split(np.arange(len(development), dtype=np.int64), config.n_groups))
    labels = development["Label"].to_numpy(dtype=np.int64)
    contracts = feature_sets()
    output.mkdir(parents=True, exist_ok=True)
    all_rankings: list[pd.DataFrame] = []
    all_splits: list[pd.DataFrame] = []
    holdout_rows: list[dict[str, object]] = []
    coefficient_rows: list[dict[str, object]] = []
    for contract in CONTRACTS:
        columns = contracts[contract]
        candidates: list[dict[str, object]] = []
        cached_paths: dict[str, np.ndarray] = {}
        print(f"\n{contract}: {len(columns)} features", flush=True)
        for spec in regularization_grid():
            paths, split_metrics, nonzero = path_predictions(
                development, columns, splits, groups, spec, config
            )
            cached_paths[spec.name] = paths
            all_splits.append(split_metrics.assign(model=contract))
            candidates.append(
                {
                    "model": contract,
                    "regularization": spec.name,
                    "penalty": spec.penalty,
                    "C": spec.c,
                    "l1_ratio": spec.l1_ratio,
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
        ranking = pd.DataFrame(candidates).sort_values(
            ["roc_auc_median", "log_loss_median"],
            ascending=[False, True],
            kind="stable",
        ).reset_index(drop=True)
        all_rankings.append(ranking)
        winner = ranking.iloc[0]
        winning_spec = next(
            item for item in regularization_grid() if item.name == winner["regularization"]
        )
        winning_paths = cached_paths[winning_spec.name]
        selected_threshold, threshold_report = select_threshold(
            winning_paths, development_pnl, config
        )
        threshold_report.assign(model=contract).to_csv(
            output / f"{contract}_thresholds.csv", index=False
        )
        model = make_model(winning_spec, config)
        dev_values = development.loc[:, list(columns)].to_numpy(dtype=np.float64)
        holdout_values = holdout.loc[:, list(columns)].to_numpy(dtype=np.float64)
        model.fit(dev_values, development["Label"].to_numpy(dtype=np.int64))
        holdout_probability = model.predict_proba(holdout_values)[:, 1]
        coefficient = model.named_steps["model"].coef_[0]
        coefficient_rows.extend(
            {
                "model": contract,
                "feature": feature,
                "coefficient_standardized": float(value),
                "abs_coefficient": abs(float(value)),
                "nonzero": bool(abs(value) > 1e-10),
            }
            for feature, value in zip(columns, coefficient)
        )
        predictive = {
            "roc_auc": roc_auc_score(holdout["Label"], holdout_probability),
            "average_precision": average_precision_score(
                holdout["Label"], holdout_probability
            ),
            "log_loss": log_loss(
                holdout["Label"], holdout_probability, labels=[0, 1]
            ),
        }
        for threshold_kind, threshold in (
            ("fixed_0.50", 0.50),
            ("development_selected", selected_threshold),
        ):
            stats = trade_statistics(
                holdout_pnl[holdout_probability >= threshold], candidates=len(holdout)
            )
            holdout_rows.append(
                {
                    "model": contract,
                    "regularization": winning_spec.name,
                    "threshold_kind": threshold_kind,
                    "threshold": threshold,
                    **predictive,
                    **stats,
                }
            )
        predictions = holdout[["Date/Time", "t1", "Label"]].copy()
        predictions["model"] = contract
        predictions["probability"] = holdout_probability
        predictions.to_parquet(
            output / f"{contract}_holdout_predictions.parquet",
            index=False,
            compression="zstd",
        )
        print(
            f"winner={winning_spec.name} dev_auc={winner['roc_auc_median']:.4f} "
            f"holdout_auc={predictive['roc_auc']:.4f} threshold={selected_threshold:.3f}",
            flush=True,
        )
    ranking_frame = pd.concat(all_rankings, ignore_index=True)
    split_frame = pd.concat(all_splits, ignore_index=True)
    holdout_frame = pd.DataFrame(holdout_rows)
    coefficient_frame = pd.DataFrame(coefficient_rows).sort_values(
        ["model", "abs_coefficient"], ascending=[True, False]
    )
    ranking_frame.to_csv(output / "regularization_ranking.csv", index=False)
    split_frame.to_csv(output / "cpcv_split_metrics.csv", index=False)
    holdout_frame.to_csv(output / "holdout_results.csv", index=False)
    coefficient_frame.to_csv(output / "final_coefficients.csv", index=False)
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "input": str(DEFAULT_INPUT),
        "trades": str(trades),
        "events": len(frame),
        "development_events": len(development),
        "chronological_confirmation_events": len(holdout),
        "contracts": list(CONTRACTS),
        "config": asdict(config),
        "regularization_selection": "highest median complete-path development CPCV ROC AUC; lowest log loss tie-break",
        "threshold_selection": "development CPCV only; holdout never consulted",
        "round_trip_cost": 6.48,
        "deployed_artifacts_written": False,
        "registry_modified": False,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print("\nChronological confirmation results:")
    print(holdout_frame.to_string(index=False))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    result.add_argument("--trades", type=Path, default=DEFAULT_TRADES)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return result


def main() -> None:
    args = parser().parse_args()
    frame = load_comparison_frame(args.input)
    run(frame, args.trades, args.output, Config())


if __name__ == "__main__":
    main()
