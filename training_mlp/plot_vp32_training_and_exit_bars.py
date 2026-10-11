"""Create VP32 learning curves and chronological exit-bar diagnostics."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

from training_mlp.compare_purged_feature_sets import ResearchMLP, feature_sets, load_comparison_frame
from training_mlp.cpcv_hyperparameter_search import (
    TrialConfig,
    fit_fixed_epochs,
    split_development_holdout,
)
from training_mlp.validation import CombinatorialPurgedCrossValidation, EventIntervals


def _seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


@torch.no_grad()
def _epoch_metrics(
    model: nn.Module,
    values: np.ndarray,
    labels: np.ndarray,
    criterion: nn.Module,
) -> tuple[float, float]:
    model.eval()
    tensor = torch.tensor(values, dtype=torch.float32)
    targets = torch.tensor(labels, dtype=torch.float32)
    logits = model(tensor)
    loss = float(criterion(logits, targets).item())
    probabilities = torch.sigmoid(logits).numpy()
    return loss, float(roc_auc_score(labels, probabilities))


def build_learning_curve(frame: pd.DataFrame, *, epochs: int, seed: int) -> pd.DataFrame:
    """Train VP32 on the strict earlier-groups CPCV split and log each epoch."""
    development, _ = split_development_holdout(frame, 0.15)
    events = EventIntervals.from_arrays(development["Date/Time"], development["t1"])
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=6, n_test_groups=2, embargo_pct=0.01
    )
    splits = list(splitter.split(events))
    split = next(item for item in splits if tuple(item.test_groups) == (4, 5))
    columns = list(feature_sets()["vp_32"])
    values = development.loc[:, columns].to_numpy(dtype=np.float32)
    labels = development["Label"].to_numpy(dtype=np.int64)
    scaler = StandardScaler()
    train_values = scaler.fit_transform(values[split.train_indices]).astype(np.float32)
    validation_values = scaler.transform(values[split.test_indices]).astype(np.float32)
    train_labels = labels[split.train_indices]
    validation_labels = labels[split.test_indices]

    _seed(seed)
    model = ResearchMLP(32, hidden_dims=(64, 32), dropout=0.3)
    positives = int((train_labels == 1).sum())
    negatives = int((train_labels == 0).sum())
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([negatives / positives], dtype=torch.float32)
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-2)
    dataset = TensorDataset(
        torch.tensor(train_values), torch.tensor(train_labels, dtype=torch.float32)
    )
    loader = DataLoader(dataset, batch_size=64, shuffle=False)
    rows: list[dict[str, float | int]] = []
    for epoch in range(1, epochs + 1):
        model.train()
        for batch_values, batch_labels in loader:
            optimizer.zero_grad()
            loss = criterion(model(batch_values), batch_labels)
            loss.backward()
            optimizer.step()
        train_loss, train_auc = _epoch_metrics(
            model, train_values, train_labels, criterion
        )
        validation_loss, validation_auc = _epoch_metrics(
            model, validation_values, validation_labels, criterion
        )
        rows.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "validation_loss": validation_loss,
                "train_auc": train_auc,
                "validation_auc": validation_auc,
                "train_n": len(split.train_indices),
                "validation_n": len(split.test_indices),
                "purged_n": len(split.purged_indices),
                "embargoed_n": len(split.embargoed_indices),
            }
        )
    return pd.DataFrame(rows)


def plot_learning_curve(curve: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    axes[0].plot(curve["epoch"], curve["train_loss"], label="Training", linewidth=2)
    axes[0].plot(
        curve["epoch"], curve["validation_loss"], label="Validation", linewidth=2
    )
    axes[0].set(title="VP32 loss by epoch", xlabel="Epoch", ylabel="Weighted BCE loss")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    axes[1].plot(curve["epoch"], curve["train_auc"], label="Training", linewidth=2)
    axes[1].plot(
        curve["epoch"], curve["validation_auc"], label="Validation", linewidth=2
    )
    axes[1].axhline(0.5, color="black", linestyle="--", linewidth=1, label="Random")
    axes[1].set(title="VP32 ROC AUC by epoch", xlabel="Epoch", ylabel="ROC AUC")
    axes[1].legend()
    axes[1].grid(alpha=0.25)
    fig.suptitle("Point-in-time-correct ESU26 VP32 — chronological CPCV split")
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def exit_bar_distribution(
    frame: pd.DataFrame, predictions_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return exact and display-bucket results for approved confirmation trades."""
    predictions = pd.read_parquet(predictions_path)
    predictions["Date/Time"] = pd.to_datetime(predictions["Date/Time"])
    approved = predictions.loc[predictions["approved"]].copy()
    source = frame[
        ["Date/Time", "entry_time", "t1", "net_pnl_at_3_24_per_side"]
    ].copy()
    joined = approved.merge(source, on=["Date/Time", "t1"], validate="one_to_one")
    seconds = (pd.to_datetime(joined["t1"]) - pd.to_datetime(joined["entry_time"])).dt.total_seconds()
    if (seconds < 0).any() or not np.allclose(seconds % 30, 0):
        raise ValueError("approved trades contain invalid 30-second exit-bar timing")
    joined["exit_bar"] = (seconds / 30).astype(int)
    joined["winner"] = joined["net_pnl_at_3_24_per_side"] > 0
    exact = joined.groupby("exit_bar", as_index=False).agg(
        trades=("exit_bar", "size"),
        winners=("winner", "sum"),
        net_profit=("net_pnl_at_3_24_per_side", "sum"),
        average_trade=("net_pnl_at_3_24_per_side", "mean"),
    )
    exact["win_rate"] = exact["winners"] / exact["trades"]
    labels = ["0", "1", "2", "3–5", "6–10", ">10"]
    joined["exit_bar_bucket"] = pd.cut(
        joined["exit_bar"],
        bins=[-1, 0, 1, 2, 5, 10, np.inf],
        labels=labels,
    )
    bucketed = joined.groupby("exit_bar_bucket", observed=False, as_index=False).agg(
        trades=("exit_bar", "size"),
        winners=("winner", "sum"),
        net_profit=("net_pnl_at_3_24_per_side", "sum"),
        average_trade=("net_pnl_at_3_24_per_side", "mean"),
    )
    bucketed["win_rate"] = np.where(
        bucketed["trades"] > 0, bucketed["winners"] / bucketed["trades"], np.nan
    )
    return exact, bucketed


