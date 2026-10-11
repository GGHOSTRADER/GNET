# GNET Training Guide

This guide covers local customer training of the MA2CrossLE canonical 13-feature MLP and
the separate volume-profile research workflow. The delivery does not include the licensor's
bars, trades, labeled datasets, weights, scaler, predictions, or evaluation artifacts. The
customer must provide properly licensed exports for initial training, later updates, and
additional research.

Training a model does not require recompiling the C++ DLLs.

## 1. Environment

The complete training environment is installed during first-time setup with:

```powershell
cd C:\GNET
.\install.ps1
```

For every training session:

```powershell
cd C:\GNET
& .\.venv\Scripts\python.exe --version
```

The version must be Python 3.12.7. Keep training and live inference separate: do not
replace active model files while the strategy router is running.

The legacy MA trainer records experiments with Weights & Biases. A cloud account is not
required when using offline mode:

```powershell
$env:WANDB_MODE = "offline"
```

Offline W&B records remain local and are excluded from customer release packages.

## 2. Exact inputs and folder layout

The initial local MA2CrossLE training requires two customer-generated TradeStation exports:

| Input | Required filename | Destination |
|---|---|---|
| 30-second ES bars | `data_30_master.txt` | `C:\GNET\training_mlp\strategies\MA2CrossLE\inputs` |
| MA2CrossLE Trades List | `trades_30_master.csv` | `C:\GNET\training_mlp\strategies\MA2CrossLE\inputs` |

The `.txt` bar file is comma-delimited text with a header row. It is not an Excel workbook.
Do not rename an `.xlsx` file to `.csv` or `.txt`; export it in the actual format shown above.

For later bar additions, keep the master unchanged and use:

```text
data_30_update_YYYY-MM-DD_to_YYYY-MM-DD.txt
```

All bar exports and the Trades List must use the same ES symbol definition, 30-second chart,
session template, time zone, rollover or continuous-contract adjustment, and tested date
range. For the current MA2CrossLE implementation, export the same RTH universe used by the
strategy report. The bars must cover every labeled entry timestamp and include at least 60
earlier bars before the first entry so the canonical rolling features are warmed up.

The customer release starts with no inputs, processed dataset, weights, or scaler. The
installer creates these local directories:

```text
training_mlp\strategies\MA2CrossLE\inputs
training_mlp\strategies\MA2CrossLE\processed
training_mlp\strategies\MA2CrossLE\model\mlp_baseline
training_mlp\strategies\MA2CrossLE\reports
```

## 3. Required TradeStation exports

### 30-second bars

Export exactly these columns:

```text
Date,Time,Open,High,Low,Close,Up,Down
```

Column requirements:

- `Date`: `MM/DD/YYYY`.
- `Time`: 24-hour `HH:MM:SS`, aligned to completed 30-second bars.
- `Open`, `High`, `Low`, `Close`: numeric ES prices with valid OHLC bounds.
- `Up`, `Down`: non-negative TradeStation uptick and downtick values.
- No VWAP column is required for canonical MA13 training.
- Tick and volume-profile data are not required for the 13-feature MA2CrossLE model.

Save ongoing files under:

```text
C:\GNET\training_mlp\strategies\MA2CrossLE\inputs
```

Use these names:

```text
data_30_master.txt
data_30_update_YYYY-MM-DD_to_YYYY-MM-DD.txt
```

Continuous `@ES` exports created under different rollover-adjustment states can contain
different historical prices for the same timestamp. Such files are conflicting sources,
not duplicates, and must not be silently combined.

### Trade report and labels

Export the TradeStation Strategy Performance Report or its Trades List as CSV. The Trades
List must contain at least:

```text
#,Type,Date/Time,Signal,% Profit
```

For the recommended execution-anomaly audit, also retain the TradeStation columns `Price`
and `Net Profit - Cum Net Profit`. A complete trade must have a numbered entry row followed
immediately by its closing row, whose `#` field is blank. The entry `Signal` must exactly
match `MA2CrossLE`; spelling and capitalization matter. Complete or exclude any position
still shown as `Open` before building the final training dataset.

Save the ongoing report as:

```text
training_mlp\strategies\MA2CrossLE\inputs\trades_30_master.csv
```

