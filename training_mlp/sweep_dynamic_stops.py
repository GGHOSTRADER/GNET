"""Tick-level breakeven and trailing-stop sweep for corrected MLP approvals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "training_mlp/strategies/MA2CrossLE/reports"
PREDICTIONS = REPORTS / (
    "old_libb_prior_bar_ablation/identical_holdout_trade_predictions.csv"
)
TICK_ROOT = ROOT / "historical_vp/prepared_continuous_2026_09_21/parquet"
OUTPUT_DIR = REPORTS / "corrected_holdout_dynamic_stop_sweep"

THRESHOLD = 0.50
TICK_SIZE = 0.25
POINT_VALUE = 50.0
STOP_TICKS = 4
TARGET_TICKS = 4
ROUND_TRIP_COST = 6.48
PRICE_ADJUSTMENT = 67.75
SWEEP_TICKS = (1, 2, 3)


@dataclass(frozen=True)
class ExitResult:
    timestamp: pd.Timestamp
    price: float
    reason: str
    activated: bool


def session_date(timestamp: pd.Timestamp) -> str:
    day = timestamp.normalize()
    if timestamp.hour >= 18:
        day += pd.Timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def simulate_long_exit(
    timestamps: np.ndarray,
    prices: np.ndarray,
    entry_price: float,
    mode: str,
    activation_ticks: int,
    trail_distance_ticks: int | None = None,
) -> ExitResult:
    """Replay one long trade using first-observed-tick market-stop fills."""
    if mode not in {"baseline", "breakeven", "trailing"}:
        raise ValueError(f"unsupported mode: {mode}")
    if len(prices) == 0:
        raise ValueError("trade has no ticks")
    if mode == "trailing" and (
        trail_distance_ticks is None or trail_distance_ticks < 1
    ):
        raise ValueError("trailing mode requires a positive trail distance")

    initial_stop = entry_price - STOP_TICKS * TICK_SIZE
    target = entry_price + TARGET_TICKS * TICK_SIZE
    activation = entry_price + activation_ticks * TICK_SIZE
    active_stop = initial_stop
    best_price = entry_price
    activated = False

    for timestamp, price_value in zip(timestamps, prices):
        price = float(price_value)
        best_price = max(best_price, price)

        if price >= target:
            return ExitResult(pd.Timestamp(timestamp), target, "profit_target", activated)

        if mode != "baseline" and best_price >= activation:
            activated = True
            if mode == "breakeven":
                active_stop = max(active_stop, entry_price)
            else:
                active_stop = max(
                    active_stop,
                    best_price - trail_distance_ticks * TICK_SIZE,
                )

        if price <= active_stop:
            reason = mode if activated and active_stop > initial_stop else "initial_stop"
            return ExitResult(pd.Timestamp(timestamp), active_stop, reason, activated)

    raise RuntimeError("no exit condition was reached before the original exit boundary")


def summarize(frame: pd.DataFrame) -> dict[str, float | int]:
    pnl = frame["net_pnl"].to_numpy(dtype=float)
    winners = pnl > 0
    losers = pnl < 0
    equity = pnl.cumsum()
    peaks = np.maximum.accumulate(np.concatenate(([0.0], equity)))[1:]
    gross_profit = float(pnl[winners].sum())
    gross_loss = float(-pnl[losers].sum())
    return {
        "trades": int(len(frame)),
        "winners": int(winners.sum()),
        "losers": int(losers.sum()),
        "win_rate": float(winners.mean()),
        "net_profit": float(pnl.sum()),
        "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
        "average_trade": float(pnl.mean()),
        "median_trade": float(np.median(pnl)),
        "maximum_drawdown": float((equity - peaks).min()),
        "activated_trades": int(frame["activated"].sum()),
    }


def load_ticks(path: Path) -> pd.DataFrame:
    table = pq.read_table(path, columns=["timestamp", "price"])
    frame = table.to_pandas()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    return frame


def run() -> None:
    predictions = pd.read_csv(PREDICTIONS)
    predictions["entry_time"] = pd.to_datetime(predictions["entry_time"], errors="raise")
    predictions["exit_time"] = pd.to_datetime(predictions["exit_time"], errors="raise")
    approved = predictions.loc[
        predictions["prob_prior_bar"] >= THRESHOLD
    ].copy()
    approved["session_date"] = approved["entry_time"].map(session_date)
    approved["adjusted_entry_price"] = approved["entry_price"] + PRICE_ADJUSTMENT

    configurations = [("baseline", 0, None)]
    configurations.extend(("breakeven", ticks, None) for ticks in SWEEP_TICKS)
    configurations.extend(
        ("trailing", activation_ticks, distance_ticks)
        for activation_ticks in SWEEP_TICKS
        for distance_ticks in SWEEP_TICKS
    )
    result_rows: list[dict[str, object]] = []

    for session, session_trades in approved.groupby("session_date", sort=True):
        tick_path = TICK_ROOT / f"session_date={session}" / "ticks.parquet"
        if not tick_path.exists():
            raise FileNotFoundError(f"missing tick partition: {tick_path}")
        ticks = load_ticks(tick_path)
        tick_times = ticks["timestamp"].to_numpy()
        tick_prices = ticks["price"].to_numpy(dtype=float)

        for trade in session_trades.itertuples(index=False):
            # TradeStation timestamps identify the containing 30-second bar.
            # Replay its full tick interval, then retain only trades whose
            # unchanged stop/target outcome exactly matches TradeStation.
            entry_bar_start = trade.entry_time - pd.Timedelta(seconds=30)
            start = int(
                np.searchsorted(tick_times, np.datetime64(entry_bar_start), side="right")
            )
            end = int(
                np.searchsorted(tick_times, np.datetime64(trade.exit_time), side="right")
            )
            trade_times = tick_times[start:end]
            trade_prices = tick_prices[start:end]
            if len(trade_prices) == 0:
                raise RuntimeError(f"no ticks for trade {trade.trade_number}")

            for mode, activation_ticks, trail_distance_ticks in configurations:
                try:
                    result = simulate_long_exit(
                        trade_times,
                        trade_prices,
                        float(trade.adjusted_entry_price),
                        mode,
                        activation_ticks,
                        trail_distance_ticks,
                    )
                except RuntimeError as error:
                    raise RuntimeError(
                        f"trade {trade.trade_number} mode={mode} "
                        f"trail_distance={trail_distance_ticks} "
                        f"entry={trade.entry_time} exit={trade.exit_time}: {error}"
                    ) from error
                gross_pnl = (result.price - trade.adjusted_entry_price) * POINT_VALUE
                result_rows.append(
                    {
                        "trade_number": int(trade.trade_number),
                        "entry_time": trade.entry_time,
                        "original_exit_time": trade.exit_time,
                        "mode": mode,
                        "activation_ticks": activation_ticks,
                        "trail_distance_ticks": trail_distance_ticks,
                        "exit_time": result.timestamp,
                        "exit_price_adjusted_scale": result.price,
                        "exit_reason": result.reason,
                        "activated": result.activated,
                        "gross_pnl": gross_pnl,
                        "net_pnl": gross_pnl - ROUND_TRIP_COST,
                    }
                )

    results = pd.DataFrame(result_rows).sort_values(
        ["mode", "activation_ticks", "trail_distance_ticks", "entry_time", "trade_number"]
    )
    baseline = results.loc[results["mode"] == "baseline"].copy()
    expected = approved.set_index("trade_number")["net_pnl_at_3_24_per_side"]
    replayed = baseline.set_index("trade_number")["net_pnl"]
    differences = replayed.subtract(expected).abs()
    expected_reason = approved.set_index("trade_number")["exit_signal"]
    replayed_reason = baseline.set_index("trade_number")["exit_reason"].map(
        {"profit_target": "Profit Target", "initial_stop": "Stop Loss"}
    )
    validated_ids = differences.index[
        (differences < 1e-9) & (replayed_reason == expected_reason)
    ]
    validation = {
        "trades": int(len(baseline)),
        "exact_trade_matches": int(len(validated_ids)),
        "excluded_ambiguous_trades": int(len(baseline) - len(validated_ids)),
        "maximum_absolute_net_pnl_difference": float(differences.max()),
    }
    results = results.loc[results["trade_number"].isin(validated_ids)].copy()

    summaries: list[dict[str, object]] = []
    for (mode, activation_ticks, trail_distance_ticks), group in results.groupby(
        ["mode", "activation_ticks", "trail_distance_ticks"], sort=True, dropna=False
    ):
        summaries.append(
            {
                "mode": mode,
                "activation_ticks": int(activation_ticks),
                "trail_distance_ticks": (
                    None if pd.isna(trail_distance_ticks) else int(trail_distance_ticks)
                ),
                **summarize(group.sort_values(["entry_time", "trade_number"])),
            }
        )
    summary = pd.DataFrame(summaries).sort_values(
        "net_profit", ascending=False
    ).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(OUTPUT_DIR / "trade_results.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "sweep_summary.csv", index=False)
    best_configuration = summary.iloc[0].to_dict()
    if pd.isna(best_configuration["trail_distance_ticks"]):
        best_configuration["trail_distance_ticks"] = None
    metadata = {
        "prediction_source": str(PREDICTIONS),
        "tick_source": str(TICK_ROOT),
        "threshold": THRESHOLD,
        "tick_size": TICK_SIZE,
        "point_value": POINT_VALUE,
        "initial_stop_ticks": STOP_TICKS,
        "profit_target_ticks": TARGET_TICKS,
        "round_trip_cost": ROUND_TRIP_COST,
        "old_to_current_price_adjustment_points": PRICE_ADJUSTMENT,
        "fill_rule": "targets and stops filled at their order prices when touched",
        "validation": validation,
        "best_configuration": best_configuration,
    }
    (OUTPUT_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    figure, axis = plt.subplots(figsize=(11, 6.5))
    for (mode, activation_ticks, trail_distance_ticks), group in results.groupby(
        ["mode", "activation_ticks", "trail_distance_ticks"], sort=True, dropna=False
    ):
        ordered = group.sort_values(["entry_time", "trade_number"])
        if mode == "baseline":
            label = "Original stop/target"
        elif mode == "breakeven":
            label = f"breakeven activate {activation_ticks}"
        else:
            label = f"trail activate {activation_ticks}, distance {int(trail_distance_ticks)}"
        axis.plot(ordered["entry_time"], ordered["net_pnl"].cumsum(), label=label)
    axis.axhline(0, color="#666666", linewidth=0.8)
    axis.set_title("Corrected MLP holdout — dynamic-stop tick sweep")
    axis.set_xlabel("Entry time")
    axis.set_ylabel("Cumulative net P&L ($)")
    axis.grid(alpha=0.25)
    axis.legend(ncol=2, fontsize=9)
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "equity_curves.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    print(summary.to_string(index=False))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    run()
