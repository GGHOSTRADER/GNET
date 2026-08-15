"""
transformer_features_pipeline.py
=================================

Clean architecture transformer feature pipeline (Redis -> Bars -> Features).

Mirrors feat_eng_1.py in structure. No pandas, no talib, no CSV.
All features computed from a rolling deque of typed Bars read from Redis1.

Layering
--------
- Adapter / Infrastructure (I/O):
    - Reads from Redis1 using redis-py xread
    - Uses get_redis_connection(host, port, stream_name)
    - Imports config from config.setting

- Application / Orchestration:
    - Builds rolling window of 60 bars (max window required)
    - Emits FeaturePoint records

- Domain (Pure):
    - FeatureEngine and all formulas live in canonical_features.py
    - parse_xread_to_bars() is PURE (from bar_codec.py)

Features emitted
----------------
  parkinson_vol_{5,15,30}  -- High/Low Parkinson volatility estimator
  ofi_{5,15,30}            -- Order Flow Imbalance: (sum(Up)-sum(Down))/sum(Up+Down), bounded [-1,1]
  volume_percentile        -- Rank of current bar volume in last 60 bars (0-1)
  volume_momentum          -- Volume % change vs 5 bars ago
  amihud_illiquidity       -- rolling 30-bar mean of |pct_change(close)| / (close * volume)
  vwap_distance            -- (close - vwap) / ATR(14)
  minutes_since_open       -- Minutes elapsed since 09:30
  is_first_last_30min      -- 1 if in first or last 30 min of session

Window requirements
-------------------
  volume_percentile : 60 bars  (largest -> governs when we start emitting)
  parkinson_vol_30  : 30 bars
  ofi_30            : 30 bars
  atr (for vwap_d.) : 15 bars  (14 TR values -> 15 bars)
  volume_momentum   : 6 bars   (current + 5 ago)
  amihud            : 31 bars  (30 pct_change values need 31 closes)

Active components
-----------------
1) FeatureEngine                     -- canonical 13-feature mathematics and rolling state
2) FeaturePoint                      -- frozen output record with metadata
3) stream_bars_from_redis(...)       -- adapter: reads validated_bar and yields typed Bars
4) stream_feature_points(...)        -- orchestration: canonical values -> FeaturePoint
5) run_publish_loop()                -- publishes FeaturePoint records to Redis

Contract compliance
-------------------
1) Connect to Redis using get_redis_connection from netwo_files.redis_tool
2) xread from redis, parse with parse_xread_to_bars from netwo_files.bar_codec
3) Validate raw field count == 11 BEFORE parsing
4) Validate typed Bar invariants + bar_num continuity
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from config.setting import (
    REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME,
    REDIS1_FEATURES_TRANSFORMER_STREAM,
)
from netwo_files.redis_tool import get_redis_connection
from netwo_files.bar_codec import parse_xread_to_bars
from feat_files.canonical_features import FeatureEngine, WINDOW_SIZE

_WINDOW = WINDOW_SIZE           # largest rolling window (volume_percentile)


# ============================================================
# Output record
# ============================================================


@dataclass(frozen=True)
class FeaturePoint:
    symbol: str
    date: int
    time_s: int
    bar_num: int
    parkinson_vol_5: float
    parkinson_vol_15: float
    parkinson_vol_30: float
    ofi_5: float
    ofi_15: float
    ofi_30: float
    volume_percentile: float
    volume_momentum: float
    amihud_illiquidity: float
    vwap_distance: float
    minutes_since_open: float
    is_first_last_30min: int
    day_of_week: int


# ============================================================
# Adapter: Redis -> raw XREAD -> parse -> validate -> bars
# ============================================================


def stream_bars_from_redis(
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[Any]:
    """
    Reads validated bars from Redis1. Data is already validated at ingestion
    (tcp_to_redis_connection.py + bar_codec.py), so we just read and cast.
    """
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME)
    last_id = start_id

    while True:
        xread_result = r.xread({REDIS1_STREAM_NAME: last_id}, count=count, block=block_ms)
        batch = parse_xread_to_bars(xread_result)
        if not batch.bars:
            continue
        last_id = batch.last_ids[REDIS1_STREAM_NAME]
        yield from batch.bars


# ============================================================
# Application: rolling window -> feature points
# ============================================================


def stream_feature_points(
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[FeaturePoint]:
    """
    Application orchestration:
    - Consume validated bars from Redis1
    - Build rolling window of 60 bars (largest required window)
    - Emit FeaturePoint once window is full
    """
    engine = FeatureEngine()

    for bar in stream_bars_from_redis(block_ms=block_ms, count=count, start_id=start_id):
        values = engine.update(bar)
        if values is None:
            print(f"[warming up] {engine.bars_seen}/{_WINDOW} bars")
            continue

        yield FeaturePoint(
            symbol=bar.symbol,
            date=bar.date,
            time_s=bar.time_s,
            bar_num=bar.bar_num,
            parkinson_vol_5=values.parkinson_vol_5,
            parkinson_vol_15=values.parkinson_vol_15,
            parkinson_vol_30=values.parkinson_vol_30,
            ofi_5=values.ofi_5,
            ofi_15=values.ofi_15,
            ofi_30=values.ofi_30,
            volume_percentile=values.volume_percentile,
            volume_momentum=values.volume_momentum,
            amihud_illiquidity=values.amihud_illiquidity,
            vwap_distance=values.vwap_distance,
            minutes_since_open=values.minutes_since_open,
            is_first_last_30min=values.is_first_last_30min,
            day_of_week=values.day_of_week,
        )


# ============================================================
# Minimal smoke loop
# ============================================================


def _feature_point_to_redis_fields(fp: FeaturePoint) -> dict:
    """Encode a FeaturePoint into canonical string fields for Redis xadd."""
    return {
        "symbol":           fp.symbol,
        "date":             str(fp.date),
        "time_s":           str(fp.time_s),
        "bar_num":          str(fp.bar_num),
        "parkinson_vol_5":  repr(fp.parkinson_vol_5),
        "parkinson_vol_15": repr(fp.parkinson_vol_15),
        "parkinson_vol_30": repr(fp.parkinson_vol_30),
        "ofi_5":            repr(fp.ofi_5),
        "ofi_15":           repr(fp.ofi_15),
        "ofi_30":           repr(fp.ofi_30),
        "volume_percentile": repr(fp.volume_percentile),
        "volume_momentum":  repr(fp.volume_momentum),
        "amihud_illiquidity": repr(fp.amihud_illiquidity),
        "vwap_distance":    repr(fp.vwap_distance),
        "minutes_since_open": repr(fp.minutes_since_open),
        "is_first_last_30min": str(fp.is_first_last_30min),
        "day_of_week":         str(fp.day_of_week),
    }


def run_publish_loop() -> None:
    """
    Main loop: compute features and push each FeaturePoint to Redis.
    Writes to stream: features_transformer
    Also prints to stdout for monitoring.
    """
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_FEATURES_TRANSFORMER_STREAM)

    for fp in stream_feature_points():
        r.xadd(
            REDIS1_FEATURES_TRANSFORMER_STREAM,
            _feature_point_to_redis_fields(fp),
            maxlen=1_000,
            approximate=True,
        )
        print(
            f"{fp.symbol} date={fp.date} t={fp.time_s} bar={fp.bar_num} "
            f"pvol5={fp.parkinson_vol_5:.6f} pvol15={fp.parkinson_vol_15:.6f} pvol30={fp.parkinson_vol_30:.6f} "
            f"ofi5={fp.ofi_5:.0f} ofi15={fp.ofi_15:.0f} ofi30={fp.ofi_30:.0f} "
            f"vol_pct={fp.volume_percentile:.3f} vol_mom={fp.volume_momentum:.4f} "
            f"amihud={fp.amihud_illiquidity:.8f} vwap_d={fp.vwap_distance:.4f} "
            f"min_open={fp.minutes_since_open:.1f} sess_flag={fp.is_first_last_30min}"
        )


if __name__ == "__main__":
    run_publish_loop()
