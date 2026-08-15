"""
zona_features.py
================

Feature engineering for the Zona strategy (MNQ 2-minute bars).

  - Directional  (14): ROC 5/20/60, EMA cross 5/20, price vs EMA 20/60,
                        bar structure, consecutive bars, breakout, ATR
  - Volume        (8): ratio, up/down pressure, spike, delta, trend, percentile
  - Volatility    (6): realized vol, vol ratio, ATR ratio, vol percentile, vol-of-vol
  - VWAP          (1): intraday VWAP distance normalized by ATR
  - Time          (5): minutes_since_open, session flags (RTH/pre/post market),
                        is_first_last_30min, day_of_week
  - Regime        (5): monthly macro regime one-hot encoded

All functions are pure: same input -> same output, no I/O, no globals.
Input DataFrame must have: Date/Time, Open, High, Low, Close, Up, Down, Volume
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ── Directional Features ──────────────────────────────────────────────────────

def price_slope(df: pd.DataFrame, windows=(5, 20, 60)) -> pd.DataFrame:
    """Linear regression slope of Close over window, normalized by price."""
    for w in windows:
        def _slope(x):
            y = np.array(x)
            return np.polyfit(np.arange(len(y)), y, 1)[0] / (y.mean() + 1e-9)
        df[f"slope_{w}"] = df["Close"].rolling(w).apply(_slope, raw=True)
    return df


def ema_features(df: pd.DataFrame) -> pd.DataFrame:
    ema5  = df["Close"].ewm(span=5,  adjust=False).mean()
    ema20 = df["Close"].ewm(span=20, adjust=False).mean()
    ema60 = df["Close"].ewm(span=60, adjust=False).mean()

    df["ema_cross_5_20"]  = (ema5  - ema20) / df["Close"]
    df["price_vs_ema_20"] = (df["Close"] - ema20) / df["Close"]
    df["price_vs_ema_60"] = (df["Close"] - ema60) / df["Close"]
    return df


def bar_structure(df: pd.DataFrame) -> pd.DataFrame:
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    df["bar_body_ratio"]     = (df["Close"] - df["Open"]) / rng
    df["high_low_position"]  = (df["Close"] - df["Low"])  / rng
    avg_rng = rng.rolling(10).mean()
    df["range_expansion_10"] = (rng - avg_rng) / avg_rng.replace(0, np.nan)
    return df


def consecutive_bars(df: pd.DataFrame) -> pd.DataFrame:
    up   = (df["Close"] > df["Open"]).astype(int)
    down = (df["Close"] < df["Open"]).astype(int)
    consec_up, consec_down = [], []
    cu = cd = 0
    for u, d in zip(up, down):
        cu = cu + 1 if u else 0
        cd = cd + 1 if d else 0
        consec_up.append(cu)
        consec_down.append(cd)
    df["consec_up"]   = consec_up
    df["consec_down"] = consec_down
    return df


def breakout_features(df: pd.DataFrame) -> pd.DataFrame:
    prev_high = df["High"].shift(1)
    prev_low  = df["Low"].shift(1)
    df["close_vs_prev_high"] = (df["Close"] - prev_high) / prev_high.replace(0, np.nan)
    df["close_vs_prev_low"]  = (df["Close"] - prev_low)  / prev_low.replace(0, np.nan)
    return df


def atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    hl  = df["High"] - df["Low"]
    hpc = (df["High"] - df["Close"].shift()).abs()
    lpc = (df["Low"]  - df["Close"].shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(window).mean() / df["Close"]
    return df


# ── VWAP Features ─────────────────────────────────────────────────────────────

def vwap_features(df: pd.DataFrame, atr_window: int = 14) -> pd.DataFrame:
    # Intraday VWAP resets each calendar day
    df["_date"] = df["Date/Time"].dt.date
    df["_pv"]   = df["Close"] * df["Volume"]
    df["_vwap"] = (
        df.groupby("_date")["_pv"].cumsum()
        / df.groupby("_date")["Volume"].cumsum().replace(0, np.nan)
    )

    hl  = df["High"] - df["Low"]
    hpc = (df["High"] - df["Close"].shift()).abs()
    lpc = (df["Low"]  - df["Close"].shift()).abs()
    atr_val = pd.concat([hl, hpc, lpc], axis=1).max(axis=1).rolling(atr_window).mean()

    df["vwap_distance"] = (df["Close"] - df["_vwap"]) / atr_val.replace(0, np.nan)
    df.drop(columns=["_date", "_pv", "_vwap"], inplace=True)
    return df


# ── Microstructure Features ───────────────────────────────────────────────────

def microstructure_features(df: pd.DataFrame) -> pd.DataFrame:
    vol = df["Volume"].replace(0, np.nan)
    net = df["Up"] - df["Down"]

    # Order flow imbalance: single bar bid/ask pressure
    df["ofi"] = net / vol

    # Bid/ask absorption: large up volume on down bar = absorption of sellers
    down_bar = (df["Close"] < df["Open"]).astype(float)
    up_bar   = (df["Close"] > df["Open"]).astype(float)
    df["buy_absorption"]  = (df["Up"]   / vol) * down_bar
    df["sell_absorption"] = (df["Down"] / vol) * up_bar

    # Aggressor ratio: who is more aggressive over last 5 bars
    df["aggressor_ratio_5"] = (
        df["Up"].rolling(5).sum() /
        (df["Up"].rolling(5).sum() + df["Down"].rolling(5).sum()).replace(0, np.nan)
    )

    # Price efficiency: how directly did price move (close-to-close vs bar range)
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    ret = (df["Close"] - df["Close"].shift(1)).abs()
    df["price_efficiency_5"] = ret.rolling(5).sum() / rng.rolling(5).sum().replace(0, np.nan)

    # Effort vs result: volume put in vs range achieved (high vol, small range = absorption)
    avg_vol = vol.rolling(20).mean().replace(0, np.nan)
    avg_rng = rng.rolling(20).mean().replace(0, np.nan)
    df["effort_vs_result"] = (vol / avg_vol) / (rng / avg_rng)

    # Tick imbalance: rolling sum of signed ticks normalized
    signed = np.sign(df["Close"] - df["Close"].shift(1))
    df["tick_imbalance_10"] = signed.rolling(10).sum() / 10

    return df


# ── Volume Features ───────────────────────────────────────────────────────────

def volume_ratio(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.DataFrame:
    avg_fast = df["Volume"].rolling(fast).mean()
    avg_slow = df["Volume"].rolling(slow).mean().replace(0, np.nan)
    df["volume_ratio_5_20"] = avg_fast / avg_slow
    return df


def up_down_ratio(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    roll_up   = df["Up"].rolling(window).sum()
    roll_down = df["Down"].rolling(window).sum()
    total     = (roll_up + roll_down).replace(0, np.nan)
    df["up_down_ratio_10"] = (roll_up - roll_down) / total
    return df


def volume_spike(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    avg = df["Volume"].rolling(window).mean()
    std = df["Volume"].rolling(window).std().replace(0, np.nan)
    df["volume_spike_20"] = (df["Volume"] - avg) / std
    return df


def cumulative_delta(df: pd.DataFrame, windows=(10, 20)) -> pd.DataFrame:
    net = df["Up"] - df["Down"]
    for w in windows:
        roll_vol = df["Volume"].rolling(w).sum().replace(0, np.nan)
        df[f"delta_{w}"] = net.rolling(w).sum() / roll_vol
    return df


def volume_trend(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    def slope(x):
        y = np.array(x)
        return np.polyfit(np.arange(len(y)), y, 1)[0] / (y.mean() + 1e-9)
    df["volume_trend_10"] = df["Volume"].rolling(window).apply(slope, raw=True)
    return df


def high_volume_bar(df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    df["high_volume_bar_60"] = (
        df["Volume"].rolling(window)
        .apply(lambda x: 1.0 if (x[-1] >= x).mean() >= 0.80 else 0.0, raw=True)
    )
    return df


def volume_percentile(df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    df["volume_percentile_60"] = (
        df["Volume"].rolling(window)
        .apply(lambda x: (x[-1] >= x).mean(), raw=True)
    )
    return df


# ── Volatility Features ───────────────────────────────────────────────────────

def volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    ret = df["Close"].pct_change()

    rv10 = ret.rolling(10).std()
    rv30 = ret.rolling(30).std()

    df["realized_vol_10"]      = rv10
    df["realized_vol_30"]      = rv30
    df["vol_ratio_short_long"] = rv10 / rv30.replace(0, np.nan)

    hl    = df["High"] - df["Low"]
    hpc   = (df["High"] - df["Close"].shift()).abs()
    lpc   = (df["Low"]  - df["Close"].shift()).abs()
    tr    = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    atr10 = tr.rolling(10).mean()
    atr50 = tr.rolling(50).mean()
    df["atr_ratio_10_50"] = atr10 / atr50.replace(0, np.nan)

    df["vol_percentile_60"] = (
        rv10.rolling(60).apply(lambda x: (x[-1] >= x).mean(), raw=True)
    )
    df["vol_of_vol_20"] = rv10.rolling(20).std()
    return df


# ── Time / Session Features ───────────────────────────────────────────────────

def time_features(df: pd.DataFrame, open_time: str = "09:30:00") -> pd.DataFrame:
    market_open  = df["Date/Time"].dt.normalize() + pd.Timedelta(open_time)
    market_close = df["Date/Time"].dt.normalize() + pd.Timedelta("16:00:00")

    # Minutes from RTH open — negative = pre-market, positive = in/post session
    mins = (df["Date/Time"] - market_open).dt.total_seconds() / 60
    df["minutes_since_open"] = mins

    # Session flags
    df["is_pre_market"]      = (mins < 0).astype(int)
    df["is_post_market"]     = (df["Date/Time"] >= market_close).astype(int)
    df["is_rth"]             = ((mins >= 0) & (df["Date/Time"] < market_close)).astype(int)
    df["is_first_last_30min"] = (
        ((mins >= 0) & (mins <= 30)) |
        ((mins >= 330) & (mins <= 390))   # 30 min before and after close
    ).astype(int)
    df["day_of_week"]        = df["Date/Time"].dt.weekday
    df["time_of_day_seconds"] = df["Date/Time"].dt.hour * 3600 + df["Date/Time"].dt.minute * 60
    return df


# ── Regime Features ───────────────────────────────────────────────────────────

REGIME_COLS = [
    "regime_late_expansion",
    "regime_mid_expansion",
    "regime_early_contraction",
    "regime_early_expansion",
    "regime_late_contraction",
]

_REGIME_MAP = {
    "Late Expansion":    "regime_late_expansion",
    "Mid Expansion":     "regime_mid_expansion",
    "Early Contraction": "regime_early_contraction",
    "Early Expansion":   "regime_early_expansion",
    "Late Contraction":  "regime_late_contraction",
}


def load_regime(filepath: str) -> pd.DataFrame:
    macro = pd.read_excel(filepath) if str(filepath).endswith(".xlsx") else pd.read_csv(filepath)
    macro.columns = ["date", "regime"]
    macro["date"]  = pd.to_datetime(macro["date"])
    macro["year"]  = macro["date"].dt.year
    macro["month"] = macro["date"].dt.month
    for col in REGIME_COLS:
        macro[col] = 0
    for label, col in _REGIME_MAP.items():
        macro.loc[macro["regime"] == label, col] = 1
    return macro[["year", "month"] + REGIME_COLS]


def regime_features(df: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    df["_year"]  = df["Date/Time"].dt.year
    df["_month"] = df["Date/Time"].dt.month
    df = df.merge(macro, left_on=["_year", "_month"], right_on=["year", "month"], how="left")
    df.drop(columns=["_year", "_month", "year", "month"], inplace=True)
    for col in REGIME_COLS:
        df[col] = df[col].fillna(0).astype(int)
    return df


# ── Fractal / Market Structure Features ──────────────────────────────────────

def fractal_features(df: pd.DataFrame) -> pd.DataFrame:
    high = df["High"]
    low  = df["Low"]
    close= df["Close"]

    # Range position: where is close within the last N-bar high-low range (0=bottom, 1=top)
    for w in (20, 60):
        rng_high = high.rolling(w).max()
        rng_low  = low.rolling(w).min()
        rng      = (rng_high - rng_low).replace(0, np.nan)
        df[f"range_position_{w}"] = (close - rng_low) / rng

    # Higher timeframe slope: trend over 120 and 240 bars (4h and 8h)
    for w in (120, 240):
        def _slope(x):
            y = np.array(x)
            return np.polyfit(np.arange(len(y)), y, 1)[0] / (y.mean() + 1e-9)
        df[f"slope_{w}"] = close.rolling(w).apply(_slope, raw=True)

    # Swing high/low distance: last pivot high/low over 20-bar window
    # Pivot high: bar whose high is highest of surrounding 5 bars
    pivot_high = high.rolling(5, center=True).max()
    pivot_low  = low.rolling(5,  center=True).min()
    last_ph = pivot_high.rolling(20).max()
    last_pl = pivot_low.rolling(20).min()
    df["dist_to_swing_high"] = (last_ph - close) / close.replace(0, np.nan)
    df["dist_to_swing_low"]  = (close - last_pl) / close.replace(0, np.nan)

    # Bars since last swing high/low
    is_ph = (high == pivot_high).astype(float)
    is_pl = (low  == pivot_low).astype(float)

    def bars_since(s, window=60):
        result = np.full(len(s), np.nan)
        last   = np.nan
        for i, v in enumerate(s):
            if v == 1:
                last = 0
            elif not np.isnan(last):
                last += 1
            result[i] = last
        return result

    df["bars_since_swing_high"] = bars_since(is_ph.values)
    df["bars_since_swing_low"]  = bars_since(is_pl.values)

    # Range compression: current 10-bar range vs 60-bar range (squeeze detection)
    rng10 = (high.rolling(10).max() - low.rolling(10).min())
    rng60 = (high.rolling(60).max() - low.rolling(60).min()).replace(0, np.nan)
    df["range_compression"] = rng10 / rng60

    return df


# ── Master Function ───────────────────────────────────────────────────────────

def engineer_features(bars_df: pd.DataFrame, open_time: str = "09:30:00", macro_path: str = None) -> pd.DataFrame:
    df = bars_df.copy()

    # Directional
    df = price_slope(df)
    df = ema_features(df)
    df = bar_structure(df)
    df = consecutive_bars(df)
    df = breakout_features(df)
    df = atr(df)

    # Microstructure
    df = microstructure_features(df)

    # VWAP
    df = vwap_features(df)

    # Volume
    df = volume_ratio(df)
    df = up_down_ratio(df)
    df = volume_spike(df)
    df = cumulative_delta(df)
    df = volume_trend(df)
    df = high_volume_bar(df)
    df = volume_percentile(df)

    # Fractal / Market Structure
    df = fractal_features(df)

    # Volatility
    df = volatility_features(df)

    # Time / Session
    df = time_features(df, open_time)

    # Regime
    if macro_path is not None:
        macro = load_regime(macro_path)
        df = regime_features(df, macro)

    return df.reset_index(drop=True)


FEATURE_COLS = [
    # Directional
    "slope_5", "slope_20", "slope_60",
    "ema_cross_5_20", "price_vs_ema_20", "price_vs_ema_60",
    "bar_body_ratio", "high_low_position", "range_expansion_10",
    "consec_up", "consec_down",
    "close_vs_prev_high", "close_vs_prev_low",
    "atr_14",
    # Fractal / Market Structure
    "range_position_20", "range_position_60",
    "slope_120", "slope_240",
    "dist_to_swing_high", "dist_to_swing_low",
    "bars_since_swing_high", "bars_since_swing_low",
    "range_compression",
    # Microstructure
    "ofi", "buy_absorption", "sell_absorption",
    "aggressor_ratio_5", "price_efficiency_5", "effort_vs_result", "tick_imbalance_10",
    # VWAP
    "vwap_distance",
    # Volume
    "volume_ratio_5_20", "up_down_ratio_10", "volume_spike_20",
    "delta_10", "delta_20",
    "volume_trend_10", "high_volume_bar_60", "volume_percentile_60",
    # Volatility
    "realized_vol_10", "realized_vol_30", "vol_ratio_short_long",
    "atr_ratio_10_50", "vol_percentile_60", "vol_of_vol_20",
    # Time / Session
    "minutes_since_open", "is_first_last_30min", "day_of_week", "time_of_day_seconds",
    # Regime
    "regime_late_expansion", "regime_mid_expansion", "regime_early_contraction",
    "regime_early_expansion", "regime_late_contraction",
]
