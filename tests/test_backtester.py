from __future__ import annotations

import json
from pathlib import Path
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from backtester.bars import aggregate
from backtester.signals import generate_signals
from strategies.ma_cross import MACrossStrategy
from strategies import StrategySpec, build_strategy
from backtester.config import BarSpec, Config, Policy, load_config
from backtester.data import ns_local, prepare, source_inventory
from backtester.replay import replay_policy
from backtester.report import find_regions
from backtester.search import adaptive_search
from backtester.workers import Evaluator


def configuration(tmp_path, **kwargs):
    return Config(str(tmp_path / "ticks"), str(tmp_path / "out"), "2026-06-15", "2026-06-15",
                  strategy=StrategySpec("ma_cross", {"fast": 1, "slow": 2}), min_trades=1, **kwargs)


def example_tape():
    times = np.arange(8, dtype="int64") * 1_000_000_000
    prices = np.array([100, 100.25, 100, 100.25, 100.5, 101, 100, 100.25])
    sessions = [{"begin": 0, "end": 8, "vintage": "old", "flatten_ns": 20_000_000_000}]
    signals = [{"signal_id": 0, "entry_event": 0, "available_after_event": -1, "signal_ns": 0, "session_index": 0},
               {"signal_id": 1, "entry_event": 2, "available_after_event": 1, "signal_ns": 2_000_000_000, "session_index": 0}]
    return times, prices, sessions, signals


def test_exit_changes_later_trade_eligibility(tmp_path):
    times, prices, sessions, signals = example_tape()
    config = configuration(tmp_path)
    narrow, narrow_trades, _ = replay_policy(times, prices, signals, sessions, Policy(1, 4, 6), config)
    wide, wide_trades, skipped = replay_policy(times, prices, signals, sessions, Policy(4, 4, 6), config)
    assert [t["entry_event"] for t in narrow_trades] == [0, 2]
    assert [t["entry_event"] for t in wide_trades] == [0]
    assert skipped == [{"signal_id": 1, "reason": "position_open"}]
    assert narrow["net_pnl"] == pytest.approx(2 * (12.5 - 6.48))
    assert wide["net_pnl"] == pytest.approx(50 - 6.48)


def test_signal_during_position_is_not_queued_after_exit(tmp_path):
    times, prices, sessions, signals = example_tape()
    signals[1].update(entry_event=6, available_after_event=3, signal_ns=3_000_000_000)
    _, trades, skipped = replay_policy(times, prices, signals, sessions, Policy(4, 4, 6), configuration(tmp_path))
    assert len(trades) == 1
    assert skipped[0]["reason"] == "position_open"


def test_tick_bars_same_timestamp_enter_only_on_next_event():
    times = np.zeros(9, dtype=np.int64)
    prices = np.array([2, 2, 1, 1, 2, 2, 3, 3, 3], dtype=float)
    bars = aggregate(times, prices, np.ones(9, dtype=int), BarSpec("tick", 2), 0, 100, 0)
    signals = generate_signals(bars, BarSpec("tick", 2), times, 0, MACrossStrategy(fast=1, slow=2))
    assert len(signals) == 1
    assert signals[0]["bar_last_event"] == 5
    assert signals[0]["entry_event"] == 6
    assert not bars[-1]["complete"]


def test_time_bars_have_no_empty_invented_bars_and_exclude_boundary_tick():
    t = np.array([0, 1, 30, 31, 90, 91], dtype=np.int64) * 1_000_000_000
    p = np.array([100, 101, 99, 100, 102, 103], dtype=float)
    bars = aggregate(t, p, np.ones(6, dtype=int), BarSpec("time", 30), 0, 120_000_000_000, 0)
    assert len(bars) == 3
    assert bars[0]["high"] == 101 and bars[0]["tick_count"] == 2
    assert bars[1]["open"] == 99 and bars[1]["start_ns"] == 30_000_000_000
    assert [b["complete"] for b in bars] == [True, True, False]


