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


def _parse_tradestation_timestamps(values):
    """Parse normal timestamps and TradeStation's midnight date-only form."""
    text = values.astype(str).str.strip()
    parsed = pd.to_datetime(
        text,
        format="%m/%d/%Y %I:%M:%S %p",
        errors="coerce",
    )
    date_only = text.str.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}")
    parsed.loc[date_only] = pd.to_datetime(
        text.loc[date_only],
        format="%m/%d/%Y",
        errors="coerce",
    )
    return parsed

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
    df["_timestamp"] = _parse_tradestation_timestamps(df["Date/Time"])
    return df.reset_index(drop=True)


# ── 2. METALABELING ───────────────────────────────────────────────────────────

def metalabel(df, signal):
    rows = []
    seen_trade_ids = set()
    position = 0
    while position < len(df):
        entry = df.iloc[position]
        if pd.isna(entry["#"]):
            raise ValueError(
                f"TradeStation row {position} is an exit without a numbered entry."
            )
        if position + 1 >= len(df):
            raise ValueError(f"Trade {entry['#']} has no following closing row.")
        close = df.iloc[position + 1]
        if pd.notna(close["#"]):
            raise ValueError(
                f"Trade {entry['#']} is followed by another entry instead of a close."
            )

        trade_id = int(entry["#"])
        if trade_id in seen_trade_ids:
            raise ValueError(f"TradeStation trade number {trade_id} is duplicated.")
        seen_trade_ids.add(trade_id)
        entry_time = entry["_timestamp"]
        close_time = close["_timestamp"]

        if pd.isna(close_time) and str(close["Date/Time"]).strip().lower() == "open":
            position += 2
            continue
        if pd.isna(entry_time) or pd.isna(close_time):
            raise ValueError(f"Trade {trade_id} has an invalid entry or close timestamp.")
        if close_time < entry_time:
            raise ValueError(f"Trade {trade_id} closes before it enters.")

        if entry["Signal"] == signal:
            if pd.isna(entry["% Profit"]):
                raise ValueError(f"Completed trade {trade_id} has no profit label.")
            rows.append(
                {
                    "Date/Time": entry_time,
                    "t1": close_time,
                    "Label": int(float(entry["% Profit"]) > 0.0),
                }
            )
        position += 2

    entries = pd.DataFrame(rows, columns=["Date/Time", "t1", "Label"])
    if entries.empty:
        raise ValueError(f"Signal '{signal}' not found.")
    return entries.reset_index(drop=True)


# ── 3. FEATURE ENGINEERING ────────────────────────────────────────────────────

def engineer_features(bars_df, *, vwap_column=None, vwap_mode="bar", reset_at=None):
    """Build features with reconstructed VWAP or an explicitly supplied series.

    TradeStation defines bar AvgPrice as OHLC/4 and its daily VWAP weights that
    value by bar volume.  For electronic futures charts configured with
    ``For volume, use: Trade Vol``, UpTicks + DownTicks is contract volume.
    """
    if vwap_mode not in {"bar", "canonical"}:
        raise ValueError(f"unknown VWAP mode: {vwap_mode}")
    if vwap_mode == "canonical" and vwap_column is not None:
        raise ValueError("canonical VWAP cannot use an external VWAP column")
    df = bars_df.copy().reset_index(drop=True)
    if vwap_mode == "canonical":
        df["_tradestation_vwap"] = np.nan
    elif vwap_column is None:
        volume = pd.to_numeric(df["Up"], errors="coerce") + pd.to_numeric(
            df["Down"], errors="coerce"
        )
        average_price = (
            pd.to_numeric(df["Open"], errors="coerce")
            + pd.to_numeric(df["High"], errors="coerce")
            + pd.to_numeric(df["Low"], errors="coerce")
            + pd.to_numeric(df["Close"], errors="coerce")
        ) / 4.0
        calendar_day = pd.to_datetime(df["Date/Time"]).dt.date
        cumulative_volume = volume.groupby(calendar_day, sort=False).cumsum()
        cumulative_price_volume = (average_price * volume).groupby(
            calendar_day, sort=False
        ).cumsum()
        df["_tradestation_vwap"] = cumulative_price_volume / cumulative_volume.replace(0, np.nan)
    else:
        if vwap_column not in df.columns:
            raise ValueError(f"native VWAP column is missing: {vwap_column}")
        df["_tradestation_vwap"] = pd.to_numeric(df[vwap_column], errors="coerce")
        if df["_tradestation_vwap"].isna().any() or (df["_tradestation_vwap"] <= 0).any():
            raise ValueError(f"native VWAP column contains missing or nonpositive values: {vwap_column}")

    engine = FeatureEngine(vwap_mode=vwap_mode)
    reset_timestamp = pd.Timestamp(reset_at) if reset_at is not None else None
    reset_done = False
    rows = []
    timestamp_position = df.columns.get_loc("Date/Time")
    vwap_position = df.columns.get_loc("_tradestation_vwap")
    for row in df.itertuples(index=False):
        timestamp = row[timestamp_position]
        if reset_timestamp is not None and not reset_done and timestamp >= reset_timestamp:
            if timestamp != reset_timestamp:
                raise ValueError(f"feature reset boundary is not a bar timestamp: {reset_timestamp}")
            engine = FeatureEngine(vwap_mode=vwap_mode)
            reset_done = True
        bar = SimpleNamespace(
            date=timestamp.date(),
            time_s=timestamp.hour * 3600 + timestamp.minute * 60 + timestamp.second,
            high=float(row.High), low=float(row.Low), close=float(row.Close),
            up=int(row.Up), down=int(row.Down),
            vwap=float(row[vwap_position]),
        )
        values = engine.update(bar)
        rows.append(
            {name: getattr(values, name) for name in FEATURE_NAMES}
            if values is not None else {name: np.nan for name in FEATURE_NAMES}
        )
    if reset_timestamp is not None and not reset_done:
        raise ValueError(f"feature reset boundary is outside the bars: {reset_timestamp}")
    feature_frame = pd.DataFrame(rows, index=df.index)
    for name in FEATURE_NAMES:
        df[name] = feature_frame[name]
    df = df.drop(columns=["_tradestation_vwap"])
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
    print(f"Saved -> {output_path}")
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
