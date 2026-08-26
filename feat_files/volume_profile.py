"""Live Redis adapter for the canonical volume-profile engine.

Domain state and mathematics live in :mod:`feat_files.canonical_volume_profile`.
This module owns only Redis input, snapshot cadence, Redis encoding, publishing,
and the command-line entry point. Compatibility aliases preserve the original
function names for existing callers.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable, Iterator, Optional

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
from netwo_files.tick_codec import (
    XReadTickBatch,
    parse_xread_to_ticks,
    tick_from_redis_fields,
)


DEFAULT_SNAPSHOT_INTERVAL_S = 30
DEFAULT_SNAPSHOT_OFFSET_S = 29.925

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


def next_snapshot_deadline(
    now_s: float,
    snapshot_interval_s: int = DEFAULT_SNAPSHOT_INTERVAL_S,
    snapshot_offset_s: float = DEFAULT_SNAPSHOT_OFFSET_S,
) -> float:
    """Return the first configured wall-clock gate strictly after ``now_s``."""
    if snapshot_interval_s <= 0:
        raise VolumeProfileError("snapshot_interval_s must be positive")
    if not 0 <= snapshot_offset_s < snapshot_interval_s:
        raise VolumeProfileError(
            "snapshot_offset_s must be within the snapshot interval"
        )
    interval_start = math.floor(now_s / snapshot_interval_s) * snapshot_interval_s
    deadline = interval_start + snapshot_offset_s
    if deadline <= now_s:
        deadline += snapshot_interval_s
    return deadline


def _stream_entry_ms(entry_id: Any) -> float:
    """Decode the millisecond wall-clock component of a Redis stream ID."""
    return float(str(entry_id).split("-", 1)[0])


def _publish_snapshot(
    redis_connection: Any,
    engine: VolumeProfileEngine,
    source_entry_id: Optional[str] = None,
    source_fields: Optional[dict[str, Any]] = None,
) -> None:
    """Commit and publish exactly one snapshot of the current canonical state."""
    snapshot_started_ns = time.time_ns()
    vp = engine.snapshot()
    snapshot_finished_ns = time.time_ns()
    fields = _vp_result_to_redis_fields(vp)
    fields["snapshot_started_ns"] = str(snapshot_started_ns)
    fields["snapshot_finished_ns"] = str(snapshot_finished_ns)
    if source_entry_id is not None and source_fields is not None:
        fields["source_validated_entry_id"] = source_entry_id
        fields["source_validated_published_ms"] = str(
            int(_stream_entry_ms(source_entry_id))
        )
        for source_name, target_name in (
            ("raw_entry_id", "source_raw_entry_id"),
            ("tcp_received_ns", "source_tcp_received_ns"),
            ("validator_received_ns", "source_validator_received_ns"),
            ("time", "source_tick_time_s"),
        ):
            value = source_fields.get(source_name)
            if value is not None:
                fields[target_name] = str(value)
    redis_connection.xadd(
        REDIS1_FEATURES_VP_STREAM,
        fields,
        maxlen=50_000,
        approximate=True,
    )
    print(
        f"{time.time():.3f} {vp.symbol} date={vp.date} bar={vp.bar_num} "
        f"bars={vp.n_bars} tick={vp.tick_size} range={vp.range_ticks} "
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
    snapshot_offset_s: float = DEFAULT_SNAPSHOT_OFFSET_S,
    *,
    block_ms: int = 250,
    count: int = 200,
    start_id: str = "$",
    clock: Callable[[], float] = time.time,
) -> None:
    """Update on every tick and publish once at each wall-clock gate."""
    if block_ms <= 0 or count <= 0:
        raise VolumeProfileError("block_ms and count must be positive")
    redis_connection = get_redis_connection(
        REDIS1_HOST,
        REDIS1_PORT,
        REDIS1_FEATURES_VP_STREAM,
    )
    engine = VolumeProfileEngine(tick_size=tick_size, range_ticks=range_ticks)
    last_id = start_id
    latest_source_entry_id: Optional[str] = None
    latest_source_fields: Optional[dict[str, Any]] = None
    deadline = next_snapshot_deadline(
        clock(), snapshot_interval_s, snapshot_offset_s
    )

    while True:
        now_s = clock()
        if now_s >= deadline:
            if engine.state is not None:
                _publish_snapshot(
                    redis_connection,
                    engine,
                    latest_source_entry_id,
                    latest_source_fields,
                )
            deadline = next_snapshot_deadline(
                now_s, snapshot_interval_s, snapshot_offset_s
            )
            continue

        until_gate_ms = max(1, math.ceil((deadline - now_s) * 1_000))
        xread_result = redis_connection.xread(
            {REDIS1_TICK_VALIDATED_STREAM: last_id},
            count=count,
            block=min(block_ms, until_gate_ms),
        )
        if not xread_result:
            continue

        for raw_stream, entries in xread_result:
            for entry_id, fields in entries:
                entry_s = _stream_entry_ms(entry_id) / 1_000
                if entry_s >= deadline:
                    if engine.state is not None:
                        _publish_snapshot(
                            redis_connection,
                            engine,
                            latest_source_entry_id,
                            latest_source_fields,
                        )
                    deadline = next_snapshot_deadline(
                        entry_s, snapshot_interval_s, snapshot_offset_s
                    )
                engine.update(tick_from_redis_fields(fields))
                last_id = str(entry_id)
                latest_source_entry_id = last_id
                latest_source_fields = dict(fields)


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
        help="Wall-clock interval length in seconds (default: 30)",
    )
    parser.add_argument(
        "--snapshot-offset-s",
        type=float,
        default=DEFAULT_SNAPSHOT_OFFSET_S,
        help="Seconds into each interval to publish once (default: 29.925)",
    )
    args = parser.parse_args(argv)
    run_publish_loop(
        tick_size=args.tick_size,
        range_ticks=args.range_ticks,
        snapshot_interval_s=args.snapshot_interval_s,
        snapshot_offset_s=args.snapshot_offset_s,
    )


if __name__ == "__main__":
    main()