def test_deadline_precedes_same_tick_price_hit_and_costs_apply(tmp_path):
    times = np.array([0, 2], dtype=np.int64) * 1_000_000_000
    sessions = [{"begin": 0, "end": 2, "vintage": "old", "flatten_ns": 99_000_000_000}]
    signal = [{"signal_id": 0, "entry_event": 0, "available_after_event": -1, "signal_ns": 0, "session_index": 0}]
    _, trades, _ = replay_policy(times, np.array([100., 102.]), signal, sessions, Policy(4, 4, 2), configuration(tmp_path))
    assert trades[0]["exit_reason"] == "time"
    assert trades[0]["net_pnl"] == pytest.approx(100 - 6.48)


def test_stop_gap_and_delayed_deadline_are_observed_not_fabricated(tmp_path):
    times, _, sessions, signals = example_tape()
    _, trades, _ = replay_policy(times, np.array([100, 98.75, 100, 100, 100, 100, 100, 100]), signals[:1], sessions, Policy(4, 4, 6), configuration(tmp_path))
    assert trades[0]["net_pnl"] == pytest.approx(-62.5 - 6.48)
    times[1:] += 100_000_000_000
    summary, trades, _ = replay_policy(times, np.full(8, 100.), signals[:1], sessions, Policy(4, 4, 2), configuration(tmp_path))
    assert not trades[0]["valid"] and not summary["eligible"]
    assert trades[0]["exit_delay_seconds"] == 99


def test_limit_gap_does_not_invent_equity_peak(tmp_path):
    times, _, sessions, signals = example_tape()
    prices = np.array([100., 103., 100., 100., 100., 100., 100., 100.])
    summary, trades, _ = replay_policy(times, prices, signals[:1], sessions, Policy(4, 4, 6), configuration(tmp_path))
    assert trades[0]["exit_price"] == 101
    assert summary["net_pnl"] == pytest.approx(43.52)
    assert summary["max_drawdown"] == pytest.approx(6.48)


def test_unresolved_position_blocks_signals_and_cannot_cross_vintage(tmp_path):
    t, _, sessions, signals = example_tape()
    sessions = [{**sessions[0], "end": 3}, {"begin": 3, "end": 8, "vintage": "new", "flatten_ns": 20_000_000_000}]
    signals[1].update(entry_event=4, available_after_event=3, signal_ns=int(t[4]), session_index=1)
    summary, trades, skipped = replay_policy(t, np.full(8, 100.), signals, sessions, Policy(4, 4, 10), configuration(tmp_path, session_exit="carry"))
    assert trades[0]["exit_reason"] == "vintage_boundary"
    assert summary["unresolved_trades"] == 1 and not summary["eligible"]
    assert skipped[0]["reason"] == "position_open"


def test_session_flatten_uses_first_tick_after_prescheduled_cutoff(tmp_path):
    t, p, sessions, signals = example_tape()
    sessions[0]["flatten_ns"] = 3_000_000_000
    _, trades, _ = replay_policy(t, p, signals[:1], sessions, Policy(8, 8, 20), configuration(tmp_path))
    assert trades[0]["exit_event"] == 3 and trades[0]["exit_reason"] == "session"


def test_search_jump_recovers_and_stops_after_failed_probes(tmp_path):
    config = configuration(tmp_path, profits=list(range(1, 21)), stops=[1], holds=[30],
                           workers=1, search_regions=1, patience=1, jump_factor=3, failed_jumps=2, max_evaluations=100)
    def evaluate(points):
        return [{"score": 20.0 if p[0] == 3 else 10.0 if p[0] == 0 else 0.0} for p in points]
    results, trace, stop = adaptive_search(config, evaluate)
    assert (3, 0, 0) in results
    assert any(t["action"] == "jump" and t["improved"] for t in trace)
    assert stop == "regions_exhausted"
    assert len(results) < 20


