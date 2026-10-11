# GNET offline backtester — agent runbook

This is the operational contract for an agent using the backtester. For the
human explanation and four-module diagram, open [BACKTESTER_GUIDE.md](BACKTESTER_GUIDE.md).
Follow [AGENTS.md](../../AGENTS.md) and applicable nested instructions as well.

## 1. Establish the checkout and task boundary

The current implementation is in `C:\Users\g_med\python_new\GNET`, not in the
older `crossover-context` research worktree. Verify before issuing a job:

```powershell
Set-Location 'C:\Users\g_med\python_new\GNET'
git rev-parse --show-toplevel
git branch --show-current
Test-Path .\backtester\run.py
Test-Path .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe -m backtester.run --help
```

Use the project's `.venv`, not base Python. Source files may be untracked;
do not assume a fresh worktree contains them. Do not make broad Git diffs over
datasets/artifacts, change live services, start TradeStation/Docker, delete
archives, or change live strategy/model deployment for an offline research task.
No new worktree is necessary unless requested or isolation is required.

## 2. Discover, do not guess

```powershell
.\.venv\Scripts\python.exe -m scripts.backtester_inventory strategies --json
.\.venv\Scripts\python.exe -m scripts.backtester_inventory data --asset ES --json
```

The strategy registry is [strategies/registry.py](../../strategies/registry.py).
Currently only `ma_cross` is registered. Parameters belong under
`strategy.parameters`, not as top-level engine settings. Read the
[strategy inventory](../backtester_strategy_inventory.md) and
[data inventory](../backtester_data_inventory.md).

Before importing or joining files, read the authoritative
[file placement, naming and schema contract](../backtester_file_contract.md).
Both paired splice and adjusted merge outputs feed the backtester. They use
different price policies; never switch implicitly. Archives marked INCOMPLETE
or missing required columns are rejected before run creation.

For grouping N imported tick/volume bars, use
[the source-bar builder](../source_bar_aggregation.md). Distinguish
source-row count from traded-volume thresholds. This builder's source row IDs
are not execution-tick IDs; its independent exports are not yet accepted by
`backtester.run`. Do not imply a raw volume source is an individual-trade tape.

Data catalog: [config/backtester.data_sources.json](../../config/backtester.data_sources.json).
Select one root and dates; do not concatenate overlapping catalog entries.
The selected splice and adjusted audit archive are different price bases,
not extra independent history. Inspect the selected manifest and any rollover
boundary. Metadata coverage does not certify completeness or tick validity.
No generic continuous-archive append service exists yet.

## 3. Write an explicit experiment configuration

Start from [preset example](../../config/backtester.preset.example.json) or
[sweep example](../../config/backtester.example.json). Save a separate JSON under
`config/` with a descriptive run name, using the normal safe editing tools.
Never overwrite someone else's experiment or an old run manifest.

Required decisions to record before a substantial run:

| Decision | Configuration / rule |
|---|---|
| Asset and source | ES only; `tick_root` from catalog; retain manifest provenance |
| Date coverage | `start_session`, `end_session`; review partial sessions and close overrides |
| Bars | `bars`: time sizes in seconds, tick sizes in records, volume sizes in traded contracts; only requested series are built |
| Primary rule | `strategy.name` and validated `strategy.parameters` |
| Exit policy | `execution_mode=preset` and `preset_policy`, OR `execution_mode=sweep` and axes |
| Exit units | `profit_ticks`, `stop_ticks`; `hold_seconds`, not bars |
| Costs | Current research assumption: `round_trip_cost=6.48` per one-contract trade; record slippage separately |
| Position/session behavior | One long position per policy; choose `session_exit` and flatten lead; source boundary handling remains enforced |
| Resource limits | `workers`, `policy_batch_size`, `max_evaluations`, `max_seconds`; do not use unlimited workers |
| Search behavior | `patience`, `jump_factor`, `failed_jumps`, search seeds/regions and eligibility limits |
| Statistical denominator | `results.initial_capital` only when supplied/justified; otherwise percentage returns/Sharpe remain unavailable |
| Confirmation | Declare `confirmation_start` before selection; no new tuning on that period |
| Output | Unique `.artifacts/backtester/<run-name>/`; only one coordinator may write there |