The builder automatically locates the `#,Type,Date/Time,Signal` header, so this may be a
full TradeStation Strategy Performance Report export or a Trades List-only CSV. Entry times
must match timestamps in the 30-second bar export exactly.

The report must contain each numbered entry followed by its closing row. Use the corrected
TradeStation configuration:

- One-tick Look-Inside-Bar testing for the tested date chunk when intrabar ordering matters.
- Built-in Stop Loss at $50 per contract.
- Built-in Profit Target at $50 per contract.
- One contract and no pyramiding for the supplied strategy configuration.

Do not train from reports produced by obsolete explicit `next bar` protective exits. Those
reports can contain artificial next-bar-open gap profits or losses.

## 4. Merge historical bars safely

From `C:\GNET`, run:

```powershell
& .\.venv\Scripts\python.exe -m training_mlp.merge_historical_bars
```

The merger:

- Discovers the master plus every named update.
- Leaves every source file unchanged.
- Sorts bars chronologically.
- Keeps one copy of exact timestamp/value duplicates.
- Writes an overlap-session audit using the 18:00 ES session boundary.
- Aborts if equal timestamps contain different OHLC/Up/Down values.

Successful outputs are:

```text
data_30_master_merged.txt
data_30_master_merged.manifest.json
data_30_master_merged_overlap_sessions.csv
```

On conflict, inspect the generated conflict and overlap reports. If one full export is the
authoritative adjustment, select it explicitly instead of deleting older source files:

```powershell
& .\.venv\Scripts\python.exe -m training_mlp.merge_historical_bars `
  --source .\training_mlp\strategies\MA2CrossLE\inputs\data_30_update_2026-01-01_to_2026-06-30.txt
```

Review the manifest's source list, date range, row count, removed duplicates, and overlap
diagnostics before continuing.

## 5. Build the canonical labeled dataset

Use explicit paths so the reviewed merged bars are unambiguous:

```powershell
& .\.venv\Scripts\python.exe -m training_mlp.build_master_dataset `
  --bars .\training_mlp\strategies\MA2CrossLE\inputs\data_30_master_merged.txt `
  --trades .\training_mlp\strategies\MA2CrossLE\inputs\trades_30_master.csv `
  --output .\training_mlp\strategies\MA2CrossLE\processed\df_features_labeled_master.csv `
  --signal-name MA2CrossLE
```

The builder uses the same canonical feature engine used by live inference and joins labels
only to exact entry timestamps. It creates a dataset manifest beside the output.

### Labels and `t1`

- `Label = 1` when the completed TradeStation trade's `% Profit` is positive.
- `Label = 0` otherwise.
- `Date/Time` is the strategy-entry timestamp.
- `t1` is the actual trade-exit timestamp.

`t1` is validation metadata, not a model feature. Purged walk-forward and CPCV use each
event interval `[Date/Time, t1]` to remove training trades whose information overlaps a
validation or test interval.

### Canonical MA13 features

The feature contract is:

```text
parkinson_vol_5
parkinson_vol_15
parkinson_vol_30
ofi_5
ofi_15
ofi_30
volume_percentile
volume_momentum
amihud_illiquidity
vwap_distance
minutes_since_open
is_first_last_30min
day_of_week
```

Never reorder, rename, or independently reimplement these fields. Both offline training
and live feature generation must call `feat_files\canonical_features.py`.

## 6. Audit the trade report before training

Generate the reusable execution-distribution and anomaly reports:

```powershell
& .\.venv\Scripts\python.exe -m training_mlp.audit_trade_anomalies `
  --trades .\training_mlp\strategies\MA2CrossLE\inputs\trades_30_master.csv `
  --bars .\training_mlp\strategies\MA2CrossLE\inputs\data_30_master_merged.txt `
  --signal-name MA2CrossLE `
  --absolute-pnl-limit 70 `
  --expected-move-points 1 `
  --point-value 50 `
  --output .\training_mlp\strategies\MA2CrossLE\reports\trade_execution_anomalies.csv
```

Review time in trade, P&L distribution, exit summary, extreme outcomes, next-bar-open fills,
and missing/invalid timestamps. Correct the TradeStation source configuration before
training; do not remove inconvenient outcomes merely because they reduce performance.

## 7. Purged walk-forward comparison

Purged walk-forward is the first model-selection filter. Each validation fold is later in
time than its training fold, and overlapping event intervals are removed from training.

