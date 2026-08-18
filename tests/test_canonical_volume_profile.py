"""Direct tests for the transport-independent canonical VP engine."""

from dataclasses import dataclass
import math

import pytest

from feat_files.canonical_volume_profile import (
    VOLUME_PROFILE_FEATURE_NAMES,
    VolumeProfileEngine,
    VolumeProfileError,
    initialize_profile,
    snapshot_profile,
    update_profile,
)
from feat_files import volume_profile as live_volume_profile
from feat_files import canonical_volume_profile as canonical


@dataclass(frozen=True)
class TickStub:
    symbol: str = "@ES"
    date: int = 1260817
    time_s: int = 12 * 3600
    high: float = 6500.0
    up: int = 1
    down: int = 0
    bar_num: int = 1


def test_live_compatibility_names_are_canonical_objects():
    assert live_volume_profile._find_poc is canonical.find_poc
    assert live_volume_profile._find_value_area is canonical.find_value_area
    assert live_volume_profile._init_session is canonical.initialize_profile
    assert live_volume_profile._update is canonical.update_profile
    assert live_volume_profile._snapshot is canonical.snapshot_profile
    assert live_volume_profile._SessionState is canonical.VolumeProfileState


def test_engine_accumulates_ticks_and_produces_canonical_snapshot():
    engine = VolumeProfileEngine(tick_size=0.25, range_ticks=20)
    engine.update(TickStub(up=3, bar_num=1))
    engine.update(TickStub(high=6500.25, up=2, bar_num=2))

    result = engine.snapshot()

    assert result.total_volume == pytest.approx(5.0)
    assert result.n_bars == 2
    assert result.poc_price == pytest.approx(6500.0)


def test_engine_resets_at_1800_and_continues_across_midnight():
    engine = VolumeProfileEngine()
    engine.update(TickStub(date=1260817, time_s=17 * 3600 + 59 * 60 + 59))
    assert engine.snapshot().n_bars == 1

    engine.update(TickStub(date=1260817, time_s=18 * 3600, bar_num=2))
    assert engine.snapshot().n_bars == 1

    engine.update(TickStub(date=1260818, time_s=1, bar_num=3))
    assert engine.snapshot().n_bars == 2


def test_low_level_update_rejects_another_session():
    first = TickStub(date=1260817, time_s=18 * 3600)
    state = initialize_profile(first, tick_size=0.25, range_ticks=20)
    update_profile(state, first)

    with pytest.raises(VolumeProfileError, match="different trading session"):
        update_profile(
            state,
            TickStub(date=1260818, time_s=18 * 3600, bar_num=2),
        )

    assert snapshot_profile(state).total_volume == pytest.approx(1.0)


def test_snapshot_preserves_up_down_and_classified_delta_by_price():
    engine = VolumeProfileEngine(tick_size=0.25, range_ticks=20)
    engine.update(TickStub(high=6500.0, up=7, down=2, bar_num=1))
    engine.update(TickStub(high=6500.25, up=1, down=5, bar_num=2))

    result = engine.snapshot()

    assert result.up_volume_at_level.sum() == pytest.approx(8.0)
    assert result.down_volume_at_level.sum() == pytest.approx(7.0)
    assert result.classified_delta_at_level.sum() == pytest.approx(1.0)
    assert result.classified_cumulative_delta == pytest.approx(1.0)
    assert result.classified_delta_ratio == pytest.approx(1.0 / 15.0)


def test_recent_delta_and_price_delta_divergence_use_snapshot_changes():
    engine = VolumeProfileEngine(tick_size=0.25, range_ticks=20)
    engine.update(TickStub(high=6500.0, up=5, down=0, bar_num=1))
    engine.snapshot()
    engine.update(TickStub(high=6500.25, up=0, down=4, bar_num=2))

    result = engine.snapshot()

    assert result.recent_classified_delta_ratio == pytest.approx(-1.0)
    assert result.price_classified_delta_divergence == pytest.approx(1.0)


def test_node_thresholds_group_levels_and_report_nearest_nodes():
    engine = VolumeProfileEngine(tick_size=0.25, range_ticks=20)
    engine.update(TickStub(high=6500.0, up=20, down=0, bar_num=1))
    engine.update(TickStub(high=6500.25, up=5, down=0, bar_num=2))
    engine.update(TickStub(high=6500.50, up=10, down=0, bar_num=3))

    result = engine.snapshot()

    assert result.hvn_count == pytest.approx(1.0)
    assert result.lvn_count == pytest.approx(1.0)
    assert result.nearest_hvn_strength == pytest.approx(2.0)
    assert result.nearest_lvn_strength == pytest.approx(0.5)
    assert result.nearest_hvn_distance_ticks == pytest.approx(2.0)
    assert result.nearest_lvn_distance_ticks == pytest.approx(1.0)


def test_poc_velocity_uses_five_snapshot_displacement():
    engine = VolumeProfileEngine(tick_size=0.25, range_ticks=20)
    result = None
    for index, volume in enumerate((1, 2, 4, 8, 16, 32)):
        engine.update(
            TickStub(
                high=6500.0 + index * 0.25,
                up=volume,
                down=0,
                bar_num=index + 1,
            )
        )
        result = engine.snapshot()

    assert result is not None
    assert result.poc_velocity_5 == pytest.approx(1.0)


def test_live_redis_encoding_contains_complete_canonical_feature_contract():
    engine = VolumeProfileEngine()
    engine.update(TickStub(up=2, down=1))
    fields = live_volume_profile._vp_result_to_redis_fields(engine.snapshot())

    assert set(VOLUME_PROFILE_FEATURE_NAMES).issubset(fields)
    assert len(VOLUME_PROFILE_FEATURE_NAMES) == 32
    assert all(math.isfinite(float(fields[name])) for name in VOLUME_PROFILE_FEATURE_NAMES)
