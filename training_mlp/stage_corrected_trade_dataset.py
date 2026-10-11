"""Stage corrected MA2CrossLE trades with features known at candidate time.

The strategy signals on a completed 30-second bar and enters at the next
bar's open. Features must therefore come from the preceding (signal) bar,
not from the entry bar. The two price vintages are kept separate at the
August handoff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.stage_spliced_trade_outcomes import _completed_trades


ROOT = Path(__file__).resolve().parent / "strategies/MA2CrossLE"
OLD_TRADES = ROOT / "inputs/trades_30_libb_2026-06-15_to_2026-09-17.csv"
NEW_TRADES = ROOT / "inputs/trades_30_libb_dec26_2026-08-16_to_2026-09-21.csv"
FEATURES = ROOT / "processed/features_spliced_canonical_2026-09-21.parquet"
OUTPUT = ROOT / "processed/ma2cross_corrected_jun_sep_2026.parquet"
OLD_START = pd.Timestamp("2026-06-14 18:00:00")
OLD_END = pd.Timestamp("2026-08-14 17:00:00")
NEW_START = pd.Timestamp("2026-08-16 18:00:00")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_corrected(
    old_path: Path = OLD_TRADES,
    new_path: Path = NEW_TRADES,
    features_path: Path = FEATURES,
    output_path: Path = OUTPUT,
) -> dict[str, object]:
    """Validate both trade vintages and save candidate-time feature rows."""
    bars = pd.read_parquet(features_path)
    required = {"Date/Time", "Open", "High", "Low", "Close", *FEATURE_NAMES}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"feature file lacks columns: {sorted(missing)}")
    if bars["Date/Time"].duplicated().any() or not bars["Date/Time"].is_monotonic_increasing:
        raise ValueError("feature bars must have unique, increasing timestamps")

    bar_end = bars["Date/Time"].max()
    old = _completed_trades(old_path, "old")
    new = _completed_trades(new_path, "new")
    old = old.loc[(old.entry_time >= OLD_START) & (old.entry_time <= OLD_END)].copy()
    new = new.loc[(new.entry_time >= NEW_START) & (new.exit_time <= bar_end)].copy()
    if (old.exit_time > OLD_END).any():
        raise ValueError("an old-vintage exit crosses the August handoff")
    trades = pd.concat([old, new], ignore_index=True)
    if trades.empty or trades.duplicated(["vintage", "trade_number"]).any():
        raise ValueError("trade selection is empty or contains duplicate trade numbers")

    bars = bars.copy()
    bars["vintage"] = "old"
    bars.loc[bars["Date/Time"] >= NEW_START, "vintage"] = "new"
    candidate_rows = []
    for vintage, group in bars.groupby("vintage", sort=False):
        group = group.reset_index(drop=True)
        fast = group["Close"].rolling(9, min_periods=9).mean()
        slow = group["Close"].rolling(18, min_periods=18).mean()
        closed_cross = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        entry_rows = group[["Date/Time", "Open", "High", "Low"]].rename(
            columns={"Date/Time": "entry_time", "Open": "bar_open",
                     "High": "bar_high", "Low": "bar_low"}
        )
        entry_rows["candidate_time"] = group["Date/Time"].shift(1)
        entry_rows["closed_bar_cross"] = closed_cross.shift(1, fill_value=False)
        entry_rows["vintage"] = vintage
        for feature in FEATURE_NAMES:
            entry_rows[feature] = group[feature].shift(1)
        candidate_rows.append(entry_rows)

    candidates = pd.concat(candidate_rows, ignore_index=True)
    joined = trades.merge(
        candidates, on=["vintage", "entry_time"], how="left",
        validate="one_to_one", indicator=True,
    )
    if not joined["_merge"].eq("both").all():
        raise ValueError("a trade entry does not match a feature bar")
    if not joined["closed_bar_cross"].all():
        raise ValueError("a trade entry lacks a crossover on the preceding completed bar")
    if joined[["candidate_time", *FEATURE_NAMES]].isna().any().any():
        raise ValueError("candidate-time features are unavailable for a trade")
    if ((joined.entry_price < joined.bar_low) | (joined.entry_price > joined.bar_high)).any():
        raise ValueError("a trade entry price lies outside its entry bar")
    if (joined.candidate_time >= joined.entry_time).any():
        raise ValueError("candidate time must precede entry time")

    joined = joined.drop(columns=["_merge"])
    joined = joined.sort_values("entry_time", kind="stable").reset_index(drop=True)
    # Match the existing trainer's event schema without moving the event start
    # forward to the fill bar, which would leak information from that bar.
    joined["Date/Time"] = joined["candidate_time"]
    joined["t1"] = joined["exit_time"]
    joined["Label"] = joined["outcome_positive"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joined.to_parquet(output_path, index=False)
    summary: dict[str, object] = {
        "dataset_ready_for_research_training": True,
        "deployed_model_unchanged": True,
        "feature_time_rule": "preceding completed crossover bar; never entry bar",
        "event_start_column": "Date/Time = candidate_time",
        "event_end_column": "t1 = exit_time",
        "label_column": "Label = net profit after $6.48 round-turn cost > 0",
        "old_source": str(old_path.resolve()),
        "old_sha256": _sha256(old_path),
        "new_source": str(new_path.resolve()),
        "new_sha256": _sha256(new_path),
        "feature_source": str(features_path.resolve()),
        "feature_sha256": _sha256(features_path),
        "old_start": str(OLD_START),
        "old_end": str(OLD_END),
        "new_start": str(NEW_START),
        "bar_end": str(bar_end),
        "old_selected": int(len(old)),
        "new_selected": int(len(new)),
        "total_selected": int(len(joined)),
        "positive_outcomes": int(joined.outcome_positive.sum()),
        "entry_at_bar_open": int((joined.entry_price == joined.bar_open).sum()),
        "entry_within_bar": int(len(joined)),
        "cost_usd_per_side": 3.24,
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-trades", type=Path, default=OLD_TRADES)
    parser.add_argument("--new-trades", type=Path, default=NEW_TRADES)
    parser.add_argument("--features", type=Path, default=FEATURES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(stage_corrected(args.old_trades, args.new_trades, args.features, args.output), indent=2))


if __name__ == "__main__":
    main()
