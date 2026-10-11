"""Analytical fixtures and integration coverage for the independent reports."""
from dataclasses import replace
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

from backtester.config import BarSpec, Config, Policy, ResultsSpec, load_config
from backtester.replay import replay_policy
from backtester.results import build_equity, calculate_results, concentration, drawdown_episodes, sharpe_statistics
from backtester.run import run
from strategies import StrategySpec


def config_for(tmp_path, **kwargs):
    return Config(str(tmp_path / "ticks"), str(tmp_path / "out"), "2026-06-15", "2026-06-15",
                  bars=[BarSpec("tick", 2)], strategy=StrategySpec("ma_cross", {"fast": 1, "slow": 2}),
                  workers=1, min_trades=1, **kwargs)


def replay_fixture(tmp_path, **kwargs):
    config = config_for(tmp_path, **kwargs)
    times = np.arange(7, dtype=np.int64) * 1_000_000_000
    prices = np.array([100., 100.25, 101., 100., 100.5, 99., 100.])
    signals = [dict(signal_id=0, entry_event=0, available_after_event=-1, signal_ns=0, session_index=0),
               dict(signal_id=1, entry_event=3, available_after_event=2, signal_ns=3_000_000_000, session_index=0)]
    sessions = [dict(begin=0, end=7, session="2026-06-15", vintage="old", flatten_ns=20_000_000_000)]
    summary, trades, _ = replay_policy(times, prices, signals, sessions, Policy(4, 4, 6), config)
    summary.update(identity="fixture", phase="development", bar_spec="tick_2")
    curve = build_equity(times, prices, trades, sessions, config, 0, len(times))
    return config, times, prices, signals, sessions, summary, trades, curve


def test_equity_reconciles_realized_costs_positions_and_peak(tmp_path):
    cfg, _, _, _, _, summary, trades, curve = replay_fixture(tmp_path, results=ResultsSpec(equity_sample_seconds=1))
    assert curve.liquidation_net_usd.iloc[0] == 0
    assert curve.liquidation_net_usd.iloc[-1] == pytest.approx(-12.96)
    assert curve.realized_net_usd.iloc[-1] == pytest.approx(summary["net_pnl"])
    marks = curve.loc[curve.event >= 0].drop_duplicates("event").set_index("event")
    assert marks.loc[0, "position_contracts"] == 1
    assert marks.loc[0, "liquidation_net_usd"] == pytest.approx(-6.48)
    assert marks.loc[2, "position_contracts"] == 0
    assert marks.loc[2, "liquidation_net_usd"] == pytest.approx(43.52)
    assert marks.loc[3, "realized_net_usd"] == pytest.approx(43.52)
    metrics, daily, _ = calculate_results(trades, curve, summary, cfg)
    assert metrics["path"]["max_drawdown_sampled_usd"] == pytest.approx(summary["max_drawdown"])
    assert metrics["execution"]["closed_trade_fees_usd"] == pytest.approx(12.96)
    assert metrics["performance"]["win_rate"] == .5
    assert metrics["performance"]["time_weighted_return"] is None
    assert "initial_capital" in metrics["risk_adjusted"]["unavailable_reason"]
    assert daily.net_change_usd.sum() == pytest.approx(-12.96)
    json.dumps(metrics, allow_nan=False)


def test_gap_target_uses_fill_not_later_observed_price(tmp_path):
    cfg, times, prices, signals, sessions, _, _, _ = replay_fixture(tmp_path)
    prices[2] = 110
    summary, trades, _ = replay_policy(times, prices, signals[:1], sessions, Policy(4, 4, 6), cfg)
    curve = build_equity(times, prices, trades, sessions, cfg, 0, len(times))
    assert curve.liquidation_net_usd.max() == pytest.approx(43.52)
    assert curve.liquidation_net_usd.iloc[-1] == pytest.approx(summary["net_pnl"])


def test_equal_timestamp_ticks_retain_entry_exit_order(tmp_path):
    cfg, times, prices, signals, sessions, _, _, _ = replay_fixture(tmp_path)
    times[:] = 0
    signals[1]["signal_ns"] = 0
    summary, trades, _ = replay_policy(times, prices, signals, sessions, Policy(4, 4, 6), cfg)
    curve = build_equity(times, prices, trades, sessions, cfg, 0, len(times))
    assert curve.event.tolist() == sorted(curve.event.tolist())
    assert curve.liquidation_net_usd.iloc[-1] == pytest.approx(summary["net_pnl"])
    assert curve.loc[curve.event == 0, "position_contracts"].iloc[0] == 1


