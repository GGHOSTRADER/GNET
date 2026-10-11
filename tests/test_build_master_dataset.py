from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from training_mlp.build_master_dataset import (
    MasterBuildResult,
    MasterDatasetError,
    find_trade_header,
    load_master_trades,
    write_master_dataset,
)


def test_finds_trades_list_header_at_dynamic_position(tmp_path: Path) -> None:
    report = tmp_path / "report.csv"
    report.write_text(
        "Performance Summary,,,,\n\n"
        "TradeStation Trades List,,,,\n"
        "#,Type,Date/Time,Signal,Price,% Profit\n"
        "1,Buy,03/15/2026 06:39:30 PM,MA2CrossLE,6738.25,0.01%\n",
        encoding="utf-8",
    )

    assert find_trade_header(report) == 3


def test_load_master_trades_accepts_trades_list_only_export(tmp_path: Path) -> None:
    report = tmp_path / "report.csv"
    report.write_text(
        "TradeStation Trades List,,,,,\n"
        ",,,,,\n"
        "#,Type,Date/Time,Signal,Price,% Profit\n"
        "1,Buy,03/15/2026 06:39:30 PM,MA2CrossLE,6738.25,0.01%\n"
        ",Sell,03/15/2026 06:40:00 PM,Profit Target,6739.25,\n",
        encoding="utf-8",
    )

    frame = load_master_trades(report)

    assert frame["Type"].tolist() == ["Buy", "Sell"]
    assert frame.loc[0, "% Profit"] == pytest.approx(0.01)
    assert frame.loc[0, "_timestamp"] == pd.Timestamp("2026-03-15 18:39:30")


def test_writer_refuses_legacy_output_name(tmp_path: Path) -> None:
    result = MasterBuildResult(pd.DataFrame(), {})

    with pytest.raises(MasterDatasetError, match="legacy"):
        write_master_dataset(result, tmp_path / "df_features_labeled.csv")
