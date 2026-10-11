from __future__ import annotations

import numpy as np

import pytest

from training_mlp.analyze_pwf_trading import TradingStatisticsError, trade_statistics


def test_trade_statistics_calculates_profit_factor_and_drawdown() -> None:
    result = trade_statistics(np.array([100.0, -50.0, -25.0, 75.0]), candidates=8)

    assert result["approved_trades"] == 4
    assert result["approval_rate"] == 0.5
    assert result["net_profit"] == 100.0
    assert result["gross_profit"] == 175.0
    assert result["gross_loss"] == 75.0
    assert result["profit_factor"] == 175.0 / 75.0
    assert result["maximum_drawdown"] == 75.0


def test_trade_statistics_rejects_no_values_only_through_analysis_boundary() -> None:
    result = trade_statistics(np.array([], dtype=float), candidates=8)

    assert result["approved_trades"] == 0
    assert np.isnan(result["average_trade"])
