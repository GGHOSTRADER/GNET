"""Plot the isolated ESU26 canonical-13 research run and trade holding times."""

from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, roc_auc_score, roc_curve

from training_mlp.validation import EventIntervals, purged_chronological_holdout


BUCKET_LABELS = [
    "0 s", "(0,30] s", "(30,60] s", "(1,2] min",
    "(2,5] min", "(5,10] min", "(10,30] min", ">30 min",
]
BUCKET_EDGES = [-1, 0, 30, 60, 120, 300, 600, 1800, np.inf]
COLOR_WIN = "#2a9d8f"
COLOR_LOSS = "#d5654e"
COLOR_TRAIN = "#2878b5"
COLOR_VAL = "#db8a19"


def _load_model(model_dir: Path, n_features: int):
    training_script = Path(__file__).with_name("30_training_mlp.py")
    spec = importlib.util.spec_from_file_location("gnet_esu26_training", training_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.MLP(input_dim=n_features)
    model.load_state_dict(torch.load(model_dir / "model_best.pt", map_location="cpu"))
    model.eval()
    return model


def _summarize_times(frame: pd.DataFrame, cohort: str) -> pd.DataFrame:
    duration = (pd.to_datetime(frame["exit_time"]) - pd.to_datetime(frame["entry_time"])).dt.total_seconds()
    if duration.isna().any() or (duration < 0).any():
        raise ValueError(f"Invalid holding time in {cohort}")
    groups = pd.cut(duration, BUCKET_EDGES, labels=BUCKET_LABELS, right=True)
    work = frame.assign(hold_seconds=duration, hold_bucket=groups)
    summary = work.groupby("hold_bucket", observed=False).agg(
        trades=("Label", "size"),
        winners=("Label", "sum"),
        net_pnl=("net_pnl_at_3_24_per_side", "sum"),
        mean_net_pnl=("net_pnl_at_3_24_per_side", "mean"),
        median_net_pnl=("net_pnl_at_3_24_per_side", "median"),
    ).reset_index()
    summary["losers"] = summary["trades"] - summary["winners"]
    summary["win_rate"] = summary["winners"] / summary["trades"].replace(0, np.nan)
    summary.insert(0, "cohort", cohort)
    return summary


def _style_axis(ax):
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def _plot_learning_curves(history: pd.DataFrame, destination: Path):
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharey=True, constrained_layout=True)
    for fold, ax in enumerate(axes.flat[:5], 1):
        one = history.loc[history["fold"] == fold]
        if one.empty:
            raise ValueError(f"Missing training history for fold {fold}")
        ax.plot(one["epoch"], one["train_loss"], color=COLOR_TRAIN, lw=2, label="Training")
        ax.plot(one["epoch"], one["val_loss"], color=COLOR_VAL, lw=2, label="Validation")
        best = one.loc[one["val_loss"].idxmin()]
        ax.scatter([best["epoch"]], [best["val_loss"]], color=COLOR_VAL, edgecolor="black", zorder=3)
        ax.set_title(f"Fold {fold}: best epoch {int(best['epoch'])}, stopped {int(one['epoch'].max())}")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Weighted BCE loss")
        _style_axis(ax)
    axes.flat[5].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower right", bbox_to_anchor=(0.89, 0.13), frameon=False)
    fig.suptitle("ESU26 canonical 13: training versus validation loss", fontsize=15)
    fig.savefig(destination, dpi=170)
    plt.close(fig)


def _plot_roc(y: np.ndarray, probs: np.ndarray, cv: pd.DataFrame, destination: Path):
    fpr, tpr, _ = roc_curve(y, probs)
    auc = roc_auc_score(y, probs)
    folds = cv.loc[cv["fold"].astype(str).str.fullmatch(r"[1-5]")].copy()
    fig, (ax_roc, ax_cv) = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    ax_roc.plot(fpr, tpr, lw=2.5, color=COLOR_TRAIN, label=f"Frozen holdout AUC = {auc:.3f}")
    ax_roc.plot([0, 1], [0, 1], ls="--", lw=1.3, color="gray", label="Chance = 0.500")
    ax_roc.set(xlim=(0, 1), ylim=(0, 1), xlabel="False-positive rate", ylabel="True-positive rate", title="ROC · frozen holdout (n=572)")
    ax_roc.legend(loc="lower right", frameon=False)
    _style_axis(ax_roc)
    fold_auc = folds["auc"].astype(float).to_numpy()
    ax_cv.bar(np.arange(1, 6), fold_auc, color=COLOR_TRAIN, alpha=0.8)
    ax_cv.axhline(0.5, ls="--", lw=1.3, color="gray", label="Chance")
    ax_cv.axhline(auc, ls=":", lw=1.6, color=COLOR_VAL, label=f"Holdout {auc:.3f}")
    ax_cv.set(xlim=(0.4, 5.6), ylim=(0.4, 0.65), xticks=np.arange(1, 6), xlabel="Walk-forward fold", ylabel="ROC AUC", title=f"Validation AUC · mean {fold_auc.mean():.3f}")
    for i, value in enumerate(fold_auc, 1):
        ax_cv.text(i, value + 0.008, f"{value:.3f}", ha="center", fontsize=9)
    ax_cv.legend(loc="upper right", frameon=False)
    _style_axis(ax_cv)
    fig.suptitle("Discrimination, not trade profitability", fontsize=15)
    fig.savefig(destination, dpi=170)
    plt.close(fig)
    return float(auc)