def development_path_predictions(
    frame: pd.DataFrame, *, epochs: int, seed: int, path_id: int = 0
) -> pd.DataFrame:
    """Materialize one complete VP32 CPCV path without duplicate events."""
    development, _ = split_development_holdout(frame, 0.15)
    events = EventIntervals.from_arrays(development["Date/Time"], development["t1"])
    splitter = CombinatorialPurgedCrossValidation(
        n_groups=6, n_test_groups=2, embargo_pct=0.01
    )
    splits = list(splitter.split(events))
    groups = list(
        np.array_split(np.arange(len(development), dtype=np.int64), 6)
    )
    columns = list(feature_sets()["vp_32"])
    values = development.loc[:, columns].to_numpy(dtype=np.float32)
    labels = development["Label"].to_numpy(dtype=np.int64)
    probabilities = np.full(len(development), np.nan, dtype=np.float64)
    trial = TrialConfig(0, (64, 32), 1e-3, 1e-2, 0.3, 64)
    for split in splits:
        split_probabilities, _, _ = fit_fixed_epochs(
            values[split.train_indices],
            labels[split.train_indices],
            values[split.test_indices],
            trial=trial,
            epochs=epochs,
            seed=seed + split.split_id,
            device_name="cpu",
        )
        probability_by_index = dict(
            zip(split.test_indices.tolist(), split_probabilities.tolist())
        )
        for group_id, assigned_path in split.path_assignments.items():
            if assigned_path == path_id:
                for event_index in groups[group_id]:
                    probabilities[event_index] = probability_by_index[int(event_index)]
    if np.isnan(probabilities).any():
        raise ValueError("selected CPCV path contains missing predictions")
    result = development[
        [
            "Date/Time",
            "entry_time",
            "t1",
            "Label",
            "net_pnl_at_3_24_per_side",
        ]
    ].copy()
    result["probability"] = probabilities
    result["approved"] = probabilities >= 0.65
    return result


