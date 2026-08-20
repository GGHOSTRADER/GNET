from datetime import datetime

import pandas as pd
import pytest

from training_mlp.study_pipeline import (
    _parse_tradestation_timestamps,
    merge_and_export,
    metalabel,
)


def _trade_rows():
    return pd.DataFrame(
        [
            {
                "#": 1,
                "Date/Time": "1/2/2026 10:00:00 AM",
                "_timestamp": datetime(2026, 1, 2, 10, 0),
                "Signal": "MA2CrossLE",
                "% Profit": 0.01,
            },
            {
                "#": None,
                "Date/Time": "1/2/2026 10:03:00 AM",
                "_timestamp": datetime(2026, 1, 2, 10, 3),
                "Signal": "Profit Target",
                "% Profit": None,
            },
            {
                "#": 2,
                "Date/Time": "1/2/2026 10:05:00 AM",
                "_timestamp": datetime(2026, 1, 2, 10, 5),
                "Signal": "MA2CrossLE",
                "% Profit": None,
            },
            {
                "#": None,
                "Date/Time": "Open",
                "_timestamp": pd.NaT,
                "Signal": None,
                "% Profit": None,
            },
        ]
    )


def test_metalabel_pairs_close_time_as_t1_and_skips_explicit_open_trade():
    result = metalabel(_trade_rows(), "MA2CrossLE")

    assert list(result.columns) == ["Date/Time", "t1", "Label"]
    assert result.to_dict(orient="records") == [
        {
            "Date/Time": pd.Timestamp("2026-01-02 10:00:00"),
            "t1": pd.Timestamp("2026-01-02 10:03:00"),
            "Label": 1,
        }
    ]


def test_tradestation_date_only_timestamp_means_midnight_but_open_is_missing():
    result = _parse_tradestation_timestamps(
        pd.Series(["12/12/2025", "12/12/2025 12:02:30 AM", "Open"])
    )

    assert result.iloc[0] == pd.Timestamp("2025-12-12 00:00:00")
    assert result.iloc[1] == pd.Timestamp("2025-12-12 00:02:30")
    assert pd.isna(result.iloc[2])


def test_metalabel_rejects_close_before_entry():
    rows = _trade_rows().iloc[:2].copy()
    rows.loc[1, "_timestamp"] = datetime(2026, 1, 2, 9, 59)

    with pytest.raises(ValueError, match="closes before"):
        metalabel(rows, "MA2CrossLE")


def test_merge_preserves_t1_as_metadata_not_feature(tmp_path):
    timestamp = pd.Timestamp("2026-01-02 10:00:00")
    features = pd.DataFrame(
        {
            "Date/Time": [timestamp],
            "parkinson_vol_5": [1.0],
            "parkinson_vol_15": [1.0],
            "parkinson_vol_30": [1.0],
            "ofi_5": [1.0],
            "ofi_15": [1.0],
            "ofi_30": [1.0],
            "volume_percentile": [1.0],
            "volume_momentum": [1.0],
            "amihud_illiquidity": [1.0],
            "vwap_distance": [1.0],
            "minutes_since_open": [1.0],
            "is_first_last_30min": [0],
            "day_of_week": [4],
        }
    )
    labels = pd.DataFrame(
        {"Date/Time": [timestamp], "t1": [timestamp], "Label": [0]}
    )

    result = merge_and_export(features, labels, tmp_path / "labeled.csv")

    assert "t1" in result.columns
    assert result.columns[-1] == "Label"
