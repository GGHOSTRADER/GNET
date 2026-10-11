"""Build an isolated 13-feature dataset from matching ESU26 bars and trades.

The corrected strategy signals at the close of one 30-second bar, then fills
at the next bar's open. The model sees features from the completed signal bar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.stage_spliced_trade_outcomes import _completed_trades
from training_mlp.study_pipeline import engineer_features, load_bars


ROOT = Path(__file__).resolve().parent / "strategies/MA2CrossLE"
BARS = ROOT / "inputs/data_30_update_2026-06-14_to_2026-09-17.txt"
TRADES = ROOT / "inputs/trades_30_libb_2026-06-15_to_2026-09-17.csv"
OUTPUT = ROOT / "processed/ma2cross_esu26_closed_bar_canonical_2026-09-18.parquet"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset(bars_path: Path = BARS, trades_path: Path = TRADES,
                  output_path: Path = OUTPUT) -> dict[str, object]:
    bars = load_bars(bars_path)
    if bars.empty or bars["Date/Time"].duplicated().any():
        raise ValueError("bar file is empty or contains duplicate timestamps")
    if bars[["Open", "High", "Low", "Close", "Up", "Down"]].isna().any().any():
        raise ValueError("bar file has missing market values")
    if ((bars[["Up", "Down"]] < 0).any().any() or
            (bars["High"] < bars[["Open", "Close", "Low"]].max(axis=1)).any() or
            (bars["Low"] > bars[["Open", "Close", "High"]].min(axis=1)).any()):
        raise ValueError("bar file violates OHLC or volume invariants")

    features = engineer_features(bars, vwap_mode="canonical")
    trades = _completed_trades(trades_path, "esu26")
    bar_end = features["Date/Time"].max()
    if (trades["exit_time"] > bar_end).any():
        raise ValueError("a trade exit extends beyond the available bar history")
    if trades["entry_time"].duplicated().any():
        raise ValueError("trade export has duplicate entry timestamps")

    fast = features["Close"].rolling(9, min_periods=9).mean()
    slow = features["Close"].rolling(18, min_periods=18).mean()
    cross = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    entry_bars = features[["Date/Time", "Open", "High", "Low"]].rename(columns={
        "Date/Time": "entry_time", "Open": "bar_open",
        "High": "bar_high", "Low": "bar_low",
    })
    entry_bars["candidate_time"] = features["Date/Time"].shift(1)
    entry_bars["closed_bar_cross"] = cross.shift(1, fill_value=False)
    for name in FEATURE_NAMES:
        entry_bars[name] = features[name].shift(1)

    joined = trades.merge(
        entry_bars, on="entry_time", how="left", validate="one_to_one", indicator=True
    )
    if not joined["_merge"].eq("both").all():
        raise ValueError("a trade entry has no exact matching 30-second bar")
    if not joined["closed_bar_cross"].all():
        raise ValueError("a trade entry lacks a preceding closed-bar crossover")
    if joined[["candidate_time", *FEATURE_NAMES]].isna().any().any():
        raise ValueError("a trade has missing candidate-time features")
    if ((joined.entry_price < joined.bar_low) |
            (joined.entry_price > joined.bar_high)).any():
        raise ValueError("a trade entry price lies outside its matching bar")
    if (joined.candidate_time >= joined.entry_time).any():
        raise ValueError("candidate features were not available before entry")

    joined = joined.drop(columns=["_merge"])
    joined["Date/Time"] = joined["candidate_time"]
    joined["t1"] = joined["exit_time"]
    joined["Label"] = joined["outcome_positive"]
    joined = joined.sort_values("Date/Time", kind="stable").reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    features_path = output_path.with_name(output_path.stem + "_bar_features.parquet")
    features.to_parquet(features_path, index=False)
    joined.to_parquet(output_path, index=False)
    csv_path = output_path.with_suffix(".csv")
    joined.to_csv(csv_path, index=False)
    summary: dict[str, object] = {
        "bar_source": str(bars_path.resolve()),
        "bar_sha256": _hash(bars_path),
        "trade_source": str(trades_path.resolve()),
        "trade_sha256": _hash(trades_path),
        "bar_count": int(len(bars)),
        "bar_first": str(bars["Date/Time"].min()),
        "bar_last": str(bar_end),
        "trade_count": int(len(joined)),
        "trade_first_entry": str(joined["entry_time"].min()),
        "trade_last_entry": str(joined["entry_time"].max()),
        "positive_labels": int(joined["Label"].sum()),
        "entry_at_bar_open": int((joined.entry_price == joined.bar_open).sum()),
        "closed_bar_cross_matches": int(joined.closed_bar_cross.sum()),
        "vwap_mode": "canonical_close_weighted_by_up_plus_down_since_18_ET",
        "feature_time_rule": "preceding completed signal bar",
        "cost_usd_per_side": 3.24,
        "feature_count": len(FEATURE_NAMES),
        "dataset_parquet": str(output_path.resolve()),
        "dataset_csv": str(csv_path.resolve()),
        "bar_features": str(features_path.resolve()),
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=BARS)
    parser.add_argument("--trades", type=Path, default=TRADES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build_dataset(args.bars, args.trades, args.output), indent=2))


if __name__ == "__main__":
    main()
