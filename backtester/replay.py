"""Chronological one-position strategy replay, independently for each policy."""
from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd

from backtester.config import Config, Policy, atomic_json


TRADE_COLUMNS = ["signal_id", "entry_event", "exit_event", "entry_ns", "exit_ns",
                 "entry_price", "exit_price", "exit_reason", "gross_pnl", "net_pnl",
                 "holding_seconds", "mfe_ticks", "mae_ticks", "exit_delay_seconds",
                 "max_tick_gap_seconds", "valid"]


def replay_policy(times, prices, signals, sessions, policy: Policy, config: Config, begin=0, end=None):
    """Each accepted signal advances this policy's own position occupancy.

    Exit event indices are retained even though first-touch scans use NumPy.
    A later cross seen before that exit is skipped, never queued for later.
    """
    end = len(times) if end is None else end
    trades, skipped = [], []
    last_exit = begin - 1
    realized = 0.0
    peak = 0.0
    drawdown = 0.0
    invalid = 0
    block_pnl = [0.0] * config.time_blocks
    slippage = config.slippage_ticks * 0.25
    vintage_edges = [sessions[i]["begin"] for i in range(1, len(sessions))
                     if sessions[i]["vintage"] != sessions[i - 1]["vintage"]]
    for signal in signals:
        entry = int(signal["entry_event"])
        session = sessions[int(signal["session_index"])]
        if session["begin"] < begin or session["begin"] >= end:
            continue
        reason = None
        if last_exit > int(signal["available_after_event"]):
            reason = "position_open"
        elif entry >= min(session["end"], end):
            reason = "no_next_tick_in_session"
        elif (times[entry] - signal["signal_ns"]) / 1e9 > config.max_entry_delay_seconds:
            reason = "stale_signal"
        elif config.session_exit == "flatten" and times[entry] >= session["flatten_ns"]:
            reason = "session_entry_cutoff"
        if reason:
            skipped.append({"signal_id": int(signal["signal_id"]), "reason": reason})
            continue

        entry_ns = int(times[entry])
        entry_price = float(prices[entry]) + slippage
        target, stop = entry_price + policy.profit_ticks * 0.25, entry_price - policy.stop_ticks * 0.25
        deadline = entry_ns + policy.hold_seconds * 1_000_000_000
        time_reason = "time"
        if config.session_exit == "flatten" and session["flatten_ns"] <= deadline:
            deadline, time_reason = session["flatten_ns"], "session"
        boundary = min([edge for edge in vintage_edges if edge > entry] + [end])
        deadline_event = max(entry + 1, int(np.searchsorted(times, deadline, side="left")))
        price_end = min(deadline_event, boundary)
        path = prices[entry + 1:price_end]
        hits = np.flatnonzero((path >= target) | (path <= stop))
        delay = 0.0
        if len(hits):
            exit_event = entry + 1 + int(hits[0])
            observed = float(prices[exit_event])
            reason = "profit" if observed >= target else "loss"
            exit_price = target if reason == "profit" else observed - slippage
        elif deadline_event < boundary:
            exit_event, reason = deadline_event, time_reason
            exit_price = float(prices[exit_event]) - slippage
            delay = max(0.0, (int(times[exit_event]) - deadline) / 1e9)
        else:
            exit_event, exit_price = None, None
            reason = "vintage_boundary" if boundary < end else "end_of_data"
        last_observed = exit_event if exit_event is not None else boundary - 1
        path = prices[entry:last_observed + 1]
        gaps = np.diff(times[entry:last_observed + 1])
        largest_gap = float(gaps.max() / 1e9) if len(gaps) else 0.0
        valid = exit_event is not None and delay <= config.max_exit_delay_seconds
        if config.max_tick_gap_seconds is not None and largest_gap > config.max_tick_gap_seconds:
            valid = False
        invalid += int(not valid)
        gross = None if exit_event is None else (exit_price - entry_price) * 50.0
        net = None if gross is None else gross - config.round_trip_cost
        # Hypothetical liquidation equity includes the full round-turn charge.
        marked = realized + (path - entry_price - slippage) * 50.0 - config.round_trip_cost
        if exit_event is not None:
            # A target fills at its limit, not at a higher gapped trade price.
            marked[-1] = realized + net
        if len(marked):
            peaks = np.maximum.accumulate(np.r_[peak, marked])[1:]
            drawdown = max(drawdown, float(np.max(peaks - marked)))
            peak = max(peak, float(marked.max()))
        trade = {
            "signal_id": int(signal["signal_id"]), "entry_event": entry,
            "exit_event": exit_event, "entry_ns": entry_ns,
            "exit_ns": None if exit_event is None else int(times[exit_event]),
            "entry_price": entry_price, "exit_price": exit_price, "exit_reason": reason,
            "gross_pnl": gross, "net_pnl": net,
            "holding_seconds": None if exit_event is None else (int(times[exit_event]) - entry_ns) / 1e9,
            "mfe_ticks": max(0.0, float((path.max() - entry_price) / 0.25)),
            "mae_ticks": max(0.0, float((entry_price - path.min()) / 0.25)),
            "exit_delay_seconds": delay, "max_tick_gap_seconds": largest_gap, "valid": bool(valid),
        }
        trades.append(trade)
        if net is None:
            # Incomplete coverage blocks the position for all later signals in this replay.
            last_exit = end
        else:
            realized += net
            peak = max(peak, realized)
            drawdown = max(drawdown, peak - realized)
            last_exit = exit_event
            block = min(config.time_blocks - 1, int((times[exit_event] - times[begin]) * config.time_blocks
                        // max(1, int(times[end - 1] - times[begin]) + 1)))
            block_pnl[block] += net
    completed = [trade for trade in trades if trade["net_pnl"] is not None]
    wins = sum(trade["net_pnl"] > 0 for trade in completed)
    positive = sum(max(0.0, trade["net_pnl"]) for trade in completed)
    negative = -sum(min(0.0, trade["net_pnl"]) for trade in completed)
    eligible = invalid == 0 and len(completed) >= config.min_trades
    if config.max_drawdown is not None and drawdown > config.max_drawdown:
        eligible = False
    summary = {
        "policy_id": policy.key, "profit_ticks": policy.profit_ticks, "stop_ticks": policy.stop_ticks,
        "hold_seconds": policy.hold_seconds, "entries": len(trades), "closed_trades": len(completed),
        "skipped_signals": len(skipped), "skipped_busy": sum(s["reason"] == "position_open" for s in skipped),
        "invalid_trades": invalid, "unresolved_trades": len(trades) - len(completed),
        "net_pnl": realized, "gross_pnl": sum(trade["gross_pnl"] for trade in completed),
        "win_rate": wins / len(completed) if completed else 0.0,
        "average_trade": realized / len(completed) if completed else 0.0,
        "profit_factor": positive / negative if negative else None,
        "max_drawdown": drawdown, "block_net_pnl": block_pnl,
        "positive_blocks": sum(value > 0 for value in block_pnl), "eligible": bool(eligible),
        "score": realized if eligible else None,
    }
    return summary, trades, skipped


def evaluate_batch(task):
    """Spawn-safe process entry: shared immutable maps, private policy position state."""
    config, bar_key, policies, phase = task
    root = Path(config.output)
    prepared = root / "prepared"
    metadata = json.loads((prepared / "metadata.json").read_text())
    times = np.load(prepared / "times.npy", mmap_mode="r")
    prices = np.load(prepared / "prices.npy", mmap_mode="r")
    signals = pd.read_parquet(prepared / f"signals_{bar_key}.parquet").to_dict("records")
    sessions = metadata["sessions"]
    split = next((s["begin"] for s in sessions if config.confirmation_start and s["session"] >= config.confirmation_start), len(times))
    begin, end = (0, split) if phase == "development" else (split, len(times))
    if begin == end:
        raise ValueError(f"no ticks in {phase} period")
    result = []
    for policy in policies:
        directory = root / "policies" / bar_key / phase / policy.key
        path = directory / "summary.json"
        if path.exists():
            summary = json.loads(path.read_text())
            if summary["identity"] != metadata["identity"]:
                raise ValueError("cached policy identity mismatch")
            result.append(summary)
            continue
        summary, trades, skipped = replay_policy(times, prices, signals, sessions, policy, config, begin, end)
        directory.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(trades, columns=TRADE_COLUMNS).to_parquet(directory / "trades.parquet", index=False)
        pd.DataFrame(skipped, columns=["signal_id", "reason"]).to_parquet(directory / "skipped_signals.parquet", index=False)
        summary.update(identity=metadata["identity"], bar_spec=bar_key, phase=phase)
        from backtester.results_report import save_results
        save_results(directory, config, times, prices, trades, signals, sessions, summary, begin, end)
        atomic_json(path, summary)
        result.append(summary)
    return result
