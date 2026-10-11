"""Regression checks for the single-vintage closed-bar research dataset."""

import pandas as pd

from training_mlp.build_esu26_canonical_dataset import build_dataset


def test_candidate_features_precede_the_entry_bar(tmp_path):
    times = pd.date_range("2026-06-14 18:00:30", periods=70, freq="30s")
    close = [100.0] * 70
    close[65] = 101.0  # Completed-bar crossover; entry is bar 66.
    bars = pd.DataFrame({
        "Date": times.strftime("%m/%d/%Y"),
        "Time": times.strftime("%H:%M:%S"),
        "Open": [100.0] * 70,
        "High": [101.0] * 70,
        "Low": [99.0] * 70,
        "Close": close,
        "Up": [100] * 70,
        "Down": [100] * 70,
    })
    bars_path = tmp_path / "bars.txt"
    bars.to_csv(bars_path, index=False)
    entry = "6/14/2026 " + times[66].strftime("%I:%M:%S %p").lstrip("0")
    exit_time = "6/14/2026 " + times[67].strftime("%I:%M:%S %p").lstrip("0")
    trades_path = tmp_path / "trades.csv"
    trades_path.write_text(
        "TradeStation Trades List\n"
        "#,Type,Date/Time,Signal,Price,Shares/Ctrts - Profit/Loss,% Profit\n"
        f"1,Buy,{entry},MA2CrossLE,$100.00,1,0.01%\n"
        f",Sell,{exit_time},Profit Target,$101.00,$50.00,\n",
        encoding="utf-8",
    )
    output = tmp_path / "dataset.parquet"
    summary = build_dataset(bars_path, trades_path, output)
    staged = pd.read_parquet(output)
    assert summary["trade_count"] == 1
    assert summary["closed_bar_cross_matches"] == 1
    assert staged.loc[0, "Date/Time"] == times[65]
    assert staged.loc[0, "entry_time"] == times[66]
    assert staged.loc[0, "Label"] == 1
