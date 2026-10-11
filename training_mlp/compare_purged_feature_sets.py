"""Compare MA, full MA+VP, and correlation-reduced MLPs with identical PWF folds."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

from feat_files.canonical_features import FEATURE_NAMES
from feat_files.canonical_volume_profile import VOLUME_PROFILE_FEATURE_NAMES
from training_mlp.validation import EventIntervals, PurgedWalkForward


DEFAULT_INPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/"
    "df_features_labeled_master_vp.parquet"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/reports/pwf_feature_comparison"
)
REDUNDANT_FEATURES = (
    "parkinson_vol_15",
    "profile_entropy",
    "classified_value_area_delta_ratio",
)
COMPACT_VP_FEATURES = (
    "poc_distance",
    "va_position",
    "poc_migration",
    "classified_delta_ratio",
    "price_classified_delta_divergence",
    "va_expansion_rate",
    "nearest_hvn_distance_ticks",
    "nearest_lvn_distance_ticks",
)


class FeatureComparisonError(RuntimeError):
    """Raised when a fair purged feature comparison cannot be run."""


@dataclass(frozen=True)
class ComparisonConfig:
    n_splits: int = 5
    embargo_pct: float = 0.01
    epochs: int = 100
    patience: int = 15
    batch_size: int = 64
    learning_rate: float = 1e-3
    minimum_learning_rate: float = 1e-6
    warmup_epochs: int = 10
    weight_decay: float = 1e-2
    threshold: float = 0.5
    seed: int = 42
    device: str = "cpu"


class ResearchMLP(nn.Module):
    """The deployed two-hidden-layer MLP architecture used for comparison."""

    def __init__(self, input_dim: int, hidden_dims=(64, 32), dropout: float = 0.3):
        super().__init__()
        layers: list[nn.Module] = []
        previous = input_dim
        for hidden in hidden_dims:
            layers.extend(
                [
                    nn.Linear(previous, hidden),
                    nn.BatchNorm1d(hidden),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                ]
            )
            previous = hidden
        layers.append(nn.Linear(previous, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return self.net(values).squeeze(1)


def feature_sets() -> dict[str, tuple[str, ...]]:
    """Return the predeclared, order-stable research model contracts."""
    ma = tuple(FEATURE_NAMES)
    vp = tuple(VOLUME_PROFILE_FEATURE_NAMES)
    full = tuple(FEATURE_NAMES + VOLUME_PROFILE_FEATURE_NAMES)
    reduced = tuple(name for name in full if name not in REDUNDANT_FEATURES)
    return {
        "ma_13": ma,
        "vp_32": vp,
        "vp_compact_8": COMPACT_VP_FEATURES,
        "ma_vp_45": full,
        "ma_vp_reduced_42": reduced,
    }


def load_comparison_frame(path: Path) -> pd.DataFrame:
    """Load one common event universe and validate every model contract."""
    if not path.is_file():
        raise FeatureComparisonError(f"comparison input does not exist: {path}")
    frame = pd.read_parquet(path).sort_values("Date/Time", kind="stable")
    frame = frame.reset_index(drop=True)
    required = {"Date/Time", "t1", "Label"}
    for names in feature_sets().values():
        required.update(names)
    missing = required - set(frame.columns)
    if missing:
        raise FeatureComparisonError(
            f"comparison input is missing columns: {', '.join(sorted(missing))}"
        )
    frame["Date/Time"] = pd.to_datetime(frame["Date/Time"], errors="coerce")
    frame["t1"] = pd.to_datetime(frame["t1"], errors="coerce")
    if frame[["Date/Time", "t1"]].isna().any().any():
        raise FeatureComparisonError("comparison input contains invalid event times")
    if (frame["t1"] < frame["Date/Time"]).any():
        raise FeatureComparisonError("comparison input contains t1 before entry")
    if not frame["Label"].isin([0, 1]).all():
        raise FeatureComparisonError("Label must contain only 0 and 1")
    values = frame.loc[:, list(feature_sets()["ma_vp_45"])].to_numpy(
        dtype=np.float64
    )
    if not np.isfinite(values).all():
        raise FeatureComparisonError("comparison features contain non-finite values")
    return frame


def make_splits(
    frame: pd.DataFrame, *, n_splits: int, embargo_pct: float
) -> list:
    """Materialize the one split schedule shared by all feature contracts."""
    events = EventIntervals.from_arrays(frame["Date/Time"], frame["t1"])
    return list(
        PurgedWalkForward(
            n_splits=n_splits, embargo_pct=embargo_pct
        ).split(events)
    )


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _scheduler(
    optimizer,
    *,
    warmup_epochs: int,
    total_epochs: int,
    learning_rate: float,
    minimum_learning_rate: float,
):
    def multiplier(epoch: int) -> float:
        if epoch < warmup_epochs:
            return (epoch + 1) / max(warmup_epochs, 1)
        progress = (epoch - warmup_epochs) / max(total_epochs - warmup_epochs, 1)
        cosine = 0.5 * (1.0 + np.cos(np.pi * progress))
        floor = minimum_learning_rate / learning_rate
        return floor + (1.0 - floor) * cosine

    return torch.optim.lr_scheduler.LambdaLR(optimizer, multiplier)


@torch.no_grad()
def _predict(model, values: np.ndarray, device: torch.device) -> np.ndarray:
    model.eval()
    tensor = torch.tensor(values, dtype=torch.float32, device=device)
    return torch.sigmoid(model(tensor)).cpu().numpy()


def _metrics(labels: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict:
    predictions = (probabilities >= threshold).astype(np.int64)
    return {
        "accuracy": accuracy_score(labels, predictions),
        "balanced_accuracy": balanced_accuracy_score(labels, predictions),
        "precision": precision_score(labels, predictions, zero_division=0),
        "recall": recall_score(labels, predictions, zero_division=0),
        "f1": f1_score(labels, predictions, zero_division=0),
        "roc_auc": roc_auc_score(labels, probabilities),
        "average_precision": average_precision_score(labels, probabilities),
        "log_loss": log_loss(labels, probabilities, labels=[0, 1]),
        "brier_score": brier_score_loss(labels, probabilities),
        "approval_rate": predictions.mean(),
    }


def train_fold(
    train_values: np.ndarray,
    train_labels: np.ndarray,
    validation_values: np.ndarray,
    validation_labels: np.ndarray,
    *,
    config: ComparisonConfig,
    seed: int,
) -> tuple[dict[str, float], np.ndarray, int]:
    """Fit preprocessing and a fresh MLP using only one fold's training rows."""
    _seed_everything(seed)
    device = torch.device(config.device)
    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_values).astype(np.float32)
    validation_scaled = scaler.transform(validation_values).astype(np.float32)

    train_tensor = TensorDataset(
        torch.tensor(train_scaled), torch.tensor(train_labels, dtype=torch.float32)
    )
    drop_last = len(train_tensor) % config.batch_size == 1
    loader = DataLoader(
        train_tensor,
        batch_size=config.batch_size,
        shuffle=False,
        drop_last=drop_last,
    )
    positives = int((train_labels == 1).sum())
    negatives = int((train_labels == 0).sum())
    if positives == 0 or negatives == 0:
        raise FeatureComparisonError("a training fold contains only one class")
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([negatives / positives], device=device)
    )
    model = ResearchMLP(train_scaled.shape[1]).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    scheduler = _scheduler(
        optimizer,
        warmup_epochs=config.warmup_epochs,
        total_epochs=config.epochs,
        learning_rate=config.learning_rate,
        minimum_learning_rate=config.minimum_learning_rate,
    )

    best_loss = np.inf
    best_state = None
    stale_epochs = 0
    epochs_run = 0
    validation_tensor = torch.tensor(
        validation_scaled, dtype=torch.float32, device=device
    )
    validation_target = torch.tensor(
        validation_labels, dtype=torch.float32, device=device
    )
    for epoch in range(config.epochs):
        model.train()
        for batch_values, batch_labels in loader:
            batch_values = batch_values.to(device)
            batch_labels = batch_labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(batch_values), batch_labels)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = float(
                criterion(model(validation_tensor), validation_target).item()
            )
        scheduler.step()
        epochs_run = epoch + 1
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= config.patience:
                break
    if best_state is None:
        raise FeatureComparisonError("training produced no valid model state")
    model.load_state_dict(best_state)
    probabilities = _predict(model, validation_scaled, device)
    return _metrics(validation_labels, probabilities, config.threshold), probabilities, epochs_run


