from pathlib import Path

import pandas as pd
import pytest

from training_mlp.analyze_vp_correlations import (
    VPCorrelationError,
    build_pair_report,
    discover_feature_parquets,
)


def test_discover_feature_parquets_is_chronological(tmp_path: Path):
    later = tmp_path / "session_date=2026-03-17"
    earlier = tmp_path / "session_date=2026-03-16"
    later.mkdir()
    earlier.mkdir()
    (later / "vp_features.parquet").touch()
    (earlier / "vp_features.parquet").touch()

    assert discover_feature_parquets(tmp_path) == [
        earlier / "vp_features.parquet",
        later / "vp_features.parquet",
    ]


def test_discover_feature_parquets_rejects_empty_root(tmp_path: Path):
    with pytest.raises(VPCorrelationError, match="no VP feature Parquets"):
        discover_feature_parquets(tmp_path)


def test_pair_report_uses_stronger_of_pearson_and_spearman():
    names = ["a", "b", "c"]
    pearson = pd.DataFrame(
        [[1.0, 0.96, 0.2], [0.96, 1.0, 0.4], [0.2, 0.4, 1.0]],
        index=names,
        columns=names,
    )
    spearman = pd.DataFrame(
        [[1.0, 0.90, 0.92], [0.90, 1.0, 0.3], [0.92, 0.3, 1.0]],
        index=names,
        columns=names,
    )

    result = build_pair_report(
        pearson, spearman, high_threshold=0.90, severe_threshold=0.95
    )

    assert list(result["classification"]) == [
        "severe",
        "high",
        "below_threshold",
    ]
    assert result.iloc[0]["feature_a"] == "a"
    assert result.iloc[0]["feature_b"] == "b"
