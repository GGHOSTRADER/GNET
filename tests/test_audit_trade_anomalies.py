from __future__ import annotations

import pandas as pd

from training_mlp.audit_trade_anomalies import _money, audit


def test_money_parser_handles_currency_parentheses_and_numeric_values() -> None:
    result = _money(pd.Series(["$50.00", "($70.25)", -80.0]))

    assert result.tolist() == [50.0, -70.25, -80.0]


def test_audit_identifies_next_bar_open_fill(tmp_path) -> None:
    trades = tmp_path / "trades.csv"
    trades.write_text(
        "TradeStation Trades List,,,,,,,,,,,,,\n"
        ",,,,,,,,,,,,,\n"
        "#,Type,Date/Time,Signal,Price,Roll Over Pips,Shares/Ctrts - Profit/Loss,"
        "Net Profit - Cum Net Profit,% Profit,Run-up/Drawdown,Efficiency,Total Eff.,Comm.,Slippage\n"
        ",,,,,,,,,,,,,\n"
        "1,Buy,03/16/2026 09:30:00 AM,MA2CrossLE,5000,0,1,100,0.01,100,1,,0,0\n"
        ",Sell,03/16/2026 09:30:30 AM,Profit Target,5002,,100,100,,0,1,1,0,0\n",
        encoding="utf-8",
    )
    bars = tmp_path / "bars.txt"
    bars.write_text(
        "Date,Time,Open,High,Low,Close,Up,Down\n"
        "03/16/2026,09:30:00,5000,5002,4999.75,5001.75,10,10\n"
        "03/16/2026,09:30:30,5002,5002.25,5001.75,5002,10,10\n",
        encoding="utf-8",
    )

    all_trades, flagged, summary = audit(trades, bars, absolute_pnl_limit=70)

    assert len(all_trades) == 1
    assert len(flagged) == 1
    assert bool(flagged.loc[0, "entry_bar_crossed_expected_level"])
    assert bool(flagged.loc[0, "exit_matches_exit_bar_open"])
    assert summary["oversized_profits"] == 1
