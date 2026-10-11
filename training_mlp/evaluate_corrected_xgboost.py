"""Regularized XGBoost benchmark on the leakage-corrected MA-13 dataset.

This experiment is isolated from the live registry.  It uses the same purged
walk-forward folds and untouched chronological holdout as the corrected MLP.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score, roc_curve
from xgboost import XGBClassifier

from training_mlp.validation import (
    EventIntervals,
    PurgedWalkForward,
    purged_chronological_holdout,
)


ROOT = Path(__file__).resolve().parent / "strategies" / "MA2CrossLE"
DATASET = ROOT / "processed" / "ma2cross_old_libb_prior_bar_13.csv"
MLP_CONFIG = ROOT / "model" / "mlp_old_libb_prior_bar_13_ablation" / "config.json"
OUTPUT = ROOT / "reports" / "xgboost_old_libb_prior_bar_13"


def _model(*, n_estimators: int, early_stopping_rounds: int | None = None) -> XGBClassifier:
    return XGBClassifier(
        objective="binary:logistic",
        # XGBoost reports both metrics.  AUC is last so early stopping keeps
        # using the original ranking criterion rather than changing the run.
        eval_metric=["logloss", "auc"],
        tree_method="hist",
        n_estimators=n_estimators,
        learning_rate=0.03,
        max_depth=2,
        min_child_weight=20.0,
        subsample=0.80,
        colsample_bytree=0.80,
        reg_alpha=1.0,
        reg_lambda=10.0,
        gamma=0.10,
        max_bin=128,
        random_state=42,
        n_jobs=4,
        early_stopping_rounds=early_stopping_rounds,
    )


def _performance(frame: pd.DataFrame, probabilities: np.ndarray, threshold: float) -> dict:
    approved = frame.loc[probabilities >= threshold]
    pnl = approved["net_pnl_at_3_24_per_side"]
    gross_profit = float(pnl.loc[pnl > 0].sum())
    gross_loss = float(-pnl.loc[pnl <= 0].sum())
    return {
        "threshold": threshold,
        "approved": int(len(approved)),
        "winners": int((pnl > 0).sum()),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
        "net_pnl": float(pnl.sum()),
        "mean_net_pnl": float(pnl.mean()) if len(pnl) else None,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
    }


def _save_charts(output: Path, folds: list[dict], train_auc_histories: list[list[float]],
                 validation_auc_histories: list[list[float]],
                 train_loss_histories: list[list[float]],
                 validation_loss_histories: list[list[float]], y_true: np.ndarray,
                 probabilities: np.ndarray, importance: dict[str, float]) -> None:
    colors = {"blue": "#176B87", "green": "#298C75", "amber": "#F4B860",
              "navy": "#10243E", "muted": "#7A8793"}
    plt.style.use("seaborn-v0_8-whitegrid")

    fig, axes = plt.subplots(len(folds), 1, figsize=(9, 12), sharex=False, sharey=True)
    for index, (ax, fold, train_values, validation_values) in enumerate(
        zip(axes, folds, train_auc_histories, validation_auc_histories, strict=True)
    ):
        ax.plot(np.arange(1, len(train_values) + 1), train_values,
                color=colors["blue"], linewidth=1.8, label="Training AUC")
        ax.plot(np.arange(1, len(validation_values) + 1), validation_values,
                color=colors["amber"], linewidth=1.8, label="Validation AUC")
        ax.axhline(0.5, color=colors["muted"], linestyle="--", linewidth=1)
        ax.axvline(fold["best_trees"], color=colors["green"], linestyle=":",
                   linewidth=1.2, label="Selected round")
        ax.set_title(
            f"Fold {index + 1}: validation AUC {fold['validation_auc']:.3f}, "
            f"selected {fold['best_trees']} trees",
            fontsize=10,
        )
        ax.set_ylabel("AUC")
        ax.set_ylim(0.45, 0.68)
    axes[-1].set_xlabel("Boosting round")
    axes[0].legend(frameon=False, ncol=3, loc="upper left")
    fig.suptitle("Purged walk-forward training and validation curves", fontsize=15)
    fig.tight_layout()
    fig.savefig(output / "training_validation_auc.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(len(folds), 1, figsize=(9, 12), sharex=False, sharey=True)
    for index, (ax, fold, train_values, validation_values) in enumerate(
        zip(axes, folds, train_loss_histories, validation_loss_histories, strict=True)
    ):
        ax.plot(np.arange(1, len(train_values) + 1), train_values,
                color=colors["blue"], linewidth=1.8, label="Training log loss")
        ax.plot(np.arange(1, len(validation_values) + 1), validation_values,
                color=colors["amber"], linewidth=1.8, label="Validation log loss")
        ax.axvline(fold["best_trees"], color=colors["green"], linestyle=":",
                   linewidth=1.2, label="AUC-selected round")
        ax.set_title(f"Fold {index + 1}: selected {fold['best_trees']} trees", fontsize=10)
        ax.set_ylabel("Log loss")
    axes[-1].set_xlabel("Boosting round")
    axes[0].legend(frameon=False, ncol=3, loc="upper right")
    fig.suptitle("Purged walk-forward training and validation log loss", fontsize=15)
    fig.tight_layout()
    fig.savefig(output / "training_validation_logloss.png", dpi=180)
    plt.close(fig)

    fpr, tpr, _ = roc_curve(y_true, probabilities)
    auc = roc_auc_score(y_true, probabilities)
    fig, ax = plt.subplots(figsize=(6.5, 6.0))
    ax.plot(fpr, tpr, color=colors["blue"], linewidth=2.5,
            label=f"XGBoost holdout AUC = {auc:.3f}")
    ax.plot([0, 1], [0, 1], color=colors["muted"], linestyle="--",
            linewidth=1.3, label="Random ranking")
    ax.set(title="Untouched chronological holdout ROC", xlabel="False-positive rate",
           ylabel="True-positive rate", xlim=(0, 1), ylim=(0, 1))
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(output / "holdout_roc_auc.png", dpi=180)
    plt.close(fig)

    ordered = sorted(importance.items(), key=lambda item: item[1])
    names = [name for name, _ in ordered]
    values = [value for _, value in ordered]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.barh(names, values, color=colors["green"])
    ax.set(title="XGBoost feature importance", xlabel="Normalized gain importance")
    fig.tight_layout()
    fig.savefig(output / "feature_importance.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fold_numbers = np.arange(1, len(folds) + 1)
    fold_aucs = [fold["validation_auc"] for fold in folds]
    axes[0].bar(fold_numbers, fold_aucs, color=colors["amber"])
    axes[0].axhline(0.5, color=colors["muted"], linestyle="--", linewidth=1,
                    label="Random ranking")
    axes[0].axhline(np.mean(fold_aucs), color=colors["blue"], linewidth=1.8,
                    label=f"Mean = {np.mean(fold_aucs):.3f}")
    axes[0].set(title="Purged validation AUC", xlabel="Fold", ylabel="ROC AUC",
                xticks=fold_numbers, ylim=(0.45, 0.56))
    axes[0].legend(frameon=False)
    axes[1].plot(fpr, tpr, color=colors["blue"], linewidth=2.3,
                 label=f"AUC = {auc:.3f}")
    axes[1].plot([0, 1], [0, 1], color=colors["muted"], linestyle="--", linewidth=1)
    axes[1].set(title="Holdout ROC", xlabel="False-positive rate",
                ylabel="True-positive rate", xlim=(0, 1), ylim=(0, 1))
    axes[1].legend(loc="lower right", frameon=False)
    axes[2].barh(names, values, color=colors["green"])
    axes[2].set(title="Feature importance", xlabel="Normalized gain")
    fig.suptitle("Leakage-corrected MA-13 XGBoost diagnostics", fontsize=16,
                 fontweight="bold", color=colors["navy"])
    fig.tight_layout()
    fig.savefig(output / "xgboost_diagnostics.png", dpi=180)
    plt.close(fig)


def evaluate(dataset: Path = DATASET, config_path: Path = MLP_CONFIG,
             output: Path = OUTPUT) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    features = config["feature_cols"]
    frame = pd.read_csv(dataset).dropna(subset=[*features, "Date/Time", "t1", "Label"])
    frame = frame.sort_values("Date/Time", kind="stable").reset_index(drop=True)
    if len(frame) != config["n_samples"]:
        raise ValueError(f"expected {config['n_samples']} rows, found {len(frame)}")

    X = frame[features].to_numpy(dtype=np.float32)
    y = frame["Label"].to_numpy(dtype=np.int64)
    if not np.isfinite(X).all():
        raise ValueError("feature matrix contains non-finite values")

    events = EventIntervals.from_arrays(
        pd.to_datetime(frame["Date/Time"]), pd.to_datetime(frame["t1"])
    )
    holdout = purged_chronological_holdout(events, test_size=config["test_size"])
    cv_indices = holdout.train_indices
    test_indices = holdout.test_indices
    if len(test_indices) != config["n_test"]:
        raise ValueError("holdout population differs from corrected MLP")

    cv_frame = frame.iloc[cv_indices].reset_index(drop=True)
    cv_events = EventIntervals.from_arrays(
        pd.to_datetime(cv_frame["Date/Time"]), pd.to_datetime(cv_frame["t1"])
    )
    splitter = PurgedWalkForward(
        n_splits=config["n_splits"], embargo_pct=config["embargo_pct"]
    )

    folds: list[dict] = []
    best_tree_counts: list[int] = []
    train_auc_histories: list[list[float]] = []
    validation_auc_histories: list[list[float]] = []
    train_loss_histories: list[list[float]] = []
    validation_loss_histories: list[list[float]] = []
    for split in splitter.split(cv_events):
        train_global = cv_indices[split.train_indices]
        valid_global = cv_indices[split.test_indices]
        model = _model(n_estimators=2000, early_stopping_rounds=75)
        model.fit(
            X[train_global], y[train_global],
            eval_set=[(X[train_global], y[train_global]),
                      (X[valid_global], y[valid_global])],
            verbose=False,
        )
        history = model.evals_result()
        train_auc_histories.append(history["validation_0"]["auc"])
        validation_auc_histories.append(history["validation_1"]["auc"])
        train_loss_histories.append(history["validation_0"]["logloss"])
        validation_loss_histories.append(history["validation_1"]["logloss"])
        probabilities = model.predict_proba(X[valid_global])[:, 1]
        tree_count = int(model.best_iteration + 1)
        best_tree_counts.append(tree_count)
        folds.append({
            "fold": int(split.split_id),
            "train_rows": int(len(train_global)),
            "validation_rows": int(len(valid_global)),
            "purged_rows": int(len(split.purged_indices)),
            "best_trees": tree_count,
            "validation_auc": float(roc_auc_score(y[valid_global], probabilities)),
            "validation_accuracy_050": float(
                accuracy_score(y[valid_global], probabilities >= 0.50)
            ),
        })

    final_tree_count = int(np.median(best_tree_counts))
    final_model = _model(n_estimators=final_tree_count)
    final_model.fit(X[cv_indices], y[cv_indices], verbose=False)
    training_probabilities = final_model.predict_proba(X[cv_indices])[:, 1]
    holdout_probabilities = final_model.predict_proba(X[test_indices])[:, 1]
    holdout_frame = frame.iloc[test_indices].copy()
    holdout_frame["probability_xgboost"] = holdout_probabilities

    naive_pnl = holdout_frame["net_pnl_at_3_24_per_side"]
    importance = {
        feature: float(value)
        for feature, value in sorted(
            zip(features, final_model.feature_importances_, strict=True),
            key=lambda item: item[1], reverse=True,
        )
    }
    result = {
        "dataset": str(dataset.resolve()),
        "dataset_rows": int(len(frame)),
        "cv_rows": int(len(cv_indices)),
        "holdout_rows": int(len(test_indices)),
        "holdout_first_entry": str(holdout_frame["entry_time"].min()),
        "holdout_last_entry": str(holdout_frame["entry_time"].max()),
        "feature_time_rule": "preceding completed signal bar; never entry bar",
        "feature_count": len(features),
        "features": features,
        "model_parameters": final_model.get_params(),
        "folds": folds,
        "mean_validation_auc": float(np.mean([row["validation_auc"] for row in folds])),
        "std_validation_auc": float(np.std([row["validation_auc"] for row in folds])),
        "median_best_trees": final_tree_count,
        "training_auc": float(roc_auc_score(y[cv_indices], training_probabilities)),
        "holdout_auc": float(roc_auc_score(y[test_indices], holdout_probabilities)),
        "holdout_accuracy_050": float(
            accuracy_score(y[test_indices], holdout_probabilities >= 0.50)
        ),
        "holdout_probability_range": {
            "minimum": float(holdout_probabilities.min()),
            "median": float(np.median(holdout_probabilities)),
            "maximum": float(holdout_probabilities.max()),
        },
        "naive_holdout": {
            "trades": int(len(holdout_frame)),
            "winners": int((naive_pnl > 0).sum()),
            "win_rate": float((naive_pnl > 0).mean()),
            "net_pnl": float(naive_pnl.sum()),
        },
        "thresholds": [
            _performance(holdout_frame, holdout_probabilities, threshold)
            for threshold in (0.50, 0.52)
        ],
        "feature_importance_gain": importance,
        "live_registry_changed": False,
    }

    output.mkdir(parents=True, exist_ok=True)
    _save_charts(
        output, folds, train_auc_histories, validation_auc_histories,
        train_loss_histories, validation_loss_histories,
        y[test_indices], holdout_probabilities, importance,
    )
    (output / "results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(folds).to_csv(output / "fold_results.csv", index=False)
    holdout_frame.to_csv(output / "holdout_predictions.csv", index=False)
    final_model.save_model(output / "model.json")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--config", type=Path, default=MLP_CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, args.config, args.output), indent=2))


if __name__ == "__main__":
    main()
