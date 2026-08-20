# Event-Aware Financial Validation

GNET keeps its two financial cross-validation methods in separate reusable
modules:

- `training_mlp.validation.purged_walk_forward.PurgedWalkForward`
- `training_mlp.validation.cpcv.CombinatorialPurgedCrossValidation`

Both import the shared interval-overlap rules from
`training_mlp.validation.event_intervals`. Training scripts must import these
modules rather than copying split functions.

## Required Data Contract

Every labeled observation must provide:

- event start: the timestamp when the strategy candidate becomes known;
- event end (`t1`): the timestamp when its outcome label becomes known.

Purging compares the complete closed interval `[event_start, t1]` against each
validation event. A fixed number of rows or bars is not a substitute for `t1`
because different trades can remain open for different durations.

```python
from training_mlp.validation import EventIntervals, PurgedWalkForward

events = EventIntervals.from_arrays(
    labeled_frame["Date/Time"],
    labeled_frame["t1"],
)

splitter = PurgedWalkForward(n_splits=5, embargo_pct=0.01)
for split in splitter.split(events):
    X_train = X[split.train_indices]
    y_train = y[split.train_indices]
    X_valid = X[split.test_indices]
    y_valid = y[split.test_indices]
```

The scaler and every other fitted preprocessing operation must be fit using
only `split.train_indices`.

## Purged Expanding Walk-Forward

Use walk-forward validation for feature, model, and threshold filtering. Each
fold trains exclusively on observations before its validation group. Purging
removes past training events whose `t1` overlaps validation.

The module reports the López de Prado post-validation embargo indices for a
complete audit record. They cannot affect the same fold's training set because
expanding walk-forward is already past-only; post-test embargo matters when a
validation method permits later observations in training.

## CPCV

Use CPCV only for finalists after walk-forward filtering:

```python
from training_mlp.validation import CombinatorialPurgedCrossValidation

splitter = CombinatorialPurgedCrossValidation(
    n_groups=6,
    n_test_groups=2,
    embargo_pct=0.01,
)
for split in splitter.split(events):
    # Fit on split.train_indices and predict split.test_indices.
    # split.path_assignments maps each test group to a backtest path.
    pass
```

`CPCV(N, k)` generates `C(N, k)` model fits and `C(N-1, k-1)` complete
out-of-sample paths. Purging removes every training event whose information
interval overlaps a selected test event. The observation-count embargo removes
the configured fraction of rows immediately after every contiguous test block.

## Current Migration Status

The MA pipeline is migrated. `study_pipeline.py` pairs each numbered
TradeStation entry with its following close, excludes an explicitly open final
trade, validates timestamps, and writes `t1`. The regenerated MA dataset has
17,768 completed trades. `30_training_mlp.py` now imports the canonical
chronological holdout and walk-forward splitter; its old fixed-row split
functions have been removed.

Zona training scripts still contain their earlier row-gap split functions and
their processed datasets have not been regenerated with `t1`. Migrate them only
after auditing their TradeStation export/label contract in the same way.