def _plot_profit_distribution(summary: pd.DataFrame, cohort: str, destination: Path):
    one = summary.loc[summary["cohort"] == cohort]
    x = np.arange(len(one))
    fig, (ax_count, ax_mean) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, constrained_layout=True)
    ax_count.bar(x, one["winners"], color=COLOR_WIN, label="Winning trades")
    ax_count.bar(x, one["losers"], bottom=one["winners"], color=COLOR_LOSS, label="Losing trades")
    ax_count.set_ylabel("Number of trades")
    ax_count.legend(loc="upper right", frameon=False)
    _style_axis(ax_count)
    means = one["mean_net_pnl"].fillna(0).to_numpy()
    ax_mean.bar(x, means, color=np.where(means >= 0, COLOR_WIN, COLOR_LOSS))
    ax_mean.axhline(0, lw=1, color="black")
    ax_mean.set_ylabel("Mean net P/L per trade (USD)")
    ax_mean.set_xticks(x, one["hold_bucket"], rotation=25, ha="right")
    ax_mean.set_xlabel("Time from entry to exit")
    _style_axis(ax_mean)
    fig.suptitle(f"Holding-time distribution · {cohort} · after $6.48 round-trip fees", fontsize=15)
    fig.savefig(destination, dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    model_dir = args.model_dir.resolve()
    dataset = args.dataset.resolve()
    output = model_dir / "plots"
    output.mkdir(exist_ok=True)
    with (model_dir / "config.json").open(encoding="utf-8") as stream:
        config = json.load(stream)
    frame = pd.read_csv(dataset).dropna().reset_index(drop=True)
    events = EventIntervals.from_arrays(pd.to_datetime(frame["Date/Time"]), pd.to_datetime(frame["t1"]))
    holdout = purged_chronological_holdout(events, test_size=config["test_size"])
    frozen = frame.iloc[holdout.test_indices].copy()
    x_test = np.load(model_dir / "X_test.npy").astype(np.float32)
    y_test = np.load(model_dir / "y_test.npy").astype(np.float32)
    if not np.allclose(x_test, frozen[config["feature_cols"]].to_numpy(dtype=np.float32)):
        raise ValueError("Holdout rows do not match the saved test features")
    if not np.array_equal(y_test, frozen["Label"].to_numpy(dtype=np.float32)):
        raise ValueError("Holdout labels do not match")
    with (model_dir / "scaler_best.pkl").open("rb") as stream:
        scaler = pickle.load(stream)
    model = _load_model(model_dir, config["n_features"])
    with torch.no_grad():
        probs = torch.sigmoid(model(torch.from_numpy(scaler.transform(x_test).astype(np.float32)))).numpy()
    frozen["model_probability"] = probs
    frozen["approved_at_0_50"] = probs >= 0.5
    frozen.to_csv(output / "holdout_predictions_with_trades.csv", index=False)
    history = pd.read_csv(model_dir / "training_history.csv")
    cv = pd.read_csv(model_dir / "results_cv.csv")
    _plot_learning_curves(history, output / "training_vs_validation.png")
    auc = _plot_roc(y_test, probs, cv, output / "roc_auc.png")
    summaries = pd.concat([
        _summarize_times(frame, "All 5,725 trades"),
        _summarize_times(frozen, "Holdout, all trades"),
        _summarize_times(frozen.loc[frozen["approved_at_0_50"]], "Holdout, NN approved"),
    ], ignore_index=True)
    summaries.to_csv(output / "holding_time_profit_buckets.csv", index=False)
    _plot_profit_distribution(summaries, "All 5,725 trades", output / "holding_time_all_trades.png")
    _plot_profit_distribution(summaries, "Holdout, NN approved", output / "holding_time_nn_approved.png")
    print(f"holdout_auc={auc:.6f} accuracy={accuracy_score(y_test, probs >= 0.5):.6f}")
    print(f"holdout_approved={int((probs >= 0.5).sum())} net_approved={frozen.loc[frozen['approved_at_0_50'], 'net_pnl_at_3_24_per_side'].sum():.2f}")
    print(summaries.to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    print(f"plots={output}")


if __name__ == "__main__":
    main()
