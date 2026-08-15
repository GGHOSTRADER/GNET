"""
zona_backtest.py
================

Test-set backtest for the Zona strategy using direction-split XGBoost models.
Loads separate long/short models and applies each to the matching trades.

Outputs saved to strategies/zona_strat/reports/:
    backtest_xgb.txt
    equity_naive.png
    equity_xgb_filtered.png

Run
---
    cd training_mlp
    python zona_backtest.py
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from dotenv import load_dotenv

# Pass "mlp" as argument to use MLP models, default is xgb
MODEL_TYPE = sys.argv[1] if len(sys.argv) > 1 else "xgb"

load_dotenv(Path(__file__).parent / ".env")

from backtest_metrics import compute_all, print_report, save_report, plot_equity_curve
from zona_pipeline import load_paired_trades
from zona_features import FEATURE_COLS

# ── Paths ─────────────────────────────────────────────────────────────────────

STRATEGY_DIR  = Path("strategies/zona_strat")
INPUTS_DIR    = STRATEGY_DIR / "inputs"
PROCESSED_DIR = STRATEGY_DIR / "processed"
REPORTS_DIR   = STRATEGY_DIR / "reports"

TRADES_FILE   = INPUTS_DIR    / "VDX_2.csv"
FEATURES_FILE = PROCESSED_DIR / "df_features_labeled.csv"
_safe_type    = MODEL_TYPE.replace("/", "_")
ENRICHED_FILE = PROCESSED_DIR / f"df_enriched_{_safe_type}.csv"
REPORT_FILE   = REPORTS_DIR   / f"backtest_{_safe_type}.txt"

LONG_DIR  = STRATEGY_DIR / "model/long"
SHORT_DIR = STRATEGY_DIR / "model/short"

REGIME_COLS = [
    ("regime_late_expansion",    "late_expansion"),
    ("regime_mid_expansion",     "mid_expansion"),
    ("regime_early_contraction", "early_contraction"),
    ("regime_early_expansion",   "early_expansion"),
    ("regime_late_contraction",  "late_contraction"),
]

# ── Settings ──────────────────────────────────────────────────────────────────

COMMISSION_PER_TRADE = float(os.getenv("COMMISSION_PER_TRADE", "3.0"))
THRESHOLD            = float(os.getenv("THRESHOLD",            "0.5"))
TEST_SIZE            = float(os.getenv("TEST_SIZE",            "0.10"))
PURGE_BARS           = int(os.getenv("PURGE_BARS",             "20"))
EMBARGO_BARS         = int(os.getenv("EMBARGO_BARS",           "60"))
INITIAL_CAPITAL      = float(os.getenv("INITIAL_CAPITAL",      "10000.0"))


# ── MLP definition (must match zona_training.py) ──────────────────────────────

class MLP(nn.Module):
    def __init__(self, input_dim, hidden_dims=(64, 32), dropout=0.3):
        super().__init__()
        layers = []
        prev = input_dim
        for h in hidden_dims:
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h), nn.ReLU(), nn.Dropout(dropout)]
            prev = h
        layers += [nn.Linear(prev, 1)]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x).squeeze(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_xgb(model_dir: Path):
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(model_dir / "model_xgb_best.json"))
    with open(model_dir / "scaler_xgb_best.pkl", "rb") as f:
        scaler = pickle.load(f)
    with open(model_dir / "config_xgb.json") as f:
        config = json.load(f)
    return model, scaler, config


def load_mlp(model_dir: Path):
    with open(model_dir / "config.json") as f:
        config = json.load(f)
    with open(model_dir / "scaler_best.pkl", "rb") as f:
        scaler = pickle.load(f)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model  = MLP(input_dim=config["n_features"]).to(device)
    model.load_state_dict(torch.load(model_dir / "model_best.pt", map_location=device))
    model.eval()
    return model, scaler, config, device


def run_inference(model, scaler, X: np.ndarray, device=None):
    X_scaled = scaler.transform(X).astype(np.float32)
    if hasattr(model, "predict_proba") and not isinstance(model, MLP):
        prob = model.predict_proba(X_scaled)[:, 1]
    else:
        with torch.no_grad():
            logits = model(torch.tensor(X_scaled).to(device)).cpu().numpy()
        prob = 1 / (1 + np.exp(-logits))
    pred = (prob >= THRESHOLD).astype(int)
    return prob, pred


def get_test_indices(n_total: int) -> np.ndarray:
    n_test = int(n_total * TEST_SIZE)
    gap    = PURGE_BARS + EMBARGO_BARS
    n_cv   = n_total - n_test - gap
    return np.arange(n_cv + gap, n_total)


def to_trade_list(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "entry_ts":    row.entry_ts.to_pydatetime(),
            "exit_ts":     row.exit_ts.to_pydatetime(),
            "pnl":         float(row.pnl),
            "entry_price": float(row.entry_price),
            "exit_price":  float(row.exit_price),
            "direction":   int(row.direction),
        }
        for row in df.itertuples()
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if REPORT_FILE.exists():
        REPORT_FILE.unlink()

    # ── Load features ─────────────────────────────────────────────────────────
    print("Loading features...")
    features_df = pd.read_csv(FEATURES_FILE).dropna().reset_index(drop=True)
    features_df["Date/Time"] = pd.to_datetime(features_df["Date/Time"])
    print(f"  {len(features_df):,} rows")

    features_df["confidence"] = np.nan
    features_df["prediction"] = np.nan

    if MODEL_TYPE == "xgb_regime_session":
        print(f"Loading models (type={MODEL_TYPE})...")
        dt = pd.to_datetime(features_df["Date/Time"])
        market_open  = dt.dt.normalize() + pd.Timedelta("09:30:00")
        market_close = dt.dt.normalize() + pd.Timedelta("16:00:00")
        features_df["session"] = ((dt >= market_open) & (dt < market_close)).map({True: "rth", False: "eth"})

        for regime_col, regime_name in REGIME_COLS:
            for session in ["rth", "eth"]:
                label     = f"{regime_name}_{session}"
                model_dir = STRATEGY_DIR / "model/regime_session" / label
                if not model_dir.exists():
                    continue
                model, scaler, config = load_xgb(model_dir)
                print(f"  {label:<35} fold {config['best_fold']}  AUC {config['best_fold_val_auc']:.4f}")
                mask = (features_df[regime_col] == 1) & (features_df["session"] == session)
                if mask.sum() == 0:
                    continue
                X = features_df.loc[mask, FEATURE_COLS].values.astype(np.float32)
                prob, pred = run_inference(model, scaler, X)
                features_df.loc[mask, "confidence"] = prob
                features_df.loc[mask, "prediction"] = pred
                print(f"    {mask.sum():,} trades  predicted={pred.sum():,} ({pred.mean()*100:.1f}%)")

        unknown_mask = features_df["confidence"].isna()
        print(f"  Skipping {unknown_mask.sum():,} unmatched trades")

    elif MODEL_TYPE == "xgb_hour":
        # ── Hour routing: one model per hour of day ────────────────────────────
        print(f"Loading models (type={MODEL_TYPE})...")
        features_df["hour"] = pd.to_datetime(features_df["Date/Time"]).dt.hour
        for h in sorted(features_df["hour"].unique()):
            model_dir = STRATEGY_DIR / "model/hour" / f"{h:02d}"
            if not model_dir.exists():
                continue
            model, scaler, config = load_xgb(model_dir)
            print(f"  {h:02d}:00  best fold {config['best_fold']}  AUC {config['best_fold_val_auc']:.4f}")
            mask = features_df["hour"] == h
            X    = features_df.loc[mask, FEATURE_COLS].values.astype(np.float32)
            prob, pred = run_inference(model, scaler, X)
            features_df.loc[mask, "confidence"] = prob
            features_df.loc[mask, "prediction"] = pred
            print(f"    {mask.sum():,} trades  predicted={pred.sum():,} ({pred.mean()*100:.1f}%)")

    elif MODEL_TYPE == "xgb_regime":
        # ── Regime routing: one model per regime, skip unknowns ───────────────
        print(f"Loading models (type={MODEL_TYPE})...")
        for col, subdir in REGIME_COLS:
            model_dir = STRATEGY_DIR / "model/regime" / subdir
            model, scaler, config = load_xgb(model_dir)
            print(f"  {subdir:<25} best fold {config['best_fold']}  AUC {config['best_fold_val_auc']:.4f}")
            mask = features_df[col] == 1
            if mask.sum() == 0:
                continue
            X = features_df.loc[mask, FEATURE_COLS].values.astype(np.float32)
            prob, pred = run_inference(model, scaler, X)
            features_df.loc[mask, "confidence"] = prob
            features_df.loc[mask, "prediction"] = pred
            print(f"    {mask.sum():,} trades  predicted={pred.sum():,} ({pred.mean()*100:.1f}%)")

        # unknowns stay NaN → dropped from filtered set (skip option 1)
        unknown_mask = features_df["confidence"].isna()
        print(f"  Skipping {unknown_mask.sum():,} unknown-regime trades")

    else:
        # ── Direction split (xgb or mlp) ──────────────────────────────────────
        print(f"Loading models (type={MODEL_TYPE})...")
        long_device = short_device = None
        if MODEL_TYPE == "mlp":
            long_model,  long_scaler,  long_cfg,  long_device  = load_mlp(LONG_DIR)
            short_model, short_scaler, short_cfg, short_device = load_mlp(SHORT_DIR)
        else:
            long_model,  long_scaler,  long_cfg  = load_xgb(LONG_DIR)
            short_model, short_scaler, short_cfg = load_xgb(SHORT_DIR)
        print(f"  Long  model: best fold {long_cfg['best_fold']}  AUC {long_cfg['best_fold_val_auc']:.4f}")
        print(f"  Short model: best fold {short_cfg['best_fold']}  AUC {short_cfg['best_fold_val_auc']:.4f}")

        long_mask  = features_df["direction"] ==  1
        short_mask = features_df["direction"] == -1

        X_long  = features_df.loc[long_mask,  FEATURE_COLS].values.astype(np.float32)
        X_short = features_df.loc[short_mask, FEATURE_COLS].values.astype(np.float32)

        long_prob,  long_pred  = run_inference(long_model,  long_scaler,  X_long,  long_device)
        short_prob, short_pred = run_inference(short_model, short_scaler, X_short, short_device)

        features_df.loc[long_mask,  "confidence"] = long_prob
        features_df.loc[long_mask,  "prediction"] = long_pred
        features_df.loc[short_mask, "confidence"] = short_prob
        features_df.loc[short_mask, "prediction"] = short_pred

        print(f"  Long  : {long_mask.sum():,} trades  predicted={long_pred.sum():,} ({long_pred.mean()*100:.1f}%)")
        print(f"  Short : {short_mask.sum():,} trades  predicted={short_pred.sum():,} ({short_pred.mean()*100:.1f}%)")

    # ── Load + merge trades ───────────────────────────────────────────────────
    print("Loading trade records...")
    trades_df = load_paired_trades(TRADES_FILE)

    enriched = pd.merge(
        features_df.rename(columns={"Date/Time": "entry_ts"}).drop(columns=["direction", "signal"], errors="ignore"),
        trades_df[["entry_ts", "exit_ts", "entry_price", "exit_price", "direction", "signal", "pnl"]],
        on="entry_ts",
        how="inner",
    ).sort_values("entry_ts").reset_index(drop=True)

    enriched.to_csv(ENRICHED_FILE, index=False)
    print(f"  Saved enriched -> {ENRICHED_FILE}  ({len(enriched):,} rows)")

    # ── Test set ──────────────────────────────────────────────────────────────
    test_idx = get_test_indices(len(enriched))
    test_df  = enriched.iloc[test_idx].reset_index(drop=True)
    print(f"\nTest set : {len(test_df):,} trades")
    print(f"  Long  : {(test_df['direction']==1).sum():,}  |  Short : {(test_df['direction']==-1).sum():,}")

    naive_trades    = to_trade_list(test_df)
    # prediction==1 naturally excludes NaN (unknown regime trades are skipped)
    filtered_trades = to_trade_list(test_df[test_df["prediction"] == 1])

    # ── Metrics ───────────────────────────────────────────────────────────────
    m_naive    = compute_all(naive_trades,    INITIAL_CAPITAL, COMMISSION_PER_TRADE)
    m_filtered = compute_all(filtered_trades, INITIAL_CAPITAL, COMMISSION_PER_TRADE)

    model_label = MODEL_TYPE.upper()
    for label, metrics in [
        ("NAIVE — Take all test signals",                                        m_naive),
        (f"{model_label} FILTERED — prediction == 1 (threshold {THRESHOLD})",   m_filtered),
    ]:
        print_report(label, metrics)
        save_report(label, metrics, REPORT_FILE)

    n_taken = len(filtered_trades)
    n_total = len(naive_trades)
    gain    = (m_filtered["net_pnl"] or 0) - (m_naive["net_pnl"] or 0)
    summary = (
        f"\n  Trades taken : {n_taken:,} / {n_total:,} ({n_taken/n_total*100:.1f}%)\n"
        f"  Net P&L gain from filter: ${gain:,.2f}\n"
    )
    print(summary)
    with open(REPORT_FILE, "a") as f:
        f.write(summary)

    # ── Charts ────────────────────────────────────────────────────────────────
    plot_equity_curve(m_naive,    "Naive — Take all test signals",
                      save_path=str(REPORTS_DIR / "equity_naive.png"))
    plot_equity_curve(m_filtered, f"{model_label} Filtered (threshold {THRESHOLD})",
                      save_path=str(REPORTS_DIR / f"equity_{MODEL_TYPE}_filtered.png"))

    # ── Threshold sweep ───────────────────────────────────────────────────────
    thresholds = np.arange(0.20, 0.61, 0.01)

    def _sweep(label, mask_fn):
        pnl_list, trades_list, wr_list = [], [], []
        print(f"\n-- Threshold sweep: {label} ---")
        print(f"{'Threshold':>10} {'Trades':>7} {'Net P&L':>10} {'Win Rate':>9}")
        print("-" * 42)
        for thr in thresholds:
            taken  = test_df[mask_fn(test_df["confidence"], thr)]
            trades = to_trade_list(taken)
            m      = compute_all(trades, INITIAL_CAPITAL, COMMISSION_PER_TRADE)
            pnl    = m["net_pnl"] or 0
            wr     = m["win_rate"] or 0
            n      = len(trades)
            pnl_list.append(pnl)
            trades_list.append(n)
            wr_list.append(wr)
            marker = " <--" if abs(thr - THRESHOLD) < 0.005 else ""
            print(f"  {thr:.2f}      {n:>7,}  ${pnl:>9,.0f}  {wr:>8.1f}%{marker}")
        best_idx = int(np.argmax(pnl_list))
        print(f"\n  Best: {thresholds[best_idx]:.2f}  "
              f"P&L ${pnl_list[best_idx]:,.0f}  trades {trades_list[best_idx]:,}")
        return pnl_list, trades_list, wr_list, best_idx

    pnl_hi, tr_hi, wr_hi, best_hi = _sweep(
        "confidence >= thr  (keep high confidence)",
        lambda conf, thr: conf >= thr,
    )
    pnl_lo, tr_lo, wr_lo, best_lo = _sweep(
        "confidence <  thr  (cut high confidence)",
        lambda conf, thr: conf < thr,
    )

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    fig.suptitle(f"Threshold Sweep — {model_label}", fontsize=12)

    axes[0].plot(thresholds, pnl_hi, color="steelblue",  linewidth=1.5, marker="o", markersize=3, label="keep >= thr")
    axes[0].plot(thresholds, pnl_lo, color="tomato",     linewidth=1.5, marker="o", markersize=3, label="cut  >= thr")
    axes[0].axhline(m_naive["net_pnl"], color="dimgray", linestyle="--", label="Naive")
    axes[0].set_ylabel("Net P&L ($)")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(thresholds, tr_hi, color="steelblue", linewidth=1.5, marker="o", markersize=3, label="keep >= thr")
    axes[1].plot(thresholds, tr_lo, color="tomato",    linewidth=1.5, marker="o", markersize=3, label="cut  >= thr")
    axes[1].axhline(len(naive_trades), color="dimgray", linestyle="--", label="Naive count")
    axes[1].set_ylabel("# Trades")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(thresholds, wr_hi, color="steelblue",  linewidth=1.5, marker="o", markersize=3, label="keep >= thr")
    axes[2].plot(thresholds, wr_lo, color="tomato",     linewidth=1.5, marker="o", markersize=3, label="cut  >= thr")
    axes[2].axhline(m_naive["win_rate"] or 0, color="dimgray", linestyle="--", label="Naive win rate")
    axes[2].set_ylabel("Win Rate (%)")
    axes[2].set_xlabel("Confidence Threshold")
    axes[2].legend(fontsize=8)
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    sweep_path = REPORTS_DIR / f"threshold_sweep_{MODEL_TYPE}.png"
    fig.savefig(sweep_path, dpi=100)
    plt.close(fig)
    print(f"\n  Saved -> {sweep_path}")

    # ── Confidence distribution ───────────────────────────────────────────────
    print("\n-- Confidence distribution (test set) -----------------------")
    for lbl, group in [(1, "Winners (Label=1)"), (0, "Losers (Label=0)")]:
        subset = test_df[test_df["Label"] == lbl]["confidence"]
        print(f"  {group:<25} mean={subset.mean():.3f}  median={subset.median():.3f}  std={subset.std():.3f}")


if __name__ == "__main__":
    run()
