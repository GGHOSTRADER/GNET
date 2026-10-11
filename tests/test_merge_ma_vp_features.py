from __future__ import annotations

import pandas as pd
import pytest

from feat_files.canonical_features import FEATURE_NAMES
from feat_files.canonical_volume_profile import VOLUME_PROFILE_FEATURE_NAMES
from training_mlp.merge_ma_vp_features import (
    MAVPMergeError,
    es_session_date,
    merge_frames,
)


def _ma_frame(times: list[str]) -> pd.DataFrame:
    rows = []
    for index, timestamp in enumerate(pd.to_datetime(times)):
        row = {
            "Date/Time": timestamp,
            "symbol": "@ES",
            "session_date": "2026-03-17",
            "t1": timestamp + pd.Timedelta(minutes=1),
            "Label": index % 2,
        }
        row.update({name: float(index + 1) for name in FEATURE_NAMES})
        rows.append(row)
    return pd.DataFrame(rows)


def _vp_frame(times: list[str]) -> pd.DataFrame:
    rows = []
    for index, timestamp in enumerate(pd.to_datetime(times)):
        row = {
            "symbol": "@ES",
            "session_date": "2026-03-17",
            "vp_snapshot_timestamp": timestamp,
        }
        row.update(
            {name: float(index + 10) for name in VOLUME_PROFILE_FEATURE_NAMES}
        )
        rows.append(row)
    return pd.DataFrame(rows)


def test_session_date_rolls_at_1800() -> None:
    result = es_session_date(
        pd.Series(pd.to_datetime(["2026-03-16 17:59:59", "2026-03-16 18:00:00"]))
    )
    assert result.tolist() == ["2026-03-16", "2026-03-17"]


def test_merge_selects_freshest_nonfuture_snapshot_and_preserves_metadata() -> None:
    ma = _ma_frame(["2026-03-16 18:01:30"])
    ma["entry_time"] = pd.Timestamp("2026-03-16 18:02:00")
    ma["net_pnl_at_3_24_per_side"] = 43.52
    vp = _vp_frame(
        [
            "2026-03-16 18:01:00",
            "2026-03-16 18:01:29",
            "2026-03-16 18:01:31",
        ]
    )

    result = merge_frames(ma, vp, max_vp_age_s=30)

    assert len(result.frame) == 1
    assert result.frame.loc[0, "vp_snapshot_timestamp"] == pd.Timestamp(
        "2026-03-16 18:01:29"
    )
    assert result.frame.loc[0, "vp_age_ms"] == 1_000.0
    assert result.frame.loc[0, VOLUME_PROFILE_FEATURE_NAMES[0]] == 11.0
    assert result.frame.loc[0, "t1"] == pd.Timestamp("2026-03-16 18:02:30")
    assert result.frame.loc[0, "entry_time"] == pd.Timestamp(
        "2026-03-16 18:02:00"
    )
    assert result.frame.loc[0, "net_pnl_at_3_24_per_side"] == 43.52
    assert result.frame.loc[0, "Label"] == 0
    assert result.summary["model_features"] == 45


def test_merge_drops_missing_or_stale_snapshots_by_default() -> None:
    ma = _ma_frame(
        ["2026-03-16 18:01:30", "2026-03-16 18:03:00"]
    )
    vp = _vp_frame(["2026-03-16 18:01:29"])

    result = merge_frames(ma, vp, max_vp_age_s=30)

    assert len(result.frame) == 1
    assert result.summary["unmatched_or_stale_rows"] == 1


def test_merge_can_retain_unmatched_rows_for_diagnostics() -> None:
    ma = _ma_frame(["2026-03-16 18:03:00"])
    vp = _vp_frame(["2026-03-16 18:01:29"])

    result = merge_frames(ma, vp, max_vp_age_s=30, drop_unmatched=False)

    assert len(result.frame) == 1
    assert pd.isna(result.frame.loc[0, "vp_snapshot_timestamp"])
    assert result.summary["matched_rows"] == 0


def test_merge_rejects_nonpositive_freshness_limit() -> None:
    with pytest.raises(MAVPMergeError, match="must be positive"):
        merge_frames(
            _ma_frame(["2026-03-16 18:01:30"]),
            _vp_frame(["2026-03-16 18:01:29"]),
            max_vp_age_s=0,
        )
