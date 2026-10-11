"""Plot and summarize the corrected MLP's profitable same-bar holdout cohort."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "training_mlp"
    / "strategies"
    / "MA2CrossLE"
    / "reports"
    / "old_libb_prior_bar_ablation"
    / "identical_holdout_trade_predictions.csv"
)
OUTPUT_DIR = (
    ROOT
    / "training_mlp"
    / "strategies"
    / "MA2CrossLE"
    / "reports"
    / "corrected_holdout_same_bar_equity"
)
THRESHOLD = 0.50
PROBABILITY_COLUMN = "prob_prior_bar"
PNL_COLUMN = "net_pnl_at_3_24_per_side"


def longest_streak(values: np.ndarray, target: bool) -> int:
    longest = 0
    current = 0
    for value in values:
        if bool(value) is target:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def maximum_drawdown_duration(equity: np.ndarray) -> int:
    peaks = np.maximum.accumulate(equity)
    underwater = equity < peaks
    return longest_streak(underwater, True)


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(SOURCE)
    frame["entry_time"] = pd.to_datetime(frame["entry_time"], errors="raise")
    frame["exit_time"] = pd.to_datetime(frame["exit_time"], errors="raise")
    selected = frame.loc[
        (frame["entry_time"] == frame["exit_time"])
        & (frame[PROBABILITY_COLUMN] >= THRESHOLD)
    ].copy()
    selected = selected.sort_values(["entry_time", "trade_number"]).reset_index(drop=True)
    if selected.empty:
        raise RuntimeError("same-bar threshold filter selected no trades")

    pnl = selected[PNL_COLUMN].to_numpy(dtype=float)
    equity = pnl.cumsum()
    running_peak = np.maximum.accumulate(np.concatenate(([0.0], equity)))[1:]
    drawdown = equity - running_peak
    winners = pnl > 0
    losers = pnl < 0
    gross_profit = float(pnl[winners].sum())
    gross_loss = float(-pnl[losers].sum())
    standard_deviation = float(pnl.std(ddof=1))

    metrics = {
        "source": str(SOURCE),
        "probability_column": PROBABILITY_COLUMN,
        "threshold": THRESHOLD,
        "same_bar_definition": "entry_time equals exit_time",
        "fees": "$3.24 per side / $6.48 round turn included",
        "start": selected["entry_time"].iloc[0].isoformat(),
        "end": selected["entry_time"].iloc[-1].isoformat(),
        "calendar_days": int(
            (selected["entry_time"].iloc[-1] - selected["entry_time"].iloc[0]).days
        ),
        "trades": int(len(selected)),
        "winning_trades": int(winners.sum()),
        "losing_trades": int(losers.sum()),
        "win_rate": float(winners.mean()),
        "net_profit": float(pnl.sum()),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss,
        "average_trade": float(pnl.mean()),
        "median_trade": float(np.median(pnl)),
        "average_winner": float(pnl[winners].mean()),
        "average_loser": float(pnl[losers].mean()),
        "payoff_ratio": float(pnl[winners].mean() / -pnl[losers].mean()),
        "trade_pnl_standard_deviation": standard_deviation,
        "system_quality_number": float(pnl.mean() / standard_deviation * np.sqrt(len(pnl))),
        "maximum_drawdown": float(drawdown.min()),
        "maximum_drawdown_duration_trades": maximum_drawdown_duration(equity),
        "longest_winning_streak": longest_streak(winners, True),
        "longest_losing_streak": longest_streak(losers, True),
        "maximum_trade": float(pnl.max()),
        "minimum_trade": float(pnl.min()),
    }

    selected["cumulative_net_pnl"] = equity
    selected["drawdown"] = drawdown
    selected.to_csv(OUTPUT_DIR / "approved_same_bar_trades.csv", index=False)
    (OUTPUT_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    figure, (equity_axis, drawdown_axis) = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    equity_axis.plot(selected["entry_time"], equity, color="#1565c0", linewidth=1.8)
    equity_axis.axhline(0, color="#666666", linewidth=0.8)
    equity_axis.fill_between(
        selected["entry_time"], 0, equity, where=equity >= 0, color="#2e7d32", alpha=0.12
    )
    equity_axis.set_title(
        "13-feature MLP holdout — same-bar exits, probability ≥ 0.50"
    )
    equity_axis.set_ylabel("Cumulative net P&L ($)")
    equity_axis.grid(alpha=0.25)
    equity_axis.text(
        0.01,
        0.97,
        f"{len(selected)} trades | Net USD {pnl.sum():,.2f} | Win rate {winners.mean():.2%} | "
        f"Max DD USD {drawdown.min():,.2f}",
        transform=equity_axis.transAxes,
        va="top",
        fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#cccccc"},
    )

    drawdown_axis.fill_between(
        selected["entry_time"], drawdown, 0, color="#c62828", alpha=0.55
    )
    drawdown_axis.set_ylabel("Drawdown ($)")
    drawdown_axis.set_xlabel("Entry time")
    drawdown_axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "equity_curve.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    print(json.dumps(metrics, indent=2))
    print(f"Saved outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    run()