def test_unresolved_vintage_is_not_marked_using_new_contract(tmp_path):
    cfg, times, prices, signals, _, _, _, _ = replay_fixture(tmp_path)
    sessions = [dict(begin=0, end=3, session="a", vintage="old", flatten_ns=20_000_000_000),
                dict(begin=3, end=7, session="b", vintage="new", flatten_ns=20_000_000_000)]
    summary, trades, _ = replay_policy(times, prices, signals[:1], sessions, Policy(40, 40, 60), cfg)
    summary.update(identity="fixture", phase="development", bar_spec="tick_2")
    curve = build_equity(times, prices, trades, sessions, cfg, 0, len(times))
    assert curve.loc[curve.event >= 3, "liquidation_net_usd"].isna().all()
    metrics, _, _ = calculate_results(trades, curve, summary, replace(cfg, results=ResultsSpec(initial_capital=10000)))
    assert metrics["status"] == "diagnostic_only"
    assert metrics["performance"]["time_weighted_return"] is None
    json.dumps(metrics, allow_nan=False)


def test_session_returns_include_flat_sessions_and_capital(tmp_path):
    cfg, times, prices, signals, _, _, _, _ = replay_fixture(tmp_path, results=ResultsSpec(initial_capital=10000))
    sessions = [dict(begin=0, end=3, session="a", vintage="old", flatten_ns=20_000_000_000),
                dict(begin=3, end=7, session="b", vintage="old", flatten_ns=20_000_000_000)]
    summary, trades, _ = replay_policy(times, prices, signals[:1], sessions, Policy(4, 4, 6), cfg)
    summary.update(identity="fixture", phase="development", bar_spec="tick_2")
    curve = build_equity(times, prices, trades, sessions, cfg, 0, len(times))
    metrics, daily, _ = calculate_results(trades, curve, summary, cfg)
    assert daily["return"].tolist() == pytest.approx([43.52 / 10000, 0])
    assert metrics["performance"]["time_weighted_return"] == pytest.approx(43.52 / 10000)
    assert metrics["risk_adjusted"]["sharpe_per_session"] is None  # only 2 observations


def test_no_trades_has_zero_pnl_not_fabricated_win_rate(tmp_path):
    cfg, times, prices, _, sessions, _, _, _ = replay_fixture(tmp_path)
    summary, trades, _ = replay_policy(times, prices, [], sessions, Policy(4, 4, 6), cfg)
    summary.update(identity="fixture", phase="development", bar_spec="tick_2")
    curve = build_equity(times, prices, trades, sessions, cfg, 0, len(times))
    metrics, _, episodes = calculate_results(trades, curve, summary, cfg)
    assert not episodes and curve.position_contracts.sum() == 0
    assert metrics["performance"]["win_rate"] is None
    assert metrics["performance"]["net_pnl"] == 0
    json.dumps(metrics, allow_nan=False)


def test_sampled_underwater_counts_recovery_and_terminal_episode():
    curve = pd.DataFrame({"time_ns": np.arange(7, dtype=np.int64) * 1_000_000_000,
                          "liquidation_net_usd": [0, 10, 5, 8, 10, 15, 12]})
    episodes = drawdown_episodes(curve)
    assert [e["depth_usd"] for e in episodes] == [5, 3]
    assert [e["duration_seconds"] for e in episodes] == [3, 1]
    assert [e["recovered"] for e in episodes] == [True, False]


def test_concentration_and_sharpe_have_analytical_values():
    assert concentration([1, 1, 1]) == pytest.approx(0)
    assert concentration([1, 0, 0]) == pytest.approx(1)
    assert concentration([1, 1]) is None
    values = np.array([-.02, -.01, 0., .01, .02])
    result = sharpe_statistics(values, ResultsSpec())
    assert result["sharpe_per_session"] == pytest.approx(0)
    assert result["probabilistic_sharpe_vs_zero"] == pytest.approx(.5)
    assert result["deflated_sharpe"] is None
    settings = ResultsSpec(effective_trials=10, trial_sharpe_variance=.25, trial_history_note="analytical fixture")
    result = sharpe_statistics(values, settings)
    benchmark = .5 * ((1-.5772156649015329) * NormalDist().inv_cdf(.9)
                     + .5772156649015329 * NormalDist().inv_cdf(1-1/(10*np.e)))
    assert result["deflated_benchmark_per_session"] == pytest.approx(benchmark)
    assert result["deflated_sharpe"] == pytest.approx(NormalDist().cdf(-benchmark * 2))
    assert sharpe_statistics([0, 0, 0], settings)["sharpe_per_session"] is None


