"""Exercise real preparation/merge outputs at the backtester boundary."""
import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from backtester.config import BarSpec, Config, Policy
from backtester.data import source_inventory
from backtester.run import run
from strategies import StrategySpec
from training_mlp.prepare_historical_vp import prepare
from training_mlp.merge_adjusted_tick_history import merge_vintages
from training_mlp.splice_historical_vintages import splice_vintages


def raw_export(path, days, offset=0):
    rows = []
    for day in days:
        for second, price in enumerate([6000, 6000, 5999, 5999, 6000, 6000, 6001, 6001, 6001, 6001]):
            rows.append({"Date": day, "Time": f"09:30:{second:02d}",
                         "Open": price + offset, "High": price + offset,
                         "Low": price + offset, "Close": price + offset, "Up": 2, "Down": 1})
    pd.DataFrame(rows).to_csv(path, index=False)


def replay_merged(root, output):
    config = Config(str(root), str(output), "2026-06-15", "2026-06-16",
                    bars=[BarSpec("time", 1), BarSpec("tick", 2), BarSpec("volume", 6)],
                    strategy=StrategySpec("ma_cross", {"fast": 1, "slow": 2}),
                    execution_mode="preset", preset_policy=Policy(4, 4, 2), workers=1, min_trades=1)
    result = run(config)
    assert result["ticks"] == 20
    assert (output / "backtesting_results.html").is_file()
    for key in ("time_1", "tick_2", "volume_6"):
        assert (output / "prepared" / f"bars_{key}.parquet").is_file()
        assert (output / "prepared" / f"signals_{key}.parquet").is_file()
        policy = output / "policies" / key / "development/pt4_sl4_h2"
        trades = pd.read_parquet(policy / "trades.parquet")
        assert len(trades) == (4 if key == "time_1" else 2)
        assert trades["valid"].all()
        stats = json.loads((policy / "statistics.json").read_text())
        assert stats
        assert (policy / "results.html").is_file()
    return config


def test_raw_exports_through_preparation_splice_and_backtest(tmp_path):
    old_csv, new_csv = tmp_path / "old.txt", tmp_path / "new.txt"
    raw_export(old_csv, ["06/15/2026"])
    raw_export(new_csv, ["06/16/2026"], offset=20)
    old, new, merged = tmp_path / "old", tmp_path / "new", tmp_path / "merged"
    prepare([old_csv], old, symbol="@ES")
    prepare([new_csv], new, symbol="@ES")
    # The paired splice also requires bar exports; one tick is a valid tiny OHLC fixture.
    old_bars, new_bars = tmp_path / "old_bars.csv", tmp_path / "new_bars.csv"
    pd.read_csv(old_csv).iloc[[0]].to_csv(old_bars, index=False)
    pd.read_csv(new_csv).iloc[[0]].to_csv(new_bars, index=False)
    splice_vintages(old_bars, new_bars, old, new, tmp_path / "spliced_bars.csv", merged,
                    cutoff_session="2026-06-15")
    output = tmp_path / "run"
    config = replay_merged(merged, output)
    sources, _ = source_inventory(config)
    assert [s["vintage"] for s in sources] == ["old", "new"]
    prices = np.load(output / "prepared/prices.npy")
    assert prices[0] == 6000 and prices[10] == 6020
    bars = pd.read_parquet(output / "prepared/bars_tick_2.parquet")
    assert bars["volume"].tolist() == [6] * 10


def test_adjusted_merge_output_consumed_without_second_adjustment(tmp_path):
    old_csv, new_csv = tmp_path / "old.txt", tmp_path / "new.txt"
    raw_export(old_csv, ["06/15/2026", "06/16/2026"])
    raw_export(new_csv, ["06/16/2026"], offset=20)
    old, new, merged = tmp_path / "old", tmp_path / "new", tmp_path / "merged"
    prepare([old_csv], old, symbol="@ES")
    prepare([new_csv], new, symbol="@ES")
    manifest = merge_vintages(old, new, merged)
    assert manifest["older_price_adjustment_points"] == 20
    output = tmp_path / "run"
    replay_merged(merged, output)
    prices = np.load(output / "prepared/prices.npy")
    assert prices[0] == prices[10] == 6020
    # Sources remain unchanged.
    assert pq.ParquetFile(old / "parquet/session_date=2026-06-15/ticks.parquet").read()["price"][0].as_py() == 6000


def test_incomplete_archive_rejected_before_output_created(tmp_path):
    root = tmp_path / "ticks"
    root.mkdir()
    (root / "INCOMPLETE.txt").write_text("failed merge")
    config = Config(str(root), str(tmp_path / "run"), "2026-06-15", "2026-06-16")
    with pytest.raises(ValueError, match="INCOMPLETE"):
        run(config)
    assert not (tmp_path / "run").exists()


def test_missing_volume_rejected_at_source_boundary(tmp_path):
    root = tmp_path / "ticks"
    partition = root / "parquet/session_date=2026-06-15/ticks.parquet"
    partition.parent.mkdir(parents=True)
    pd.DataFrame({"timestamp": pd.to_datetime(["2026-06-15 09:30:00"]), "price": [6000.]}).to_parquet(partition)
    config = Config(str(root), str(tmp_path / "run"), "2026-06-15", "2026-06-16")
    with pytest.raises(ValueError, match="volume"):
        run(config)
    assert not (tmp_path / "run").exists()


def test_volume_bars_work_with_exit_sweep_and_surface_report(tmp_path):
    raw = tmp_path / "ticks.txt"
    raw_export(raw, ["06/15/2026", "06/16/2026"])
    root = tmp_path / "ticks"
    prepare([raw], root, symbol="@ES")
    output = tmp_path / "sweep"
    config = Config(str(root), str(output), "2026-06-15", "2026-06-16",
                    bars=[BarSpec("volume", 6)],
                    strategy=StrategySpec("ma_cross", {"fast": 1, "slow": 2}),
                    profits=[1, 4], stops=[1, 4], holds=[2], workers=1,
                    max_evaluations=4, min_trades=1)
    run(config)
    report = output / "reports/volume_6"
    for name in ("index.html", "policies.csv", "regions.json", "selection.json",
                 "surface_h2.png", "surface3d_h2.png"):
        assert (report / name).is_file()
