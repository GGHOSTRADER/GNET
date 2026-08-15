"""
zona_pipeline.py
================

Meta-labeling pipeline for the Zona strategy (VDX_2.csv).

Key differences from study_pipeline.py:
  - Both directions: long (Buy/Sell) and short (Sell Short/Buy to Cover)
  - Date format: "%m/%d/%Y %H:%M" (no seconds, 24-hour clock)
  - No large header block — data starts at row 3 (skiprows=2)
  - Footer garbage at end of file — filtered by checking Trade # column is numeric
  - PnL column: "Shares/Ctrts - Profit/Loss" on the exit row (Sell or Buy to Cover)
  - Entry signals: VDX.Buy (long) and VDX.SellShort (short)
  - Bar data: 2-minute bars (data_2min.txt) — same column schema as 30s bars

Output: strategies/zona_strat/processed/df_features_labeled.csv
        same schema as study_pipeline.py output — plug directly into 30_training_mlp.py

Run
---
    cd training_mlp
    python zona_pipeline.py
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from zona_features import engineer_features, FEATURE_COLS

OPEN_TIME = os.getenv("OPEN_TIME", "09:30:00")

STRATEGY_DIR  = Path("strategies/zona_strat")
INPUTS_DIR    = STRATEGY_DIR / "inputs"
PROCESSED_DIR = STRATEGY_DIR / "processed"

BARS_FILE   = INPUTS_DIR / "data_2min.txt"
TRADES_FILE = INPUTS_DIR / "VDX_2.csv"
MACRO_FILE  = INPUTS_DIR / "Macroeconomics_output_regime_only.xlsx"
OUTPUT_FILE = PROCESSED_DIR / "df_features_labeled.csv"

ENTRY_SIGNALS = {"VDX.Buy", "VDX.SellShort"}
EXIT_TYPES    = {"Sell", "Buy to Cover"}
ENTRY_TYPES   = {"Buy", "Sell Short"}


# ── 1. LOADERS ────────────────────────────────────────────────────────────────

def load_bars(filepath: Path) -> pd.DataFrame:
    df = pd.read_csv(filepath)
    df["Date/Time"] = pd.to_datetime(
        df["Date"].astype(str) + " " + df["Time"].astype(str),
        format="%m/%d/%Y %H:%M",
        errors="coerce",
    )
    for col in ["Open", "High", "Low", "Close", "Up", "Down"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Volume"] = df["Up"] + df["Down"]
    df = df.dropna(subset=["Date/Time"]).sort_values("Date/Time").reset_index(drop=True)
    # Keep only bars from 2018-10-01 onward — enough warmup for all rolling windows
    # before the first trade in 2019-01, reduces memory on 1.4M bar dataset
    df = df[df["Date/Time"] >= "2018-10-01"].reset_index(drop=True)
    return df


def _parse_pnl(s) -> float:
    """Convert TradeStation dollar strings: ($16.50) -> -16.5, $14.00 -> 14.0"""
    if pd.isna(s):
        return float("nan")
    s = str(s).strip().replace("$", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        return -float(s[1:-1])
    try:
        return float(s)
    except ValueError:
        return float("nan")


def load_paired_trades(filepath: Path) -> pd.DataFrame:
    """
    Parse VDX_2.csv into paired entry/exit records for both directions.

    Format:
        Entry row — numbered, Type in {Buy, Sell Short}, Signal in ENTRY_SIGNALS
        Exit  row — unnumbered (NaN #), Type in {Sell, Buy to Cover}

    Returns DataFrame with columns:
        entry_ts, exit_ts, entry_price, exit_price, direction, signal, pnl
    """
    # skiprows=2 skips the title row and blank row; footer is filtered below
    df = pd.read_csv(filepath, skiprows=2, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    col_num    = df.columns[0]          # trade number column (unnamed in some exports)
    col_type   = "Type"
    col_dt     = "Date/Time"
    col_signal = "Signal"
    col_price  = "Price"
    col_pnl    = "Shares/Ctrts - Profit/Loss"

    # Drop footer rows — only keep rows where either the # col is numeric or Type is a known trade type
    known_types = ENTRY_TYPES | EXIT_TYPES
    df = df[df[col_type].str.strip().isin(known_types)].copy()
    df = df.reset_index(drop=True)

    # Parse timestamps — format is "9/05/2019 08:00" (no seconds)
    df[col_dt] = pd.to_datetime(df[col_dt].str.strip(), format="%m/%d/%Y %H:%M", errors="coerce")
    df[col_price] = df[col_price].apply(_parse_pnl)
    df[col_pnl]   = df[col_pnl].apply(_parse_pnl)
    df[col_signal] = df[col_signal].str.strip()
    df[col_type]   = df[col_type].str.strip()

    records = []
    i = 0
    while i < len(df):
        row = df.iloc[i]

        # Entry row: type is Buy or Sell Short, signal is a known entry signal
        if row[col_type] in ENTRY_TYPES and row[col_signal] in ENTRY_SIGNALS:
            direction = 1 if row[col_type] == "Buy" else -1

            # Next row must be the exit
            if i + 1 < len(df):
                exit_row = df.iloc[i + 1]
                if exit_row[col_type] in EXIT_TYPES:
                    hold_min = (exit_row[col_dt] - row[col_dt]).total_seconds() / 60
                    if hold_min <= 480:  # discard trades never closed intraday (bad pairs)
                        records.append({
                            "entry_ts":    row[col_dt],
                            "exit_ts":     exit_row[col_dt],
                            "entry_price": float(row[col_price])      if pd.notna(row[col_price])      else float("nan"),
                            "exit_price":  float(exit_row[col_price]) if pd.notna(exit_row[col_price]) else float("nan"),
                            "direction":   direction,
                            "signal":      row[col_signal],
                            "pnl":         float(exit_row[col_pnl])   if pd.notna(exit_row[col_pnl])   else float("nan"),
                        })
                    i += 2
                    continue
        i += 1

    paired = pd.DataFrame(records)
    paired = paired.dropna(subset=["entry_ts", "exit_ts", "pnl"]).reset_index(drop=True)
    return paired


def metalabel(paired: pd.DataFrame) -> pd.DataFrame:
    """Label each trade: 1 = profitable (pnl > 0), 0 = loss or breakeven."""
    labeled = paired[["entry_ts", "direction", "signal", "pnl"]].copy()
    labeled["Label"] = (labeled["pnl"] > 0).astype(int)
    labeled = labeled.rename(columns={"entry_ts": "Date/Time"})
    return labeled[["Date/Time", "direction", "signal", "Label"]].reset_index(drop=True)


# ── 2. FEATURE ENGINEERING (imported from zona_features.py) ──────────────────
# engineer_features and FEATURE_COLS are imported at the top of this file.

# ── 3. MERGE & EXPORT ─────────────────────────────────────────────────────────


def merge_and_export(features_df: pd.DataFrame, labels_df: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    merged = pd.merge(features_df[["Date/Time"] + FEATURE_COLS], labels_df, on="Date/Time", how="inner")
    # Put Label last (same convention as study_pipeline.py)
    label = merged.pop("Label")
    merged["Label"] = label
    merged = merged.dropna().reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    print(f"Saved -> {output_path}")
    return merged


# ── 4. MAIN ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading bars...")
    df_bars = load_bars(BARS_FILE)
    print(f"  {len(df_bars):,} bars loaded  ({df_bars['Date/Time'].min()} -> {df_bars['Date/Time'].max()})")

    print("Loading trades...")
    paired = load_paired_trades(TRADES_FILE)
    print(f"  {len(paired):,} paired trades loaded")
    print(f"  Long  entries: {(paired['direction'] == 1).sum():,}")
    print(f"  Short entries: {(paired['direction'] == -1).sum():,}")

    print("Meta-labeling...")
    df_labeled = metalabel(paired)
    print(f"  Label distribution:\n{df_labeled['Label'].value_counts().to_string()}")

    print("Engineering features...")
    df_features = engineer_features(df_bars, open_time=OPEN_TIME, macro_path=str(MACRO_FILE))

    print("Merging and exporting...")
    df_final = merge_and_export(df_features, df_labeled, OUTPUT_FILE)

    print(f"\nFinal shape : {df_final.shape}")
    print(f"Date range  : {df_final['Date/Time'].min()} -> {df_final['Date/Time'].max()}")
    print(f"Label dist  :\n{df_final['Label'].value_counts().to_string()}")
    print(f"\nDirections in merged set:")
    print(df_final["direction"].value_counts().to_string())
