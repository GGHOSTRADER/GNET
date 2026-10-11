"""Per-backtest statistics, independent of exit search and parameter selection.

Sharpe inference follows Bailey / Lopez de Prado (2014), equation 2:
https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
It is approximate, not an autocorrelation correction or evidence of validation.
"""
from __future__ import annotations

from math import exp, sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd


def concentration(values):
    """Normalized HHI of nonnegative contributions; undefined for <3 items."""
    values = np.asarray(values, dtype=float)
    if len(values) < 3 or values.sum() <= 0:
        return None
    weights = values / values.sum()
    return float((np.sum(weights ** 2) - 1 / len(values)) / (1 - 1 / len(values)))


def sharpe_statistics(returns, settings):
    values = np.asarray(returns, dtype=float) - settings.risk_free_per_session
    result = dict(sharpe_per_session=None, sharpe_annualized=None,
                  probabilistic_sharpe_vs_zero=None, deflated_sharpe=None,
                  deflated_benchmark_per_session=None, observations=len(values))
    if len(values) < 3 or not np.isfinite(values).all() or np.std(values, ddof=1) <= 0:
        result["unavailable_reason"] = "Need at least three finite, nonconstant session returns."
        return result
    centered = values - values.mean()
    moment2 = np.mean(centered ** 2)
    skew = float(np.mean(centered ** 3) / moment2 ** 1.5)
    kurtosis = float(np.mean(centered ** 4) / moment2 ** 2)  # Pearson, not excess
    sr = float(values.mean() / np.std(values, ddof=1))
    variance = 1 - skew * sr + (kurtosis - 1) * sr * sr / 4
    result.update(sharpe_per_session=sr, sharpe_annualized=sr * sqrt(settings.sessions_per_year),
                  skewness=skew, pearson_kurtosis=kurtosis)
    if variance <= 0:
        result["unavailable_reason"] = "Nonpositive estimated Sharpe sampling variance."
        return result
    normal = NormalDist()
    scale = sqrt((len(values) - 1) / variance)
    result["probabilistic_sharpe_vs_zero"] = normal.cdf(sr * scale)
    if settings.effective_trials is not None:
        n, gamma = settings.effective_trials, 0.5772156649015329
        benchmark = sqrt(settings.trial_sharpe_variance) * (
            (1 - gamma) * normal.inv_cdf(1 - 1 / n) + gamma * normal.inv_cdf(1 - 1 / (n * exp(1))))
        result.update(deflated_benchmark_per_session=benchmark,
                      deflated_sharpe=normal.cdf((sr - benchmark) * scale),
                      trial_history_note=settings.trial_history_note)
    else:
        result["dsr_unavailable_reason"] = "Full research-trial variance and effective independent trial count not supplied."
    return result


