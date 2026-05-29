import pandas as pd
import numpy as np
from pathlib import Path

# INJECTIBLE -------------------------------------------------------------------
signal_name = "MA2CrossLE"
OPEN_TIME   = "09:30:00"
TRADES_FILE = r"C:\Users\g_med\Desktop\trades_30.csv"
BARS_FILE   = r"C:\Users\g_med\Downloads\data_30.txt"
OUTPUT_FILE = "df_features_labeled.csv"
# ------------------------------------------------------------------------------

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

def parkinson_vol(df, windows=(5, 15, 30)):
    log_hl = np.log(df["High"] / df["Low"]) ** 2
    for w in windows:
        df[f"parkinson_vol_{w}"] = (
            log_hl.rolling(w).sum() / (4 * w * np.log(2))
        ).apply(np.sqrt)
    return df


def order_flow_imbalance(df, windows=(5, 15, 30)):
    for w in windows:
        net = df["Up"].rolling(w).sum() - df["Down"].rolling(w).sum()
        tot = df["Volume"].rolling(w).sum().replace(0, np.nan)
        df[f"ofi_{w}"] = net / tot
    return df


def volume_features(df):
    df["volume_percentile"] = (
        df["Volume"].rolling(60)
        .apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
    )
    df["volume_momentum"] = df["Volume"].pct_change(5)
    return df


def amihud_illiquidity(df, window=30):
    ret        = df["Close"].pct_change().abs()
    dollar_vol = df["Close"] * df["Volume"]
    df["amihud_illiquidity"] = (
        (ret / dollar_vol.replace(0, np.nan)).rolling(window).mean()
    )
    return df


def vwap_distance(df, atr_window=14):
    df["_date"] = df["Date/Time"].dt.date
    df["_pv"]   = df["Close"] * df["Volume"]
    df["_vwap"] = df.groupby("_date")["_pv"].cumsum() / df.groupby("_date")["Volume"].cumsum()

    hl  = df["High"] - df["Low"]
    hpc = (df["High"] - df["Close"].shift()).abs()
    lpc = (df["Low"]  - df["Close"].shift()).abs()
    atr = pd.concat([hl, hpc, lpc], axis=1).max(axis=1).rolling(atr_window).mean()

    df["vwap_distance"] = (df["Close"] - df["_vwap"]) / atr.replace(0, np.nan)
    df.drop(columns=["_date", "_pv", "_vwap"], inplace=True)
    return df


def time_features(df):
    market_open = df["Date/Time"].dt.normalize() + pd.Timedelta(OPEN_TIME)
    df["minutes_since_open"] = (
        (df["Date/Time"] - market_open).dt.total_seconds() / 60
    ).clip(lower=0)
    df["is_first_last_30min"] = (
        (df["minutes_since_open"] <= 30) |
        (df["minutes_since_open"] >= 360)
    ).astype(int)
    df["day_of_week"] = df["Date/Time"].dt.weekday
    return df


def engineer_features(bars_df):
    df = bars_df.copy()
    df = parkinson_vol(df)
    df = order_flow_imbalance(df)
    df = volume_features(df)
    df = amihud_illiquidity(df)
    df = vwap_distance(df)
    df = time_features(df)
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