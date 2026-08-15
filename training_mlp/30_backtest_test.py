"""
30_backtest_test.py
===================

Test-set backtest report + enriched dataset generator.

Does two things:

1. DATASET — runs model_best.pt over the full labeled dataset and saves
   df_enriched.csv with every trade record enriched with:
       confidence   : sigmoid probability from the MLP
       prediction   : 1 if confidence >= THRESHOLD else 0

2. REPORT — on the held-out test set only, computes backtest metrics for:
       Naive    — take all signals
       Filtered — take only trades where prediction == 1

Outputs saved to strategies/{STRATEGY_NAME}/reports/:
    backtest_test.txt
    equity_naive.png
    equity_mlp_filtered.png

df_enriched.csv saved to strategies/{STRATEGY_NAME}/processed/

Run
---
    cd training_mlp
    python 30_backtest_test.py
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / ".env")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from backtest_metrics import compute_all, print_report, save_report, plot_equity_curve
from pipeline_paths import INPUTS_DIR, PROCESSED_DIR, MODEL_DIR, REPORTS_DIR, TRADES_FILE, FEATURES_FILE, ENRICHED_FILE

REPORT_FILE          = REPORTS_DIR / "backtest_test.txt"

SIGNAL_NAME          = os.getenv("SIGNAL_NAME",           "MA2CrossLE")
INITIAL_CAPITAL      = float(os.getenv("INITIAL_CAPITAL",      "100000.0"))
COMMISSION_PER_TRADE = float(os.getenv("COMMISSION_PER_TRADE", "0.0"))
THRESHOLD            = float(os.getenv("THRESHOLD",            "0.5"))
TEST_SIZE            = float(os.getenv("TEST_SIZE",            "0.10"))
PURGE_BARS           = int(os.getenv("PURGE_BARS",             "20"))
EMBARGO_BARS         = int(os.getenv("EMBARGO_BARS",           "60"))

FEATURE_COLS = [
    "parkinson_vol_5", "parkinson_vol_15", "parkinson_vol_30",
    "ofi_5", "ofi_15", "ofi_30",
    "volume_percentile", "volume_momentum",
    "amihud_illiquidity", "vwap_distance",
    "minutes_since_open", "is_first_last_30min", "day_of_week",
]


# ── Model (must match 30_training_mlp.py) ────────────────────────────────────

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


# ── Trade loader ──────────────────────────────────────────────────────────────

def _parse_dollar(s) -> float:
    if pd.isna(s):
        return 0.0
    s = str(s).strip().replace("$", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        return -float(s[1:-1])
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_paired_trades(filepath: Path, signal_name: str) -> pd.DataFrame:
    df = pd.read_csv(filepath, skiprows=173, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df[df["Type"].isin(["Buy", "Sell"])].reset_index(drop=True)

    col_pnl   = "Shares/Ctrts - Profit/Loss"
    col_price = "Price"

    buys  = df[df["Type"] == "Buy"].reset_index(drop=True)
    sells = df[df["Type"] == "Sell"].reset_index(drop=True)
    buys  = buys[buys["Signal"] == signal_name].reset_index(drop=True)

    min_len = min(len(buys), len(sells))
    buys, sells = buys.iloc[:min_len], sells.iloc[:min_len]

    return pd.DataFrame({
        "entry_ts":    pd.to_datetime(buys["Date/Time"].values,  format="%m/%d/%Y %I:%M:%S %p", errors="coerce"),
        "exit_ts":     pd.to_datetime(sells["Date/Time"].values, format="%m/%d/%Y %I:%M:%S %p", errors="coerce"),
        "entry_price": buys[col_price].apply(_parse_dollar).values,
        "exit_price":  sells[col_price].apply(_parse_dollar).values,
        "exit_signal": sells["Signal"].values,
        "pnl":         sells[col_pnl].apply(_parse_dollar).values,
    }).dropna(subset=["entry_ts", "exit_ts"]).reset_index(drop=True)


# ── Inference ─────────────────────────────────────────────────────────────────

@torch.no_grad()
def run_inference(X: np.ndarray, model: MLP, scaler, device) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    X_scaled    = scaler.transform(X).astype(np.float32)
    logits      = model(torch.tensor(X_scaled).to(device)).cpu().numpy()
    confidence  = 1 / (1 + np.exp(-logits))
    prediction  = (confidence >= THRESHOLD).astype(int)
    return confidence, prediction


# ── Test split (mirrors 30_training_mlp.py) ──────────────────────────────────

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
        }
        for row in df.itertuples()
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if REPORT_FILE.exists():
        REPORT_FILE.unlink()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ── Load config + model + scaler ─────────────────────────────────────────
    with open(MODEL_DIR / "config.json") as f:
        config = json.load(f)

    print("Loading model and scaler...")
    with open(MODEL_DIR / "scaler_best.pkl", "rb") as f:
        scaler = pickle.load(f)

    model = MLP(input_dim=config["n_features"]).to(device)
    model.load_state_dict(torch.load(MODEL_DIR / "model_best.pt", map_location=device))
    print(f"  Model loaded (best fold {config['best_fold']}, val AUC {config['best_fold_val_auc']:.4f})")

    # ── Load features + labels ───────────────────────────────────────────────
    print("Loading features + labels...")
    features_df = pd.read_csv(FEATURES_FILE).dropna().reset_index(drop=True)
    features_df["Date/Time"] = pd.to_datetime(features_df["Date/Time"])
    X = features_df[FEATURE_COLS].values.astype(np.float32)
    print(f"  {len(features_df)} rows")

    # ── Run inference on full dataset ────────────────────────────────────────
    print("Running inference on full dataset...")
    confidence, prediction = run_inference(X, model, scaler, device)

    # ── Load trades ──────────────────────────────────────────────────────────
    print("Loading trade records...")
    trades_df = load_paired_trades(TRADES_FILE, SIGNAL_NAME)

    # ── Build + save enriched dataset ────────────────────────────────────────
    features_df["confidence"] = confidence
    features_df["prediction"] = prediction

    enriched = pd.merge(
        features_df.rename(columns={"Date/Time": "entry_ts"}),
        trades_df[["entry_ts", "exit_ts", "entry_price", "exit_price", "exit_signal", "pnl"]],
        on="entry_ts",
        how="inner",
    ).sort_values("entry_ts").reset_index(drop=True)

    enriched.to_csv(ENRICHED_FILE, index=False)
    print(f"  Saved enriched dataset -> {ENRICHED_FILE}  ({len(enriched)} rows)")

    # ── Isolate test set ─────────────────────────────────────────────────────
    test_idx = get_test_indices(len(enriched))
    test_df  = enriched.iloc[test_idx].reset_index(drop=True)
    print(f"\nTest set: {len(test_df)} trades (last {TEST_SIZE*100:.0f}% with {PURGE_BARS+EMBARGO_BARS}-bar gap)")

    naive_trades    = to_trade_list(test_df)
    filtered_trades = to_trade_list(test_df[test_df["prediction"] == 1])

    # ── Metrics ──────────────────────────────────────────────────────────────
    m_naive    = compute_all(naive_trades,    INITIAL_CAPITAL, COMMISSION_PER_TRADE)
    m_filtered = compute_all(filtered_trades, INITIAL_CAPITAL, COMMISSION_PER_TRADE)

    for label, metrics in [
        ("NAIVE — Take all test signals", m_naive),
        (f"MLP FILTERED — prediction == 1 (threshold {THRESHOLD})", m_filtered),
    ]:
        print_report(label, metrics)
        save_report(label, metrics, REPORT_FILE)

    n_taken = len(filtered_trades)
    n_total = len(naive_trades)
    gain    = (m_filtered["net_pnl"] or 0) - (m_naive["net_pnl"] or 0)
    summary = (
        f"\n  Trades taken by filter : {n_taken} / {n_total} ({n_taken/n_total*100:.1f}%)\n"
        f"  Net P&L gain from filter: ${gain:,.2f}\n"
    )
    print(summary)
    with open(REPORT_FILE, "a") as f:
        f.write(summary)

    # ── Save charts ──────────────────────────────────────────────────────────
    plot_equity_curve(m_naive,    "Naive — Take all test signals",
                      save_path=str(REPORTS_DIR / "equity_naive.png"))
    plot_equity_curve(m_filtered, f"MLP Filtered — prediction == 1 (threshold {THRESHOLD})",
                      save_path=str(REPORTS_DIR / "equity_mlp_filtered.png"))

    # ── Confidence score distribution ────────────────────────────────────────
    print(f"\n-- Confidence score distribution (test set) -----------------")
    for lbl, group in [(1, "Winners (Label=1)"), (0, "Losers (Label=0)")]:
        subset = test_df[test_df["Label"] == lbl]["confidence"]
        print(f"  {group:<25} mean={subset.mean():.3f}  median={subset.median():.3f}  std={subset.std():.3f}")
    print()


if __name__ == "__main__":
    run()
