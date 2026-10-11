"""Leakage-controlled CPCV hyperparameter search for MA+VP MLP contracts.

The final chronological holdout is removed before any CPCV split, model,
threshold, or feature-contract selection. Research reports are written, but no
deployable model or registry artifact is produced.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

from training_mlp.analyze_pwf_trading import load_entry_pnl, trade_statistics
from training_mlp.compare_purged_feature_sets import (
    REDUNDANT_FEATURES,
    ResearchMLP,
    feature_sets,
    load_comparison_frame,
)
from training_mlp.validation import CombinatorialPurgedCrossValidation, EventIntervals


DEFAULT_INPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/"
    "df_features_labeled_master_libb_vp.parquet"
)
DEFAULT_TRADES = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/"
    "trades_30_libb_2026-04-07.csv"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/reports/"
    "cpcv_hyperparameter_search_libb"
)
SEARCH_CONTRACTS = (
    "vp_compact_8",
    "vp_32",
    "ma_vp_45",
    "ma_vp_reduced_42",
)
HIDDEN_CHOICES = ((32, 16), (64, 32), (96, 48), (128, 64), (128, 64, 32))
BATCH_CHOICES = (32, 64, 128, 256)


class CPCVSearchError(RuntimeError):
    """Raised when the research search contract cannot be honored."""


@dataclass(frozen=True)
class SearchConfig:
    trials_per_contract: int = 24
    n_groups: int = 6
    n_test_groups: int = 2
    embargo_pct: float = 0.01
    holdout_fraction: float = 0.15
    epochs: int = 60
    threshold_min: float = 0.35
    threshold_max: float = 0.65
    threshold_step: float = 0.025
    minimum_approval_rate: float = 0.10
    additional_round_trip_cost: float = 0.0
    seed: int = 42
    device: str = "cpu"


@dataclass(frozen=True)
class TrialConfig:
    trial: int
    hidden_dims: tuple[int, ...]
    learning_rate: float
    weight_decay: float
    dropout: float
    batch_size: int


def split_development_holdout(
    frame: pd.DataFrame, holdout_fraction: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return chronological development/holdout frames with interval purging."""
    if not 0.05 <= holdout_fraction <= 0.40:
        raise CPCVSearchError("holdout_fraction must be between 0.05 and 0.40")
    boundary = int(np.floor(len(frame) * (1.0 - holdout_fraction)))
    if boundary < 2 or len(frame) - boundary < 2:
        raise CPCVSearchError("development and holdout must each contain two events")
    holdout_start = frame.loc[boundary, "Date/Time"]
    development = frame.iloc[:boundary].copy()
    development = development.loc[development["t1"] < holdout_start].reset_index(drop=True)
    holdout = frame.iloc[boundary:].reset_index(drop=True)
    if development.empty:
        raise CPCVSearchError("holdout purging removed every development event")
    return development, holdout


def sample_trials(count: int, seed: int) -> list[TrialConfig]:
    """Generate a deterministic bounded randomized search over every dimension."""
    if count < 1:
        raise CPCVSearchError("trials_per_contract must be positive")
    rng = np.random.default_rng(seed)
    trials: list[TrialConfig] = []
    baseline = TrialConfig(0, (64, 32), 1e-3, 1e-2, 0.3, 64)
    trials.append(baseline)
    seen = {(baseline.hidden_dims, baseline.learning_rate, baseline.weight_decay, baseline.dropout, baseline.batch_size)}
    while len(trials) < count:
        candidate = TrialConfig(
            trial=len(trials),
            hidden_dims=HIDDEN_CHOICES[int(rng.integers(len(HIDDEN_CHOICES)))],
            learning_rate=float(10 ** rng.uniform(np.log10(1e-4), np.log10(3e-3))),
            weight_decay=float(10 ** rng.uniform(np.log10(1e-5), np.log10(3e-2))),
            dropout=float(rng.uniform(0.0, 0.5)),
            batch_size=BATCH_CHOICES[int(rng.integers(len(BATCH_CHOICES)))],
        )
        key = (candidate.hidden_dims, candidate.learning_rate, candidate.weight_decay, candidate.dropout, candidate.batch_size)
        if key not in seen:
            seen.add(key)
            trials.append(candidate)
    return trials


def _seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


@torch.no_grad()
def _predict(model: nn.Module, values: np.ndarray, device: torch.device) -> np.ndarray:
    model.eval()
    tensor = torch.tensor(values, dtype=torch.float32, device=device)
    return torch.sigmoid(model(tensor)).cpu().numpy()


