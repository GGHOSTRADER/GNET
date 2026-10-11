"""Guard the historical LIBB trade-outcome staging contract."""

import pandas as pd
import pytest

from training_mlp.stage_spliced_trade_outcomes import _completed_trades, _money


def test_money_preserves_tradestation_parenthesized_losses():
    values = pd.Series(["$50.00", "($62.50)", "$0.00"])
    assert _money(values).tolist() == [50.0, -62.5, 0.0]


def test_completed_trades_subtracts_both_sides_at_current_cost(tmp_path):
    report = tmp_path / "trades.csv"
    report.write_text(
        "TradeStation Trades List\n"
        "#,Type,Date/Time,Signal,Price,Shares/Ctrts - Profit/Loss,% Profit\n"
        "1,Buy,8/16/2026 6:41:00 PM,MA2CrossLE,$7877.00,1,0.01%\n"
        ",Sell,8/16/2026 6:48:30 PM,Profit Target,$7878.00,$50.00,\n",
        encoding="utf-8",
    )
    staged = _completed_trades(report, "new")
    assert len(staged) == 1
    assert staged.loc[0, "gross_pnl"] == pytest.approx(50.0)
    assert staged.loc[0, "net_pnl_at_3_24_per_side"] == pytest.approx(43.52)
    assert staged.loc[0, "outcome_positive"] == 1
