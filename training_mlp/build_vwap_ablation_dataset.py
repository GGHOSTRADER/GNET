"""Build a controlled old-VWAP-proxy counterpart to a canonical MA dataset.

Only ``vwap_distance`` is replaced.  Every event, label, t1 value, and other
feature remains byte-for-byte sourced from the supplied canonical dataset.
This module exists for ablation analysis and must not be used for deployment.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from training_mlp.study_pipeline import load_bars


DEFAULT_BARS = Path(
    "training_mlp/strategies/MA2CrossLE/inputs/data_30_master.txt"
)
DEFAULT_CANONICAL = Path(
    "training_mlp/strategies/MA2CrossLE/processed/"
    "df_features_labeled_master_libb_ts_vwap.csv"
)
DEFAULT_OUTPUT = Path(
    "training_mlp/strategies/MA2CrossLE/processed/"
    "df_features_labeled_master_libb_old_vwap_ablation.csv"
)


def old_proxy_vwap_distance(bars: pd.DataFrame) -> pd.DataFrame:
    """Return the superseded close-weighted calendar-day VWAP distance."""
    frame = bars.copy().sort_values("Date/Time", kind="stable").reset_index(drop=True)
    volume = frame["Up"] + frame["Down"]
    calendar_day = frame["Date/Time"].dt.date
    cumulative_volume = volume.groupby(calendar_day, sort=False).cumsum()
    cumulative_price_volume = (frame["Close"] * volume).groupby(
        calendar_day, sort=False
    ).cumsum()
    old_vwap = cumulative_price_volume / cumulative_volume.replace(0, np.nan)

    previous_close = frame["Close"].shift()
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(14).mean()
    distance = (frame["Close"] - old_vwap) / atr.replace(0, np.nan)
    return pd.DataFrame(
        {"Date/Time": frame["Date/Time"], "vwap_distance_old_proxy": distance}
    )


def build_ablation_dataset(
    canonical_path: Path, bars_path: Path, output_path: Path
) -> pd.DataFrame:
    canonical = pd.read_csv(
        canonical_path, parse_dates=["Date/Time", "t1"]
    )
    if canonical["Date/Time"].duplicated().any():
        raise ValueError("canonical event timestamps must be unique")

    proxy = old_proxy_vwap_distance(load_bars(bars_path))
    result = canonical.merge(proxy, on="Date/Time", how="left", validate="one_to_one")
    if result["vwap_distance_old_proxy"].isna().any():
        missing = int(result["vwap_distance_old_proxy"].isna().sum())
        raise ValueError(f"old proxy VWAP is missing for {missing} canonical events")
    result["vwap_distance"] = result.pop("vwap_distance_old_proxy")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=DEFAULT_BARS)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = build_ablation_dataset(args.canonical, args.bars, args.output)
    print(f"VWAP ablation dataset: {args.output}")
    print(f"Rows: {len(result):,}; only vwap_distance was replaced.")


if __name__ == "__main__":
    main()
