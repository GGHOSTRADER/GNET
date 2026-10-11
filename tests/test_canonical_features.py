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
    engine = FeatureEngine(vwap_mode="bar")
    outputs = []
    cumulative_price_volume = 0.0
    cumulative_volume = 0
    for bar_number, (timestamp, close, up, down) in enumerate(source, start=1):
        volume = up + down
        average_price = ((close - 0.25) + (close + 0.50) + (close - 0.50) + close) / 4.0
        cumulative_price_volume += average_price * volume
        cumulative_volume += volume
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
                    vwap=cumulative_price_volume / cumulative_volume,
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


def test_spliced_canonical_features_restart_full_window_at_handoff():
    old = _frame(_bars(70))
    new = _frame(_bars(70))
    new["Date/Time"] += pd.Timedelta(days=133)
    new[["Open", "High", "Low", "Close"]] += 67.75
    joined = pd.concat([old, new], ignore_index=True)
    boundary = new.iloc[0]["Date/Time"]

    result = engineer_features(joined, vwap_mode="canonical", reset_at=boundary)
    standalone = engineer_features(new, vwap_mode="canonical")

    assert result.loc[69, "vwap_distance"] == pytest.approx(
        engineer_features(old, vwap_mode="canonical").loc[69, "vwap_distance"]
    )
    assert result.loc[70:128, list(FEATURE_NAMES)].isna().all().all()
    for name in FEATURE_NAMES:
        assert result.loc[129, name] == pytest.approx(standalone.loc[59, name])


def test_canonical_engine_matches_tradestation_vwap_formula():
    frame = _frame(_bars())
    canonical = engineer_features(frame)

    log_hl = np.log(frame["High"] / frame["Low"]) ** 2
    expected_rank = frame["Volume"].rolling(60).apply(
        lambda values: pd.Series(values).rank(pct=True).iloc[-1], raw=False
    )
    average_price = frame[["Open", "High", "Low", "Close"]].mean(axis=1)
    expected_vwap = (average_price * frame["Volume"]).cumsum() / frame["Volume"].cumsum()
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


def test_explicit_bar_vwap_mode_uses_bar_vwap_not_process_history():
    source = _bars(70)
    full = _live_outputs(source)[-1]
    restarted_source = source[-60:]
    frame = _frame(source)
    average_price = frame[["Open", "High", "Low", "Close"]].mean(axis=1)
    full_day_vwap = float(
        (average_price * frame["Volume"]).cumsum().iloc[-1]
        / frame["Volume"].cumsum().iloc[-1]
    )

    engine = FeatureEngine(vwap_mode="bar")
    restarted = None
    for bar_number, (timestamp, close, up, down) in enumerate(restarted_source, start=1):
        restarted = engine.update(
            SimpleNamespace(
                date=1260406,
                time_s=timestamp.hour * 3600 + timestamp.minute * 60 + timestamp.second,
                high=close + 0.50,
                low=close - 0.50,
                close=close,
                up=up,
                down=down,
                vwap=full_day_vwap if bar_number == 60 else 5000.0,
                bar_num=bar_number,
            )
        )

    assert full is not None
    assert restarted is not None
    assert restarted.vwap_distance == pytest.approx(full.vwap_distance)


def test_canonical_vwap_uses_all_seen_session_bars_not_bar_field():
    engine = FeatureEngine()
    result = None
    for index in range(70):
        close = 5000.0 + index * 0.25
        result = engine.update(SimpleNamespace(
            date=1260406, time_s=34200 + index * 30,
            high=close + 0.5, low=close - 0.5, close=close,
            up=100, down=100, vwap=1.0,
        ))
    assert result is not None
    expected_vwap = sum(5000.0 + index * 0.25 for index in range(70)) / 70
    assert result.vwap_distance == pytest.approx(
        (5000.0 + 69 * 0.25 - expected_vwap) / 1.0
    )


def test_canonical_vwap_resets_at_es_open_and_not_midnight():
    engine = FeatureEngine()
    result = None
    for index in range(60):
        result = engine.update(SimpleNamespace(
            date=1260406, time_s=18 * 3600 + 30 + index * 30,
            high=5001.0, low=4999.0, close=5000.0,
            up=100, down=100, vwap=1.0,
        ))
    assert result is not None
    midnight = engine.update(SimpleNamespace(
        date=1260407, time_s=30, high=5002.0, low=5000.0,
        close=5001.0, up=100, down=100, vwap=1.0,
    ))
    assert midnight is not None
    assert midnight.vwap_distance == pytest.approx(
        (5001.0 - (60 * 5000.0 + 5001.0) / 61) / 2.0
    )
    next_session = engine.update(SimpleNamespace(
        date=1260407, time_s=18 * 3600 + 30,
        high=5003.0, low=5001.0, close=5002.0,
        up=100, down=100, vwap=1.0,
    ))
    assert next_session is not None
    assert next_session.vwap_distance == pytest.approx(0.0)
