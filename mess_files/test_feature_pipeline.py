# -----------------------------------------------------------------
# Redis1 ---> Feat Eng ---> Redis2
# recollects data from Redis1, process when LEN > threshold, push to Redis2
# Feat Eng :
# Raw Data → Technical Indicators → Feature Engineering → Transformations
#    ↓            ↓                    ↓
#  Load     ATR (14), Returns     Parkinson (5,15,30)
#            Volume (Up+Down)     OFI (5,15,30)
#                                 Volume Percentile (60)
#                                 Volume Momentum (5)
#                                 Amihud (1)
#                                 VWAP Distance
#                                 Time Features
# -----------------------------------------------------------------

import numpy as np
import pandas as pd
import talib as ta
import joblib
import redis
from datetime import datetime, time
from sklearn.preprocessing import RobustScaler
from collections import deque
import json


# =========================
# Redis Configuration
# =========================
REDIS1_HOST = "127.0.0.1"
REDIS1_PORT = 6381
REDIS1_STREAM = "bars_raw"

REDIS2_HOST = "127.0.0.1"
REDIS2_PORT = 6380
REDIS2_STREAM = "bars_features"

# Initialize Redis connections
redis1 = redis.Redis(host=REDIS1_HOST, port=REDIS1_PORT, decode_responses=True)
redis2 = redis.Redis(host=REDIS2_HOST, port=REDIS2_PORT, decode_responses=True)

# =========================
# Feature Engineering Functions
# =========================


def parkinson_volatility(df: pd.DataFrame, window: int) -> pd.Series:
    """Parkinson volatility using High/Low ratio"""
    hl = np.log(df["High"] / df["Low"])
    sigma2 = (hl**2).rolling(window).mean() / (4 * np.log(2))
    return np.sqrt(sigma2)


def order_flow_imbalance(df: pd.DataFrame, window: int) -> pd.Series:
    """Order Flow Imbalance (Up - Down) rolling sum"""
    net_of = df["Up"] - df["Down"]
    return net_of.rolling(window).sum()


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    """Rolling percentile of last value in window"""

    def last_rank_pct(x: pd.Series) -> float:
        if len(x) <= 1:
            return np.nan
        rank = x.rank().iloc[-1]
        return (rank - 1) / (len(x) - 1)

    return series.rolling(window).apply(last_rank_pct, raw=False)


def get_minutes_since_open(
    dt_index: pd.DatetimeIndex, open_time: str = "09:30"
) -> pd.Series:
    """Minutes elapsed since market open (9:30 AM)"""
    open_t = pd.to_datetime(open_time).time()
    mins = []
    for ts in dt_index:
        if hasattr(ts, "date"):
            session_open = pd.Timestamp.combine(ts.date(), open_t)
            delta_min = (ts - session_open).total_seconds() / 60.0
            mins.append(max(delta_min, 0.0))
        else:
            mins.append(np.nan)
    return pd.Series(mins, index=dt_index)


def get_session_flag(
    dt_index: pd.DatetimeIndex, first_last: int = 30, open_time: str = "09:30"
) -> pd.Series:
    """Flag for first/last 30 minutes of trading session"""
    mins = get_minutes_since_open(dt_index, open_time=open_time)
    first_mask = (mins > 0) & (mins < (first_last + 1))
    last_mask = (mins > 359) & (mins < 390)
    result = (first_mask | last_mask).astype(int)
    return result.fillna(0)