def build_equity(times, prices, trades, sessions, config, begin, end):
    """As-of marks on a wall-clock grid, plus exact entry/exit and session events.

    Position is post-event. Equal timestamps retain source-event ordering.
    Flat intervals are included. No price is carried across a vintage boundary
    for an unresolved position. Marking uses the replay's liquidation convention.
    """
    pieces = []
    step = config.results.equity_sample_seconds * 1_000_000_000
    for session in sessions:
        lo, hi = max(begin, session["begin"]), min(end, session["end"])
        if lo >= hi:
            continue
        first, last = int(times[lo]), int(times[hi - 1])
        grid = np.unique(np.r_[first, np.arange(((first // step) + 1) * step, last, step, dtype=np.int64), last])
        events = np.searchsorted(times, grid, side="right") - 1
        events = np.clip(events, lo, hi - 1)
        extra = {lo, hi - 1}
        for trade in trades:
            for key in ("entry_event", "exit_event"):
                event = trade[key]
                if event is not None and lo <= event < hi:
                    extra.add(int(event))
        extras = sorted(extra)
        frame = pd.DataFrame({"time_ns": np.r_[grid, times[extras]], "event": np.r_[events, extras]})
        frame = frame.drop_duplicates().sort_values(["time_ns", "event"])
        frame["session"] = session["session"]
        frame["session_end"] = False
        frame.iloc[-1, frame.columns.get_loc("session_end")] = True
        pieces.append(frame)
    curve = pd.concat(pieces, ignore_index=True)
    # Explicit pre-entry baseline even if first entry occurs at the first tick.
    baseline = curve.iloc[[0]].copy()
    baseline["event"] = begin - 1
    baseline["session_end"] = False
    curve = pd.concat([baseline, curve], ignore_index=True)
    events = curve["event"].to_numpy(dtype=np.int64)
    closed = [trade for trade in trades if trade["exit_event"] is not None]
    exit_events = np.asarray([trade["exit_event"] for trade in closed], dtype=np.int64)
    cumulative = np.r_[0.0, np.cumsum([trade["net_pnl"] for trade in closed])]
    realized = cumulative[np.searchsorted(exit_events, events, side="right")]
    marked = realized.copy()
    position = np.zeros(len(curve), dtype=np.int8)
    valid = np.ones(len(curve), dtype=bool)
    cash = 0.0
    slip = config.slippage_ticks * .25
    for trade in trades:
        entry, exit_event = trade["entry_event"], trade["exit_event"]
        left = int(np.searchsorted(events, entry, side="left"))
        right = len(curve) if exit_event is None else int(np.searchsorted(events, exit_event, side="left"))
        position[left:right] = 1
        marked[left:right] = cash + (prices[events[left:right]] - trade["entry_price"] - slip) * 50 - config.round_trip_cost
        if exit_event is None:
            entry_vintage = next(s["vintage"] for s in sessions if s["begin"] <= entry < s["end"])
            boundary = next((s["begin"] for s in sessions if s["begin"] > entry and s["vintage"] != entry_vintage), end)
            unknown = events >= boundary
            marked[unknown] = np.nan
            valid[left:] = False
        else:
            cash += trade["net_pnl"]
            if not trade["valid"]:
                valid[left:right + 1] = False
    curve["position_contracts"] = position
    curve["realized_net_usd"] = realized
    curve["liquidation_net_usd"] = marked
    curve["valid"] = valid
    curve["last_tick_ns"] = times[np.maximum(events, begin)]
    curve["mark_age_seconds"] = (curve["time_ns"] - curve["last_tick_ns"]) / 1e9
    return curve


def drawdown_episodes(curve):
    """Sampled underwater episodes, including unrecovered terminal episodes."""
    peak, peak_time, active, episodes = 0.0, int(curve.iloc[0]["time_ns"]), None, []
    for row in curve.itertuples(index=False):
        value = row.liquidation_net_usd
        if not np.isfinite(value):
            break
        if value >= peak:
            if active is not None:
                episodes.append({**active, "end_ns": int(row.time_ns), "recovered": True,
                                 "duration_seconds": (row.time_ns - active["start_ns"]) / 1e9})
                active = None
            peak, peak_time = value, int(row.time_ns)
        else:
            if active is None:
                active = {"start_ns": peak_time, "depth_usd": 0.0}
            active["depth_usd"] = max(active["depth_usd"], float(peak - value))
        last_time = int(row.time_ns)
    if active is not None:
        episodes.append({**active, "end_ns": last_time, "recovered": False,
                         "duration_seconds": (last_time - active["start_ns"]) / 1e9})
    return episodes


def grouped_outcomes(frame, column):
    return [{"group": str(key), "trades": len(group), "net_pnl": float(group.net_pnl.sum()),
             "gross_pnl": float(group.gross_pnl.sum()), "win_rate": float((group.net_pnl > 0).mean())}
            for key, group in frame.groupby(column, observed=True)]


def calculate_results(trades, curve, summary, config, *, entry_shortfall=None, modeled_slippage=None):
    """No selection decisions, report I/O, or dependency on the exit analyzer."""
    frame = pd.DataFrame(trades)
    closed = frame.loc[frame.net_pnl.notna()].copy() if len(frame) else pd.DataFrame(
        columns=["net_pnl", "gross_pnl", "holding_seconds", "exit_reason", "exit_ns", "entry_price", "exit_price"])
    pnls = closed.net_pnl.to_numpy(dtype=float)
    wins, losses = pnls[pnls > 0], -pnls[pnls < 0]
    episodes = drawdown_episodes(curve)
    daily = curve.loc[curve.session_end, ["session", "time_ns", "liquidation_net_usd"]].copy()
    daily["net_change_usd"] = np.diff(np.r_[0.0, daily.liquidation_net_usd.to_numpy()])
    settings = config.results
    capital = settings.initial_capital
    inference_reason = None
    returns = None
    if capital is None:
        inference_reason = "initial_capital not configured; no assumed futures-notional denominator."
    elif summary["invalid_trades"]:
        inference_reason = "Invalid or unresolved trades prevent return inference."
    elif not np.isfinite(curve.liquidation_net_usd).all() or (capital + curve.liquidation_net_usd).min() <= 0:
        inference_reason = "Equity is unknown or exhausted; percentage-return inference disabled."
    else:
        prior_nav = capital + np.r_[0., daily.liquidation_net_usd.to_numpy()[:-1]]
        returns = daily.net_change_usd.to_numpy() / prior_nav
    daily["return"] = np.nan if returns is None else returns
    risk = sharpe_statistics(returns, settings) if returns is not None else {"unavailable_reason": inference_reason}
    elapsed = (int(curve.time_ns.iloc[-1]) - int(curve.time_ns.iloc[0])) / 1e9
    occupied = sum((int(t["exit_ns"] if t["exit_ns"] is not None else curve.time_ns.iloc[-1]) - t["entry_ns"]) / 1e9 for t in trades)
    closed["holding_bucket"] = pd.cut(closed.holding_seconds.astype(float),
        [-np.inf, 30, 60, 300, 1800, np.inf], labels=["0–30s", "30–60s", "1–5m", "5–30m", ">30m"])
    if len(closed):
        closed["month"] = pd.to_datetime(closed.exit_ns.astype("int64"), utc=True).dt.tz_convert(config.timezone).dt.strftime("%Y-%m")
    else:
        closed["month"] = pd.Series(dtype=str)
    metrics = {
        "schema_version": 1, "policy_id": summary["policy_id"], "phase": summary["phase"],
        "bar_spec": summary["bar_spec"], "identity": summary["identity"],
        "strategy": config.strategy.name, "strategy_parameters": config.strategy.parameters,
        "status": "diagnostic_only" if summary["invalid_trades"] else "complete_replay",
        "activity": {"start_ns": int(curve.time_ns.iloc[0]), "end_ns": int(curve.time_ns.iloc[-1]),
            "observed_sessions": len(daily), "entries": len(trades), "closed_trades": len(closed),
            "skipped_signals": summary["skipped_signals"], "invalid_trades": summary["invalid_trades"],
            "unresolved_trades": summary["unresolved_trades"], "calendar_exposure_fraction": occupied / elapsed if elapsed else None,
            "average_hold_seconds": float(closed.holding_seconds.mean()) if len(closed) else None},
        "performance": {"gross_pnl": summary["gross_pnl"], "net_pnl": summary["net_pnl"],
            "win_rate": float((pnls > 0).mean()) if len(pnls) else None,
            "average_trade": float(pnls.mean()) if len(pnls) else None,
            "average_win": float(wins.mean()) if len(wins) else None,
            "average_loss": float(losses.mean()) if len(losses) else None,
            "profit_factor": float(wins.sum() / losses.sum()) if losses.sum() else None,
            "initial_capital": capital,
            "time_weighted_return": float(np.prod(1 + returns) - 1) if returns is not None else None},
        "path": {"max_drawdown_tick_usd": summary["max_drawdown"],
            "max_drawdown_sampled_usd": max((e["depth_usd"] for e in episodes), default=0.0),
            "max_time_underwater_sampled_seconds": max((e["duration_seconds"] for e in episodes), default=0.0),
            "winning_trade_concentration": concentration(wins), "losing_trade_concentration": concentration(losses),
            "monthly_exit_count_concentration": concentration(closed.groupby("month").size().to_numpy()),
            "max_sample_mark_age_seconds": float(curve.mark_age_seconds.max())},
        "execution": {"closed_trade_fees_usd": len(closed) * config.round_trip_cost,
            "modeled_slippage_usd": modeled_slippage, "entry_shortfall_vs_signal_close_usd": entry_shortfall,
            "round_trip_cost": config.round_trip_cost, "slippage_ticks": config.slippage_ticks,
            "turnover_notional_usd_closed": float(((closed.entry_price + closed.exit_price) * 50).sum())},
        "risk_adjusted": risk,
        "attribution": {"exit_reason": grouped_outcomes(closed, "exit_reason"),
            "holding_time": grouped_outcomes(closed, "holding_bucket"), "month": grouped_outcomes(closed, "month")},
        "assumptions": [
            "One long ES contract. No deposits/withdrawals. Returns use supplied capital and observed session-end liquidation marks.",
            "Open-position marks reserve the entire round-trip fee and exit slippage; closed-trade fees are charged once.",
            "Equity grid uses last observed ticks, plus exact entry/exit events. Sampled underwater duration can miss intragrid recovery.",
            "Sharpe/PSR use session returns, not trade returns. Annualization assumes the configured sessions per year; no serial-correlation adjustment.",
            "Missing archive sessions are not invented; verify contiguous coverage before interpreting annualized statistics.",
            "Profit-touch fills are modeled; no order-book queue reconstruction. Entry shortfall compares fills with completed signal-bar closes, not realized broker costs.",
            "Classification/factor attribution unavailable without predictions/labels/benchmark inputs. This report does not perform purging, embargo or CV.",
        ],
        "return_settings": {"sessions_per_year": settings.sessions_per_year, "risk_free_per_session": settings.risk_free_per_session,
            "effective_trials": settings.effective_trials, "trial_sharpe_variance": settings.trial_sharpe_variance,
            "trial_history_note": settings.trial_history_note},
    }
    return metrics, daily, episodes