For the canonical MA/VP research comparison:

```powershell
& .\.venv\Scripts\python.exe -m training_mlp.compare_purged_feature_sets `
  --input .\training_mlp\strategies\MA2CrossLE\processed\df_features_labeled_master_vp.parquet `
  --output-root .\training_mlp\strategies\MA2CrossLE\reports\pwf_candidate `
  --n-splits 5 `
  --embargo-pct 0.01 `
  --epochs 100 `
  --patience 15 `
  --device cpu
```

This research runner compares MA13, full MA+VP, and correlation-reduced MA+VP on the same
event universe. It writes reports and predictions but does not create deployable artifacts
or modify the registry.

Evaluate fixed-threshold trading behavior from out-of-sample fold predictions:

```powershell
& .\.venv\Scripts\python.exe -m training_mlp.analyze_pwf_trading `
  --predictions .\training_mlp\strategies\MA2CrossLE\reports\pwf_candidate\validation_predictions.parquet `
  --trades .\training_mlp\strategies\MA2CrossLE\inputs\trades_30_master.csv `
  --output .\training_mlp\strategies\MA2CrossLE\reports\pwf_candidate\trading_statistics.csv `
  --threshold 0.50 `
  --commission-per-side 0
```

Use `--commission-per-side 0` only when the TradeStation export already includes commission.
Otherwise supply the actual per-side commission. Never count commission twice.

For CME ES at TradeStation's 0-500 monthly-contract tier, the September 2026
published estimate is **$3.24 per side ($6.48 round trip)**: $1.75 broker
commission + $0.10 TradeStation clearing fee + $1.38 CME ES exchange fee +
$0.01 NFA fee. The corrected LIBB export already embeds $2.25 per side, so use
`--commission-per-side 0.99` when converting that report to the current estimate.
Use `0` only to reproduce the historical $4.50-round-trip report. An actual
account confirmation overrides this estimate, and slippage must be modeled
separately.

Review at least ROC AUC, average precision, approval rate, trade count, net P&L, average
trade, profit factor, and maximum drawdown. P&L statistics supplement prediction metrics;
they do not replace leakage-controlled validation.

## 8. CPCV and hyperparameter selection

After a feature contract survives purged walk-forward, use CPCV to estimate variability
across multiple purged paths:

```powershell
& .\.venv\Scripts\python.exe -m training_mlp.cpcv_hyperparameter_search `
  --input .\training_mlp\strategies\MA2CrossLE\processed\df_features_labeled_master_vp.parquet `
  --trades .\training_mlp\strategies\MA2CrossLE\inputs\trades_30_master.csv `
  --output-root .\training_mlp\strategies\MA2CrossLE\reports\cpcv_candidate `
  --trials 50 `
  --epochs 100 `
  --device cpu
```

The search covers hidden-layer shape, learning rate, weight decay, dropout, batch size, and
decision threshold. Its final chronological holdout is excluded from CPCV ranking. This
runner produces research evidence only—it does not write deployable weights or update the
live registry.

Do not repeatedly inspect the chronological holdout while tuning. Once it influences a
decision, it is no longer a pristine final test and new future data is required for another
honest confirmation.

## 9. Train a deployable MA13 candidate

Never train directly into the currently deployed `mlp_baseline` directory. Stage the
reviewed master dataset and select a new model name:

```powershell
cd C:\GNET\training_mlp
$candidate = "ma13_candidate_YYYYMMDD"
$candidateData = "strategies\MA2CrossLE\processed\$candidate"
New-Item -ItemType Directory -Path $candidateData -Force
Copy-Item `
  ".\strategies\MA2CrossLE\processed\df_features_labeled_master.csv" `
  ".\$candidateData\df_features_labeled.csv"
$env:PROCESSED_DIR = $candidateData
$env:MODEL_NAME = $candidate
$env:MODEL_DIR = "strategies\MA2CrossLE\model\$candidate"
$env:SIGNAL_NAME = "MA2CrossLE"
$env:WANDB_MODE = "offline"
& ..\.venv\Scripts\python.exe .\30_training_mlp.py
```

The trainer:

