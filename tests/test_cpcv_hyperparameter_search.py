import pandas as pd

from training_mlp.cpcv_hyperparameter_search import (
    SearchConfig,
    rank_trials,
    sample_trials,
    split_development_holdout,
)


def test_sample_trials_is_deterministic_and_covers_every_dimension():
    first = sample_trials(12, 7)
    second = sample_trials(12, 7)
    assert first == second
    assert len({trial.hidden_dims for trial in first}) > 1
    assert len({trial.learning_rate for trial in first}) > 1
    assert len({trial.weight_decay for trial in first}) > 1
    assert len({trial.dropout for trial in first}) > 1
    assert len({trial.batch_size for trial in first}) > 1


def test_holdout_is_chronological_and_purges_crossing_development_event():
    starts = pd.date_range("2026-01-01", periods=10, freq="h")
    frame = pd.DataFrame({"Date/Time": starts, "t1": starts})
    frame.loc[7, "t1"] = starts[9]
    development, holdout = split_development_holdout(frame, 0.2)
    assert len(holdout) == 2
    assert development["Date/Time"].max() < holdout["Date/Time"].min()
    assert starts[7] not in set(development["Date/Time"])


def test_rank_trials_rewards_predictive_trading_quality_and_lower_drawdown():
    rows = pd.DataFrame(
        [
            {"model": "a", "roc_auc_median": 0.60, "average_precision_median": 0.60,
             "profit_factor_median": 1.1, "average_trade_median": 2.0,
             "maximum_drawdown_p95": 500.0},
            {"model": "b", "roc_auc_median": 0.70, "average_precision_median": 0.70,
             "profit_factor_median": 1.6, "average_trade_median": 8.0,
             "maximum_drawdown_p95": 200.0},
        ]
    )
    ranked = rank_trials(rows)
    assert ranked.iloc[0]["model"] == "b"
    assert ranked.iloc[0]["selection_score"] > ranked.iloc[1]["selection_score"]
