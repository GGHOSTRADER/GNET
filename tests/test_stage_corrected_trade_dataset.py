"""Tests for corrected trade/feature timing at the contract-vintage handoff."""

import pandas as pd
import pytest

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp import stage_corrected_trade_dataset as staging


def _fixtures(tmp_path, monkeypatch):
    timestamps = [
        pd.date_range("2026-06-14 18:00:30", periods=70, freq="30s"),
        pd.date_range("2026-08-16 18:00:30", periods=70, freq="30s"),
    ]
    groups = []
    trades = {}
    for vintage, dates in zip(("old", "new"), timestamps):
        closes = [100.0] * 70
        closes[65] = 101.0
        frame = pd.DataFrame({
            "Date/Time": dates,
            "Open": [100.0] * 70,
            "High": [101.0] * 70,
            "Low": [99.0] * 70,
            "Close": closes,
        })
        for name in FEATURE_NAMES:
            frame[name] = list(range(70))
        groups.append(frame)
        trades[vintage] = pd.DataFrame({
            "vintage": [vintage],
            "trade_number": [1],
            "entry_time": [dates[66]],
            "exit_time": [dates[67]],
            "entry_price": [100.0],
            "exit_price": [101.0],
            "exit_signal": ["Profit Target"],
            "gross_pnl": [50.0],
            "net_pnl_at_3_24_per_side": [43.52],
            "outcome_positive": [1],
        })

    feature_path = tmp_path / "features.parquet"
    pd.concat(groups, ignore_index=True).to_parquet(feature_path, index=False)
    old_path = tmp_path / "old.csv"
    new_path = tmp_path / "new.csv"
    old_path.write_text("old", encoding="utf-8")
    new_path.write_text("new", encoding="utf-8")
    monkeypatch.setattr(
        staging, "_completed_trades",
        lambda path, vintage: trades[vintage].copy(),
    )
    return old_path, new_path, feature_path, tmp_path / "staged.parquet", trades


def test_features_are_from_signal_bar_before_entry(tmp_path, monkeypatch):
    old_path, new_path, feature_path, output_path, _ = _fixtures(tmp_path, monkeypatch)
    summary = staging.stage_corrected(old_path, new_path, feature_path, output_path)
    result = pd.read_parquet(output_path)
    assert summary["total_selected"] == 2
    assert summary["positive_outcomes"] == 2
    assert result["closed_bar_cross"].all()
    assert (result[FEATURE_NAMES[0]] == 65).all()
    assert (result["candidate_time"] < result["entry_time"]).all()
    assert (result["Date/Time"] == result["candidate_time"]).all()
    assert (result["t1"] == result["exit_time"]).all()
    assert result["Label"].tolist() == [1, 1]


def test_rejects_entry_without_preceding_closed_cross(tmp_path, monkeypatch):
    old_path, new_path, feature_path, output_path, trades = _fixtures(tmp_path, monkeypatch)
    trades["old"].loc[0, "entry_time"] += pd.Timedelta(seconds=30)
    with pytest.raises(ValueError, match="lacks a crossover"):
        staging.stage_corrected(old_path, new_path, feature_path, output_path)
    assert not output_path.exists()
