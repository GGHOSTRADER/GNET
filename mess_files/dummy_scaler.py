# setup_dummy_bundle.py
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler
import os


def create_dummy_bundle():
    """Create a realistic dummy transformation bundle"""

    # Define features based on your feature engineering
    feature_cols = [
        "parkinson_vol_5",
        "parkinson_vol_15",
        "parkinson_vol_30",
        "ofi_5",
        "ofi_15",
        "ofi_30",
        "volume_percentile",
        "volume_momentum",
        "amihud_illiquidity",
        "vwap_distance",
        "minutes_since_open",
        "is_first_last_30min",
    ]

    cont_cols = [
        "parkinson_vol_5",
        "parkinson_vol_15",
        "parkinson_vol_30",
        "ofi_5",
        "ofi_15",
        "ofi_30",
        "volume_percentile",
        "volume_momentum",
        "amihud_illiquidity",
        "vwap_distance",
        "minutes_since_open",
    ]

    binary_cols = ["is_first_last_30min"]

    # Create realistic dummy data ranges based on feature definitions
    n_samples = 1000

    # Parkinson volatility: typically 0.01 to 0.5 (1% to 50% volatility)
    parkinson_range = np.random.uniform(0.01, 0.3, (n_samples, 3))

    # OFI: can be positive or negative, typically in thousands
    ofi_range = np.random.uniform(-50000, 50000, (n_samples, 3))

    # Volume percentile: 0 to 1
    vol_percentile = np.random.uniform(0, 1, n_samples)

    # Volume momentum: -1 to 5 (-100% to +500%)
    vol_momentum = np.random.uniform(-0.8, 3, n_samples)

    # Amihud illiquidity: typically very small values
    amihud = np.random.exponential(0.0001, n_samples)

    # VWAP distance: typically -3 to 3 standard deviations
    vwap_dist = np.random.uniform(-2.5, 2.5, n_samples)

    # Minutes since open: 0 to 390 (6.5 hours)
    minutes = np.random.uniform(0, 390, n_samples)

    # Combine all
    dummy_data = np.column_stack(
        [
            parkinson_range[:, 0],
            parkinson_range[:, 1],
            parkinson_range[:, 2],
            ofi_range[:, 0],
            ofi_range[:, 1],
            ofi_range[:, 2],
            vol_percentile,
            vol_momentum,
            amihud,
            vwap_dist,
            minutes,
        ]
    )

    dummy_df = pd.DataFrame(dummy_data, columns=cont_cols)

    # Create and fit scaler
    scaler = RobustScaler()
    scaler.fit(dummy_df)

    # Create bundle
    bundle = {
        "feature_cols": feature_cols,
        "cont_cols": cont_cols,
        "binary_cols": binary_cols,
        "log_cols": ["amihud_illiquidity", "vwap_distance"],
        "clip_bounds": {
            "parkinson_vol_5": (0.001, 0.5),
            "parkinson_vol_15": (0.001, 0.5),
            "parkinson_vol_30": (0.001, 0.5),
            "ofi_5": (-100000, 100000),
            "ofi_15": (-200000, 200000),
            "ofi_30": (-300000, 300000),
            "volume_percentile": (0, 1),
            "volume_momentum": (-0.95, 10),
            "vwap_distance": (-5, 5),
        },
        "max_minutes": 390,
        "scaler": scaler,
    }

    return bundle


if __name__ == "__main__":
    bundle = create_dummy_bundle()
    joblib.dump(bundle, "feature_transform_bundle.joblib")

    print("✅ Created realistic dummy transformation bundle")
    print(f"📁 Saved to: {os.path.abspath('feature_transform_bundle.joblib')}")
    print(f"📊 Features: {len(bundle['feature_cols'])}")
    print(f"📈 Continuous features: {len(bundle['cont_cols'])}")
    print(f"🔢 Binary features: {len(bundle['binary_cols'])}")
    print(f"✂️  Clip bounds for {len(bundle['clip_bounds'])} features")

    # Test it can be loaded
    loaded = joblib.load("feature_transform_bundle.joblib")
    print(f"\n✅ Bundle loaded successfully")
    print(f"   Scaler fitted on: {loaded['scaler'].n_features_in_} features")
