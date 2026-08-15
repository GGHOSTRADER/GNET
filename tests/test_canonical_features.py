"""Parity and boundary tests for the shared MA2CrossLE feature engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from feat_files.canonical_features import FEATURE_NAMES, FeatureEngine
from training_mlp.study_pipeline import engineer_features


def _bars(count: int = 75):
    start = datetime(2026, 4, 6, 9, 30)
    result = []
    for index in range(count):
        timestamp = start + timedelta(seconds=30 * index)
        close = 5000.0 + index * 0.25
        # Repeated totals exercise pandas-compatible average ranking for ties.
        up = 100 + index % 4
        down = 80 + index % 3
        result.append((timestamp, close, up, down))
    return result


def _frame(source):
    return pd.DataFrame(
        {
            "Date/Time": [item[0] for item in source],
            "Open": [item[1] - 0.25 for item in source],
            "High": [item[1] + 0.50 for item in source],
            "Low": [item[1] - 0.50 for item in source],
            "Close": [item[1] for item in source],
            "Up": [item[2] for item in source],
            "Down": [item[3] for item in source],
            "Volume": [item[2] + item[3] for item in source],
        }
    )


def _live_outputs(source):
    engine = FeatureEngine()
    outputs = []
    for bar_number, (timestamp, close, up, down) in enumerate(source, start=1):
        outputs.append(
            engine.update(
                SimpleNamespace(
                    date=1260406,
                    time_s=timestamp.hour * 3600 + timestamp.minute * 60 + timestamp.second,
                    high=close + 0.50,
                    low=close - 0.50,
                    close=close,
                    up=up,
                    down=down,
                    bar_num=bar_number,
                )
            )
        )
    return outputs


def test_training_and_live_adapters_produce_identical_features():
    source = _bars()
    trained = engineer_features(_frame(source))
    live = _live_outputs(source)

    for index in range(59, len(source)):
        assert live[index] is not None
        for name in FEATURE_NAMES:
            assert getattr(live[index], name) == pytest.approx(
                trained.loc[index, name], rel=1e-12, abs=1e-12
            )


def test_canonical_engine_matches_original_training_formulas():
    frame = _frame(_bars())
    canonical = engineer_features(frame)

    log_hl = np.log(frame["High"] / frame["Low"]) ** 2
    expected_rank = frame["Volume"].rolling(60).apply(
        lambda values: pd.Series(values).rank(pct=True).iloc[-1], raw=False
    )
    expected_vwap = (frame["Close"] * frame["Volume"]).cumsum() / frame["Volume"].cumsum()
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - frame["Close"].shift()).abs(),
            (frame["Low"] - frame["Close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    last = len(frame) - 1
    assert canonical.loc[last, "parkinson_vol_30"] == pytest.approx(
        np.sqrt(log_hl.rolling(30).sum().iloc[last] / (4 * 30 * np.log(2)))
    )
    assert canonical.loc[last, "volume_percentile"] == pytest.approx(expected_rank.iloc[last])
    assert canonical.loc[last, "vwap_distance"] == pytest.approx(
        (frame.loc[last, "Close"] - expected_vwap.iloc[last])
        / true_range.rolling(14).mean().iloc[last]
    )


def test_tradestation_year_and_session_boundary_match_training():
    outputs = _live_outputs(_bars(60))
    result = outputs[-1]
    assert result is not None
    assert result.day_of_week == date(2026, 4, 6).weekday()
    assert result.is_first_last_30min == 1