def fit_fixed_epochs(
    train_values: np.ndarray,
    train_labels: np.ndarray,
    test_values: np.ndarray,
    *,
    trial: TrialConfig,
    epochs: int,
    seed: int,
    device_name: str,
) -> tuple[np.ndarray, StandardScaler, dict[str, torch.Tensor]]:
    """Fit without consulting the test partition and return test probabilities."""
    _seed(seed)
    device = torch.device(device_name)
    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_values).astype(np.float32)
    test_scaled = scaler.transform(test_values).astype(np.float32)
    dataset = TensorDataset(
        torch.tensor(train_scaled), torch.tensor(train_labels, dtype=torch.float32)
    )
    loader = DataLoader(
        dataset,
        batch_size=trial.batch_size,
        shuffle=False,
        drop_last=len(dataset) % trial.batch_size == 1,
    )
    positives = int((train_labels == 1).sum())
    negatives = int((train_labels == 0).sum())
    if positives == 0 or negatives == 0:
        raise CPCVSearchError("a training partition contains one class")
    model = ResearchMLP(
        train_scaled.shape[1], hidden_dims=trial.hidden_dims, dropout=trial.dropout
    ).to(device)
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([negatives / positives], device=device)
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=trial.learning_rate, weight_decay=trial.weight_decay
    )
    for _ in range(epochs):
        model.train()
        for batch_values, batch_labels in loader:
            batch_values = batch_values.to(device)
            batch_labels = batch_labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(batch_values), batch_labels)
            loss.backward()
            optimizer.step()
    probabilities = _predict(model, test_scaled, device)
    state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    return probabilities, scaler, state


def _thresholds(config: SearchConfig) -> np.ndarray:
    count = int(round((config.threshold_max - config.threshold_min) / config.threshold_step))
    return np.round(config.threshold_min + np.arange(count + 1) * config.threshold_step, 6)