Paths in an experiment JSON resolve relative to the JSON file, not the shell.
Use absolute paths when running from another checkout. Ask one precise question
when an unresolved choice materially changes the experiment; do not silently
choose risk limits, invent a capital amount, or expand the search budget.

## 4. Prepare, inspect, then execute

The following examples use a user-created `config/backtester.my_run.json`.
That file is a placeholder name, not a supplied configuration.

```powershell
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.my_run.json --prepare-only
```

Inspect output `run.json` and `prepared/metadata.json`: correct source, dates,
tick count, requested bar keys, signals and source vintages. The prepared bar
and signal Parquet files are available for inspection. Candidates are not
executed trades; every exit policy has separate position occupancy.

For a new setup, first create a **separate two-session smoke configuration**
and output folder. Do not alter the full experiment's dates in place after
creating its run identity. Once the checks pass, execute the prepared run:

```powershell
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.my_run.json --resume
```

Preset mode bypasses exit search and still writes statistics. Sweep mode
evaluates policy configurations over the full chronology in parallel; do not
partition occupied trades into independent date buckets. Finite search budgets
bound work, but an in-flight batch may finish after the nominal time budget.

## 5. Check and deliver both report types

Read [report directory](../backtester_reports.md) for actual example
links. Under the chosen output, verify:

| Artifact | Verify / purpose |
|---|---|
| `run.json` | Effective config, source inventory, code/data identity |
| `prepared/bars_<bar>.parquet` | Constructed bar output |
| `prepared/signals_<bar>.parquet` | All candidate events |
| `policies/<bar>/<phase>/<policy>/trades.parquet` | Actual entries, exits, status, gross/net outcomes |
| `.../skipped_signals.parquet` | Occupancy and other skip reasons |
| `.../statistics.json`, `.../results.html` | Independent backtest statistics, not exit rankings |
| `backtesting_results.html` | Catalog linking all per-policy reports |
| `reports/<bar>/index.html` | Exit-finder report; expected only in sweep mode |
| `reports/<bar>/policies.csv` | Tested combinations and numerical results |
| `reports/<bar>/surface_h*.png`, `surface3d_h*.png` | Tested surface nodes; missing cells must remain unknown |
| `reports/<bar>/regions.json`, `selection.json` | Region support and selection reasoning |

Before discussing a winning rule, reconcile closed-trade net totals with replay
summary/statistics; inspect unresolved or invalid outcomes, trade counts,
costs, drawdown and time-block support. A selected rule can be negative or
ineligible for deployment. Do not substitute zero for unavailable statistics.
DSR requires documented effective trial count and Sharpe-variance history;
do not set these equal to the grid size merely to obtain a number.

Report exact source/date/strategy/policy/cost assumptions. Link the readable
backtest HTML, exit-analysis HTML and numeric outputs separately. State whether
the result is a smoke test, development search or reserved confirmation.
Do not claim buy-and-hold, a candlestick trade viewer, ML training, or
purged/embargoed CPCV ran: those are not implemented in this backtester.

## 6. Resume, regenerate, confirm

Use `--resume` only with matching material configuration, code and source
identity. Identity mismatch means a new output folder, not editing the manifest
or deleting completed artifacts. For unchanged completed search outputs:

```powershell
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.my_run.json --report-only
```

This regenerates comparison/catalog output from existing policy results;
it does not reconstruct missing per-policy statistics or migrate old runs.
Only when confirmation is authorized and its dates were reserved beforehand:

```powershell
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.my_run.json --confirm
```

Confirmation freezes selected policies and starts flat. It is not a fresh
search on later dates. Reusing a previously inspected period does not make it
untouched; describe the actual research history.

## 7. Verification when changing the tool

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_backtester.py tests/test_backtester_results.py tests/test_exit_module.py tests/test_backtester_inventory.py tests/test_backtester_merge_integration.py tests/test_backtester_volume_bars.py
```

Inspect only relevant source changes and preserve other work. After structural
edits, import affected modules and compare top-level definitions with HEAD;
if a file has no HEAD version, explicitly compare against its pre-edit inventory
instead. Recheck strategy inventory, config examples and documentation links.
Do not run the entire tick archive merely to validate documentation.
