"""Calculate out-of-sample trading statistics from PWF validation predictions."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from training_mlp.build_master_dataset import load_master_trades


DEFAULT_PREDICTIONS = Path(
    "training_mlp/strategies/MA2CrossLE/reports/pwf_feature_comparison/"
    "validation_predictions.parquet"
)
DEFAULT_TRADES = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/trades_30_master.csv"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/reports/pwf_feature_comparison/"
    "trading_statistics_cost_adjusted.csv"
)


class TradingStatisticsError(RuntimeError):
    """Raised when exact prediction-to-trade statistics cannot be calculated."""


def load_entry_pnl(path: Path, *, signal_name: str = "MA2CrossLE") -> pd.DataFrame:
    """Extract exact entry timestamps and TradeStation per-trade P&L."""
    trades = load_master_trades(path)
    entries = trades[
        (trades["Type"] == "Buy") & (trades["Signal"] == signal_name)
    ].copy()
    pnl_column = "Net Profit - Cum Net Profit"
    if pnl_column not in entries.columns:
        raise TradingStatisticsError(f"trade report has no '{pnl_column}' column")
    entries["trade_pnl"] = pd.to_numeric(
        entries[pnl_column]
            .astype(str)
            .str.replace(r"[$,()]", "", regex=True)
            .str.strip(),
        errors="coerce",
    )
    parenthesized = entries[pnl_column].astype(str).str.contains("(", regex=False)
    entries.loc[parenthesized, "trade_pnl"] *= -1.0
    if entries[["_timestamp", "trade_pnl"]].isna().any().any():
        raise TradingStatisticsError("entry timestamps or P&L contain invalid values")
    if entries["_timestamp"].duplicated().any():
        raise TradingStatisticsError("trade entries contain duplicate timestamps")
    return entries.loc[:, ["_timestamp", "trade_pnl"]].rename(
        columns={"_timestamp": "Date/Time"}
    )


def trade_statistics(pnl: np.ndarray, *, candidates: int) -> dict[str, float | int]:
    """Return chronological per-trade and equity-curve statistics."""
    values = np.asarray(pnl, dtype=np.float64)
    wins = values[values > 0]
    losses = values[values < 0]
    equity = values.cumsum()
    peaks = np.maximum.accumulate(np.concatenate(([0.0], equity)))
    drawdowns = peaks[1:] - equity
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    standard_deviation = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    return {
        "candidates": int(candidates),
        "approved_trades": int(len(values)),
        "approval_rate": float(len(values) / candidates),
        "net_profit": float(values.sum()),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else np.inf,
        "win_rate": float(len(wins) / len(values)) if len(values) else np.nan,
        "average_trade": float(values.mean()) if len(values) else np.nan,
        "median_trade": float(np.median(values)) if len(values) else np.nan,
        "average_win": float(wins.mean()) if len(wins) else np.nan,
        "average_loss": float(losses.mean()) if len(losses) else np.nan,
        "payoff_ratio": (
            float(wins.mean() / -losses.mean()) if len(wins) and len(losses) else np.nan
        ),
        "maximum_drawdown": float(drawdowns.max()) if len(drawdowns) else 0.0,
        "largest_win": float(values.max()) if len(values) else np.nan,
        "largest_loss": float(values.min()) if len(values) else np.nan,
        "trade_sequence_sharpe": (
            float(values.mean() / standard_deviation * np.sqrt(len(values)))
            if standard_deviation > 0
            else np.nan
        ),
    }


def analyze(
    predictions_path: Path,
    trades_path: Path,
    *,
    threshold: float = 0.5,
    commission_per_side: float = 2.23,
) -> pd.DataFrame:
    """Join exact events, filter approved trades, and summarize each model."""
    if commission_per_side < 0:
        raise TradingStatisticsError("commission_per_side must be nonnegative")
    predictions = pd.read_parquet(predictions_path)
    predictions["Date/Time"] = pd.to_datetime(
        predictions["Date/Time"], errors="coerce"
    )
    entries = load_entry_pnl(trades_path)
    merged = predictions.merge(
        entries, on="Date/Time", how="left", validate="many_to_one"
    )
    if merged["trade_pnl"].isna().any():
        missing = int(merged["trade_pnl"].isna().sum())
        raise TradingStatisticsError(f"{missing} predictions have no exact trade P&L")
    rows = []
    for model, group in merged.groupby("model", sort=False):
        ordered = group.sort_values("Date/Time", kind="stable")
        approved = ordered.loc[
            ordered["probability"] >= threshold, "trade_pnl"
        ] - (2.0 * commission_per_side)
        rows.append(
            {
                "model": model,
                "threshold": threshold,
                "commission_per_side": commission_per_side,
                "commission_round_trip": 2.0 * commission_per_side,
                **trade_statistics(approved.to_numpy(), candidates=len(ordered)),
            }
        )
    return pd.DataFrame(rows)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--trades", type=Path, default=DEFAULT_TRADES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--commission-per-side", type=float, default=2.23)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = analyze(
        args.predictions,
        args.trades,
        threshold=args.threshold,
        commission_per_side=args.commission_per_side,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(result.to_string(index=False))
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
