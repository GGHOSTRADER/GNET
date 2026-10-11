"""Compare corrected same-bar holdout equity with one-contract ES buy-and-hold."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TRADES_FILE = (
    ROOT
    / "training_mlp"
    / "strategies"
    / "MA2CrossLE"
    / "reports"
    / "corrected_holdout_same_bar_equity"
    / "approved_same_bar_trades.csv"
)
BARS_FILE = (
    ROOT
    / "training_mlp"
    / "strategies"
    / "MA2CrossLE"
    / "inputs"
    / "data_30_master.txt"
)
OUTPUT_FILE = (
    ROOT
    / "training_mlp"
    / "strategies"
    / "MA2CrossLE"
    / "reports"
    / "corrected_holdout_same_bar_equity"
    / "strategy_vs_buy_hold.png"
)
POINT_VALUE = 50.0
COMMISSION_PER_SIDE = 3.24


def drawdown(equity: pd.Series) -> pd.Series:
    return equity - equity.cummax().clip(lower=0.0)


def run() -> None:
    trades = pd.read_csv(TRADES_FILE)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], errors="raise")
    trades = trades.sort_values(["entry_time", "trade_number"]).reset_index(drop=True)
    start = trades["entry_time"].iloc[0]
    end = trades["entry_time"].iloc[-1]

    bars = pd.read_csv(BARS_FILE)
    bars["timestamp"] = pd.to_datetime(
        bars["Date"].astype(str) + " " + bars["Time"].astype(str), errors="raise"
    )
    bars = bars.loc[(bars["timestamp"] >= start) & (bars["timestamp"] <= end)].copy()
    if bars.empty:
        raise RuntimeError("no bars overlap the selected trade period")

    entry_price = float(bars.iloc[0]["Open"])
    buy_hold_equity = (bars["Close"] - entry_price) * POINT_VALUE - COMMISSION_PER_SIDE
    buy_hold_equity.iloc[-1] -= COMMISSION_PER_SIDE

    strategy_events = trades.set_index("entry_time")["cumulative_net_pnl"]
    strategy_equity = strategy_events.reindex(
        strategy_events.index.union(pd.DatetimeIndex(bars["timestamp"]))
    ).sort_index().ffill().fillna(0.0)
    strategy_equity = strategy_equity.reindex(pd.DatetimeIndex(bars["timestamp"]))

    buy_hold_series = pd.Series(
        buy_hold_equity.to_numpy(), index=pd.DatetimeIndex(bars["timestamp"])
    )
    strategy_drawdown = drawdown(strategy_equity)
    buy_hold_drawdown = drawdown(buy_hold_series)

    figure, (equity_axis, drawdown_axis) = plt.subplots(
        2,
        1,
        figsize=(13, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    equity_axis.plot(
        strategy_equity.index,
        strategy_equity,
        label=f"NN same-bar strategy: USD {strategy_equity.iloc[-1]:,.2f}",
        color="#1565c0",
        linewidth=2.0,
    )
    equity_axis.plot(
        buy_hold_series.index,
        buy_hold_series,
        label=f"Buy and hold 1 ES: USD {buy_hold_series.iloc[-1]:,.2f}",
        color="#ef6c00",
        linewidth=1.5,
    )
    equity_axis.axhline(0, color="#555555", linewidth=0.8)
    equity_axis.set_title(
        "Corrected MLP same-bar strategy vs. one-contract ES buy-and-hold"
    )
    equity_axis.set_ylabel("Net equity ($)")
    equity_axis.legend(loc="upper left")
    equity_axis.grid(alpha=0.25)

    drawdown_axis.plot(
        strategy_drawdown.index,
        strategy_drawdown,
        label=f"Strategy max DD: USD {strategy_drawdown.min():,.2f}",
        color="#1565c0",
        linewidth=1.7,
    )
    drawdown_axis.plot(
        buy_hold_drawdown.index,
        buy_hold_drawdown,
        label=f"Buy-and-hold max DD: USD {buy_hold_drawdown.min():,.2f}",
        color="#ef6c00",
        linewidth=1.2,
    )
    drawdown_axis.fill_between(
        strategy_drawdown.index, strategy_drawdown, 0, color="#1565c0", alpha=0.12
    )
    drawdown_axis.fill_between(
        buy_hold_drawdown.index, buy_hold_drawdown, 0, color="#ef6c00", alpha=0.12
    )
    drawdown_axis.set_ylabel("Drawdown ($)")
    drawdown_axis.set_xlabel("Time")
    drawdown_axis.legend(loc="lower left")
    drawdown_axis.grid(alpha=0.25)

    figure.tight_layout()
    figure.savefig(OUTPUT_FILE, dpi=180, bbox_inches="tight")
    plt.close(figure)
    print(f"Saved {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