def test_search_is_bounded_and_reproducible(tmp_path):
    config = configuration(tmp_path, max_evaluations=3)
    evaluate = lambda points: [{"score": float(sum(p))} for p in points]
    a = adaptive_search(config, evaluate)
    b = adaptive_search(config, evaluate)
    assert a == b and len(a[0]) == 3 and a[2] == "evaluation_budget"


def test_region_area_requires_four_tested_qualifying_corners():
    rows = [{"profit_ticks": p, "stop_ticks": s, "hold_seconds": 30, "eligible": True,
             "net_pnl": 10., "positive_blocks": 3, "policy_id": f"{p}_{s}"}
            for p, s in ((1, 1), (3, 1), (1, 4), (3, 4))]
    assert find_regions(rows, [1, 3], [1, 4], 2)[0]["supported_area_ticks_squared"] == 6
    assert find_regions(rows[:3], [1, 3], [1, 4], 2)[0]["supported_area_ticks_squared"] == 0


def test_serial_parallel_and_cached_results_match(tmp_path):
    config = configuration(tmp_path, bars=[BarSpec("tick", 2)], profits=[1, 4], stops=[4], holds=[10], workers=1, policy_batch_size=1)
    partition = Path(config.tick_root) / "parquet/session_date=2026-06-15"
    partition.mkdir(parents=True)
    pd.DataFrame({"timestamp": pd.date_range("2026-06-15 10:00:00", periods=16, freq="s"),
                  "price": [100, 100, 99, 99, 100, 100, 100, 100.25, 99, 99, 100, 100, 100, 101, 100, 100],
                  "volume": [1] * 16}).to_parquet(partition / "ticks.parquet", index=False)
    sources, identity = source_inventory(config)
    prepare(config, sources, identity, progress=lambda *a, **k: None)
    with Evaluator(config, "tick_2") as evaluator:
        serial = evaluator([(0, 0, 0), (1, 0, 0)])
    # Confirmation is a distinct output scope, so processes actually execute replay.
    config.confirmation_start = config.start_session
    config.workers = 2
    with Evaluator(config, "tick_2", "confirmation") as evaluator:
        parallel = evaluator([(0, 0, 0), (1, 0, 0)])
        cached = evaluator([(0, 0, 0), (1, 0, 0)])
    for a, b in zip(serial, parallel):
        assert {k: v for k, v in a.items() if k != "phase"} == {k: v for k, v in b.items() if k != "phase"}
        policy_root = Path(config.output) / "policies" / "tick_2"
        for filename in ("trades.parquet", "skipped_signals.parquet"):
            pd.testing.assert_frame_equal(
                pd.read_parquet(policy_root / "development" / a["policy_id"] / filename),
                pd.read_parquet(policy_root / "confirmation" / b["policy_id"] / filename),
            )
    assert parallel == cached


def test_confirmation_freezes_search_and_reuses_completed_results(tmp_path, monkeypatch):
    from backtester.run import run
    config = configuration(tmp_path, bars=[BarSpec("tick", 2)], profits=[1], stops=[4], holds=[10],
                           workers=1, max_evaluations=1, confirmation_start="2026-06-16")
    config.end_session = "2026-06-16"
    for day in ("2026-06-15", "2026-06-16"):
        partition = Path(config.tick_root) / f"parquet/session_date={day}"
        partition.mkdir(parents=True)
        pd.DataFrame({"timestamp": pd.date_range(f"{day} 10:00:00", periods=10, freq="s"),
                      "price": [100, 100, 99, 99, 100, 100, 100, 100.25, 100, 100],
                      "volume": [1] * 10}).to_parquet(partition / "ticks.parquet", index=False)
    monkeypatch.setattr("backtester.exit_analyzer.write_report", lambda cfg, key, rows, reason:
                        {"bar_spec": key, "selection": rows[0]})
    development = run(config)
    assert development["reports"][0]["selection"]["closed_trades"] == 1
    confirmation = run(config, confirm=True)
    assert confirmation["results"][0]["closed_trades"] == 1
    assert run(config, confirm=True) == confirmation
    with pytest.raises(ValueError, match="search is frozen"):
        run(config, resume=True)