@pytest.mark.parametrize("settings", [ResultsSpec(initial_capital=0), ResultsSpec(equity_sample_seconds=0),
    ResultsSpec(effective_trials=10), ResultsSpec(risk_free_per_session=float("nan")),
    ResultsSpec(effective_trials=1, trial_sharpe_variance=1, trial_history_note="x")])
def test_bad_statistics_settings_fail(settings):
    with pytest.raises(ValueError):
        settings.validate()


def write_tape(config, day="2026-06-15"):
    partition = Path(config.tick_root) / f"parquet/session_date={day}"
    partition.mkdir(parents=True)
    pd.DataFrame({"timestamp": pd.date_range(f"{day} 10:00:00", periods=16, freq="s"),
                  "price": [100, 100, 99, 99, 100, 100, 100, 100.25, 99, 99, 100, 100, 100, 101, 100, 100],
                  "volume": [1] * 16}).to_parquet(partition / "ticks.parquet", index=False)


def test_preset_bypasses_analyzer_and_accepts_policy_outside_grid(tmp_path, monkeypatch):
    cfg = config_for(tmp_path, execution_mode="preset", preset_policy=Policy(5, 7, 13))
    write_tape(cfg)
    def forbidden(*args, **kwargs):
        raise AssertionError("Preset must not construct exit analyzer")
    monkeypatch.setattr("backtester.exit_analyzer.ExitAnalyzer.__init__", forbidden)
    result = run(cfg)
    root = Path(cfg.output)
    assert not (root / "search").exists()
    assert not (root / "reports").exists()
    assert result["reports"][0]["selection"]["policy_id"] == "pt5_sl7_h13"
    directory = root / "policies/tick_2/development/pt5_sl7_h13"
    for filename in ("statistics.json", "results.html", "equity.parquet", "session_returns.csv", "drawdowns.csv"):
        assert (directory / filename).exists()
    stats = json.loads((directory / "statistics.json").read_text())
    assert stats["run_config"]["execution_mode"] == "preset"
    assert "Backtesting results" in Path(result["backtesting_results"]).read_text()
    assert run(cfg, resume=True) == result
    assert run(cfg, report_only=True) == result


def test_preset_confirmation_outside_grid_and_freeze(tmp_path):
    cfg = config_for(tmp_path, execution_mode="preset", preset_policy=Policy(5, 7, 13), confirmation_start="2026-06-16")
    cfg.end_session = "2026-06-16"
    write_tape(cfg)
    write_tape(cfg, "2026-06-16")
    run(cfg)
    result = run(cfg, confirm=True)
    assert result["results"][0]["policy_id"] == cfg.preset_policy.key
    assert run(cfg, confirm=True) == result
    assert (Path(cfg.output) / "policies/tick_2/confirmation/pt5_sl7_h13/results.html").exists()


def test_sweep_produces_both_reports(tmp_path):
    cfg = config_for(tmp_path, profits=[1], stops=[4], holds=[10], max_evaluations=1)
    write_tape(cfg)
    result = run(cfg)
    html = Path(result["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "GNET Exit Analysis" in html and "backtesting_results.html" in html
    assert (Path(cfg.output) / "policies/tick_2/development/pt1_sl4_h10/results.html").exists()
    assert run(cfg, report_only=True)["reports"] == result["reports"]


def test_config_roundtrips_preset_and_statistics(tmp_path):
    cfg = config_for(tmp_path, execution_mode="preset", preset_policy=Policy(4, 4, 30), results=ResultsSpec(initial_capital=10000))
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg.dictionary()))
    loaded = load_config(path)
    assert loaded == cfg
    assert replace(cfg, results=ResultsSpec(initial_capital=20000)).identity() != cfg.identity()
    with pytest.raises(ValueError, match="preset_policy"):
        replace(cfg, preset_policy=None).validate()
