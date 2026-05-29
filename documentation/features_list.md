# Features Documentation
> **What:** Quick reference table of all engineered features — what each one measures and which file computes it.

All features are computed in `feat_files/transformer_features.py` from a 60-bar rolling window and published to the `features_transformer` Redis stream.

| Feature                 | Type  | Description                                                                        |
| ----------------------- | ----- | ---------------------------------------------------------------------------------- |
| parkinson_vol_{5,15,30} | float | Volatility estimated from High/Low range — more efficient than close-to-close vol  |
| ofi_{5,15,30}           | float | Order Flow Imbalance — net buy vs sell volume (Up - Down) over rolling window      |
| volume_percentile       | float | Where current volume ranks vs last 60 bars (0–1)                                   |
| volume_momentum         | float | Volume % change over last 5 bars                                                   |
| amihud_illiquidity      | float | Price impact per unit volume — high = illiquid, moves easily                       |
| vwap_distance           | float | How far price is from VWAP, normalized by ATR                                      |
| minutes_since_open      | float | Minutes elapsed since 09:30 open                                                   |
| is_first_last_30min     | int   | Binary flag — 1 if in first or last 30min of session                               |
| day_of_week             | int   | Day of week — Monday=0 … Friday=4. Derived from `bar.date` (YYYYMMDD)             |

**Total: 13 features** (3 parkinson + 3 ofi + 7 others)

## MLP Model Input

The inference model (`inference/inference_engine.py`) uses all 13 features above in this exact order:

```python
FEATURE_COLS = [
    "parkinson_vol_5", "parkinson_vol_15", "parkinson_vol_30",
    "ofi_5", "ofi_15", "ofi_30",
    "volume_percentile", "volume_momentum",
    "amihud_illiquidity", "vwap_distance",
    "minutes_since_open", "is_first_last_30min", "day_of_week",
]
```

Output: `signal=1` (buy) when `sigmoid(logit) >= THRESHOLD` (default 0.5).

## Volume Profile Features (not used by current MLP)

Computed by `feat_files/volume_profile.py` from tick data. Available in `features_volume_profile` stream but not included in the trained model yet.

| Feature          | Description                              |
| ---------------- | ---------------------------------------- |
| poc_price        | Point of Control — price with most volume |
| poc_volume       | Volume at the POC level                  |
| value_area_low   | VAL — lower bound of 70% value area      |
| value_area_high  | VAH — upper bound of 70% value area      |
| total_volume     | Total session volume so far              |
