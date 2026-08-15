import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
import os
import sys
from types import SimpleNamespace

load_dotenv(Path(__file__).parent / ".env")

# Keep the documented ``cd training_mlp; python study_pipeline.py`` command
# working while importing the shared live/training feature package.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

signal_name = os.getenv("SIGNAL_NAME", "MA2CrossLE")

try:
    from .pipeline_paths import INPUTS_DIR, PROCESSED_DIR, TRADES_FILE, BARS_FILE, FEATURES_FILE as OUTPUT_FILE
except ImportError:  # Direct execution from inside training_mlp.
    from pipeline_paths import INPUTS_DIR, PROCESSED_DIR, TRADES_FILE, BARS_FILE, FEATURES_FILE as OUTPUT_FILE
from feat_files.canonical_features import FEATURE_NAMES, FeatureEngine

# ── 1. LOADERS ────────────────────────────────────────────────────────────────

def load_bars(filepath):
    df = pd.read_csv(filepath)
    df["Date/Time"] = pd.to_datetime(
        df["Date"].astype(str) + " " + df["Time"].astype(str),
        format="%m/%d/%Y %H:%M:%S", errors="coerce"
    )
    for col in ["Open", "High", "Low", "Close", "Up", "Down"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Volume"] = df["Up"] + df["Down"]
    return df.dropna(subset=["Date/Time"]).sort_values("Date/Time").reset_index(drop=True)


def load_trades(filepath):
    df = pd.read_csv(filepath, skiprows=173)
    df = df[df["Type"].isin(["Buy", "Sell"])].copy()
    df["% Profit"] = (
        df["% Profit"].astype(str)
        .str.replace(r"[$,%()]", "", regex=True).str.strip()
    )
    df["% Profit"]  = pd.to_numeric(df["% Profit"], errors="coerce")
    df["Date/Time"] = pd.to_datetime(df["Date/Time"], format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    return df.dropna(subset=["Date/Time"]).reset_index(drop=True)


# ── 2. METALABELING ───────────────────────────────────────────────────────────

def metalabel(df, signal):
    entries = df[df["Signal"] == signal][["Date/Time", "% Profit"]].copy()
    if entries.empty:
        raise ValueError(f"Signal '{signal}' not found.")
    entries["Label"] = (entries["% Profit"] > 0).astype(int)
    return entries[["Date/Time", "Label"]].dropna().reset_index(drop=True)


# ── 3. FEATURE ENGINEERING ────────────────────────────────────────────────────

def engineer_features(bars_df):
    """Build training features with the same engine used by the live stream."""
    df = bars_df.copy().reset_index(drop=True)
    engine = FeatureEngine()
    rows = []
    timestamp_position = df.columns.get_loc("Date/Time")
    for row in df.itertuples(index=False):
        timestamp = row[timestamp_position]
        bar = SimpleNamespace(
            date=timestamp.date(),
            time_s=timestamp.hour * 3600 + timestamp.minute * 60 + timestamp.second,
            high=float(row.High), low=float(row.Low), close=float(row.Close),
            up=int(row.Up), down=int(row.Down),
        )
        values = engine.update(bar)
        rows.append(
            {name: getattr(values, name) for name in FEATURE_NAMES}
            if values is not None else {name: np.nan for name in FEATURE_NAMES}
        )
    feature_frame = pd.DataFrame(rows, index=df.index)
    for name in FEATURE_NAMES:
        df[name] = feature_frame[name]
    return df.reset_index(drop=True)


# ── 4. MERGE & EXPORT ────────────────────────────────────────────────────────

FEATURE_COLS = [
    "Date/Time",
    "parkinson_vol_5", "parkinson_vol_15", "parkinson_vol_30",
    "ofi_5", "ofi_15", "ofi_30",
    "volume_percentile", "volume_momentum",
    "amihud_illiquidity", "vwap_distance",
    "minutes_since_open", "is_first_last_30min", "day_of_week",
]

def merge_and_export(features_df, labels_df, output_path):
    df = pd.merge(features_df[FEATURE_COLS], labels_df, on="Date/Time", how="inner")
    label = df.pop("Label")
    df["Label"] = label
    df = df.dropna().reset_index(drop=True)
    df.to_csv(output_path, index=False)
    print(f"Saved → {output_path}")
    return df


# ── 5. MAIN ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading bars...")
    df_bars    = load_bars(BARS_FILE)

    print("Loading trades...")
    df_trades  = load_trades(TRADES_FILE)
    df_labeled = metalabel(df_trades, signal_name)

    print("Engineering features...")
    df_features = engineer_features(df_bars)

    print("Merging and exporting...")
    df_final = merge_and_export(df_features, df_labeled, OUTPUT_FILE)

    print(f"\nShape     : {df_final.shape}")
    print(f"Label dist:\n{df_final['Label'].value_counts()}")
    print(df_final.head())