def engineer_features(df: pd.DataFrame, window_sizes=(5, 15, 30)) -> pd.DataFrame:
    """Engineer all features for a DataFrame"""
    features = {}

    # Parkinson Volatility
    for w in window_sizes:
        features[f"parkinson_vol_{w}"] = parkinson_volatility(df, w)

    # Order Flow Imbalance
    for w in window_sizes:
        features[f"ofi_{w}"] = order_flow_imbalance(df, w)

    # Volume features
    features["volume_percentile"] = rolling_percentile(df["Volume"], 60)
    features["volume_momentum"] = df["Volume"].pct_change(5)

    # Liquidity & Price features
    vol_safe = df["Volume"].replace(0, np.nan)
    features["amihud_illiquidity"] = np.abs(df["Returns"]) / vol_safe
    features["vwap_distance"] = (df["Close"] - df["VWAP"]) / df["ATR"]

    # Time features
    if isinstance(df.index, pd.DatetimeIndex):
        features["minutes_since_open"] = get_minutes_since_open(df.index)
        features["is_first_last_30min"] = get_session_flag(df.index, first_last=30)
    else:
        features["minutes_since_open"] = pd.Series(np.nan, index=df.index)
        features["is_first_last_30min"] = pd.Series(0, index=df.index)

    return pd.DataFrame(features, index=df.index)


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add required technical indicators (ATR, Returns, Volume)"""
    df = df.copy()

    # Ensure we have Volume
    if "Volume" not in df.columns:
        if "Up" in df.columns and "Down" in df.columns:
            df["Volume"] = df["Up"] + df["Down"]
        else:
            raise ValueError("Need either Volume column or Up/Down columns")

    # Add Returns
    df["Returns"] = np.log(df["Close"]).diff()

    # Add ATR
    if len(df) >= 14 and all(col in df.columns for col in ["High", "Low", "Close"]):
        high = df["High"].values.astype(float)
        low = df["Low"].values.astype(float)
        close = df["Close"].values.astype(float)
        df["ATR"] = ta.ATR(high, low, close, timeperiod=14)
    else:
        df["ATR"] = np.nan

    return df


def load_transform_bundle(bundle_path: str = "feature_transform_bundle.joblib") -> dict:
    """Load the pre-trained transformation bundle"""
    try:
        bundle = joblib.load(bundle_path)
        print(f"✅ Loaded transformation bundle from {bundle_path}")
        return bundle
    except Exception as e:
        print(f"❌ Error loading transformation bundle: {e}")
        raise


def apply_feature_transform(features_df: pd.DataFrame, bundle: dict) -> pd.DataFrame:
    """Apply transformations using pre-trained bundle"""
    df = features_df.copy()

    # Apply log1p transformation
    for c in bundle.get("log_cols", []):
        if c in df.columns:
            df[c] = np.log1p(df[c].clip(lower=0))

    # Apply clipping
    for c, (lo, hi) in bundle.get("clip_bounds", {}).items():
        if c in df.columns:
            df[c] = df[c].clip(lower=lo, upper=hi)

    # Scale minutes since open
    if "minutes_since_open" in df.columns and bundle.get("max_minutes"):
        mm = bundle["max_minutes"]
        if mm and mm > 0:
            if df["minutes_since_open"].max() > mm:
                df["minutes_since_open"] = df["minutes_since_open"] / mm
            df["minutes_since_open"] = df["minutes_since_open"].clip(0, 1)

    # Scale continuous features
    scaler = bundle.get("scaler")
    cont_cols = bundle.get("cont_cols", [])
    binary_cols = set(bundle.get("binary_cols", []))

    if scaler and cont_cols:
        available_cont_cols = [c for c in cont_cols if c in df.columns]

        if available_cont_cols:
            scaled_data = df[available_cont_cols].copy()

            for col in available_cont_cols:
                if scaled_data[col].isna().any():
                    if not scaled_data[col].isna().all():
                        scaled_data[col] = scaled_data[col].fillna(
                            scaled_data[col].median()
                        )
                    else:
                        scaled_data[col] = scaled_data[col].fillna(0)

            expected_features = (
                scaler.n_features_in_
                if hasattr(scaler, "n_features_in_")
                else len(available_cont_cols)
            )

            if len(available_cont_cols) != expected_features:
                aligned_data = pd.DataFrame(
                    0, index=scaled_data.index, columns=cont_cols[:expected_features]
                )
                for col in available_cont_cols:
                    if col in aligned_data.columns:
                        aligned_data[col] = scaled_data[col]
                scaled = scaler.transform(aligned_data)
                out = pd.DataFrame(
                    scaled, columns=cont_cols[:expected_features], index=df.index
                )
            else:
                scaled = scaler.transform(scaled_data)
                out = pd.DataFrame(scaled, columns=available_cont_cols, index=df.index)

            # Add binary columns
            for c in bundle.get("feature_cols", []):
                if c in binary_cols and c in df.columns:
                    out[c] = df[c]

            # Add remaining non-continuous columns
            for c in bundle.get("feature_cols", []):
                if c not in out.columns and c in df.columns and c not in cont_cols:
                    out[c] = df[c]

            existing_cols = [
                c for c in bundle.get("feature_cols", []) if c in out.columns
            ]
            out = out[existing_cols]
            return out

    return df


# =========================
# MODIFIED: Fixed Array Feature Engineer
# =========================


class FixedArrayFeatureEngineer:
    def __init__(
        self, array_size: int = 70, bundle_path: str = "feature_transform_bundle.joblib"
    ):
        """
        Initialize with fixed-size array

        Args:
            array_size: Fixed size of the data array (default: 70)
            bundle_path: Path to transformation bundle
        """
        self.bundle = load_transform_bundle(bundle_path)
        self.array_size = array_size
        self.data_array = []  # Will store raw data dictionaries
        self.processed_count = 0
        self.is_ready = False

        print("=" * 50)
        print(f"🚀 FixedArrayFeatureEngineer Initialized")
        print(f"   Array size: {array_size}")
        print("=" * 50)
        print("Processing Logic:")
        print(f"  • Data will be appended to array of size {array_size}")
        print(f"  • Processing starts ONLY when array is full")
        print(f"  • After processing, oldest item is removed, new added (FIFO)")
        print("=" * 50)

    def add_bar(self, bar_data: dict) -> bool:
        """
        Add bar to array and process if array is full

        Args:
            bar_data: Dictionary with bar data from Redis1

        Returns:
            bool: True if processing occurred, False otherwise
        """
        # Add bar to array
        self.data_array.append(bar_data)

        # Check if array is full
        if len(self.data_array) < self.array_size:
            # Array not full yet
            if len(self.data_array) % 10 == 0 or len(self.data_array) < 10:
                print(f"⏳ Array: {len(self.data_array)}/{self.array_size} items...")
            return False

        # Array is full - process data
        self.processed_count += 1
        print(f"✅ Array full ({self.array_size} items), processing...")

        return True

    def process_array(self) -> dict:
        """
        Process the current array and return features for the latest bar

        Returns:
            Dictionary with features for the latest bar
        """
        if len(self.data_array) < self.array_size:
            print(f"⚠️  Array not full yet: {len(self.data_array)}/{self.array_size}")
            return None

        # Convert array to DataFrame
        df = self._array_to_dataframe()

        # Add technical indicators
        df = add_technical_indicators(df)

        # Engineer features
        features_df = engineer_features(df)

        # Get only the most recent row (latest bar)
        latest_features = features_df.iloc[[-1]].copy()

        # Check for NaN values
        nan_features = latest_features.columns[latest_features.isna().any()].tolist()
        if nan_features:
            print(f"⚠️  Warning: NaN in features {nan_features}")

        # Apply transformations
        transformed_features = apply_feature_transform(latest_features, self.bundle)

        if not transformed_features.empty:
            features_dict = transformed_features.iloc[0].to_dict()

            # Add metadata from the latest bar
            latest_bar = self.data_array[-1]
            features_dict["timestamp"] = latest_bar.get(
                "timestamp", datetime.now().isoformat()
            )
            features_dict["symbol"] = latest_bar.get("symbol", "UNKNOWN")
            features_dict["msg_id"] = latest_bar.get("msg_id", "")
            features_dict["array_size"] = len(self.data_array)
            features_dict["processed_count"] = self.processed_count

            # Maintain array size by removing oldest item
            self.data_array.pop(0)

            return features_dict

        return None

    def _array_to_dataframe(self) -> pd.DataFrame:
        """Convert data array to pandas DataFrame"""
        # Create DataFrame from array
        df = pd.DataFrame(self.data_array)

        # Ensure proper datetime index
        if "Datetime" in df.columns:
            df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
            df = df.set_index("Datetime").sort_index()
        elif "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.set_index("timestamp").sort_index()

        # Ensure numeric columns
        numeric_cols = ["Open", "High", "Low", "Close", "Up", "Down", "Volume", "VWAP"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df


def push_to_redis2(features_dict: dict):
    """Push features to Redis2 stream"""
    try:
        # Convert numpy types to Python native types
        features_serializable = {}
        for key, value in features_dict.items():
            if isinstance(value, (np.integer, np.floating)):
                features_serializable[key] = float(value)
            elif isinstance(value, np.ndarray):
                features_serializable[key] = value.tolist()
            elif pd.isna(value):
                features_serializable[key] = None
            else:
                features_serializable[key] = value

        # Push to Redis2
        msg_id = redis2.xadd(REDIS2_STREAM, features_serializable, maxlen=1000)
        print(
            f"✅ [{datetime.now().strftime('%H:%M:%S')}] Pushed to Redis2 (ID: {msg_id[:10]}...)"
        )
        return msg_id
    except Exception as e:
        print(f"❌ Error pushing to Redis2: {e}")
        return None


def parse_redis_message(fields: dict) -> dict:
    """Parse Redis stream message to standardized bar data"""
    bar_data = {}

    # Map Redis fields to our expected columns
    field_mapping = {
        "t": "timestamp",
        "T": "symbol",
        "o": "Open",
        "h": "High",
        "l": "Low",
        "c": "Close",
        "v": "Volume",
        "u": "Up",
        "d": "Down",
        "vw": "VWAP",
        "dt": "Datetime",
    }

    for redis_key, value in fields.items():
        if redis_key in field_mapping:
            bar_data[field_mapping[redis_key]] = value
        else:
            bar_data[redis_key] = value

    # Ensure we have essential fields
    essential_fields = ["Open", "High", "Low", "Close", "Up", "Down"]
    for field in essential_fields:
        if field not in bar_data:
            print(f"⚠️  Warning: Missing {field} in Redis message")

    return bar_data


# =========================
# Main Processing Loop
# =========================


def main():
    """Main processing loop with fixed array size"""
    print("=" * 60)
    print("🚀 Starting FIXED ARRAY Feature Engineering Pipeline")
    print(f"📥 Reading from: {REDIS1_HOST}:{REDIS1_PORT} -> {REDIS1_STREAM}")
    print(f"📤 Writing to:   {REDIS2_HOST}:{REDIS2_PORT} -> {REDIS2_STREAM}")
    print("=" * 60)

    # Initialize feature engineer with fixed array
    try:
        feature_engineer = FixedArrayFeatureEngineer(
            array_size=70,  # Fixed array size
            bundle_path="feature_transform_bundle.joblib",
        )
    except Exception as e:
        print(f"❌ Failed to initialize FeatureEngineer: {e}")
        return

    # Declare redis1 and redis2 as None initially, will initialize in try block
    redis1 = None
    redis2 = None

    def init_redis_connections():
        """Initialize or reinitialize Redis connections"""
        nonlocal redis1, redis2
        redis1 = redis.Redis(host=REDIS1_HOST, port=REDIS1_PORT, decode_responses=True)
        redis2 = redis.Redis(host=REDIS2_HOST, port=REDIS2_PORT, decode_responses=True)
        # Test connections
        redis1.ping()
        redis2.ping()
        print("✅ Redis connections initialized")
        return redis1, redis2

    # Initialize connections
    try:
        redis1, redis2 = init_redis_connections()
    except Exception as e:
        print(f"❌ Failed to initialize Redis connections: {e}")
        print("Make sure Redis servers are running on ports 6381 and 6380")
        return

    last_id = "$"  # Start from new data

    while True:
        try:
            # Read from Redis1 stream
            resp = redis1.xread({REDIS1_STREAM: last_id}, block=0, count=1)

            for stream, messages in resp:
                for msg_id, fields in messages:
                    last_id = msg_id

                    # Parse the message
                    bar_data = parse_redis_message(fields)
                    bar_data["msg_id"] = msg_id

                    # Add timestamp if not present
                    if "timestamp" not in bar_data:
                        bar_data["timestamp"] = datetime.now().isoformat()

                    # Add bar to array
                    should_process = feature_engineer.add_bar(bar_data)

                    if should_process:
                        # Array is full, process it
                        print(
                            f"🔧 Processing batch #{feature_engineer.processed_count}"
                        )
                        print(f"   Symbol: {bar_data.get('symbol', 'UNKNOWN')}")
                        print(f"   Time: {bar_data.get('timestamp', '')}")

                        # Get features for the latest bar
                        features = feature_engineer.process_array()

                        if features is not None:
                            # Remove metadata for cleaner output
                            feature_summary = {
                                k: v
                                for k, v in features.items()
                                if k
                                not in [
                                    "timestamp",
                                    "symbol",
                                    "msg_id",
                                    "array_size",
                                    "processed_count",
                                ]
                            }
                            print(f"   Features generated: {len(feature_summary)}")

                            # Push to Redis2
                            push_to_redis2(features, redis2)  # Pass redis2 as parameter
                        else:
                            print("   No features generated")

                        print(
                            f"   Array size maintained: {len(feature_engineer.data_array)}"
                        )

        except KeyboardInterrupt:
            print("\n👋 Shutting down feature engineering pipeline...")
            print(f"Total batches processed: {feature_engineer.processed_count}")
            print(f"Current array size: {len(feature_engineer.data_array)}")
            break
        except redis.exceptions.ConnectionError as e:
            print(f"❌ Redis connection error: {e}")
            print("Reconnecting in 5 seconds...")
            import time

            time.sleep(5)
            try:
                redis1, redis2 = init_redis_connections()
            except Exception as reconnect_error:
                print(f"❌ Reconnection failed: {reconnect_error}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback

            traceback.print_exc()


# Also update the push_to_redis2 function to accept redis2 as parameter:
def push_to_redis2(features_dict: dict, redis_conn=None):
    """Push features to Redis2 stream"""
    if redis_conn is None:
        # Fallback to global redis2 if not provided
        redis_conn = redis2

    try:
        # Convert numpy types to Python native types
        features_serializable = {}
        for key, value in features_dict.items():
            if isinstance(value, (np.integer, np.floating)):
                features_serializable[key] = float(value)
            elif isinstance(value, np.ndarray):
                features_serializable[key] = value.tolist()
            elif pd.isna(value):
                features_serializable[key] = None
            else:
                features_serializable[key] = value

        # Push to Redis2
        msg_id = redis_conn.xadd(REDIS2_STREAM, features_serializable, maxlen=1000)
        print(
            f"✅ [{datetime.now().strftime('%H:%M:%S')}] Pushed to Redis2 (ID: {msg_id[:10]}...)"
        )
        return msg_id
    except Exception as e:
        print(f"❌ Error pushing to Redis2: {e}")
        return None


if __name__ == "__main__":
    main()
