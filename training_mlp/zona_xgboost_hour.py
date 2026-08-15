"""
zona_xgboost_hour.py
====================
XGBoost meta-labeling trained separately per hour of day.

Outputs saved to strategies/zona_strat/model/hour/{HH}/
  model_xgb_best.json
  scaler_xgb_best.pkl
  config_xgb.json
  results_cv_xgb.csv
  feature_importance.png
  cv_summary_xgb.png

Run
---
    cd training_mlp
    python zona_xgboost_hour.py
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

load_dotenv(Path(__file__).parent / ".env")

from pipeline_paths import FEATURES_FILE as DATA_FILE
from zona_features import FEATURE_COLS

RANDOM_SEED  = int(os.getenv("RANDOM_SEED",  "42"))
N_SPLITS     = int(os.getenv("N_SPLITS",     "25"))
PURGE_BARS   = int(os.getenv("PURGE_BARS",   "20"))
EMBARGO_BARS = int(os.getenv("EMBARGO_BARS", "60"))
TEST_SIZE    = float(os.getenv("TEST_SIZE",  "0.10"))

BASE_DIR = Path("strategies/zona_strat/model/hour")

np.random.seed(RANDOM_SEED)


# ── Splits ────────────────────────────────────────────────────────────────────

def split_test(X, y, test_size, purge, embargo):
    n_total = len(X)
    n_test  = int(n_total * test_size)
    gap     = purge + embargo
    n_cv    = n_total - n_test - gap
    return X[:n_cv], y[:n_cv], X[n_cv + gap:], y[n_cv + gap:]


def purged_embargo_splits(n_samples, n_splits, purge, embargo, fold_size=None):
    indices = np.arange(n_samples)
    if fold_size is None:
        fold_size = n_samples // (n_splits + 1)
    for i in range(1, n_splits + 1):
        val_start = i * fold_size
        val_end   = val_start + fold_size
        if val_end > n_samples:
            break
        train_end = val_start - purge
        train_idx = indices[:max(train_end, 0)]
        val_idx   = indices[val_start:val_end]
        if len(train_idx) == 0 or len(val_idx) == 0:
            continue
        yield train_idx, val_idx


# ── Plots ─────────────────────────────────────────────────────────────────────

def plot_feature_importance(model, feature_names, out_dir, label):
    scores = model.get_booster().get_score(importance_type="gain")
    named  = {feature_names[int(k[1:])]: v for k, v in scores.items()}
    sorted_items = sorted(named.items(), key=lambda x: x[1], reverse=True)
    names = [x[0] for x in sorted_items]
    vals  = [x[1] for x in sorted_items]

    fig, ax = plt.subplots(figsize=(8, max(6, len(names) * 0.25)))
    ax.barh(names[::-1], vals[::-1], color="steelblue", alpha=0.8)
    ax.set_title(f"Feature Importance -- Gain ({label})")
    ax.set_xlabel("Gain")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "feature_importance.png", dpi=100)
    plt.close(fig)


def plot_cv_summary(results, naive_acc, out_dir, label):
    res_df   = pd.DataFrame(results)
    folds    = res_df["fold"].tolist()
    aucs     = res_df["auc"].tolist()
    mean_auc = res_df["auc"].mean()

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    ax = axes[0]
    bars = ax.bar(folds, aucs, color="steelblue", alpha=0.8)
    ax.axhline(mean_auc, color="tomato",  linestyle="--", label=f"Mean AUC {mean_auc:.4f}")
    ax.axhline(0.5,      color="dimgray", linestyle=":",  label="Random (0.50)")
    ax.set_title(f"XGBoost Val AUC -- {label}")
    ax.set_xlabel("Fold")
    ax.set_ylabel("AUC")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    for bar, v in zip(bars, aucs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.001,
                f"{v:.3f}", ha="center", va="bottom", fontsize=7)

    ax2 = axes[1]
    metrics = ["acc", "f1", "auc"]
    means   = [res_df[m].mean() for m in metrics]
    stds    = [res_df[m].std()  for m in metrics]
    ax2.bar(metrics, means, yerr=stds, capsize=5,
            color=["steelblue", "seagreen", "darkorange"], alpha=0.8)
    ax2.axhline(naive_acc, color="dimgray", linestyle="--", label=f"Naive acc {naive_acc:.4f}")
    ax2.set_ylim(0, 1)
    ax2.set_title("CV Mean +/- Std")
    ax2.legend()
    ax2.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "cv_summary_xgb.png", dpi=100)
    plt.close(fig)


# ── Train one hour ────────────────────────────────────────────────────────────

def train_hour(df_h: pd.DataFrame, hour_label: str, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    X = df_h[FEATURE_COLS].values.astype(np.float32)
    y = df_h["Label"].values.astype(np.float32)

    fold_size = max(len(X) // (N_SPLITS + 1), 50)

    X_cv, y_cv, X_test, y_test = split_test(X, y, TEST_SIZE, PURGE_BARS, EMBARGO_BARS)

    majority  = int(np.round(y_cv.mean()))
    naive_acc = (y_cv == majority).mean()
    scale_pos = float((y_cv == 0).sum() / max((y_cv == 1).sum(), 1))

    print(f"  Total={len(X):,}  CV={len(X_cv):,}  Test={len(X_test):,}  "
          f"naive_acc={naive_acc:.4f}  label_bal={y_cv.mean():.3f}")

    results       = []
    best_auc      = -np.inf
    best_fold_idx = None
    best_model    = None
    best_scaler   = None

    for fold, (train_idx, val_idx) in enumerate(
        purged_embargo_splits(len(X_cv), N_SPLITS, PURGE_BARS, EMBARGO_BARS, fold_size)
    ):
        X_train, X_val = X_cv[train_idx], X_cv[val_idx]
        y_train, y_val = y_cv[train_idx], y_cv[val_idx]

        scaler  = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_val   = scaler.transform(X_val)

        model = XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos,
            use_label_encoder=False,
            eval_metric="logloss",
            early_stopping_rounds=20,
            random_state=RANDOM_SEED,
            verbosity=0,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        y_prob = model.predict_proba(X_val)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)
        acc = accuracy_score(y_val, y_pred)
        f1  = f1_score(y_val, y_pred, zero_division=0)
        auc = roc_auc_score(y_val, y_prob)

        results.append({"fold": fold+1, "acc": acc, "f1": f1, "auc": auc,
                        "train_n": len(train_idx), "val_n": len(val_idx)})
        print(f"    Fold {fold+1:>2}  train={len(train_idx):>5,}  val={len(val_idx):>4,}  "
              f"acc={acc:.4f}  f1={f1:.4f}  auc={auc:.4f}")

        if auc > best_auc:
            best_auc      = auc
            best_fold_idx = fold + 1
            best_model    = model
            best_scaler   = pickle.loads(pickle.dumps(scaler))

    res_df = pd.DataFrame(results)
    res_df.to_csv(out_dir / "results_cv_xgb.csv", index=False)
    best_model.save_model(str(out_dir / "model_xgb_best.json"))
    with open(out_dir / "scaler_xgb_best.pkl", "wb") as f:
        pickle.dump(best_scaler, f)

    config = {
        "hour": hour_label,
        "n_features": len(FEATURE_COLS), "feature_cols": FEATURE_COLS,
        "n_splits": N_SPLITS, "fold_size": fold_size,
        "purge_bars": PURGE_BARS, "embargo_bars": EMBARGO_BARS,
        "test_size": TEST_SIZE, "naive_acc": naive_acc,
        "best_fold": best_fold_idx, "best_fold_val_auc": best_auc,
        "output_dir": str(out_dir.resolve()),
    }
    with open(out_dir / "config_xgb.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n  -- CV Summary ({hour_label}) --")
    print(res_df.to_string(index=False))
    print(f"  Best fold: {best_fold_idx}  (val AUC {best_auc:.4f})  naive_acc: {naive_acc:.4f}")

    plot_feature_importance(best_model, FEATURE_COLS, out_dir, hour_label)
    plot_cv_summary(results, naive_acc, out_dir, hour_label)
    print(f"  Artifacts -> {out_dir.resolve()}")

    return best_auc, naive_acc, len(X_test)


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("=" * 55)
    print("  ZONA XGBoost -- HOUR OF DAY SPLIT")
    print("=" * 55)
    print(f"  Features      : {len(FEATURE_COLS)}")
    print(f"  N splits      : {N_SPLITS}")
    print(f"  Purge/Embargo : {PURGE_BARS} / {EMBARGO_BARS} bars")
    print(f"  Test size     : {TEST_SIZE*100:.0f}%")
    print("=" * 55)

    df = pd.read_csv(DATA_FILE).dropna().reset_index(drop=True)
    df["Date/Time"] = pd.to_datetime(df["Date/Time"])
    df["hour"] = df["Date/Time"].dt.hour

    hours = sorted(df["hour"].unique())
    summary = []

    for h in hours:
        label = f"{h:02d}:00"
        print(f"\n{'='*55}")
        print(f"  Hour: {label}  ({(df['hour']==h).sum():,} trades)")
        print(f"{'='*55}")
        df_h    = df[df["hour"] == h].reset_index(drop=True)
        out_dir = BASE_DIR / f"{h:02d}"
        best_auc, naive_acc, n_test = train_hour(df_h, label, out_dir)
        summary.append({"hour": label, "trades": len(df_h),
                        "best_auc": best_auc, "naive_acc": naive_acc, "n_test": n_test})

    print(f"\n{'='*55}")
    print("  SUMMARY")
    print(f"{'='*55}")
    print(f"  {'Hour':<8} {'Trades':>7} {'Best AUC':>9} {'Naive Acc':>10} {'Test N':>7}")
    print(f"  {'-'*45}")
    for s in summary:
        print(f"  {s['hour']:<8} {s['trades']:>7,} {s['best_auc']:>9.4f} {s['naive_acc']:>10.4f} {s['n_test']:>7,}")


if __name__ == "__main__":
    run()
