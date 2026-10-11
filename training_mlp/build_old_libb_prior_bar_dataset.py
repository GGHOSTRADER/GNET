"""Rebuild the old LIBB trades with features available before each entry bar.

This is a point-in-time ablation: preserve the original bar/trade exports,
original calendar-day OHLC4 VWAP, outcomes, and costs; shift only the feature
timestamp from the entry bar to its preceding completed 30-second bar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.stage_spliced_trade_outcomes import _completed_trades
from training_mlp.study_pipeline import engineer_features, load_bars


ROOT = Path(__file__).resolve().parent / "strategies/MA2CrossLE"
BARS = ROOT / "inputs/data_30_master.txt"
TRADES = ROOT / "inputs/trades_30_libb_2026-04-07.csv"
ORIGINAL = ROOT / "processed/df_features_labeled_master_libb_ts_vwap.csv"
OUTPUT = ROOT / "processed/ma2cross_old_libb_prior_bar_13.csv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset(bars_path: Path = BARS, trades_path: Path = TRADES,
                  original_path: Path = ORIGINAL, output_path: Path = OUTPUT) -> dict:
    bars = load_bars(bars_path)
    if bars.empty or bars["Date/Time"].duplicated().any():
        raise ValueError("bar timestamps must be nonempty and unique")
    features = engineer_features(bars, vwap_mode="bar")
    trades = _completed_trades(trades_path, "old_libb")
    if trades["entry_time"].duplicated().any():
        raise ValueError("trade entry timestamps must be unique")
    trades = trades.loc[trades["exit_time"] <= features["Date/Time"].max()].copy()

    # Verify that the historical feature calculation reproduces the dataset
    # used by the prior profitable study before shifting any timestamps.
    original = pd.read_csv(original_path)
    original["Date/Time"] = pd.to_datetime(original["Date/Time"])
    baseline = original[["Date/Time", *FEATURE_NAMES]].merge(
        features[["Date/Time", *FEATURE_NAMES]], on="Date/Time",
        how="left", validate="one_to_one", suffixes=("_old", "_rebuilt"),
    )
    if baseline.filter(like="_rebuilt").isna().any().any():
        raise ValueError("original dataset contains an unmatched or missing feature")
    largest_feature_difference = max(
        float(np.max(np.abs(baseline[f"{name}_old"] - baseline[f"{name}_rebuilt"])))
        for name in FEATURE_NAMES
    )
    if largest_feature_difference > 1e-8:
        raise ValueError(f"historical feature calculation changed: {largest_feature_difference}")

    # TradeStation's entry timestamp identifies the entry bar. A previous
    # row is always complete before that bar begins, including with IOG.
    entry_bars = features[["Date/Time", "Open", "High", "Low"]].rename(columns={
        "Date/Time": "entry_time", "Open": "bar_open",
        "High": "bar_high", "Low": "bar_low",
    })
    entry_bars["feature_time"] = features["Date/Time"].shift(1)
    for name in FEATURE_NAMES:
        entry_bars[name] = features[name].shift(1)
    joined = trades.merge(entry_bars, on="entry_time", how="left",
                          validate="one_to_one", indicator=True)
    if not joined["_merge"].eq("both").all():
        raise ValueError("an old trade entry has no matching bar")
    if joined[["feature_time", *FEATURE_NAMES]].isna().any().any():
        raise ValueError("an old trade lacks prior-bar features")
    if not joined["feature_time"].lt(joined["entry_time"]).all():
        raise ValueError("a feature timestamp is not before the entry")
    if ((joined.entry_price < joined.bar_low) |
            (joined.entry_price > joined.bar_high)).any():
        raise ValueError("an entry price is outside its entry bar")

    joined = joined.drop(columns=["_merge"])
    joined["Date/Time"] = joined["feature_time"]
    joined["t1"] = joined["exit_time"]
    joined["Label"] = joined["outcome_positive"]
    joined = joined.sort_values(["Date/Time", "trade_number"], kind="stable").reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joined.to_csv(output_path, index=False)
    summary = {
        "bar_source": str(bars_path.resolve()), "bar_sha256": _sha256(bars_path),
        "trade_source": str(trades_path.resolve()), "trade_sha256": _sha256(trades_path),
        "original_dataset": str(original_path.resolve()),
        "original_sha256": _sha256(original_path),
        "original_feature_max_absolute_difference": largest_feature_difference,
        "original_vwap_method": "calendar-day OHLC4 weighted by Up+Down",
        "changed_variable": "feature timestamp shifted from entry bar to immediately prior completed bar",
        "trades": len(joined), "positive_labels": int(joined.Label.sum()),
        "first_entry": str(joined.entry_time.min()), "last_entry": str(joined.entry_time.max()),
        "feature_count": len(FEATURE_NAMES), "round_trip_cost_usd": 6.48,
        "output": str(output_path.resolve()),
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=BARS)
    parser.add_argument("--trades", type=Path, default=TRADES)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build_dataset(args.bars, args.trades, args.original, args.output), indent=2))


if __name__ == "__main__":
    main()
