"""Live Redis adapter for the canonical volume-profile engine.

Domain state and mathematics live in :mod:`feat_files.canonical_volume_profile`.
This module owns only Redis input, snapshot cadence, Redis encoding, publishing,
and the command-line entry point. Compatibility aliases preserve the original
function names for existing callers.
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

from config.setting import (
    REDIS1_FEATURES_VP_STREAM,
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_TICK_VALIDATED_STREAM,
)
from feat_files.canonical_volume_profile import (
    DEFAULT_RANGE_TICKS,
    EXTENSION_PCT,
    SESSION_START_S,
    VALUE_AREA_PCT,
    VOLUME_PROFILE_FEATURE_NAMES,
    VolumeProfileEngine,
    VolumeProfileError,
    VolumeProfileResult,
    VolumeProfileState,
    compute_derived_features,
    find_poc,
    find_value_area,
    initialize_profile,
    next_packed_date,
    require_volume_profile,
    session_key,
    snapshot_profile,
    update_profile,
)
from netwo_files.redis_tool import get_redis_connection
from netwo_files.tick_codec import XReadTickBatch, parse_xread_to_ticks


DEFAULT_SNAPSHOT_INTERVAL_S = 30

# Backward-compatible aliases. All resolve to the canonical implementation.
_SessionState = VolumeProfileState
_require_vp = require_volume_profile
_find_poc = find_poc
_find_value_area = find_value_area
_compute_derived_features = compute_derived_features
_next_packed_date = next_packed_date
_session_key = session_key
_init_session = initialize_profile
_update = update_profile
_snapshot = snapshot_profile


def stream_ticks_from_redis(
    *,
    block_ms: int = 100,
    count: int = 500,
    start_id: str = "$",
) -> Iterator[Any]:
    """Yield typed ticks from the already-validated Redis tick stream."""
    redis_connection = get_redis_connection(
        REDIS1_HOST,
        REDIS1_PORT,
        REDIS1_TICK_VALIDATED_STREAM,
    )
    last_id = start_id
    while True:
        xread_result = redis_connection.xread(
            {REDIS1_TICK_VALIDATED_STREAM: last_id},
            count=count,
            block=block_ms,
        )
        batch: XReadTickBatch = parse_xread_to_ticks(xread_result)
        if not batch.ticks:
            continue
        last_id = batch.last_ids[REDIS1_TICK_VALIDATED_STREAM]
        yield from batch.ticks


def stream_volume_profile(
    tick_size: float = 0.25,
    range_ticks: int = DEFAULT_RANGE_TICKS,
    snapshot_interval_s: int = DEFAULT_SNAPSHOT_INTERVAL_S,
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
) -> Iterator[VolumeProfileResult]:
    """Update canonical state per tick and snapshot at the configured gate."""
    if snapshot_interval_s <= 0:
        raise VolumeProfileError("snapshot_interval_s must be positive")
    engine = VolumeProfileEngine(tick_size=tick_size, range_ticks=range_ticks)
    for tick in stream_ticks_from_redis(
        block_ms=block_ms,
        count=count,
        start_id=start_id,
    ):
        engine.update(tick)
        if tick.time_s % snapshot_interval_s == snapshot_interval_s - 1:
            yield engine.snapshot()


def _vp_result_to_redis_fields(vp: VolumeProfileResult) -> dict[str, str]:
    """Encode canonical scalar snapshot fields for Redis."""
    fields = {
        "symbol": vp.symbol,
        "date": str(vp.date),
        "bar_num": str(vp.bar_num),
        "tick_size": repr(vp.tick_size),
        "range_ticks": str(vp.range_ticks),
        "poc_price": repr(vp.poc_price),
        "poc_volume": repr(vp.poc_volume),
        "value_area_low": repr(vp.value_area_low),
        "value_area_high": repr(vp.value_area_high),
        "total_volume": repr(vp.total_volume),
    }
    fields.update(
        {
            name: repr(float(getattr(vp, name)))
            for name in VOLUME_PROFILE_FEATURE_NAMES
        }
    )
    return fields


def run_publish_loop(
    tick_size: float = 0.25,
    range_ticks: int = DEFAULT_RANGE_TICKS,
    snapshot_interval_s: int = DEFAULT_SNAPSHOT_INTERVAL_S,
) -> None:
    """Publish canonical VP snapshots to the configured Redis stream."""
    redis_connection = get_redis_connection(
        REDIS1_HOST,
        REDIS1_PORT,
        REDIS1_FEATURES_VP_STREAM,
    )
    for vp in stream_volume_profile(
        tick_size=tick_size,
        range_ticks=range_ticks,
        snapshot_interval_s=snapshot_interval_s,
    ):
        redis_connection.xadd(
            REDIS1_FEATURES_VP_STREAM,
            _vp_result_to_redis_fields(vp),
            maxlen=50_000,
            approximate=True,
        )
        print(
            f"{vp.symbol} date={vp.date} bar={vp.bar_num} bars={vp.n_bars} "
            f"tick={vp.tick_size} range={vp.range_ticks} "
            f"POC={vp.poc_price:.2f} ({vp.poc_volume:.0f}) "
            f"VA=[{vp.value_area_low:.2f} - {vp.value_area_high:.2f}] "
            f"TotalVol={vp.total_volume:.0f} "
            f"GridLevels={len(vp.price_levels)} Extensions={vp.extensions} | "
            f"poc_dist={vp.poc_distance:.2f} poc_conc={vp.poc_concentration:.3f} "
            f"va_width={vp.va_width:.2f} va_pos={vp.va_position:.2f} "
            f"vol_above={vp.vol_above_poc_ratio:.3f} "
            f"entropy={vp.profile_entropy:.3f} kurt={vp.profile_kurtosis:.2f} "
            f"poc_mig={vp.poc_migration:.2f}"
        )


def main(argv: Optional[list[str]] = None) -> None:
    """Run the live VP publisher from the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Volume Profile Pipeline")
    parser.add_argument(
        "--tick-size",
        type=float,
        default=0.25,
        help="Price increment per level (default: 0.25)",
    )
    parser.add_argument(
        "--range-ticks",
        type=int,
        default=DEFAULT_RANGE_TICKS,
        help="Ticks to pre-allocate at session start (default: 400)",
    )
    parser.add_argument(
        "--snapshot-interval-s",
        type=int,
        default=DEFAULT_SNAPSHOT_INTERVAL_S,
        help="Bar length in seconds; snapshot fires 1s before close (default: 30)",
    )
    args = parser.parse_args(argv)
    run_publish_loop(
        tick_size=args.tick_size,
        range_ticks=args.range_ticks,
        snapshot_interval_s=args.snapshot_interval_s,
    )


if __name__ == "__main__":
    main()
