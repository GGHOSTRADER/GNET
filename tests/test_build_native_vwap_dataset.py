from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.build_native_vwap_dataset import (
    NativeVwapDatasetError,
    attach_native_vwap,
    build_native_dataset,
    load_native_vwap,
)
from training_mlp.study_pipeline import engineer_features, load_bars


def test_native_export_rejects_duplicate_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "vwap.csv"
    path.write_text(
        "Date,Time,VWAP\n03/15/2026,18:00:30,100.25\n"
        "03/15/2026,18:00:30,100.50\n",
        encoding="utf-8",
    )
    with pytest.raises(NativeVwapDatasetError, match="duplicate"):
        load_native_vwap(path)


def test_native_join_rejects_missing_master_bar() -> None:
    bars = pd.DataFrame(
        {"Date/Time": pd.to_datetime(["2026-03-15 18:00:30", "2026-03-15 18:01:00"])}
    )
    native = pd.DataFrame(
        {"Date/Time": pd.to_datetime(["2026-03-15 18:00:30"]), "VWAP": [100.0]}
    )
    with pytest.raises(NativeVwapDatasetError, match="missing 1 master bars"):
        attach_native_vwap(bars, native)


def test_native_export_accepts_nonoverlapping_chunks(tmp_path: Path) -> None:
    (tmp_path / "march.csv").write_text(
        "Date,Time,VWAP\n03/15/2026,18:00:30,100.25\n", encoding="utf-8"
    )
    (tmp_path / "april.csv").write_text(
        "Date,Time,VWAP\n04/01/2026,18:00:30,101.25\n", encoding="utf-8"
    )
    frame = load_native_vwap(tmp_path)
    assert len(frame) == 2
    assert frame["Date/Time"].is_unique


def test_native_dataset_changes_only_vwap_feature(tmp_path: Path) -> None:
    timestamps = pd.date_range("2026-03-15 18:00:30", periods=64, freq="30s")
    prices = np.linspace(100.0, 102.0, len(timestamps))
    bars_path = tmp_path / "bars.csv"
    pd.DataFrame(
        {
            "Date": timestamps.strftime("%m/%d/%Y"),
            "Time": timestamps.strftime("%H:%M:%S"),
            "Open": prices,
            "High": prices + 0.5,
            "Low": prices - 0.5,
            "Close": prices + 0.25,
            "Up": np.full(len(timestamps), 100),
            "Down": np.full(len(timestamps), 80),
        }
    ).to_csv(bars_path, index=False)
    bars = load_bars(bars_path)
    reference = engineer_features(bars).loc[60:, ["Date/Time", *FEATURE_NAMES]].copy()
    reference["t1"] = reference["Date/Time"]
    reference["Label"] = 1
    reference_path = tmp_path / "reference.csv"
    reference.to_csv(reference_path, index=False)

    native_path = tmp_path / "native.csv"
    pd.DataFrame(
        {
            "Date": timestamps.strftime("%m/%d/%Y"),
            "Time": timestamps.strftime("%H:%M:%S"),
            "VWAP": np.full(len(timestamps), 100.0),
        }
    ).to_csv(native_path, index=False)
    output, summary = build_native_dataset(bars_path, native_path, reference_path)

    assert len(output) == len(reference)
    assert summary["changed_vwap_features"] == len(reference)
    assert not np.allclose(output["vwap_distance"], reference["vwap_distance"])
    for feature in FEATURE_NAMES:
        if feature != "vwap_distance":
            np.testing.assert_allclose(output[feature], reference[feature])
    assert output["Label"].tolist() == reference["Label"].tolist()