def path_exit_bar_distribution(
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    approved = predictions.loc[predictions["approved"]].copy()
    seconds = (
        pd.to_datetime(approved["t1"]) - pd.to_datetime(approved["entry_time"])
    ).dt.total_seconds()
    if (seconds < 0).any() or not np.allclose(seconds % 30, 0):
        raise ValueError("CPCV path contains invalid 30-second exit-bar timing")
    approved["exit_bar"] = (seconds / 30).astype(int)
    approved["winner"] = approved["net_pnl_at_3_24_per_side"] > 0
    exact = approved.groupby("exit_bar", as_index=False).agg(
        trades=("exit_bar", "size"),
        winners=("winner", "sum"),
        net_profit=("net_pnl_at_3_24_per_side", "sum"),
        average_trade=("net_pnl_at_3_24_per_side", "mean"),
    )
    exact["win_rate"] = exact["winners"] / exact["trades"]
    labels = ["0", "1", "2", "3–5", "6–10", ">10"]
    approved["exit_bar_bucket"] = pd.cut(
        approved["exit_bar"],
        bins=[-1, 0, 1, 2, 5, 10, np.inf],
        labels=labels,
    )
    bucketed = approved.groupby(
        "exit_bar_bucket", observed=False, as_index=False
    ).agg(
        trades=("exit_bar", "size"),
        winners=("winner", "sum"),
        net_profit=("net_pnl_at_3_24_per_side", "sum"),
        average_trade=("net_pnl_at_3_24_per_side", "mean"),
    )
    bucketed["win_rate"] = np.where(
        bucketed["trades"] > 0,
        bucketed["winners"] / bucketed["trades"],
        np.nan,
    )
    return exact, bucketed


def plot_exit_bars(
    bucketed: pd.DataFrame, output: Path, *, title: str, subtitle: str
) -> None:
    labels = bucketed["exit_bar_bucket"].astype(str)
    colors = ["#17823b" if value >= 0 else "#bd2c2c" for value in bucketed["net_profit"]]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.2), sharex=True)
    axes[0].bar(labels, bucketed["net_profit"], color=colors)
    axes[0].axhline(0, color="black", linewidth=1)
    axes[0].set(ylabel="Net P&L ($)", title=title)
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(labels, bucketed["trades"], color="#3366aa")
    for index, row in bucketed.iterrows():
        if row["trades"]:
            axes[1].text(
                index,
                row["trades"] + 0.25,
                f"{row['win_rate']:.1%}",
                ha="center",
                fontsize=9,
            )
    axes[1].set(
        xlabel="Exit bar after entry (0 = entry bar)",
        ylabel="Approved trades",
        title="Trade count (labels show win rate)",
    )
    axes[1].grid(axis="y", alpha=0.25)
    fig.suptitle(subtitle)
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    frame = load_comparison_frame(args.input)
    args.report_root.mkdir(parents=True, exist_ok=True)
    curve = build_learning_curve(frame, epochs=args.epochs, seed=args.seed)
    curve.to_csv(args.report_root / "vp32_learning_curve.csv", index=False)
    plot_learning_curve(curve, args.report_root / "vp32_learning_curve.png")
    exact, bucketed = exit_bar_distribution(
        frame, args.report_root / "final_holdout_predictions.parquet"
    )
    exact.to_csv(args.report_root / "vp32_exit_bar_exact.csv", index=False)
    bucketed.to_csv(args.report_root / "vp32_exit_bar_buckets.csv", index=False)
    plot_exit_bars(
        bucketed,
        args.report_root / "vp32_exit_bar_distribution.png",
        title="VP32 confirmation net profit by exit bar",
        subtitle=(
            f"Chronological confirmation — {int(bucketed['trades'].sum())} "
            "VP32 approvals, $6.48 round trip"
        ),
    )
    path_predictions = development_path_predictions(
        frame, epochs=args.epochs, seed=args.seed, path_id=0
    )
    path_predictions.to_parquet(
        args.report_root / "vp32_cpcv_path_1_predictions.parquet",
        index=False,
        compression="zstd",
    )
    path_exact, path_bucketed = path_exit_bar_distribution(path_predictions)
    path_exact.to_csv(args.report_root / "vp32_cpcv_path_1_exit_bar_exact.csv", index=False)
    path_bucketed.to_csv(
        args.report_root / "vp32_cpcv_path_1_exit_bar_buckets.csv", index=False
    )
    plot_exit_bars(
        path_bucketed,
        args.report_root / "vp32_cpcv_path_1_exit_bar_distribution.png",
        title="VP32 CPCV path 1 net profit by exit bar",
        subtitle=(
            f"Development OOS path 1 — {int(path_bucketed['trades'].sum())} "
            "unique VP32 approvals, $6.48 round trip"
        ),
    )
    print(curve.tail(1).to_string(index=False))
    print(bucketed.to_string(index=False))
    print(path_bucketed.to_string(index=False))


if __name__ == "__main__":
    main()
