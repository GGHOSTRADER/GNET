"""Hyperparameter sweep for the leakage-corrected 13-feature MLP.

The final chronological holdout is isolated before the sweep. Configurations
are ranked only by mean ROC AUC across purged expanding walk-forward folds.
No live registry or production model artifacts are modified.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from training_mlp.validation import (
    EventIntervals,
    PurgedWalkForward,
    purged_chronological_holdout,
)


ROOT = Path(__file__).resolve().parents[1]
DATASET = (
    ROOT
    / "training_mlp"
    / "strategies"
    / "MA2CrossLE"
    / "processed"
    / "ma2cross_old_libb_prior_bar_13.csv"
)
OUTPUT_DIR = (
    ROOT
    / "training_mlp"
    / "strategies"
    / "MA2CrossLE"
    / "reports"
    / "mlp_corrected_hyperparameter_sweep"
)

FEATURE_COLS = [
    "parkinson_vol_5",
    "parkinson_vol_15",
    "parkinson_vol_30",
    "ofi_5",
    "ofi_15",
    "ofi_30",
    "volume_percentile",
    "volume_momentum",
    "amihud_illiquidity",
    "vwap_distance",
    "minutes_since_open",
    "is_first_last_30min",
    "day_of_week",
]

SEED = 42
MAX_EPOCHS = 80
PATIENCE = 10
N_SPLITS = 5
EMBARGO_PCT = 0.01
TEST_SIZE = 0.10


@dataclass(frozen=True)
class SweepConfig:
    name: str
    hidden_dims: tuple[int, ...]
    activation: str
    dropout: float
    learning_rate: float
    weight_decay: float
    batch_size: int
    balanced_loss: bool


CONFIGS = [
    SweepConfig("small_relu", (16,), "relu", 0.0, 1e-3, 1e-4, 128, True),
    SweepConfig("small_relu_do20", (16,), "relu", 0.2, 1e-3, 1e-3, 128, True),
    SweepConfig("small_silu", (16,), "silu", 0.1, 1e-3, 1e-3, 128, True),
    SweepConfig("medium_relu", (32, 16), "relu", 0.1, 1e-3, 1e-3, 128, True),
    SweepConfig("medium_relu_do30", (32, 16), "relu", 0.3, 1e-3, 1e-2, 128, True),
    SweepConfig("medium_silu", (32, 16), "silu", 0.2, 1e-3, 1e-3, 128, True),
    SweepConfig("medium_gelu", (32, 16), "gelu", 0.2, 1e-3, 1e-3, 128, True),
    SweepConfig("wide_relu", (64, 32), "relu", 0.3, 1e-3, 1e-2, 64, True),
    SweepConfig("wide_silu", (64, 32), "silu", 0.2, 3e-4, 1e-3, 128, True),
    SweepConfig("deep_relu", (64, 32, 16), "relu", 0.3, 3e-4, 1e-2, 128, True),
    SweepConfig("medium_fast", (32, 16), "relu", 0.2, 3e-3, 1e-3, 256, True),
    SweepConfig("medium_unweighted", (32, 16), "relu", 0.2, 1e-3, 1e-3, 128, False),
]


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def activation_layer(name: str) -> nn.Module:
    if name == "relu":
        return nn.ReLU()
    if name == "gelu":
        return nn.GELU()
    if name == "silu":
        return nn.SiLU()
    raise ValueError(f"unsupported activation: {name}")


class SweepMLP(nn.Module):
    def __init__(self, input_dim: int, config: SweepConfig):
        super().__init__()
        layers: list[nn.Module] = []
        previous = input_dim
        for width in config.hidden_dims:
            layers.extend(
                [
                    nn.Linear(previous, width),
                    nn.BatchNorm1d(width),
                    activation_layer(config.activation),
                    nn.Dropout(config.dropout),
                ]
            )
            previous = width
        layers.append(nn.Linear(previous, 1))
        self.network = nn.Sequential(*layers)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features).squeeze(1)


@torch.no_grad()
def predict(model: nn.Module, features: np.ndarray) -> np.ndarray:
    model.eval()
    tensor = torch.tensor(features, dtype=torch.float32)
    return torch.sigmoid(model(tensor)).numpy()


def train_fold(
    config: SweepConfig,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_valid: np.ndarray,
    y_valid: np.ndarray,
    seed: int,
) -> tuple[np.ndarray, int, float, float]:
    seed_everything(seed)
    model = SweepMLP(X_train.shape[1], config)
    dataset = TensorDataset(
        torch.tensor(X_train, dtype=torch.float32),
        torch.tensor(y_train, dtype=torch.float32),
    )
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        dataset,
        batch_size=config.batch_size,
        shuffle=True,
        generator=generator,
        drop_last=len(dataset) % config.batch_size == 1,
    )
    if config.balanced_loss:
        positive_weight = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))
        criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([positive_weight]))
    else:
        criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )

    best_auc = -np.inf
    best_loss = np.inf
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    stale_epochs = 0

    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        for batch_features, batch_labels in loader:
            optimizer.zero_grad()
            loss = criterion(model(batch_features), batch_labels)
            loss.backward()
            optimizer.step()

        valid_probabilities = predict(model, X_valid)
        valid_auc = roc_auc_score(y_valid, valid_probabilities)
        valid_loss = log_loss(y_valid, valid_probabilities, labels=[0, 1])
        improved = valid_auc > best_auc + 1e-5 or (
            abs(valid_auc - best_auc) <= 1e-5 and valid_loss < best_loss
        )
        if improved:
            best_auc = float(valid_auc)
            best_loss = float(valid_loss)
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
        if stale_epochs >= PATIENCE:
            break

    if best_state is None:
        raise RuntimeError("training produced no checkpoint")
    model.load_state_dict(best_state)
    return predict(model, X_valid), best_epoch, best_auc, best_loss


def load_development_data() -> tuple[pd.DataFrame, np.ndarray, np.ndarray, EventIntervals, int]:
    frame = pd.read_csv(DATASET).dropna().reset_index(drop=True)
    starts = pd.to_datetime(frame["Date/Time"], errors="raise")
    ends = pd.to_datetime(frame["t1"], errors="raise")
    events = EventIntervals.from_arrays(starts, ends)
    holdout = purged_chronological_holdout(events, test_size=TEST_SIZE)
    development = frame.iloc[holdout.train_indices].reset_index(drop=True)
    development_events = EventIntervals.from_arrays(
        starts.iloc[holdout.train_indices], ends.iloc[holdout.train_indices]
    )
    X = development[FEATURE_COLS].to_numpy(dtype=np.float32)
    y = development["Label"].to_numpy(dtype=np.float32)
    return development, X, y, development_events, len(holdout.test_indices)


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    development, X, y, events, frozen_holdout_size = load_development_data()
    splits = list(
        PurgedWalkForward(n_splits=N_SPLITS, embargo_pct=EMBARGO_PCT).split(events)
    )
    fold_rows: list[dict[str, object]] = []
    oof_rows: list[pd.DataFrame] = []

    print(f"Dataset: {DATASET}")
    print(f"Development pool: {len(X):,}")
    print(f"Frozen holdout excluded: {frozen_holdout_size:,}")
    print(f"Configurations: {len(CONFIGS)} x {len(splits)} folds")

    for config_index, config in enumerate(CONFIGS, start=1):
        print(f"\n[{config_index:02d}/{len(CONFIGS):02d}] {config.name}")
        for fold_index, split in enumerate(splits, start=1):
            scaler = StandardScaler()
            X_train = scaler.fit_transform(X[split.train_indices]).astype(np.float32)
            X_valid = scaler.transform(X[split.test_indices]).astype(np.float32)
            y_train = y[split.train_indices]
            y_valid = y[split.test_indices]
            probabilities, best_epoch, auc, validation_loss = train_fold(
                config,
                X_train,
                y_train,
                X_valid,
                y_valid,
                seed=SEED + fold_index,
            )
            predictions = (probabilities >= 0.5).astype(np.int64)
            row = {
                "config": config.name,
                "fold": fold_index,
                "train_n": len(split.train_indices),
                "validation_n": len(split.test_indices),
                "purged_n": len(split.purged_indices),
                "best_epoch": best_epoch,
                "auc": auc,
                "log_loss": validation_loss,
                "accuracy": accuracy_score(y_valid, predictions),
                "f1": f1_score(y_valid, predictions, zero_division=0),
            }
            fold_rows.append(row)
            oof_part = development.iloc[split.test_indices][
                ["Date/Time", "t1", "Label", "net_pnl_at_3_24_per_side"]
            ].copy()
            oof_part["config"] = config.name
            oof_part["fold"] = fold_index
            oof_part["probability"] = probabilities
            oof_rows.append(oof_part)
            print(
                f"  fold {fold_index}: AUC={auc:.4f} "
                f"loss={validation_loss:.4f} acc={row['accuracy']:.4f} "
                f"epoch={best_epoch}"
            )

    fold_results = pd.DataFrame(fold_rows)
    summary = (
        fold_results.groupby("config", as_index=False)
        .agg(
            mean_auc=("auc", "mean"),
            std_auc=("auc", "std"),
            mean_log_loss=("log_loss", "mean"),
            mean_accuracy=("accuracy", "mean"),
            mean_f1=("f1", "mean"),
            mean_best_epoch=("best_epoch", "mean"),
        )
        .sort_values(["mean_auc", "mean_log_loss"], ascending=[False, True])
        .reset_index(drop=True)
    )
    config_table = pd.DataFrame(
        [{**asdict(config), "hidden_dims": list(config.hidden_dims)} for config in CONFIGS]
    )
    summary = summary.merge(config_table, left_on="config", right_on="name").drop(
        columns="name"
    )

    fold_results.to_csv(OUTPUT_DIR / "fold_results.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "sweep_summary.csv", index=False)
    pd.concat(oof_rows, ignore_index=True).to_csv(
        OUTPUT_DIR / "out_of_fold_probabilities.csv", index=False
    )
    metadata = {
        "dataset": str(DATASET),
        "features": FEATURE_COLS,
        "development_rows": len(X),
        "frozen_holdout_rows": frozen_holdout_size,
        "holdout_used_for_selection": False,
        "selection_metric": "mean ROC AUC across five purged walk-forward folds",
        "max_epochs": MAX_EPOCHS,
        "patience": PATIENCE,
        "seed": SEED,
        "best_configuration": summary.iloc[0].to_dict(),
    }
    (OUTPUT_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str), encoding="utf-8"
    )

    print("\nSweep ranking")
    print(
        summary[
            ["config", "mean_auc", "std_auc", "mean_log_loss", "mean_accuracy", "mean_f1"]
        ].to_string(index=False)
    )
    print(f"\nSaved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run()