1. Requires `Date/Time`, `t1`, `Label`, and the exact 13 features.
2. Reserves the final chronological holdout.
3. Purges training events that overlap the holdout.
4. Runs event-aware expanding purged walk-forward folds.
5. Fits each scaler on training data only.
6. Uses early stopping within each fold.
7. Saves fold artifacts and selects the best validation-AUC fold.

Artifacts are written under:

```text
training_mlp\strategies\MA2CrossLE\model\ma13_candidate_YYYYMMDD
```

They include `model_best.pt`, `scaler_best.pkl`, `config.json`, fold models/scalers,
`X_test.npy`, `y_test.npy`, and cross-validation results.

## 10. One-time held-out evaluation

Keep the same PowerShell environment variables and run:

```powershell
& ..\.venv\Scripts\python.exe .\30_evaluate_mlp.py
```

Treat this as a one-time final evaluation. Do not tune architecture, threshold, features,
or training settings using this result and then report the same test as untouched.

Archive:

- Input dataset manifest and hash.
- Training configuration and random seed.
- Fold schedule and metrics.
- Held-out metrics.
- Model/scaler/config hashes.
- TradeStation export settings and commission assumptions.

## 11. Promote a model to live inference

Promotion is a controlled deployment, not a file overwrite during operation.

1. Stop GNET with `C:\GNET\stop.ps1`.
2. Preserve any current registry file and deployed artifact directory. For the first local
   deployment, copy `model_registry\MA2CrossLE\registry.template.json` to `registry.json`
   only after the locally trained artifacts pass validation.
3. Confirm the candidate directory contains `model_best.pt`, `scaler_best.pkl`, and
   `config.json`.
4. Confirm `config.json` contains exactly the canonical 13 feature names in their canonical
   order.
5. Create or update `model_registry\MA2CrossLE\registry.json` from the disabled template:
   - Set `artifact_dir` to the candidate directory.
   - Set the approved threshold.
   - Keep `strategy_id` as `MA2CrossLE`.
   - Keep `feature_stream` as `features_transformer` for MA13.
   - Keep `device` as `cpu` unless the deployment was specifically validated otherwise.
   - Set `enabled` to `true` only after all three locally generated artifacts have been
     verified together.
6. Run the automatic verification.
7. Restart the pipeline and complete `CUSTOMER_ACCEPTANCE.md` in simulation.

Example verification:

```powershell
cd C:\GNET
.\.venv\Scripts\Activate.ps1
.\verify_install.ps1 -AutomatedOnly
```

If verification or simulation fails, stop the pipeline and restore the previous registry
entry. Do not partially mix a candidate model with an older scaler or configuration.

## 12. Adding another strategy

A new strategy normally reuses the generic `StrategyBridge.dll` and `SignalBridge.dll`.
It requires:

1. New EasyLanguage primary-signal logic.
2. A distinct `StrategyId`.
3. A unique `InstanceId` for every simultaneous TradeStation window.
4. A documented canonical feature contract.
5. A separate training/input/processed/model/report directory.
6. Leakage-controlled validation and a frozen chronological test.
7. A new `model_registry\<StrategyId>\registry.json` entry.
8. End-to-end simulation acceptance.

Recompile a DLL only when changing an exported DLL function or the TCP message protocol.

## 13. Volume-profile status

The delivery includes canonical VP math, historical tick preparation, offline VP replay,
MA/VP merging, correlation analysis, purged walk-forward comparison, and CPCV search.

The current live production registry deploys MA13 from `features_transformer`. The VP42/45
research contracts are not automatically promoted by the research scripts. Do not represent
VP as live-deployed until its selected feature contract, deployable training runner, registry
entry, live join, timeout behavior, and simulation acceptance are completed.

## 14. Reproducibility checklist

Before reporting or deploying a result, retain:

- [ ] Immutable raw-export hashes.
- [ ] Merge and dataset manifests.
- [ ] Exact feature names and order.
- [ ] `Date/Time`, `t1`, and label definition.
- [ ] Purge/embargo and fold configuration.
- [ ] Random seed and hyperparameters.
- [ ] Commission and slippage assumptions.
- [ ] Model, scaler, configuration, and registry hashes.
- [ ] Held-out evaluation date and whether it was previously inspected.
- [ ] Customer simulation-acceptance evidence.

For deeper implementation notes, see `documentation\how_to_train.md` and the offline
architecture diagram under `diagrams\gnet_offline_training.mmd`.