def _joined_pnl(
    frame: pd.DataFrame, trades_path: Path, additional_round_trip_cost: float
) -> np.ndarray:
    if additional_round_trip_cost < 0:
        raise CPCVSearchError("additional_round_trip_cost cannot be negative")
    if "net_pnl_at_3_24_per_side" in frame.columns:
        pnl = pd.to_numeric(
            frame["net_pnl_at_3_24_per_side"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        if not np.isfinite(pnl).all():
            raise CPCVSearchError("research events contain invalid embedded net P&L")
        return pnl - additional_round_trip_cost
    entries = load_entry_pnl(trades_path)
    event_times = frame["entry_time"] if "entry_time" in frame.columns else frame["Date/Time"]
    join_frame = pd.DataFrame({"Date/Time": pd.to_datetime(event_times)})
    joined = join_frame.merge(
        entries, on="Date/Time", how="left", validate="one_to_one"
    )
    if joined["trade_pnl"].isna().any():
        raise CPCVSearchError("one or more research events have no exact TradeStation P&L")
    return (
        joined["trade_pnl"].to_numpy(dtype=np.float64)
        - additional_round_trip_cost
    )


def _trading_row(probabilities: np.ndarray, pnl: np.ndarray, threshold: float) -> dict:
    approved = pnl[probabilities >= threshold]
    return trade_statistics(approved, candidates=len(probabilities))


def evaluate_trial(
    frame: pd.DataFrame,
    pnl: np.ndarray,
    columns: tuple[str, ...],
    splits: list,
    groups: list[np.ndarray],
    *,
    model_name: str,
    trial: TrialConfig,
    config: SearchConfig,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Evaluate one configuration and materialize complete CPCV paths."""
    values = frame.loc[:, list(columns)].to_numpy(dtype=np.float32)
    labels = frame["Label"].to_numpy(dtype=np.int64)
    n_paths = comb(config.n_groups - 1, config.n_test_groups - 1)
    path_probabilities = np.full((n_paths, len(frame)), np.nan, dtype=np.float64)
    split_rows: list[dict] = []
    for split in splits:
        probabilities, _, _ = fit_fixed_epochs(
            values[split.train_indices], labels[split.train_indices], values[split.test_indices],
            trial=trial, epochs=config.epochs,
            seed=config.seed + trial.trial * 1000 + split.split_id,
            device_name=config.device,
        )
        probability_by_index = dict(zip(split.test_indices.tolist(), probabilities.tolist()))
        for group_id, path_id in split.path_assignments.items():
            for event_index in groups[group_id]:
                path_probabilities[path_id, event_index] = probability_by_index[int(event_index)]
        split_rows.append({
            "model": model_name, "trial": trial.trial, "split": split.split_id + 1,
            "test_groups": ",".join(map(str, split.test_groups)),
            "train_n": len(split.train_indices), "test_n": len(split.test_indices),
            "purged_n": len(split.purged_indices), "embargoed_n": len(split.embargoed_indices),
            "roc_auc": roc_auc_score(labels[split.test_indices], probabilities),
            "average_precision": average_precision_score(labels[split.test_indices], probabilities),
            "log_loss": log_loss(labels[split.test_indices], probabilities, labels=[0, 1]),
        })
    if np.isnan(path_probabilities).any():
        raise CPCVSearchError("CPCV path assembly left missing predictions")
    path_rows: list[dict] = []
    for threshold in _thresholds(config):
        for path_id, probabilities in enumerate(path_probabilities):
            stats = _trading_row(probabilities, pnl, float(threshold))
            path_rows.append({
                "model": model_name, "trial": trial.trial, "path": path_id + 1,
                "threshold": float(threshold),
                "roc_auc": roc_auc_score(labels, probabilities),
                "average_precision": average_precision_score(labels, probabilities),
                "log_loss": log_loss(labels, probabilities, labels=[0, 1]),
                **stats,
            })
    paths = pd.DataFrame(path_rows)
    threshold_summary = paths.groupby("threshold", as_index=False).agg(
        roc_auc_median=("roc_auc", "median"),
        average_precision_median=("average_precision", "median"),
        profit_factor_median=("profit_factor", "median"),
        average_trade_median=("average_trade", "median"),
        maximum_drawdown_median=("maximum_drawdown", "median"),
        maximum_drawdown_p95=("maximum_drawdown", lambda values: float(np.quantile(values, 0.95))),
        approval_rate_median=("approval_rate", "median"),
        net_profit_median=("net_profit", "median"),
    )
    eligible = threshold_summary[
        threshold_summary["approval_rate_median"] >= config.minimum_approval_rate
    ].copy()
    if eligible.empty:
        eligible = threshold_summary.copy()
    eligible["threshold_score"] = (
        eligible["profit_factor_median"].rank(pct=True)
        + eligible["average_trade_median"].rank(pct=True)
        + eligible["net_profit_median"].rank(pct=True)
        + eligible["maximum_drawdown_p95"].rank(pct=True, ascending=False)
    ) / 4.0
    best = eligible.sort_values(
        ["threshold_score", "roc_auc_median"], ascending=False, kind="stable"
    ).iloc[0]
    summary = {
        "model": model_name, **asdict(trial), "features": len(columns),
        **best.to_dict(),
    }
    return summary, pd.DataFrame(split_rows), paths


def rank_trials(summaries: pd.DataFrame) -> pd.DataFrame:
    """Create a transparent combined predictive/trading robustness score."""
    result = summaries.copy()
    result["selection_score"] = (
        result["roc_auc_median"].rank(pct=True)
        + result["average_precision_median"].rank(pct=True)
        + result["profit_factor_median"].clip(upper=3.0).rank(pct=True)
        + result["average_trade_median"].rank(pct=True)
        + result["maximum_drawdown_p95"].rank(pct=True, ascending=False)
    ) / 5.0
    return result.sort_values(
        ["selection_score", "roc_auc_median"], ascending=False, kind="stable"
    ).reset_index(drop=True)


def run_search(
    frame: pd.DataFrame, trades_path: Path, config: SearchConfig
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    development, holdout = split_development_holdout(frame, config.holdout_fraction)
    pnl = _joined_pnl(
        development, trades_path, config.additional_round_trip_cost
    )
    events = EventIntervals.from_arrays(development["Date/Time"], development["t1"])
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=config.n_groups, n_test_groups=config.n_test_groups,
        embargo_pct=config.embargo_pct,
    )
    splits = list(splitter.split(events))
    groups = list(np.array_split(np.arange(len(development), dtype=np.int64), config.n_groups))
    summaries: list[dict] = []
    split_frames: list[pd.DataFrame] = []
    path_frames: list[pd.DataFrame] = []
    trials = sample_trials(config.trials_per_contract, config.seed)
    contracts = feature_sets()
    for model_index, model_name in enumerate(SEARCH_CONTRACTS):
        for trial in trials:
            effective = TrialConfig(**{**asdict(trial), "trial": trial.trial})
            summary, split_frame, path_frame = evaluate_trial(
                development, pnl, contracts[model_name], splits, groups,
                model_name=model_name, trial=effective, config=config,
            )
            summaries.append(summary)
            split_frames.append(split_frame)
            path_frames.append(path_frame)
            print(
                f"model={model_name} trial={trial.trial + 1}/{len(trials)} "
                f"auc={summary['roc_auc_median']:.4f} "
                f"pf={summary['profit_factor_median']:.3f} "
                f"threshold={summary['threshold']:.3f}", flush=True
            )
    ranked = rank_trials(pd.DataFrame(summaries))
    winner = ranked.iloc[0]
    winner_trial = TrialConfig(
        trial=int(winner["trial"]),
        hidden_dims=tuple(winner["hidden_dims"]),
        learning_rate=float(winner["learning_rate"]),
        weight_decay=float(winner["weight_decay"]),
        dropout=float(winner["dropout"]),
        batch_size=int(winner["batch_size"]),
    )
    columns = contracts[str(winner["model"])]
    dev_values = development.loc[:, list(columns)].to_numpy(dtype=np.float32)
    holdout_values = holdout.loc[:, list(columns)].to_numpy(dtype=np.float32)
    probabilities, _, _ = fit_fixed_epochs(
        dev_values, development["Label"].to_numpy(dtype=np.int64), holdout_values,
        trial=winner_trial, epochs=config.epochs, seed=config.seed + 999_999,
        device_name=config.device,
    )
    holdout_pnl = _joined_pnl(
        holdout, trades_path, config.additional_round_trip_cost
    )
    threshold = float(winner["threshold"])
    holdout_stats = _trading_row(probabilities, holdout_pnl, threshold)
    holdout_result = pd.DataFrame([{
        "model": winner["model"], "trial": int(winner["trial"]),
        "threshold": threshold, "features": len(columns),
        "roc_auc": roc_auc_score(holdout["Label"], probabilities),
        "average_precision": average_precision_score(holdout["Label"], probabilities),
        "log_loss": log_loss(holdout["Label"], probabilities, labels=[0, 1]),
        **holdout_stats,
    }])
    holdout_predictions = holdout[["Date/Time", "t1", "Label"]].copy()
    holdout_predictions.insert(0, "model", winner["model"])
    holdout_predictions["probability"] = probabilities
    holdout_predictions["approved"] = probabilities >= threshold
    return ranked, pd.concat(split_frames), pd.concat(path_frames), holdout_result, holdout_predictions


def write_results(
    outputs: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame],
    *, input_path: Path, trades_path: Path, output_root: Path, config: SearchConfig,
) -> None:
    ranked, splits, paths, holdout, holdout_predictions = outputs
    output_root.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(output_root / "trial_ranking.csv", index=False)
    splits.to_csv(output_root / "cpcv_split_metrics.csv", index=False)
    paths.to_parquet(output_root / "cpcv_path_metrics.parquet", index=False, compression="zstd")
    holdout.to_csv(output_root / "final_holdout_result.csv", index=False)
    holdout_predictions.to_parquet(
        output_root / "final_holdout_predictions.parquet", index=False, compression="zstd"
    )
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "input": str(input_path), "trades": str(trades_path),
        "config": asdict(config), "contracts": list(SEARCH_CONTRACTS),
        "removed_as_redundant": list(REDUNDANT_FEATURES),
        "winner": ranked.iloc[0].to_dict(),
        "holdout_result": holdout.iloc[0].to_dict(),
        "deployed_artifacts_written": False,
        "registry_modified": False,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--trades", type=Path, default=DEFAULT_TRADES)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--trials", type=int, default=24)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument(
        "--additional-round-trip-cost",
        type=float,
        default=0.0,
        help="Cost to subtract from each source trade P&L beyond embedded costs.",
    )
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    return parser


def main() -> None:
    args = _parser().parse_args()
    config = SearchConfig(
        trials_per_contract=args.trials,
        epochs=args.epochs,
        additional_round_trip_cost=args.additional_round_trip_cost,
        device=args.device,
    )
    frame = load_comparison_frame(args.input)
    development, holdout = split_development_holdout(frame, config.holdout_fraction)
    print(
        f"CPCV search: events={len(frame):,} development={len(development):,} "
        f"chronological_confirmation={len(holdout):,} "
        f"trials/contract={config.trials_per_contract} "
        f"device={config.device}", flush=True
    )
    outputs = run_search(frame, args.trades, config)
    write_results(
        outputs, input_path=args.input, trades_path=args.trades,
        output_root=args.output_root, config=config,
    )
    print("\nWinner:")
    print(outputs[0].head(1).to_string(index=False))
    print("\nChronological confirmation segment:")
    print(outputs[3].to_string(index=False))
    print(f"\nReports: {args.output_root}")


if __name__ == "__main__":
    main()
