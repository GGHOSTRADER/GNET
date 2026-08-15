"""
30_backtest_train.py
====================

Training-data backtest report.

Loads the full labeled dataset and the raw TradeStation trade export,
pairs entry/exit rows, merges on entry timestamp, and computes backtest
metrics for two scenarios:

    1. Naive  — all trades (no filter)
    2. Oracle — only trades with Label=1 (theoretical upper bound)

Outputs saved to strategies/{STRATEGY_NAME}/reports/:
    backtest_train.txt
    equity_naive.png
    equity_oracle.png

Run
---
    cd training_mlp
    python 30_backtest_train.py
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / ".env")

import pandas as pd
from backtest_metrics import compute_all, print_report, save_report, plot_equity_curve
from pipeline_paths import INPUTS_DIR, PROCESSED_DIR, REPORTS_DIR, TRADES_FILE, FEATURES_FILE

REPORT_FILE          = REPORTS_DIR / "backtest_train.txt"

SIGNAL_NAME          = os.getenv("SIGNAL_NAME",           "MA2CrossLE")
INITIAL_CAPITAL      = float(os.getenv("INITIAL_CAPITAL",      "100000.0"))
COMMISSION_PER_TRADE = float(os.getenv("COMMISSION_PER_TRADE", "0.0"))


# ── Loaders ───────────────────────────────────────────────────────────────────

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


def load_features(filepath: Path) -> pd.DataFrame:
    df = pd.read_csv(filepath)
    df["Date/Time"] = pd.to_datetime(df["Date/Time"])
    return df


def merge_trades_and_labels(trades: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    features = features.rename(columns={"Date/Time": "entry_ts"})
    merged = pd.merge(trades, features[["entry_ts", "Label"]], on="entry_ts", how="inner")
    return merged.sort_values("entry_ts").reset_index(drop=True)


def to_trade_list(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "entry_ts":    row.entry_ts.to_pydatetime(),
            "exit_ts":     row.exit_ts.to_pydatetime(),
            "pnl":         float(row.pnl),
            "entry_price": float(row.entry_price),
            "exit_price":  float(row.exit_price),
            "exit_signal": row.exit_signal,
        }
        for row in df.itertuples()
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Clear previous report file
    if REPORT_FILE.exists():
        REPORT_FILE.unlink()

    print("Loading trades...")
    trades_df = load_paired_trades(TRADES_FILE, SIGNAL_NAME)
    print(f"  {len(trades_df)} paired trade records loaded")

    print("Loading features + labels...")
    features_df = load_features(FEATURES_FILE)
    print(f"  {len(features_df)} labeled feature rows loaded")

    print("Merging on entry timestamp...")
    merged = merge_trades_and_labels(trades_df, features_df)
    print(f"  {len(merged)} rows after merge")

    naive_trades  = to_trade_list(merged)
    oracle_trades = to_trade_list(merged[merged["Label"] == 1])

    m_naive  = compute_all(naive_trades,  INITIAL_CAPITAL, COMMISSION_PER_TRADE)
    m_oracle = compute_all(oracle_trades, INITIAL_CAPITAL, COMMISSION_PER_TRADE)

    # Print + save report
    for label, metrics in [
        ("NAIVE — Take all signals", m_naive),
        ("ORACLE — Take Label=1 only (theoretical upper bound)", m_oracle),
    ]:
        print_report(label, metrics)
        save_report(label, metrics, REPORT_FILE)

    headroom = (m_oracle["net_pnl"] or 0) - (m_naive["net_pnl"] or 0)
    summary = (
        f"\n  P&L headroom from filtering: ${headroom:,.2f}\n"
        f"  Oracle trades taken: {len(oracle_trades)} / {len(naive_trades)} "
        f"({len(oracle_trades)/len(naive_trades)*100:.1f}%)\n"
    )
    print(summary)
    with open(REPORT_FILE, "a") as f:
        f.write(summary)

    # Save charts
    plot_equity_curve(m_naive,  "Naive — Take all signals",
                      save_path=str(REPORTS_DIR / "equity_naive.png"))
    plot_equity_curve(m_oracle, "Oracle — Take Label=1 only (theoretical upper bound)",
                      save_path=str(REPORTS_DIR / "equity_oracle.png"))


if __name__ == "__main__":
    run()
