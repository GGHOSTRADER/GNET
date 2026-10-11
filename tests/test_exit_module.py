from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from exit_module.collect import TickStore, _required_entries, collect_exit_data
from exit_module.replay import ExitPolicy, policy_grid, replay_long, replay_long_grid


def _ticks(*offset_and_price: tuple[int, float]) -> tuple[np.ndarray, np.ndarray]:
    start = np.datetime64("2026-06-15T10:00:00", "ns")
    times = np.array([start + np.timedelta64(second, "s") for second, _ in offset_and_price])
    prices = np.array([price for _, price in offset_and_price], dtype=float)
    return times, prices


def test_first_price_barrier_wins_in_file_order_even_with_equal_timestamps() -> None:
    times, prices = _ticks((0, 100.0), (1, 101.0), (1, 99.0))
    result = replay_long(
        times, prices, entry_time=times[0], entry_price=100.0,
        policy=ExitPolicy(4, 4, 30),
    )
    assert result.reason == "profit"
    assert result.exit_price == 101.0
    assert result.net_pnl_usd == pytest.approx(43.52)


def test_stop_gap_uses_first_observed_price_not_optimistic_stop_level() -> None:
    times, prices = _ticks((0, 100.0), (1, 98.75))
    result = replay_long(
        times, prices, entry_time=times[0], entry_price=100.0,
        policy=ExitPolicy(4, 4, 30),
    )
    assert result.reason == "loss"
    assert result.exit_price == 98.75
    assert result.net_pnl_usd == pytest.approx(-68.98)


def test_time_barrier_precedes_price_test_at_its_deadline() -> None:
    times, prices = _ticks((0, 100.0), (2, 100.25), (5, 101.0))
    result = replay_long(
        times, prices, entry_time=times[0], entry_price=100.0,
        policy=ExitPolicy(4, 4, 3),
    )
    assert result.reason == "time"
    assert result.exit_price == 101.0
    assert result.time_exit_delay_seconds == 2.0


def test_missing_future_tick_is_censored_and_grid_is_deduplicated() -> None:
    times, prices = _ticks((0, 100.0), (1, 100.25))
    result = replay_long(
        times, prices, entry_time=times[0], entry_price=100.0,
        policy=ExitPolicy(4, 4, 5),
    )
    assert result.reason == "censored"
    assert result.net_pnl_usd is None
    assert len(policy_grid((2, 1, 2), (4,), (30, 60))) == 4
    with pytest.raises(ValueError):
        ExitPolicy(0, 4, 30)


def test_grid_matches_single_policy_replay() -> None:
    times, prices = _ticks(
        (0, 100.0), (1, 100.25), (2, 99.75), (3, 100.5), (4, 99.0)
    )
    policies = policy_grid((1, 2, 4), (1, 2, 4), (2, 3, 5))
    grid = replay_long_grid(
        times, prices, entry_time=times[0], entry_price=100.0, policies=policies
    )
    singles = tuple(
        replay_long(times, prices, entry_time=times[0], entry_price=100.0, policy=p)
        for p in policies
    )
    assert grid == singles


def test_collector_writes_outcomes_and_trade_station_audit(tmp_path) -> None:
    entries = tmp_path / "entries.parquet"
    pd.DataFrame([{
        "trade_number": 7,
        "vintage": "old",
        "candidate_time": pd.Timestamp("2026-06-15 10:00:00"),
        "entry_time": pd.Timestamp("2026-06-15 10:00:30"),
        "exit_time": pd.Timestamp("2026-06-15 10:00:30"),
        "entry_price": 100.0,
        "exit_price": 101.0,
        "exit_signal": "Profit Target",
        "net_pnl_at_3_24_per_side": 43.52,
    }]).to_parquet(entries, index=False)
    tick_root = tmp_path / "ticks"
    partition = tick_root / "parquet" / "session_date=2026-06-15"
    partition.mkdir(parents=True)
    times, prices = _ticks((0, 100.0), (1, 100.25), (2, 101.0), (31, 100.5))
    pd.DataFrame({"timestamp": times, "price": prices}).to_parquet(
        partition / "ticks.parquet", index=False
    )
    output = tmp_path / "out"
    manifest = collect_exit_data(
        entries, tick_root, output,
        profits=(4, 8), stops=(4,), hold_seconds=(1, 10),
    )
    assert manifest["entries"] == 1
    assert manifest["policies"] == 4
    assert manifest["baseline_4tick_matches"] == 1
    assert manifest["dataset_ready_for_training"] is True
    rows = pd.read_parquet(output / "outcomes/entry_session=2026-06-15/outcomes.parquet")
    assert set(rows["exit_reason"]) == {"profit", "time"}
    assert rows["baseline_replay_matched"].all()
    assert not (output / "INCOMPLETE.txt").exists()
    assert json.loads((output / "manifest.json").read_text())["no_model_trained"]
    with pytest.raises(FileExistsError):
        collect_exit_data(
            entries, tick_root, output,
            profits=(4,), stops=(4,), hold_seconds=(30,),
        )


def test_older_prior_bar_csv_is_accepted_without_rewriting_source(tmp_path) -> None:
    path = tmp_path / "older_entries.csv"
    pd.DataFrame([{
        "trade_number": 12,
        "vintage": "old_libb",
        "feature_time": "2026-04-07 10:00:00",
        "entry_time": "2026-04-07 10:00:30",
        "exit_time": "2026-04-07 10:01:00",
        "entry_price": 100.0,
        "exit_price": 101.0,
        "exit_signal": "Profit Target",
        "net_pnl_at_3_24_per_side": 43.52,
    }]).to_csv(path, index=False)

    entries = _required_entries(path)
    assert entries.loc[0, "candidate_time"] == pd.Timestamp("2026-04-07 10:00:00")
    assert entries.loc[0, "entry_market_time"] == pd.Timestamp("2026-04-07 10:00:00")
    assert entries.loc[0, "vintage"] == "old_libb"


def test_tick_store_crosses_session_and_retains_time_exit_delay(tmp_path) -> None:
    root = tmp_path / "ticks"
    for day, stamp, price in (
        ("2026-06-15", "2026-06-15 16:59:59", 100.0),
        ("2026-06-16", "2026-06-15 18:00:00", 99.5),
    ):
        partition = root / "parquet" / f"session_date={day}"
        partition.mkdir(parents=True)
        pd.DataFrame({"timestamp": [pd.Timestamp(stamp)], "price": [price]}).to_parquet(
            partition / "ticks.parquet", index=False
        )
    store = TickStore(root)
    times, prices, reached = store.window(
        pd.Timestamp("2026-06-15 16:59:59"), pd.Timestamp("2026-06-15 17:00:29")
    )
    result = replay_long(
        times, prices, entry_time=np.datetime64("2026-06-15T16:59:59"),
        entry_price=100.0, policy=ExitPolicy(4, 4, 30),
    )
    assert reached
    assert result.reason == "time"
    assert result.exit_price == 99.5
    assert result.time_exit_delay_seconds > 0
    unavailable = replay_long_grid(
        times, prices, entry_time=np.datetime64("2026-06-15T16:59:59"),
        entry_price=100.0, policies=(ExitPolicy(4, 4, 30),),
        max_time_exit_delay_seconds=30,
    )[0]
    assert unavailable.reason == "unavailable_time"
    assert unavailable.net_pnl_usd is None
