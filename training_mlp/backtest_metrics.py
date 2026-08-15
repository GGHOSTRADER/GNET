"""
backtest_metrics.py
===================

Pure metric functions implementing the mathematical reference in
backtest_metrics_math.md.

All functions are stateless: same input -> same output, no I/O.

Input contract (§0 of the reference):
    initial_capital : float > 0
    trades          : list[dict] sorted ascending by entry_ts, each with:
                        entry_ts   : datetime
                        exit_ts    : datetime
                        pnl        : float ($)

Returns from compute_all() match the metric summary table in §7.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


# ── Equity curve (§0.2) ───────────────────────────────────────────────────────

def build_equity_curve(trades: list[dict], initial_capital: float) -> tuple[np.ndarray, list[datetime]]:
    """
    E_k = C_0 + sum(pnl_1..k), indexed by trade close.
    Returns (equity_array, timestamps) where equity_array[0] = C_0 at t=0.
    """
    pnls = np.array([t["pnl"] for t in trades], dtype=np.float64)
    equity = np.empty(len(trades) + 1, dtype=np.float64)
    equity[0] = initial_capital
    equity[1:] = initial_capital + np.cumsum(pnls)
    timestamps = [trades[0]["entry_ts"]] + [t["exit_ts"] for t in trades]
    return equity, timestamps


def _running_peak(equity: np.ndarray) -> np.ndarray:
    """E_hat_k = max(E_0..E_k) — §4.1."""
    return np.maximum.accumulate(equity)


# ── §1 Returns ────────────────────────────────────────────────────────────────

def daily_returns(equity: np.ndarray, timestamps: list[datetime]) -> list[float]:
    """R_d = (E_d - E_{d-1}) / E_{d-1} * 100 — §1.2."""
    by_day: dict = defaultdict(lambda: None)
    for eq, ts in zip(equity, timestamps):
        day = ts.date()
        by_day[day] = eq

    days = sorted(by_day)
    returns = []
    for i in range(1, len(days)):
        e_prev = by_day[days[i - 1]]
        e_curr = by_day[days[i]]
        if e_prev and e_prev != 0:
            returns.append((e_curr - e_prev) / e_prev * 100)
    return returns


def monthly_returns(equity: np.ndarray, timestamps: list[datetime]) -> list[float]:
    """R_m = (E_m - E_{m-1}) / E_{m-1} * 100 — §1.3."""
    by_month: dict = defaultdict(lambda: None)
    for eq, ts in zip(equity, timestamps):
        month = (ts.year, ts.month)
        by_month[month] = eq

    months = sorted(by_month)
    returns = []
    for i in range(1, len(months)):
        e_prev = by_month[months[i - 1]]
        e_curr = by_month[months[i]]
        if e_prev and e_prev != 0:
            returns.append((e_curr - e_prev) / e_prev * 100)
    return returns


# ── §2 Time metrics ───────────────────────────────────────────────────────────

def avg_time_per_trade_s(trades: list[dict]) -> Optional[float]:
    """Delta_i = exit_ts - entry_ts in seconds — §2.1."""
    if not trades:
        return None
    durations = [(t["exit_ts"] - t["entry_ts"]).total_seconds() for t in trades]
    return float(np.mean(durations))


def avg_time_between_trades_s(trades: list[dict]) -> Optional[float]:
    """G_i = entry_{i+1} - exit_i in seconds — §2.2."""
    if len(trades) < 2:
        return None
    gaps = [
        (trades[i + 1]["entry_ts"] - trades[i]["exit_ts"]).total_seconds()
        for i in range(len(trades) - 1)
    ]
    return float(np.mean(gaps))


def time_underwater(equity: np.ndarray) -> float:
    """U_% = fraction of trade-close points where E_k < E_hat_k — §2.3."""
    if len(equity) <= 1:
        return 0.0
    peak = _running_peak(equity)
    underwater = equity[1:] < peak[1:]
    return float(underwater.mean() * 100)


def avg_drawdown_duration_trades(equity: np.ndarray) -> Optional[float]:
    """Mean number of trade-close points per drawdown period — §2.4."""
    if len(equity) <= 1:
        return None
    peak = _running_peak(equity)
    underwater = equity[1:] < peak[1:]

    periods, count = [], 0
    for u in underwater:
        if u:
            count += 1
        elif count > 0:
            periods.append(count)
            count = 0
    if count > 0:
        periods.append(count)

    return float(np.mean(periods)) if periods else None


# ── §3 Peak metrics ───────────────────────────────────────────────────────────

def _peak_indices(equity: np.ndarray) -> list[int]:
    """S = indices where E sets a new all-time high — §3."""
    peaks = []
    running_max = equity[0]
    for k in range(1, len(equity)):
        if equity[k] > running_max:
            running_max = equity[k]
            peaks.append(k)
    return peaks


def avg_time_to_peak_trades(equity: np.ndarray) -> Optional[float]:
    """Mean inter-peak interval in trade-close units — §3.1."""
    peaks = _peak_indices(equity)
    if len(peaks) < 2:
        return None
    intervals = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
    return float(np.mean(intervals))


def max_time_between_peaks_trades(equity: np.ndarray) -> Optional[float]:
    """Max inter-peak interval in trade-close units — §3.2."""
    peaks = _peak_indices(equity)
    if len(peaks) < 2:
        return float(len(equity) - 1)
    intervals = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
    return float(max(intervals))


# ── §4 Drawdown ───────────────────────────────────────────────────────────────

def max_drawdown_pct(equity: np.ndarray) -> float:
    """MaxDD_% = max_k((E_hat_k - E_k) / E_hat_k * 100) — §4.3."""
    if len(equity) <= 1:
        return 0.0
    peak = _running_peak(equity)
    dd = (peak - equity) / np.where(peak != 0, peak, 1) * 100
    return float(dd.max())


def max_drawdown_dollar(equity: np.ndarray) -> float:
    """MaxDD_$ = max_k(E_hat_k - E_k) — §4.4."""
    if len(equity) <= 1:
        return 0.0
    peak = _running_peak(equity)
    return float((peak - equity).max())


# ── §5 Streaks ────────────────────────────────────────────────────────────────

def _extract_streaks(trades: list[dict]) -> tuple[list[int], list[int]]:
    """Win and loss streak lengths — §5.2. Breakeven trades break streaks."""
    wins, losses = [], []
    if not trades:
        return wins, losses

    outcomes = [1 if t["pnl"] > 0 else (-1 if t["pnl"] < 0 else 0) for t in trades]
    count, current = 1, outcomes[0]

    for o in outcomes[1:]:
        if o == current and o != 0:
            count += 1
        else:
            if current == 1:
                wins.append(count)
            elif current == -1:
                losses.append(count)
            count = 1
            current = o

    if current == 1:
        wins.append(count)
    elif current == -1:
        losses.append(count)

    return wins, losses


def streak_metrics(trades: list[dict]) -> dict:
    wins, losses = _extract_streaks(trades)
    return {
        "max_consec_wins":    int(max(wins))        if wins   else None,
        "avg_consec_wins":    float(np.mean(wins))  if wins   else None,
        "max_consec_losses":  int(max(losses))      if losses else None,
        "avg_consec_losses":  float(np.mean(losses)) if losses else None,
    }


# ── §6 Summary ────────────────────────────────────────────────────────────────

def compute_all(trades: list[dict], initial_capital: float, commission_per_trade: float = 0.0) -> dict:
    """Compute every metric in §7. Returns dict keyed by metric name."""
    if not trades:
        return {k: None for k in [
            "first_entry", "last_exit", "days_tested",
            "n_trades", "net_pnl", "commission_per_trade", "commission_total",
            "win_rate", "avg_win", "avg_loss", "expected_value",
            "daily_returns", "monthly_returns",
            "avg_time_per_trade_s", "avg_time_between_trades_s",
            "time_underwater_pct", "avg_drawdown_duration_trades",
            "avg_time_to_peak_trades", "max_time_between_peaks_trades",
            "max_drawdown_pct", "max_drawdown_dollar",
            "max_consec_wins", "avg_consec_wins",
            "max_consec_losses", "avg_consec_losses",
        ]}

    # Apply commission: subtract from each trade's pnl before all calculations
    commission_total = commission_per_trade * len(trades)
    trades = [{**t, "pnl": t["pnl"] - commission_per_trade} for t in trades]

    first_entry = trades[0]["entry_ts"]
    last_exit   = trades[-1]["exit_ts"]
    days_tested = (last_exit - first_entry).days

    equity, timestamps = build_equity_curve(trades, initial_capital)
    dr  = daily_returns(equity, timestamps)
    mr  = monthly_returns(equity, timestamps)
    sk  = streak_metrics(trades)

    winners = [t for t in trades if t["pnl"] > 0]
    losers  = [t for t in trades if t["pnl"] <= 0]

    avg_win  = float(np.mean([t["pnl"] for t in winners])) if winners else 0.0
    avg_loss = float(np.mean([t["pnl"] for t in losers]))  if losers  else 0.0
    wr       = len(winners) / len(trades)
    ev       = wr * avg_win + (1 - wr) * avg_loss

    return {
        "n_trades":                    len(trades),
        "first_entry":                 first_entry,
        "last_exit":                   last_exit,
        "days_tested":                 days_tested,
        "net_pnl":                     float(equity[-1] - initial_capital),
        "commission_per_trade":        float(commission_per_trade),
        "commission_total":            float(commission_total),
        "win_rate":                    float(wr * 100),
        "avg_win":                     avg_win,
        "avg_loss":                    avg_loss,
        "expected_value":              float(ev),
        "daily_returns":               dr,
        "monthly_returns":             mr,
        "avg_time_per_trade_s":        avg_time_per_trade_s(trades),
        "avg_time_between_trades_s":   avg_time_between_trades_s(trades),
        "time_underwater_pct":         time_underwater(equity),
        "avg_drawdown_duration_trades":avg_drawdown_duration_trades(equity),
        "avg_time_to_peak_trades":     avg_time_to_peak_trades(equity),
        "max_time_between_peaks_trades":max_time_between_peaks_trades(equity),
        "max_drawdown_pct":            max_drawdown_pct(equity),
        "max_drawdown_dollar":         max_drawdown_dollar(equity),
        "_equity":                     equity,                    # equity (initial capital base) — % metrics
        "_cum_pnl":                    equity - initial_capital,  # cumulative P&L from $0 — for plotting
        **sk,
    }


def _report_lines(label: str, metrics: dict) -> list[str]:
    """Build report lines shared by print_report and save_report."""
    def fmt(v):
        if v is None:            return "N/A"
        if isinstance(v, float): return f"{v:,.2f}"
        if isinstance(v, list):  return f"[{len(v)} points]"
        if isinstance(v, datetime): return v.strftime("%Y-%m-%d %H:%M:%S")
        return str(v)

    width = 38
    rows = [
        ("First Entry",                metrics.get("first_entry")),
        ("Last Exit",                  metrics.get("last_exit")),
        ("Days Tested",                metrics.get("days_tested")),
        ("Trades",                     metrics["n_trades"]),
        (f"Net P&L ($, after ${metrics['commission_per_trade'] or 0:,.2f}/trade)", metrics["net_pnl"]),
        ("Commission Total ($)",       metrics["commission_total"]),
        ("Win Rate (%)",               metrics["win_rate"]),
        ("Avg Win ($)",                metrics["avg_win"]),
        ("Avg Loss ($)",               metrics["avg_loss"]),
        ("Expected Value ($/trade)",   metrics["expected_value"]),
        ("Max Drawdown (% of running equity)", metrics["max_drawdown_pct"]),
        ("Max Drawdown ($)",           metrics["max_drawdown_dollar"]),
        ("Time Underwater (%)",        metrics["time_underwater_pct"]),
        ("Avg DD Duration (trades)",   metrics["avg_drawdown_duration_trades"]),
        ("Avg Time/Trade (s)",         metrics["avg_time_per_trade_s"]),
        ("Avg Time Between (s)",       metrics["avg_time_between_trades_s"]),
        ("Avg Time to Peak (trades)",  metrics["avg_time_to_peak_trades"]),
        ("Max Time Between Peaks (trades)", metrics["max_time_between_peaks_trades"]),
        ("Max Consec Wins",            metrics["max_consec_wins"]),
        ("Avg Consec Wins",            metrics["avg_consec_wins"]),
        ("Max Consec Losses",          metrics["max_consec_losses"]),
        ("Avg Consec Losses",          metrics["avg_consec_losses"]),
    ]
    lines = [f"\n{'-' * 55}", f"  {label}", f"{'-' * 55}"]
    for name, val in rows:
        lines.append(f"  {name:<{width}} {fmt(val)}")
    lines.append(f"{'-' * 55}")
    return lines


def print_report(label: str, metrics: dict) -> None:
    """Print a formatted metric table to stdout."""
    for line in _report_lines(label, metrics):
        print(line)


def save_report(label: str, metrics: dict, filepath: str) -> None:
    """Write the metric table to a .txt file."""
    from pathlib import Path
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as f:
        for line in _report_lines(label, metrics):
            f.write(line + "\n")
    print(f"[report] Saved -> {filepath}")


def plot_equity_curve(
    metrics: dict,
    label: str,
    save_path: Optional[str] = None,
) -> None:
    """
    Plot cumulative P&L curve (from $0) with:
      - Small green dots at every all-time high
      - Single red dot at the max drawdown trough
    Y axis in $ (cumulative P&L) | X axis in trade number.

    Peaks and drawdown are computed on the equity curve, but since cumulative
    P&L = equity - initial_capital (a constant shift), the peak/trough indices
    are identical; only the plotted Y values differ.
    """
    equity  = metrics.get("_equity")
    cum_pnl = metrics.get("_cum_pnl")
    if equity is None or cum_pnl is None or len(equity) < 2:
        print(f"[plot] No equity data for '{label}' — skipping.")
        return

    x      = np.arange(len(cum_pnl))
    peak   = _running_peak(equity)
    dd     = peak - equity
    mdd_idx = int(np.argmax(dd))

    peak_idx = _peak_indices(equity)

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(x, cum_pnl, color="#4a90d9", linewidth=1.0, zorder=2)
    ax.axhline(0, color="#888888", linewidth=0.8, linestyle="-", zorder=1)

    # Green dots — all-time highs
    if peak_idx:
        ax.scatter(
            peak_idx,
            cum_pnl[peak_idx],
            color="#2ecc71", s=12, zorder=3, linewidths=0,
            label="New high",
        )

    # Red dot — max drawdown trough
    ax.scatter(
        mdd_idx,
        cum_pnl[mdd_idx],
        color="#e74c3c", s=40, zorder=4, linewidths=0,
        label=f"Max DD  ${dd[mdd_idx]:,.2f}",
    )

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.set_xlabel("Trade #", fontsize=10)
    ax.set_ylabel("Cumulative P&L ($)", fontsize=10)
    ax.set_title(label, fontsize=11, fontweight="bold")
    ax.legend(fontsize=9, framealpha=0.7)
    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.6)
    ax.set_xlim(0, len(equity) - 1)
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
        print(f"[plot] Saved -> {save_path}")
    else:
        plt.show()
    plt.close(fig)
