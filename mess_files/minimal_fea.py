# redis_ingest_parse.py
# ------------------------------------------
# Standalone Redis ingest + parse utilities:
# - Connect to Redis
# - Read 1 message from a stream (XREAD count=1)
# - Parse message fields into a normalized "bar" dict
# - Engineer 12 features (pure functions)
# ------------------------------------------

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import redis


# =========================
# Redis connection / read
# =========================
def make_redis_client(host: str, port: int) -> redis.Redis:
    """Create redis client; expects host and port."""
    return redis.Redis(host=host, port=port, decode_responses=True)


def xread_one(
    r: redis.Redis, stream: str, last_id: str
) -> List[Tuple[str, List[Tuple[str, Any]]]]:
    """Read one entry from stream; expects redis client."""
    return r.xread({stream: last_id}, block=0, count=1)


# =========================
# Redis message parsing
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

    # New format: symbol,date,bar_secs,o,h,l,c,up,down,vwap,bar_num
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


# =========================
# Feature engineering (12 features, pure)
# =========================
def add_ma_close_5_10_15(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = pd.to_numeric(out["Close"], errors="coerce")
    out["ma_close_5"] = close.rolling(5).mean()
    out["ma_close_10"] = close.rolling(10).mean()
    out["ma_close_15"] = close.rolling(15).mean()
    return out


def add_vol_delta_5_10_15(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    up = pd.to_numeric(out["Up"], errors="coerce")
    down = pd.to_numeric(out["Down"], errors="coerce")
    delta = up - down
    out["vol_delta_5"] = delta.rolling(5).sum()
    out["vol_delta_10"] = delta.rolling(10).sum()
    out["vol_delta_15"] = delta.rolling(15).sum()
    return out


def add_vwap_dist_mean_5_10_15(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = pd.to_numeric(out["Close"], errors="coerce")
    vwap = pd.to_numeric(out["VWAP"], errors="coerce")
    dist = close - vwap
    out["vwap_dist_mean_5"] = dist.rolling(5).mean()
    out["vwap_dist_mean_10"] = dist.rolling(10).mean()
    out["vwap_dist_mean_15"] = dist.rolling(15).mean()
    return out


def _slope_from_window(arr: np.ndarray) -> float:
    if arr is None or arr.size == 0:
        return np.nan

    y = np.asarray(arr, dtype=float)
    if np.isnan(y).any():
        return np.nan

    n = y.size
    if n < 2:
        return np.nan

    x = np.arange(n, dtype=float)
    x_mean = (n - 1) / 2.0

    var_x = np.sum((x - x_mean) ** 2)
    if var_x == 0:
        return np.nan

    y_mean = np.mean(y)
    cov_xy = np.sum((x - x_mean) * (y - y_mean))
    return cov_xy / var_x


def add_slope_close_5_10_15(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = pd.to_numeric(out["Close"], errors="coerce")
    out["slope_close_5"] = close.rolling(5).apply(_slope_from_window, raw=True)
    out["slope_close_10"] = close.rolling(10).apply(_slope_from_window, raw=True)
    out["slope_close_15"] = close.rolling(15).apply(_slope_from_window, raw=True)
    return out


def engineer_12_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = add_ma_close_5_10_15(out)
    out = add_vol_delta_5_10_15(out)
    out = add_vwap_dist_mean_5_10_15(out)
    out = add_slope_close_5_10_15(out)
    return out


# =========================
# Runner: read -> parse -> buffer -> features
# =========================
def run_forever(host: str, port: int, stream: str) -> None:
    r = make_redis_client(host, port)
    last_id = "$"

    r2 = make_redis_client("127.0.0.1", 6380)
    out_stream = "bars_features"

    bars: List[Dict[str, Any]] = []

    print(f"Listening on {host}:{port} stream={stream}")

    while True:
        resp = xread_one(r, stream, last_id)

        for _stream, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id

                bar = parse_redis_message(fields, msg_id)
                if bar is None:
                    print(f"SKIP msg_id={msg_id}")
                    continue

                bars.append(bar)

                df = pd.DataFrame(bars)
                needed = ["Close", "VWAP", "Up", "Down"]
                ok = all(c in df.columns for c in needed)

                if not ok:
                    print(f"OK msg_id={msg_id} (parsed) — missing needed columns")
                    continue

                feats = engineer_12_features(df)

                latest_feats = feats.iloc[[-1]][
                    [
                        "ma_close_5",
                        "ma_close_10",
                        "ma_close_15",
                        "vol_delta_5",
                        "vol_delta_10",
                        "vol_delta_15",
                        "vwap_dist_mean_5",
                        "vwap_dist_mean_10",
                        "vwap_dist_mean_15",
                        "slope_close_5",
                        "slope_close_10",
                        "slope_close_15",
                    ]
                ]

                print(f"OK msg_id={msg_id}")
                print(latest_feats.to_string(index=False))
                # if any feature is NaN, don't write this bar yet
                # skip until all rolling features are available
                if pd.isna(latest_feats.iloc[0]).any():
                    continue

                # Create payload and send to Redis
                feat_payload = latest_feats.iloc[0].to_dict()
                # Add metadata
                feat_payload["symbol"] = bar["symbol"]
                feat_payload["timestamp"] = bar["timestamp"]
                feat_payload["msg_id"] = bar["msg_id"]

                xadd_features_to_redis2(r2, out_stream, feat_payload, maxlen=1000)


def xadd_features_to_redis2(
    r2: redis.Redis,
    stream: str,
    payload: Dict[str, Any],
    maxlen: int = 1000,
) -> str:
    out: Dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, (np.integer, np.floating)):
            out[k] = float(v)
        elif v is None:
            out[k] = None
        elif isinstance(v, float) and np.isnan(v):
            out[k] = None
        else:
            out[k] = v
    return r2.xadd(stream, out, maxlen=maxlen, approximate=True)


if __name__ == "__main__":
    run_forever("127.0.0.1", 6381, "bars_raw")
