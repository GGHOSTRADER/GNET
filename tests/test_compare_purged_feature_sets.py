from __future__ import annotations

import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from feat_files.canonical_volume_profile import VOLUME_PROFILE_FEATURE_NAMES
from training_mlp.compare_purged_feature_sets import (
    COMPACT_VP_FEATURES,
    REDUNDANT_FEATURES,
    feature_sets,
    make_splits,
)


def test_feature_contracts_are_ordered_and_reduced_only_by_declared_names() -> None:
    contracts = feature_sets()

    assert contracts["ma_13"] == tuple(FEATURE_NAMES)
    assert contracts["vp_32"] == tuple(VOLUME_PROFILE_FEATURE_NAMES)
    assert len(contracts["vp_32"]) == 32
    assert contracts["vp_compact_8"] == COMPACT_VP_FEATURES
    assert len(contracts["vp_compact_8"]) == 8
    assert set(contracts["vp_compact_8"]).issubset(contracts["vp_32"])
    assert contracts["ma_vp_45"] == tuple(
        FEATURE_NAMES + VOLUME_PROFILE_FEATURE_NAMES
    )
    assert len(contracts["ma_vp_reduced_42"]) == 42
    assert set(contracts["ma_vp_45"]) - set(contracts["ma_vp_reduced_42"]) == set(
        REDUNDANT_FEATURES
    )


def test_one_materialized_split_schedule_can_be_shared_by_all_models() -> None:
    starts = pd.date_range("2026-03-16 09:30:00", periods=18, freq="30s")
    frame = pd.DataFrame(
        {
            "Date/Time": starts,
            "t1": starts + pd.Timedelta(seconds=30),
            "Label": [0, 1] * 9,
        }
    )

    splits = make_splits(frame, n_splits=2, embargo_pct=0.01)

    assert len(splits) == 2
    assert all(split.train_indices.max() < split.test_indices.min() for split in splits)
    assert all(len(split.train_indices) > 0 for split in splits)
