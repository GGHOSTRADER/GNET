# Features Documentation
> **What:** Quick reference table of all engineered features — what each one measures and which file computes it.

All features are computed in `feat_files/transformer_features.py` from a 60-bar rolling window and published to the `features_transformer` Redis stream.

| Feature                 | Type  | Description                                                                        |
| ----------------------- | ----- | ---------------------------------------------------------------------------------- |
| parkinson_vol_{5,15,30} | float | Volatility estimated from High/Low range — more efficient than close-to-close vol  |
| ofi_{5,15,30}           | float | Order Flow Imbalance — (sum(Up)-sum(Down)) / (sum(Up)+sum(Down)) over rolling window, bounded [-1,1] |
| volume_percentile       | float | Where current volume ranks vs last 60 bars (0–1)                                   |
| volume_momentum         | float | Volume % change over last 5 bars                                                   |
| amihud_illiquidity      | float | Rolling 30-bar mean of \|pct_change(Close)\| / (Close × Volume) — price impact per dollar traded |
| vwap_distance           | float | How far price is from VWAP, normalized by ATR                                      |
| minutes_since_open      | float | Minutes elapsed since 09:30 open                                                   |
| is_first_last_30min     | int   | Binary flag — 1 if in first or last 30min of session                               |
| day_of_week             | int   | Day of week — Monday=0 … Friday=4. Derived from `bar.date` (YYYYMMDD)             |

**Total: 13 features** (3 parkinson + 3 ofi + 7 others)

## MLP Model Input

The MA model loaded by `inference/strategy_router.py` uses all 13 features above in this exact order:

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

Computed by `feat_files/canonical_volume_profile.py` from TradeStation-classified
`Up` and `Down` tick volume. The live adapter can emit multiple records per
interval because every qualifying final-second tick currently requests a
snapshot. These fields are available in `features_volume_profile` but are not
included in the MA model.

| Feature             | Description                                                              |
| ------------------- | ------------------------------------------------------------------------ |
| poc_price           | Point of Control — price with most volume                               |
| poc_volume          | Volume at the POC level                                                  |
| value_area_low      | VAL — lower bound of 70% value area                                      |
| value_area_high     | VAH — upper bound of 70% value area                                      |
| total_volume        | Total session volume so far                                              |
| poc_distance        | (current_price - poc_price) / tick_size — signed distance from POC      |
| poc_concentration   | poc_volume / total_volume — how peaked vs diffuse the profile is        |
| va_width            | (value_area_high - value_area_low) / tick_size                          |
| va_position         | (current_price - VAL) / (VAH - VAL) — 0=at VAL, 1=at VAH, outside [0,1]=outside VA |
| vol_above_poc_ratio | Fraction of total volume traded above the POC price                     |
| profile_entropy     | -Σp·log(p) over the volume distribution — low=concentrated, high=diffuse |
| profile_kurtosis    | Excess kurtosis of the volume distribution — peakedness of the profile  |
| poc_migration       | (poc_price_now - poc_price_prev_bar) / tick_size — POC drift since last bar |

### Extended canonical VP contract

`Up` and `Down` are TradeStation price-direction classifications, not verified
bid/ask aggressor flags. Delta fields are therefore named **classified** delta.

| Feature | Definition |
|---|---|
| classified_cumulative_delta | Session cumulative `sum(Up - Down)` |
| classified_delta_ratio | Cumulative classified delta / total session volume |
| classified_delta_at_poc_ratio | Classified delta at POC / POC volume |
| classified_value_area_delta_ratio | Classified delta inside VAL–VAH / volume inside VAL–VAH |
| classified_delta_above_below_poc | `(delta above POC - delta below POC) / total volume` |
| max_abs_delta_price_distance | Signed current-price distance from the largest absolute-delta level, in ticks |
| classified_delta_concentration | Largest absolute level delta / total absolute level delta |
| recent_classified_delta_ratio | Classified delta since prior snapshot / volume since prior snapshot |
| price_classified_delta_divergence | `-price_change_ticks * recent_classified_delta_ratio`; positive means opposing directions |
| va_expansion_rate | Change in Value Area width since the previous snapshot, in ticks |
| poc_velocity_5 | POC displacement over five snapshots / five, in ticks per snapshot |
| volume_above_vah_ratio | Session volume above VAH / total volume |
| volume_below_val_ratio | Session volume below VAL / total volume |
| profile_skewness | Volume-weighted profile skewness |
| current_price_acceptance_ratio | Volume within current price ±4 ticks / total volume |
| distance_to_val_ticks | `(current price - VAL) / tick_size` |
| distance_to_vah_ticks | `(VAH - current price) / tick_size` |
| nearest_hvn_distance_ticks | Signed distance from current price to nearest grouped HVN |
| nearest_lvn_distance_ticks | Signed distance from current price to nearest grouped LVN |
| nearest_hvn_strength | Nearest HVN representative volume / median occupied-level volume |
| nearest_lvn_strength | Nearest LVN representative volume / median occupied-level volume |
| hvn_count | Count of contiguous nodes at or above 1.5× the occupied-level median |
| lvn_count | Count of contiguous nodes at or below 0.5× the occupied-level median |
| current_price_in_hvn | `1.0` when the current price level belongs to an HVN, otherwise `0.0` |

The canonical tuple `VOLUME_PROFILE_FEATURE_NAMES` is the authoritative ordered
list of all 32 candidate VP features. Snapshots also retain total, Up, Down, and
classified-delta arrays by price for offline analysis; Redis publishes only
scalar fields.