def test_invalid_configuration_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        configuration(tmp_path, profits=[4, 1]).validate()
    with pytest.raises(ValueError):
        Policy(0, 4, 30)


def test_strategy_config_owns_ma_parameters_and_identity(tmp_path):
    config = configuration(tmp_path)
    assert not {"fast", "slow", "reset_ma_each_session"} & config.dictionary().keys()
    assert config.dictionary()["strategy"] == {"name": "ma_cross", "parameters": {"fast": 1, "slow": 2}}
    assert config.identity() != replace(config, strategy=StrategySpec("ma_cross", {"fast": 1, "slow": 3})).identity()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.dictionary()))
    loaded = load_config(path)
    assert loaded.strategy == config.strategy
    data = config.dictionary()
    data["fast"] = 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="strategy.parameters"):
        load_config(path)


def test_ma_strategy_validates_its_parameters_and_controls_reset():
    for parameters in ({"fast": 18, "slow": 9}, {"fast": True}, {"unknown": 1}, {"reset_each_session": "false"}):
        with pytest.raises(ValueError):
            build_strategy(StrategySpec("ma_cross", parameters))
    with pytest.raises(ValueError, match="unknown entry strategy"):
        build_strategy(StrategySpec("unregistered"))
    carry = MACrossStrategy(fast=1, slow=2)
    reset = MACrossStrategy(fast=1, slow=2, reset_each_session=True)
    for strategy in (carry, reset):
        assert not strategy.on_bar({"close": 2})
        assert not strategy.on_bar({"close": 1})
        strategy.on_session_start()
    assert carry.on_bar({"close": 2})
    assert not reset.on_bar({"close": 2})


def test_signal_engine_uses_strategy_interface_not_ma_parameters(monkeypatch):
    from strategies.registry import STRATEGIES
    class UpBarStrategy:
        def on_session_start(self):
            pass

        def on_bar(self, bar):
            return bar["close"] > bar["open"]

    monkeypatch.setitem(STRATEGIES, "test_up_bar", UpBarStrategy)
    times = np.arange(5, dtype=np.int64) * 1_000_000_000
    bars = aggregate(times, np.array([100., 101., 100., 99., 100.]), np.ones(5, dtype=int), BarSpec("tick", 2), 0, 10_000_000_000, 0)
    strategy = build_strategy(StrategySpec("test_up_bar"))
    signals = generate_signals(bars, BarSpec("tick", 2), times, 0, strategy)
    assert len(signals) == 1
    assert signals[0]["entry_event"] == 2


def test_strategy_plugin_imports_without_backtester():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-c",
        "import sys; from strategies import StrategySpec, build_strategy; "
        "s=build_strategy(StrategySpec()); "
        "assert s.__class__.__module__=='strategies.ma_cross'; "
        "assert not any(n=='backtester' or n.startswith('backtester.') for n in sys.modules)"],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_strategy_source_change_invalidates_cache_identity(tmp_path, monkeypatch):
    config = configuration(tmp_path)
    partition = Path(config.tick_root) / "parquet/session_date=2026-06-15"
    partition.mkdir(parents=True)
    pd.DataFrame({"timestamp": [pd.Timestamp("2026-06-15 10:00:00")],
                  "price": [100.], "volume": [1]}).to_parquet(partition / "ticks.parquet", index=False)
    _, original = source_inventory(config)
    original_read = Path.read_bytes
    def changed_source(path):
        content = original_read(path)
        return content + b"\n# simulated strategy revision\n" if path.name == "ma_cross.py" else content
    monkeypatch.setattr(Path, "read_bytes", changed_source)
    _, changed = source_inventory(config)
    assert changed != original
