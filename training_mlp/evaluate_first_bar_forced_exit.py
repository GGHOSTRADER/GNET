"""Evaluate a forced exit at the close of every trade's entry-stamped bar.

The experiment uses the point-in-time-correct prior-bar MLP holdout. Trades
that TradeStation already closed within the entry-stamped 30-second bar retain
their realized LIBB result. Any trade that remained open is repriced at that
bar's close. This is a bar-close research approximation, not a live rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "training_mlp/strategies/MA2CrossLE/reports"
PREDICTIONS = REPORT_ROOT / (
    "old_libb_prior_bar_ablation/identical_holdout_trade_predictions.csv"
)
BARS = ROOT / "training_mlp/strategies/MA2CrossLE/inputs/data_30_master.txt"
OUTPUT_DIR = REPORT_ROOT / "corrected_holdout_forced_first_bar_exit"
PROBABILITY_COLUMN = "prob_prior_bar"
THRESHOLD = 0.50
POINT_VALUE = 50.0
ROUND_TRIP_COST = 6.48


def maximum_drawdown(pnl: np.ndarray) -> float:
    equity = pnl.cumsum()
    peaks = np.maximum.accumulate(np.concatenate(([0.0], equity)))[1:]
    return float((equity - peaks).min())


def summarize(pnl: np.ndarray) -> dict[str, float | int]:
    winners = pnl > 0
    losers = pnl < 0
    gross_profit = float(pnl[winners].sum())
    gross_loss = float(-pnl[losers].sum())
    return {
        "trades": int(len(pnl)),
        "winning_trades": int(winners.sum()),
        "losing_trades": int(losers.sum()),
        "breakeven_trades": int((pnl == 0).sum()),
        "win_rate": float(winners.mean()),
        "net_profit": float(pnl.sum()),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
        "average_trade": float(pnl.mean()),
        "median_trade": float(np.median(pnl)),
        "maximum_trade": float(pnl.max()),
        "minimum_trade": float(pnl.min()),
        "maximum_drawdown": maximum_drawdown(pnl),
    }


def run() -> None:
    predictions = pd.read_csv(PREDICTIONS)
    predictions["entry_time"] = pd.to_datetime(predictions["entry_time"], errors="raise")
    predictions["exit_time"] = pd.to_datetime(predictions["exit_time"], errors="raise")
    approved = predictions.loc[
        predictions[PROBABILITY_COLUMN] >= THRESHOLD
    ].copy()

    bars = pd.read_csv(BARS)
    bars["entry_time"] = pd.to_datetime(
        bars["Date"].astype(str) + " " + bars["Time"].astype(str), errors="raise"
    )
    if bars["entry_time"].duplicated().any():
        raise RuntimeError("bar source contains duplicate timestamps")

    approved = approved.merge(
        bars[["entry_time", "Close"]], on="entry_time", how="left", validate="many_to_one"
    )
    if approved["Close"].isna().any():
        missing = approved.loc[approved["Close"].isna(), "entry_time"].head().tolist()
        raise RuntimeError(f"missing entry bars for approved trades: {missing}")

    same_bar = approved["entry_time"] == approved["exit_time"]
    approved["forced_exit_price"] = np.where(
        same_bar, approved["exit_price"], approved["Close"]
    )
    approved["forced_exit_source"] = np.where(
        same_bar, "realized_intrabar_stop_or_target", "entry_bar_close"
    )
    approved["forced_gross_pnl"] = (
        approved["forced_exit_price"] - approved["entry_price"]
    ) * POINT_VALUE
    approved["forced_net_pnl"] = approved["forced_gross_pnl"] - ROUND_TRIP_COST
    approved = approved.sort_values(["entry_time", "trade_number"]).reset_index(drop=True)

    pnl = approved["forced_net_pnl"].to_numpy(dtype=float)
    original_pnl = approved["net_pnl_at_3_24_per_side"].to_numpy(dtype=float)
    metrics = {
        "experiment": "force positions still open to exit at entry 30-second bar close",
        "feature_timing": "preceding completed signal bar",
        "threshold": THRESHOLD,
        "point_value": POINT_VALUE,
        "round_trip_cost": ROUND_TRIP_COST,
        "bar_close_approximation": True,
        "start": approved["entry_time"].iloc[0].isoformat(),
        "end": approved["entry_time"].iloc[-1].isoformat(),
        "already_exited_in_entry_bar": int(same_bar.sum()),
        "repriced_at_entry_bar_close": int((~same_bar).sum()),
        "forced_exit": summarize(pnl),
        "original_stop_target": summarize(original_pnl),
        "net_improvement": float(pnl.sum() - original_pnl.sum()),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    approved["forced_cumulative_net_pnl"] = approved["forced_net_pnl"].cumsum()
    approved["original_cumulative_net_pnl"] = approved[
        "net_pnl_at_3_24_per_side"
    ].cumsum()
    approved.to_csv(OUTPUT_DIR / "forced_first_bar_exit_trades.csv", index=False)
    (OUTPUT_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    figure, axis = plt.subplots(figsize=(12, 6.5))
    axis.plot(
        approved["entry_time"],
        approved["forced_cumulative_net_pnl"],
        label="Forced exit at entry-bar close",
        linewidth=2,
    )
    axis.plot(
        approved["entry_time"],
        approved["original_cumulative_net_pnl"],
        label="Original stop/target exits",
        linewidth=1.5,
        alpha=0.8,
    )
    axis.axhline(0, color="#666666", linewidth=0.8)
    axis.set_title("Corrected 13-feature MLP holdout — first-bar forced-exit test")
    axis.set_xlabel("Entry time")
    axis.set_ylabel("Cumulative net P&L ($)")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "equity_comparison.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    print(json.dumps(metrics, indent=2))
    print(f"Saved outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    run()