def run_comparison(
    frame: pd.DataFrame, config: ComparisonConfig
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run all feature contracts on identical precomputed PWF splits."""
    splits = make_splits(
        frame, n_splits=config.n_splits, embargo_pct=config.embargo_pct
    )
    labels = frame["Label"].to_numpy(dtype=np.int64)
    results: list[dict[str, object]] = []
    predictions: list[pd.DataFrame] = []
    schedule: list[dict[str, object]] = []
    for split in splits:
        schedule.append(
            {
                "fold": split.split_id + 1,
                "train_n": len(split.train_indices),
                "validation_n": len(split.test_indices),
                "purged_n": len(split.purged_indices),
                "embargoed_after_validation_n": len(split.embargoed_indices),
                "train_start": frame.loc[split.train_indices[0], "Date/Time"],
                "train_end": frame.loc[split.train_indices[-1], "Date/Time"],
                "validation_start": frame.loc[split.test_indices[0], "Date/Time"],
                "validation_end": frame.loc[split.test_indices[-1], "Date/Time"],
            }
        )
        for model_index, (model_name, columns) in enumerate(feature_sets().items()):
            values = frame.loc[:, list(columns)].to_numpy(dtype=np.float32)
            fold_seed = config.seed + split.split_id * 100 + model_index
            metrics, probabilities, epochs_run = train_fold(
                values[split.train_indices],
                labels[split.train_indices],
                values[split.test_indices],
                labels[split.test_indices],
                config=config,
                seed=fold_seed,
            )
            results.append(
                {
                    "model": model_name,
                    "fold": split.split_id + 1,
                    "features": len(columns),
                    "train_n": len(split.train_indices),
                    "validation_n": len(split.test_indices),
                    "purged_n": len(split.purged_indices),
                    "epochs_run": epochs_run,
                    **metrics,
                }
            )
            predictions.append(
                pd.DataFrame(
                    {
                        "model": model_name,
                        "fold": split.split_id + 1,
                        "event_index": split.test_indices,
                        "Date/Time": frame.loc[split.test_indices, "Date/Time"].to_numpy(),
                        "t1": frame.loc[split.test_indices, "t1"].to_numpy(),
                        "Label": labels[split.test_indices],
                        "probability": probabilities,
                    }
                )
            )
            print(
                f"fold={split.split_id + 1} model={model_name} "
                f"auc={metrics['roc_auc']:.4f} f1={metrics['f1']:.4f} "
                f"epochs={epochs_run}"
            )
    return (
        pd.DataFrame(results),
        pd.concat(predictions, ignore_index=True),
        pd.DataFrame(schedule),
    )


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fold-level metrics without hiding dispersion."""
    metric_columns = [
        "accuracy",
        "balanced_accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "average_precision",
        "log_loss",
        "brier_score",
        "approval_rate",
    ]
    summary = results.groupby("model", sort=False)[metric_columns].agg(["mean", "std"])
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    return summary.reset_index()


def write_results(
    results: pd.DataFrame,
    predictions: pd.DataFrame,
    schedule: pd.DataFrame,
    *,
    input_path: Path,
    output_root: Path,
    config: ComparisonConfig,
) -> pd.DataFrame:
    """Write auditable reports; never write deployable model artifacts."""
    output_root.mkdir(parents=True, exist_ok=True)
    summary = summarize(results)
    results.to_csv(output_root / "fold_results.csv", index=False)
    summary.to_csv(output_root / "summary.csv", index=False)
    predictions.to_parquet(
        output_root / "validation_predictions.parquet", index=False, compression="zstd"
    )
    schedule.to_csv(output_root / "fold_schedule.csv", index=False)
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "input": str(input_path),
        "output_root": str(output_root),
        "events": int(predictions["event_index"].nunique()),
        "models": {name: list(columns) for name, columns in feature_sets().items()},
        "removed_as_redundant": list(REDUNDANT_FEATURES),
        "config": config.__dict__,
        "folds": config.n_splits,
        "deployed_artifacts_written": False,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--embargo-pct", type=float, default=0.01)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    return parser


def main() -> None:
    args = _parser().parse_args()
    config = ComparisonConfig(
        n_splits=args.n_splits,
        embargo_pct=args.embargo_pct,
        epochs=args.epochs,
        patience=args.patience,
        device=args.device,
    )
    frame = load_comparison_frame(args.input)
    print(
        f"Purged comparison: {len(frame):,} common events, "
        f"{config.n_splits} folds, device={config.device}."
    )
    results, predictions, schedule = run_comparison(frame, config)
    summary = write_results(
        results,
        predictions,
        schedule,
        input_path=args.input,
        output_root=args.output_root,
        config=config,
    )
    print("\nComparison summary:")
    print(summary.to_string(index=False))
    print(f"\nReports: {args.output_root}")


if __name__ == "__main__":
    main()
