import numpy as np
import pandas as pd

from training_mlp.sweep_dynamic_stops import simulate_long_exit


def _times(count: int) -> np.ndarray:
    return pd.date_range("2026-01-02 10:00:00", periods=count, freq="s").to_numpy()


def test_breakeven_activates_then_exits_at_entry() -> None:
    result = simulate_long_exit(
        _times(3), np.array([100.0, 100.25, 100.0]), 100.0, "breakeven", 1
    )
    assert result.price == 100.0
    assert result.reason == "breakeven"
    assert result.activated


def test_trailing_stop_follows_best_price() -> None:
    result = simulate_long_exit(
        _times(4),
        np.array([100.0, 100.25, 100.5, 100.25]),
        100.0,
        "trailing",
        1,
        1,
    )
    assert result.price == 100.25
    assert result.reason == "trailing"


def test_profit_target_has_priority_when_reached() -> None:
    result = simulate_long_exit(
        _times(2), np.array([100.0, 101.0]), 100.0, "trailing", 1, 1
    )
    assert result.price == 101.0
    assert result.reason == "profit_target"


def test_initial_stop_remains_before_activation() -> None:
    result = simulate_long_exit(
        _times(2), np.array([100.0, 99.0]), 100.0, "breakeven", 3
    )
    assert result.price == 99.0
    assert result.reason == "initial_stop"
    assert not result.activated
