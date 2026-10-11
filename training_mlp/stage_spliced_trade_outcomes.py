"""Stage old/new LIBB trade outcomes without assuming a candidate feature timestamp.

TradeStation timestamps time bars at their close. The Trades List timestamp
alone does not establish which completed bar informed a next-bar fill, especially
with IOG and LIBB enabled. This is an audit artifact until timing is verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from training_mlp.build_master_dataset import load_master_trades


ROOT = Path(__file__).resolve().parent / "strategies/MA2CrossLE"
OLD_TRADES = ROOT / "inputs/trades_30_libb_2026-04-07.csv"
NEW_TRADES = ROOT / "inputs/trades_30_libb_dec26_2026-08-16_to_2026-09-21.csv"
FEATURES = ROOT / "processed/features_spliced_canonical_2026-09-21.parquet"
OUTPUT = ROOT / "processed/trade_outcomes_spliced_libb_2026-09-21.parquet"
OLD_END = pd.Timestamp("2026-08-14 17:00:00")
NEW_START = pd.Timestamp("2026-08-16 18:00:00")
ROUND_TURN_COST = 6.48


def _money(values: pd.Series) -> pd.Series:
    text = values.astype(str).str.replace(r"[$,]", "", regex=True).str.strip()
    negative = text.str.startswith("(") & text.str.endswith(")")
    text = text.str.replace(r"[()]", "", regex=True)
    amounts = pd.to_numeric(text, errors="raise")
    return amounts.where(~negative, -amounts)


def _completed_trades(path: Path, vintage: str) -> pd.DataFrame:
    rows = load_master_trades(path)
    if len(rows) % 2:
        raise ValueError(f"unpaired trade row in {path}")
    entries = rows.iloc[::2].reset_index(drop=True)
    exits = rows.iloc[1::2].reset_index(drop=True)
    if entries["#"].isna().any() or exits["#"].notna().any():
        raise ValueError(f"TradeStation entry/exit pairs are malformed: {path}")
    if not entries["Signal"].eq("MA2CrossLE").all():
        raise ValueError(f"unexpected entry signal in {path}")
    if (exits["_timestamp"] < entries["_timestamp"]).any():
        raise ValueError(f"exit precedes entry in {path}")
    gross_pnl = _money(exits["Shares/Ctrts - Profit/Loss"])
    return pd.DataFrame({
        "vintage": vintage,
        "trade_number": entries["#"].astype("int64"),
        "entry_time": entries["_timestamp"],
        "exit_time": exits["_timestamp"],
        "entry_price": _money(entries["Price"]),
        "exit_price": _money(exits["Price"]),
        "exit_signal": exits["Signal"].astype(str),
        "gross_pnl": gross_pnl,
        "net_pnl_at_3_24_per_side": gross_pnl - ROUND_TURN_COST,
        "outcome_positive": (gross_pnl - ROUND_TURN_COST > 0).astype("int8"),
    })


def stage(old_path: Path, new_path: Path, features_path: Path, output_path: Path) -> dict:
    bars = pd.read_parquet(features_path, columns=["Date/Time", "Low", "High", "vwap_distance"])
    if bars["Date/Time"].duplicated().any():
        raise ValueError("duplicate feature timestamps")
    bar_end = bars["Date/Time"].max()
    old = _completed_trades(old_path, "old")
    new = _completed_trades(new_path, "new")
    old_selected = old.loc[old["entry_time"] <= OLD_END].copy()
    new_selected = new.loc[(new["entry_time"] >= NEW_START) & (new["entry_time"] <= bar_end)].copy()
    selected = pd.concat([old_selected, new_selected], ignore_index=True)
    if ((selected["vintage"] == "old") & (selected["exit_time"] > OLD_END)).any():
        raise ValueError("old-vintage exits cross the handoff")
    if (selected["exit_time"] > bar_end).any():
        raise ValueError("selected exits extend beyond bar history")
    checked = selected.merge(
        bars, left_on="entry_time", right_on="Date/Time",
        how="left", validate="many_to_one", indicator=True,
    )
    if not checked["_merge"].eq("both").all():
        raise ValueError("a selected trade has no exact entry bar")
    if checked["vwap_distance"].isna().any():
        raise ValueError("a selected trade falls in the feature warm-up")
    if ((checked["entry_price"] < checked["Low"]) | (checked["entry_price"] > checked["High"])).any():
        raise ValueError("a trade entry price is outside its matching bar")
    if selected.duplicated(["vintage", "trade_number"]).any():
        raise ValueError("duplicate vintage/trade number")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.sort_values("entry_time", kind="stable").to_parquet(output_path, index=False)
    summary = {
        "training_ready": False,
        "reason": "TradeStation entry timestamps have not been verified against live completed-bar candidate timing",
        "old_source": str(old_path.resolve()),
        "new_source": str(new_path.resolve()),
        "old_sha256": hashlib.sha256(old_path.read_bytes()).hexdigest(),
        "new_sha256": hashlib.sha256(new_path.read_bytes()).hexdigest(),
        "feature_source": str(features_path.resolve()),
        "old_cutoff": str(OLD_END),
        "new_start": str(NEW_START),
        "bar_end": str(bar_end),
        "old_selected": len(old_selected),
        "new_selected": len(new_selected),
        "new_after_bar_end": int((new["entry_time"] > bar_end).sum()),
        "total_selected": len(selected),
        "positive_outcomes": int(selected["outcome_positive"].sum()),
        "round_turn_cost_usd": ROUND_TURN_COST,
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
    print(json.dumps(stage(args.old_trades, args.new_trades, args.features, args.output), indent=2))


if __name__ == "__main__":
    main()
