# -----------------------------------------------------------------
# Redis1 ---> Feat Eng ---> Redis2
# Reads Redis1 bars_raw, computes features, writes bars_features.
# Uses Up/Down/VWAP from payload; keeps functions pure.
# -----------------------------------------------------------------

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import redis
import talib as ta


# =========================
# Redis Configuration
# =========================
REDIS1_HOST = "127.0.0.1"
REDIS1_PORT = 6381
REDIS1_STREAM = "bars_raw"

REDIS2_HOST = "127.0.0.1"
REDIS2_PORT = 6380
REDIS2_STREAM = "bars_features"


# =========================
# Bundle / Columns helpers
# =========================
def load_transform_bundle(bundle_path: str) -> dict:
    """Load transform bundle dict; expects file path."""
    bundle = joblib.load(bundle_path)
    print(f"✅ Loaded transformation bundle from {bundle_path}")
    return bundle


def ensure_columns(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    """Ensure columns exist; expects df and col names."""
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    return out


def to_numeric_columns(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    """Coerce numeric columns; expects df and numeric names."""
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


# =========================
# Time feature helpers
# =========================
def parse_ts_date(d: int) -> Tuple[int, int, int]:
    """Convert TS YYMMDD or YYYYMMDD to safe date."""
    d = int(d)
    if d < 10_000_00:  # YYMMDD
        s = f"{d:06d}"
        yy = int(s[:2])
        mm = int(s[2:4])
        dd = int(s[4:6])
        yyyy = 2000 + yy
    else:  # YYYYMMDD
        yyyy = d // 10000
        mm = (d // 100) % 100
        dd = d % 100
    return yyyy, mm, dd


def build_datetime_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    """Build datetime index from TS date and bar_seconds."""
    if "yyyymmdd" not in df.columns or len(df) == 0:
        return pd.DatetimeIndex([pd.NaT] * len(df))

    yyyy, mm, dd = parse_ts_date(int(df["yyyymmdd"].iloc[-1]))

    # Defensive: pandas-safe bounds
    if not (1900 <= yyyy <= 2200):
        return pd.DatetimeIndex([pd.NaT] * len(df))

    base = pd.Timestamp(year=yyyy, month=mm, day=dd)

    bar_secs = int(df["bar_seconds"].iloc[-1]) if "bar_seconds" in df.columns else 5
    bar_secs = max(bar_secs, 1)

    return pd.DatetimeIndex(
        [base + pd.Timedelta(seconds=i * bar_secs) for i in range(len(df))]
    )


def minutes_since_open(
    dt_index: pd.DatetimeIndex, open_time: str = "09:30"
) -> pd.Series:
    """Minutes since open; expects datetime index."""
    if not isinstance(dt_index, pd.DatetimeIndex) or len(dt_index) == 0:
        return pd.Series([], dtype=float)

    if dt_index.isna().all():
        return pd.Series(np.nan, index=dt_index)

    open_t = pd.to_datetime(open_time).time()
    session_open = pd.to_datetime(
        [pd.Timestamp.combine(ts.date(), open_t) for ts in dt_index]
    )
    mins = (dt_index - session_open).total_seconds() / 60.0
    mins = np.maximum(mins, 0.0)
    return pd.Series(mins, index=dt_index)


def first_last_30min_flag(mins_since_open: pd.Series) -> pd.Series:
    """Flag first/last 30 minutes; expects minutes series."""
    arr = pd.to_numeric(mins_since_open, errors="coerce").to_numpy()

    first = (arr > 0) & (arr <= 30)
    last = (arr >= 360) & (arr < 390)

    out = (first | last).astype(int)
    out = np.where(np.isnan(arr), 0, out)

    return pd.Series(out, index=mins_since_open.index)


# =========================
# Core feature math (pure)
# =========================
def parkinson_volatility(df: pd.DataFrame, window: int) -> pd.Series:
    """Parkinson volatility from High/Low; expects High Low."""
    hl = np.log(df["High"] / df["Low"])
    sigma2 = (hl**2).rolling(window).mean() / (4 * np.log(2))
    return np.sqrt(sigma2)


def order_flow_imbalance(df: pd.DataFrame, window: int) -> pd.Series:
    """Rolling OFI from Up/Down; expects Up Down."""
    net_of = df["Up"] - df["Down"]
    return net_of.rolling(window).sum()


def rolling_last_percentile(series: pd.Series, window: int) -> pd.Series:
    """Rolling percentile of last value; expects numeric series."""

    # No nested functions: do via rank on each window using apply with numpy.
    def _pct(arr: np.ndarray) -> float:
        if arr.size <= 1:
            return np.nan
        last = arr[-1]
        # rank position among values (ties handled by <=)
        rank = np.sum(arr <= last)
        return (rank - 1) / (arr.size - 1)

    return series.rolling(window).apply(lambda x: _pct(x.to_numpy()), raw=False)


def add_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Add log returns column; expects Close column."""
    out = df.copy()
    out["Returns"] = np.log(out["Close"]).diff()
    return out


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ATR column; expects High Low Close."""
    out = df.copy()
    if len(out) >= period and all(c in out.columns for c in ["High", "Low", "Close"]):
        high = out["High"].to_numpy(dtype=float)
        low = out["Low"].to_numpy(dtype=float)
        close = out["Close"].to_numpy(dtype=float)
        out["ATR"] = ta.ATR(high, low, close, timeperiod=period)
    else:
        out["ATR"] = np.nan
    return out


def add_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure Volume column exists; expects Volume or Up/Down."""
    out = df.copy()
    if "Volume" in out.columns and out["Volume"].notna().any():
        return out
    if "Up" in out.columns and "Down" in out.columns:
        out["Volume"] = out["Up"].fillna(0) + out["Down"].fillna(0)
        return out
    raise ValueError("Need Volume or Up/Down to derive.")


def amihud_illiquidity(df: pd.DataFrame) -> pd.Series:
    """Compute Amihud illiquidity; expects Returns Volume."""
    vol_safe = df["Volume"].replace(0, np.nan)
    return np.abs(df["Returns"]) / vol_safe


def vwap_distance(df: pd.DataFrame) -> pd.Series:
    """Compute VWAP distance; expects Close VWAP ATR."""
    return (df["Close"] - df["VWAP"]) / df["ATR"]


def engineer_features(
    df: pd.DataFrame, windows: Tuple[int, ...] = (5, 15, 30)
) -> pd.DataFrame:
    """Compute feature table; expects required OHLCV+UpDownVWAP."""
    feats: Dict[str, pd.Series] = {}

    for w in windows:
        feats[f"parkinson_vol_{w}"] = parkinson_volatility(df, w)

    for w in windows:
        feats[f"ofi_{w}"] = order_flow_imbalance(df, w)

    feats["volume_percentile"] = rolling_last_percentile(df["Volume"], 60)
    feats["volume_momentum"] = df["Volume"].pct_change(5)
    feats["amihud_illiquidity"] = amihud_illiquidity(df)
    feats["vwap_distance"] = vwap_distance(df)

    dt_index = build_datetime_index(df)
    mins_raw = minutes_since_open(dt_index)

    # force mins onto df.index (prevents duplicate-datetime alignment issues)
    mins = pd.Series(mins_raw.to_numpy(), index=df.index)

    # flag uses numpy internally (no reindex)
    flag = first_last_30min_flag(mins)

    feats["minutes_since_open"] = mins
    feats["is_first_last_30min"] = flag

    return pd.DataFrame(feats, index=df.index)


# =========================
# Transform pipeline (pure)
# =========================
def apply_log1p(df: pd.DataFrame, log_cols: List[str]) -> pd.DataFrame:
    """Apply log1p to columns; expects nonnegative numeric."""
    out = df.copy()
    for c in log_cols:
        if c in out.columns:
            out[c] = np.log1p(out[c].clip(lower=0))
    return out


def apply_clip_bounds(
    df: pd.DataFrame, clip_bounds: Dict[str, Tuple[float, float]]
) -> pd.DataFrame:
    """Clip columns to bounds; expects numeric features."""
    out = df.copy()
    for c, (lo, hi) in clip_bounds.items():
        if c in out.columns:
            out[c] = out[c].clip(lower=lo, upper=hi)
    return out


def normalize_minutes_since_open(
    df: pd.DataFrame, max_minutes: Optional[float]
) -> pd.DataFrame:
    """Normalize minutes column; expects minutes_since_open present."""
    out = df.copy()
    if "minutes_since_open" not in out.columns:
        return out
    if not max_minutes or max_minutes <= 0:
        return out

    # If values look like raw minutes, scale to [0,1].
    if pd.notna(out["minutes_since_open"]).any():
        if out["minutes_since_open"].max() > 1.5:
            out["minutes_since_open"] = out["minutes_since_open"] / max_minutes
    out["minutes_since_open"] = out["minutes_since_open"].clip(0, 1)
    return out


def fill_missing_for_scaler(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Fill missing for scaler; expects df and cols."""
    out = df.copy()
    out = ensure_columns(out, cols)
    for c in cols:
        if out[c].isna().any():
            if out[c].isna().all():
                out[c] = 0.0
            else:
                out[c] = out[c].fillna(out[c].median())
    return out


def align_columns_for_scaler(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Align scaler input columns; expects scaler fitted columns."""
    out = ensure_columns(df, cols)
    return out[cols]


def scale_continuous(
    df: pd.DataFrame, scaler: Any, cont_cols: List[str]
) -> pd.DataFrame:
    """Scale continuous columns; expects fitted scaler and cols."""
    if scaler is None or not cont_cols:
        return df.copy()

    data = align_columns_for_scaler(df, cont_cols)
    data = fill_missing_for_scaler(data, cont_cols)

    scaled = scaler.transform(data)
    return pd.DataFrame(scaled, columns=cont_cols, index=df.index)


def assemble_final_features(
    scaled_cont: pd.DataFrame,
    original: pd.DataFrame,
    feature_cols: List[str],
    binary_cols: List[str],
) -> pd.DataFrame:
    """Assemble final features; expects feature_cols ordering."""
    out = scaled_cont.copy()
    binary_set = set(binary_cols or [])

    for c in feature_cols:
        if c in binary_set and c in original.columns and c not in out.columns:
            out[c] = original[c]

    for c in feature_cols:
        if c in original.columns and c not in out.columns:
            out[c] = original[c]

    existing = [c for c in feature_cols if c in out.columns]
    return out[existing]


def apply_feature_transform(features_df: pd.DataFrame, bundle: dict) -> pd.DataFrame:
    """Transform features using bundle; expects bundle dict."""
    df1 = features_df.copy()

    df2 = apply_log1p(df1, bundle.get("log_cols", []))
    df3 = apply_clip_bounds(df2, bundle.get("clip_bounds", {}))
    df4 = normalize_minutes_since_open(df3, bundle.get("max_minutes"))

    scaler = bundle.get("scaler")
    cont_cols = bundle.get("cont_cols", [])
    feature_cols = bundle.get("feature_cols", [])
    binary_cols = bundle.get("binary_cols", [])

    scaled_cont = scale_continuous(df4, scaler, cont_cols)
    final_df = assemble_final_features(scaled_cont, df4, feature_cols, binary_cols)
    return final_df


# =========================
# Redis parsing / IO (pure)
# =========================
def is_structured_bar(fields: Any) -> bool:
    """Check structured dict bar; expects redis fields object."""
    return isinstance(fields, dict) and "open" in fields and "close" in fields


def normalize_symbol(sym: str) -> str:
    """Normalize symbol string; expects raw sym string."""
    s = str(sym or "UNKNOWN")
    return s[1:] if s.startswith("@") else s


def parse_structured_bar(
    fields: Dict[str, Any], msg_id: str
) -> Optional[Dict[str, Any]]:
    """Parse structured redis dict; expects bar keys present."""
    try:
        sym = normalize_symbol(fields.get("symbol", "UNKNOWN"))
        bar_secs = int(fields.get("time", 0))
        yyyymmdd = int(fields.get("date"))
        ts = datetime.now().isoformat()

        up = int(fields.get("up", 0))
        down = int(fields.get("down", 0))

        vol_raw = fields.get("volume", None)
        volume = float(vol_raw) if vol_raw is not None else float(up + down)

        return {
            "timestamp": ts,
            "Datetime": ts,
            "symbol": sym,
            "yyyymmdd": yyyymmdd,
            "bar_seconds": bar_secs,
            "Open": float(fields.get("open")),
            "High": float(fields.get("high")),
            "Low": float(fields.get("low")),
            "Close": float(fields.get("close")),
            "Up": up,
            "Down": down,
            "VWAP": float(fields.get("vwap")),
            "Volume": volume,
            "bar_num": int(fields.get("bar_num")),
            "msg_id": msg_id,
        }
    except Exception as e:
        print(f"⚠️  Skipping malformed dict message: {fields!r} err={e}")
        return None


def extract_raw_line(fields: Any) -> Optional[str]:
    """Extract raw line from fields; expects dict or str."""
    if isinstance(fields, dict):
        if len(fields) == 1:
            return str(next(iter(fields.values())))
        return str(fields.get("line") or fields.get("data") or "")
    return str(fields)


def parse_line_bar(raw_line: str, msg_id: str) -> Optional[Dict[str, Any]]:
    """Parse raw line format; expects '<ts> @CSV'."""
    line = str(raw_line).strip()
    if not line:
        return None

    parts = line.split()
    if len(parts) < 2:
        print(f"⚠️  Skipping malformed line: {line!r}")
        return None

    ts_str = parts[0]
    payload = parts[-1]
    if not payload.startswith("@"):
        print(f"⚠️  Skipping malformed payload: {line!r}")
        return None

    toks = payload[1:].split(",")

    # Old format: symbol,date,bar_secs,o,h,l,c,vol,bar_num
    if len(toks) == 9:
        symbol, yyyymmdd, bar_secs, o, h, l, c, vol, bar_num = toks
        sym = normalize_symbol(symbol)
        return {
            "timestamp": ts_str,
            "Datetime": ts_str,
            "symbol": sym,
            "yyyymmdd": int(yyyymmdd),
            "bar_seconds": int(bar_secs),
            "Open": float(o),
            "High": float(h),
            "Low": float(l),
            "Close": float(c),
            "Volume": float(vol),
            "msg_id": msg_id,
            "bar_num": int(bar_num),
        }

    # New format example: @ES,1260119,5,6901,6901,6901,6901,2,0,6913.294501,36
    # symbol,date,bar_secs,o,h,l,c,up,down,vwap,bar_num
    if len(toks) == 11:
        symbol, yyyymmdd, bar_secs, o, h, l, c, up, down, vwap, bar_num = toks
        sym = normalize_symbol(symbol)
        return {
            "timestamp": ts_str,
            "Datetime": ts_str,
            "symbol": sym,
            "yyyymmdd": int(yyyymmdd),
            "bar_seconds": int(bar_secs),
            "Open": float(o),
            "High": float(h),
            "Low": float(l),
            "Close": float(c),
            "Up": int(up),
            "Down": int(down),
            "VWAP": float(vwap),
            "Volume": float(int(up) + int(down)),
            "msg_id": msg_id,
            "bar_num": int(bar_num),
        }

    print(f"⚠️  Skipping malformed CSV fields={len(toks)} line={line!r}")
    return None


def parse_redis_message(fields: Any, msg_id: str) -> Optional[Dict[str, Any]]:
    """Parse redis message to bar dict; expects fields+id."""
    if is_structured_bar(fields):
        return parse_structured_bar(fields, msg_id)

    raw_line = extract_raw_line(fields)
    if raw_line is None:
        return None
    return parse_line_bar(raw_line, msg_id)


def make_redis_client(host: str, port: int) -> redis.Redis:
    """Create redis client; expects host and port."""
    return redis.Redis(host=host, port=port, decode_responses=True)


def xread_one(
    r: redis.Redis, stream: str, last_id: str
) -> List[Tuple[str, List[Tuple[str, Any]]]]:
    """Read one entry from stream; expects redis client."""
    return r.xread({stream: last_id}, block=0, count=1)


def serialize_for_redis(d: Dict[str, Any]) -> Dict[str, Any]:
    """Convert values for redis xadd; expects dict."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, (np.integer, np.floating)):
            out[k] = float(v)
        elif isinstance(v, np.ndarray):
            out[k] = v.tolist()
        elif v is None:
            out[k] = None
        elif isinstance(v, float) and np.isnan(v):
            out[k] = None
        else:
            out[k] = v
    return out


def xadd_features(
    r: redis.Redis, stream: str, features: Dict[str, Any], maxlen: int = 1000
) -> str:
    """Append features to stream; expects redis+stream+dict."""
    payload = serialize_for_redis(features)
    return r.xadd(stream, payload, maxlen=maxlen)


# =========================
# Feature Engineer (state)
# =========================
@dataclass
class FeatureEngineerState:
    """State for rolling computation; expects bundle, buffer."""

    bundle: dict
    buffer: deque
    processed_count: int = 0


def init_feature_engineer(
    bundle_path: str, buffer_maxlen: int = 100
) -> FeatureEngineerState:
    """Initialize engineer state; expects bundle path string."""
    bundle = load_transform_bundle(bundle_path)
    buf = deque(maxlen=buffer_maxlen)
    print("=" * 50)
    print("🚀 FeatureEngineer Initialized")
    print("=" * 50)
    print("  • volume_percentile needs 60 bars")
    print("  • ATR needs 14 bars")
    print("  • volume_momentum needs 5 bars")
    print("  • minutes_since_open must exist")
    print("  → Minimum for full features: 61 bars")
    print("=" * 50)
    return FeatureEngineerState(bundle=bundle, buffer=buf, processed_count=0)


def append_bar(
    state: FeatureEngineerState, bar: Dict[str, Any]
) -> FeatureEngineerState:
    """Append bar into buffer; expects state and bar."""
    state.buffer.append(bar)
    return state


def buffer_size(state: FeatureEngineerState) -> int:
    """Return buffer length; expects FeatureEngineerState."""
    return len(state.buffer)


def buffer_to_dataframe(state: FeatureEngineerState) -> pd.DataFrame:
    """Convert buffer to DataFrame; expects populated buffer."""
    df = pd.DataFrame(list(state.buffer))

    # Force a unique, stable index. Redis stream IDs are unique.
    if "msg_id" in df.columns:
        df = df.set_index("msg_id", drop=False)
    elif "bar_num" in df.columns:
        df = df.set_index("bar_num", drop=False)
    else:
        # worst-case fallback: monotonic index
        df = df.reset_index(drop=True)

    df = ensure_columns(
        df,
        [
            "Open",
            "High",
            "Low",
            "Close",
            "Up",
            "Down",
            "VWAP",
            "Volume",
            "yyyymmdd",
            "bar_seconds",
        ],
    )

    df = to_numeric_columns(
        df,
        [
            "Open",
            "High",
            "Low",
            "Close",
            "Up",
            "Down",
            "VWAP",
            "Volume",
            "bar_seconds",
            "yyyymmdd",
        ],
    )

    return df


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add indicators to df; expects OHLC Up Down VWAP."""
    out = df.copy()
    out = add_volume(out)
    out = add_returns(out)
    out = add_atr(out, period=14)
    return out


def compute_latest_features(
    df: pd.DataFrame, state: FeatureEngineerState
) -> pd.DataFrame:
    """Compute latest-row features; expects enriched df."""
    feats = engineer_features(df)
    latest = feats.iloc[[-1]].copy()
    # Make sure minutes_since_open exists even if NaN.
    latest = ensure_columns(latest, ["minutes_since_open"])
    return latest


def add_feature_metadata(
    features: Dict[str, Any], bar: Dict[str, Any], state: FeatureEngineerState
) -> Dict[str, Any]:
    """Attach metadata to features; expects features and bar."""
    out = dict(features)
    out["timestamp"] = bar.get("timestamp", datetime.now().isoformat())
    out["symbol"] = bar.get("symbol", "UNKNOWN")
    out["msg_id"] = bar.get("msg_id", "")
    out["buffer_size"] = buffer_size(state)
    out["processed_count"] = state.processed_count
    return out


def ingest_and_compute(
    state: FeatureEngineerState, bar: Dict[str, Any], min_bars: int = 61
) -> Optional[Dict[str, Any]]:
    """Ingest bar and maybe compute; expects bar dict."""
    append_bar(state, bar)
    n = buffer_size(state)

    if n < min_bars:
        if n % 10 == 0 or n < 10:
            print(f"⏳ Buffer: {n}/{min_bars} bars...")
        return None

    state.processed_count += 1

    df0 = buffer_to_dataframe(state)
    df1 = add_technical_indicators(df0)
    latest = compute_latest_features(df1, state)

    transformed = apply_feature_transform(latest, state.bundle)
    if transformed.empty:
        return None

    feat_dict = transformed.iloc[0].to_dict()
    return add_feature_metadata(feat_dict, bar, state)


# =========================
# Main loop
# =========================
def main() -> None:
    """Run redis pipeline loop; expects redis running."""
    r1 = make_redis_client(REDIS1_HOST, REDIS1_PORT)
    r2 = make_redis_client(REDIS2_HOST, REDIS2_PORT)

    print("=" * 60)
    print("🚀 Starting Feature Engineering Pipeline")
    print(f"📥 Reading from: {REDIS1_HOST}:{REDIS1_PORT} -> {REDIS1_STREAM}")
    print(f"📤 Writing to:   {REDIS2_HOST}:{REDIS2_PORT} -> {REDIS2_STREAM}")
    print("=" * 60)

    try:
        fe = init_feature_engineer("feature_transform_bundle.joblib", buffer_maxlen=100)
    except Exception as e:
        print(f"❌ Failed to initialize FeatureEngineer: {e}")
        return

    last_id = "$"

    while True:
        try:
            resp = xread_one(r1, REDIS1_STREAM, last_id)

            for _stream, messages in resp:
                for msg_id, fields in messages:
                    last_id = msg_id

                    bar = parse_redis_message(fields, msg_id)
                    if bar is None:
                        print(f"SKIP msg_id={msg_id} fields={fields!r}")
                        continue

                    features = ingest_and_compute(fe, bar, min_bars=61)
                    if features is None:
                        continue

                    # Remove metadata from “count” print only.
                    core = {
                        k: v
                        for k, v in features.items()
                        if k
                        not in [
                            "timestamp",
                            "symbol",
                            "msg_id",
                            "buffer_size",
                            "processed_count",
                        ]
                    }
                    print(
                        f"🔧 Processed bar #{fe.processed_count}: {bar.get('symbol','UNKNOWN')}  features={len(core)}"
                    )

                    xadd_features(r2, REDIS2_STREAM, features, maxlen=1000)

        except KeyboardInterrupt:
            print("\n👋 Shutting down feature engineering pipeline...")
            print(f"Total bars processed: {fe.processed_count}")
            break
        except redis.exceptions.ConnectionError as e:
            print(f"❌ Redis connection error: {e}")
            print("Reconnecting in 5 seconds...")
            import time as _time

            _time.sleep(5)
            r1 = make_redis_client(REDIS1_HOST, REDIS1_PORT)
            r2 = make_redis_client(REDIS2_HOST, REDIS2_PORT)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    main()
