from pathlib import Path

import pandas as pd

from training_mlp.build_vwap_ablation_dataset import build_ablation_dataset


def test_ablation_replaces_only_vwap_distance(tmp_path: Path):
    bars = tmp_path / "bars.csv"
    rows = []
    start = pd.Timestamp("2026-04-06 09:30:00")
    for index in range(70):
        timestamp = start + pd.Timedelta(seconds=30 * index)
        close = 5000.0 + index * 0.25
        rows.append(
            {
                "Date": timestamp.strftime("%m/%d/%Y"),
                "Time": timestamp.strftime("%H:%M:%S"),
                "Open": close - 0.25,
                "High": close + 0.50,
                "Low": close - 0.50,
                "Close": close,
                "Up": 100 + index,
                "Down": 80 + index,
            }
        )
    pd.DataFrame(rows).to_csv(bars, index=False)

    event_time = start + pd.Timedelta(seconds=30 * 69)
    canonical = tmp_path / "canonical.csv"
    pd.DataFrame(
        [{"Date/Time": event_time, "other": 7.0, "vwap_distance": 999.0,
          "t1": event_time + pd.Timedelta(seconds=30), "Label": 1}]
    ).to_csv(canonical, index=False)

    output = tmp_path / "ablation.csv"
    result = build_ablation_dataset(canonical, bars, output)

    assert output.is_file()
    assert result.loc[0, "other"] == 7.0
    assert result.loc[0, "Label"] == 1
    assert result.loc[0, "vwap_distance"] != 999.0
