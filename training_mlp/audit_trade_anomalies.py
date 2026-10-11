"""Audit TradeStation exits whose absolute per-contract P&L exceeds a limit."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from training_mlp.build_master_dataset import load_master_trades


DEFAULT_TRADES = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/trades_30_master.csv"
)
DEFAULT_BARS = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/data_30_master.txt"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/reports/trade_execution_anomalies.csv"
)


class TradeAuditError(RuntimeError):
    """Raised when the TradeStation trade audit cannot be completed safely."""


def _money(values: pd.Series) -> pd.Series:
    text = values.astype(str).str.strip()
    negative = text.str.contains("(", regex=False)
    parsed = pd.to_numeric(
        text.str.replace(r"[$,()]", "", regex=True), errors="coerce"
    )
    parsed.loc[negative] *= -1.0
    return parsed


def pair_completed_trades(
    trades_path: Path, *, signal_name: str = "MA2CrossLE"
) -> pd.DataFrame:
    """Pair each numbered MA entry with its immediately following exit."""
    trades = load_master_trades(trades_path)
    rows: list[dict[str, object]] = []
    position = 0
    while position < len(trades):
        entry = trades.iloc[position]
        if position + 1 >= len(trades):
            break
        exit_row = trades.iloc[position + 1]
        if pd.isna(entry["#"]) or pd.notna(exit_row["#"]):
            raise TradeAuditError(f"invalid entry/exit pairing at trade row {position}")
        if entry["Signal"] == signal_name and pd.notna(exit_row["_timestamp"]):
            pnl = _money(pd.Series([entry["Net Profit - Cum Net Profit"]])).iloc[0]
            entry_price = _money(pd.Series([entry["Price"]])).iloc[0]
            exit_price = _money(pd.Series([exit_row["Price"]])).iloc[0]
            if pd.isna(pnl) or pd.isna(entry_price) or pd.isna(exit_price):
                raise TradeAuditError(f"invalid price or P&L for trade {entry['#']}")
            rows.append(
                {
                    "trade_id": int(entry["#"]),
                    "entry_type": entry["Type"],
                    "entry_time": entry["_timestamp"],
                    "exit_time": exit_row["_timestamp"],
                    "duration_seconds": (
                        exit_row["_timestamp"] - entry["_timestamp"]
                    ).total_seconds(),
                    "entry_signal": entry["Signal"],
                    "exit_signal": exit_row["Signal"],
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "price_change_points": float(exit_price - entry_price),
                    "trade_pnl": float(pnl),
                    "absolute_pnl": abs(float(pnl)),
                }
            )
        position += 2
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise TradeAuditError(f"no completed '{signal_name}' trades found")
    return frame


def load_bars(path: Path) -> pd.DataFrame:
    """Load exact bar OHLC values for entry/exit context."""
    bars = pd.read_csv(path)
    required = {"Date", "Time", "Open", "High", "Low", "Close"}
    missing = required - set(bars.columns)
    if missing:
        raise TradeAuditError(f"bar file is missing: {', '.join(sorted(missing))}")
    bars["bar_time"] = pd.to_datetime(
        bars["Date"].astype(str) + " " + bars["Time"].astype(str),
        format="%m/%d/%Y %H:%M:%S",
        errors="coerce",
    )
    return bars.loc[:, ["bar_time", "Open", "High", "Low", "Close"]]


def audit(
    trades_path: Path,
    bars_path: Path,
    *,
    absolute_pnl_limit: float = 70.0,
    expected_move_points: float = 1.0,
    point_value: float = 50.0,
    signal_name: str = "MA2CrossLE",
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Return flagged trades and an audit summary using a strict > limit."""
    if absolute_pnl_limit < 0:
        raise TradeAuditError("absolute_pnl_limit must be nonnegative")
    if expected_move_points <= 0 or point_value <= 0:
        raise TradeAuditError("expected_move_points and point_value must be positive")
    trades = pair_completed_trades(trades_path, signal_name=signal_name)
    bars = load_bars(bars_path)
    entry_bars = bars.rename(
        columns={
            "bar_time": "entry_time",
            "Open": "entry_bar_open",
            "High": "entry_bar_high",
            "Low": "entry_bar_low",
            "Close": "entry_bar_close",
        }
    )
    exit_bars = bars.rename(
        columns={
            "bar_time": "exit_time",
            "Open": "exit_bar_open",
            "High": "exit_bar_high",
            "Low": "exit_bar_low",
            "Close": "exit_bar_close",
        }
    )
    trades = trades.merge(entry_bars, on="entry_time", how="left", validate="many_to_one")
    trades = trades.merge(exit_bars, on="exit_time", how="left", validate="many_to_one")
    long_trade = trades["entry_type"].eq("Buy")
    target_exit = trades["exit_signal"].eq("Profit Target")
    expected_target = np.where(
        long_trade,
        trades["entry_price"] + expected_move_points,
        trades["entry_price"] - expected_move_points,
    )
    expected_stop = np.where(
        long_trade,
        trades["entry_price"] - expected_move_points,
        trades["entry_price"] + expected_move_points,
    )
    trades["expected_exit_price"] = np.where(
        target_exit, expected_target, expected_stop
    )
    trades["expected_pnl"] = np.where(
        target_exit, expected_move_points * point_value, -expected_move_points * point_value
    )
    trades["pnl_vs_expected"] = trades["trade_pnl"] - trades["expected_pnl"]
    target_beyond = np.where(
        long_trade,
        trades["exit_price"] - expected_target,
        expected_target - trades["exit_price"],
    )
    stop_beyond = np.where(
        long_trade,
        expected_stop - trades["exit_price"],
        trades["exit_price"] - expected_stop,
    )
    trades["fill_beyond_expected_points"] = np.where(
        target_exit, target_beyond, stop_beyond
    )
    trades["entry_bar_crossed_expected_level"] = np.where(
        target_exit,
        np.where(
            long_trade,
            trades["entry_bar_high"] >= expected_target,
            trades["entry_bar_low"] <= expected_target,
        ),
        np.where(
            long_trade,
            trades["entry_bar_low"] <= expected_stop,
            trades["entry_bar_high"] >= expected_stop,
        ),
    )
    trades["exit_matches_exit_bar_open"] = np.isclose(
        trades["exit_price"], trades["exit_bar_open"], equal_nan=False
    )
    trades["entry_bar_range_points"] = (
        trades["entry_bar_high"] - trades["entry_bar_low"]
    )
    flagged = trades.loc[trades["absolute_pnl"] > absolute_pnl_limit].copy()
    flagged["anomaly_type"] = np.where(
        flagged["trade_pnl"] < 0, "oversized_loss", "oversized_profit"
    )
    flagged = flagged.sort_values(
        ["absolute_pnl", "entry_time"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    summary = {
        "completed_trades": int(len(trades)),
        "absolute_pnl_limit": float(absolute_pnl_limit),
        "flagged_trades": int(len(flagged)),
        "flagged_rate": float(len(flagged) / len(trades)),
        "oversized_losses": int((flagged["trade_pnl"] < 0).sum()),
        "oversized_profits": int((flagged["trade_pnl"] > 0).sum()),
        "largest_loss": float(trades["trade_pnl"].min()),
        "largest_profit": float(trades["trade_pnl"].max()),
        "median_duration_seconds": float(trades["duration_seconds"].median()),
        "p95_duration_seconds": float(trades["duration_seconds"].quantile(0.95)),
        "flagged_exit_matches_bar_open": int(
            flagged["exit_matches_exit_bar_open"].sum()
        ),
        "flagged_entry_bar_crossed_expected_level": int(
            flagged["entry_bar_crossed_expected_level"].sum()
        ),
        "expected_move_points": float(expected_move_points),
        "point_value": float(point_value),
        "signal_name": signal_name,
    }
    return trades, flagged, summary


def write_report_suite(
    trades: pd.DataFrame,
    flagged: pd.DataFrame,
    summary: dict[str, object],
    *,
    anomaly_output: Path,
) -> dict[str, Path]:
    """Write reusable anomaly, distribution, duration, and exit-signal reports."""
    anomaly_output.parent.mkdir(parents=True, exist_ok=True)
    flagged.to_csv(anomaly_output, index=False)
    stem = anomaly_output.with_suffix("")

    pnl_edges = [-np.inf, -500, -250, -150, -100, -70, -50, 0, 50, 70, 100, 150, 250, 500, np.inf]
    pnl_bands = pd.cut(trades["trade_pnl"], pnl_edges, right=True)
    pnl_distribution = (
        pnl_bands.value_counts(sort=False)
        .rename_axis("pnl_band")
        .reset_index(name="trades")
    )
    pnl_distribution["percentage"] = pnl_distribution["trades"] / len(trades)

    duration_distribution = (
        trades["duration_seconds"]
        .value_counts()
        .sort_index()
        .rename_axis("duration_seconds")
        .reset_index(name="trades")
    )
    duration_distribution["percentage"] = duration_distribution["trades"] / len(trades)

    exit_summary = (
        trades.groupby("exit_signal", dropna=False)
        .agg(
            trades=("trade_id", "size"),
            average_pnl=("trade_pnl", "mean"),
            median_pnl=("trade_pnl", "median"),
            minimum_pnl=("trade_pnl", "min"),
            maximum_pnl=("trade_pnl", "max"),
            average_duration_seconds=("duration_seconds", "mean"),
            exit_matches_bar_open=("exit_matches_exit_bar_open", "sum"),
            entry_bar_crossed_expected=("entry_bar_crossed_expected_level", "sum"),
        )
        .reset_index()
    )
    anomaly_counts = flagged.groupby("exit_signal").size().rename("anomalies")
    exit_summary = exit_summary.merge(
        anomaly_counts, on="exit_signal", how="left"
    ).fillna({"anomalies": 0})

    all_trades_path = stem.with_name(stem.name + "_all_trades.csv")
    pnl_path = stem.with_name(stem.name + "_pnl_distribution.csv")
    duration_path = stem.with_name(stem.name + "_duration_distribution.csv")
    exits_path = stem.with_name(stem.name + "_exit_summary.csv")
    summary_path = stem.with_name(stem.name + "_summary.json")
    trades.to_csv(all_trades_path, index=False)
    pnl_distribution.to_csv(pnl_path, index=False)
    duration_distribution.to_csv(duration_path, index=False)
    exit_summary.to_csv(exits_path, index=False)
    summary_path.write_text(
        json.dumps(
            {"created_at": datetime.now().astimezone().isoformat(), **summary},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "anomalies": anomaly_output,
        "all_trades": all_trades_path,
        "pnl_distribution": pnl_path,
        "duration_distribution": duration_path,
        "exit_summary": exits_path,
        "summary": summary_path,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=Path, default=DEFAULT_TRADES)
    parser.add_argument("--bars", type=Path, default=DEFAULT_BARS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--absolute-pnl-limit", type=float, default=70.0)
    parser.add_argument("--expected-move-points", type=float, default=1.0)
    parser.add_argument("--point-value", type=float, default=50.0)
    parser.add_argument("--signal-name", default="MA2CrossLE")
    return parser


def main() -> None:
    args = _parser().parse_args()
    trades, flagged, summary = audit(
        args.trades,
        args.bars,
        absolute_pnl_limit=args.absolute_pnl_limit,
        expected_move_points=args.expected_move_points,
        point_value=args.point_value,
        signal_name=args.signal_name,
    )
    paths = write_report_suite(
        trades, flagged, summary, anomaly_output=args.output
    )
    print(
        f"Flagged {summary['flagged_trades']:,}/{summary['completed_trades']:,} "
        f"trades ({summary['flagged_rate']:.2%}) with |P&L| > "
        f"${summary['absolute_pnl_limit']:.2f}."
    )
    print(
        f"Oversized losses: {summary['oversized_losses']:,}; "
        f"oversized profits: {summary['oversized_profits']:,}."
    )
    print(
        f"Flagged exits at next bar open: "
        f"{summary['flagged_exit_matches_bar_open']:,}/"
        f"{summary['flagged_trades']:,}."
    )
    print("Reports:")
    for name, path in paths.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
