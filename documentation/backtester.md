# GNET Backtester

For the human-oriented walkthrough, module inventory, worktree details and
four-stage diagram, start with [the Backtester User Guide](guides/BACKTESTER_GUIDE.md).
This file is the detailed technical reference.

An independent offline ES backtester: ordered ticks -> selected bars ->
completed-bar MA crosses -> chronological execution for each exit policy ->
optional adaptive exit search and independent backtesting results. No TradeStation, Docker, Redis, or live model is
required. The existing `exit_module` remains an independent-entry collector;
it has not been replaced.

## Run in the GNET environment

From the GNET repository in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backtester\requirements.txt
.\.venv\Scripts\python.exe -m backtester.run --config config\backtester.example.json
```

Edit or copy the example JSON before a full experiment. Paths inside it are
relative to that JSON file, not the terminal directory. Use a separate output
folder for each experiment. The supplied settings are engineering defaults,
not an optimized strategy. It searches June 15–September 17, 2026; it does not
reserve a confirmation period unless `confirmation_start` is explicitly set.

```powershell
# Resume interrupted work; completed policies are reused.
.\.venv\Scripts\python.exe -m backtester.run --config config\backtester.example.json --resume

# Override the number of policy workers.
.\.venv\Scripts\python.exe -m backtester.run --config config\backtester.example.json --resume --workers 2

# Build ticks/bars/signals without evaluating policies.
.\.venv\Scripts\python.exe -m backtester.run --config config\backtester.example.json --prepare-only

# Rebuild figures from existing search results.
.\.venv\Scripts\python.exe -m backtester.run --config config\backtester.example.json --report-only
```

Only run one coordinator against a given output folder. Ctrl+C may wait for
an in-flight worker batch; completed policy summaries are retained. Resume
reconstructs deterministic search decisions using cached results rather than
rerunning those policies. Increase `max_evaluations` or `max_seconds` to continue
a budget-limited search. Other experiment changes require a new output folder.

## Preset backtest versus optional exit analysis

Choose `execution_mode: "sweep"` (the backward-compatible default) to enable
`backtester.exit_analyzer.ExitAnalyzer`. It proposes exit combinations, requests
complete backtests, and owns the comparison/surface HTML under `reports/<bar>/`.

Choose `execution_mode: "preset"` to run one explicit policy per requested bar
type. The analyzer is not constructed; no search state or surface report is
created. The policy does not need to belong to the search grid:

```json
"execution_mode": "preset",
"preset_policy": {"profit_ticks": 4, "stop_ticks": 4, "hold_seconds": 120},
"results": {"initial_capital": null, "equity_sample_seconds": 60, "sessions_per_year": 252}
```

```powershell
.\.venv\Scripts\python.exe -m backtester.run --config config\backtester.preset.example.json
```

The supplied preset is a two-session engineering example, not an optimized
recommendation. Existing runs cannot be resumed after this code/configuration
revision; use new output folders. Both modes preserve the strategy's entry
parameters and the tick-level profit, stop and time execution rules. Native
strategy-specific exits and the five-strategy expansion remain future work.

### Independent backtesting results

Every completed policy writes `statistics.json`, `results.html`,
`equity.parquet`, `session_returns.csv`, and `drawdowns.csv` beside its trades.
The root `backtesting_results.html` indexes them across bar types and phases.
The results module never selects exit parameters. `--report-only` rebuilds
HTML from saved outputs; it does not replay ticks. Confirmation also produces
these reports and can evaluate a preset outside the search grid.

Statistics cover gross/net P&L, win rate, payoff sizes, fees, modeled slippage,
holding time, exposure, turnover, return concentration, drawdown, underwater
duration, and distributions by exit reason/holding interval/month. Holding-time
buckets are elapsed seconds, **not** a same-bar-exit classification.

`initial_capital` is intentionally null by default: dollar statistics work,
but percentage returns and Sharpe inference remain unavailable until capital
is explicitly supplied. No external cash flows are assumed. Returns are changes
in session-end liquidation NAV divided by the preceding NAV, including flat
sessions. Open positions reserve the round-trip cost and liquidation slippage.
The existing exact tick-level maximum drawdown remains available. The saved
equity uses a clock grid plus entry/exit events; its underwater durations and
drawdowns are labeled sampled, and mark age is reported.

Sharpe and probabilistic Sharpe require at least three nonconstant session
returns, positive equity and no invalid trades; this minimum is a calculation
condition, not statistical confidence. Annualization assumes
`sessions_per_year` (252 by default); `risk_free_per_session` defaults to zero.
No autocorrelation correction is applied, and missing archive sessions are
not treated as observed zero-return sessions. Verify coverage before interpreting
annualized statistics.

Deflated Sharpe is conditional on supplying all three `results` fields:
`effective_trials` (>1), `trial_sharpe_variance` (variance of **unannualized
session** Sharpe ratios across the full research history), and a nonempty
`trial_history_note` documenting provenance and dependence assumptions.
The number of grid points is not automatically an independent trial count.
These inputs must include unsuccessful trials and relevant prior searches;
without them DSR is unavailable. Formula reference: [Bailey and López de Prado,
equation 2](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).
Classification/factor statistics need additional adapters and remain unavailable.
Reporting does not perform purging, embargo or combinatorial CV.

The combined bars/trades viewer is still planned; neither HTML report claims
to be that viewer.

## Inputs and bars

The current input adapter accepts prepared session partitions:

```text
tick_root/
  manifest.json                         optional provenance/timezone metadata
  parquet/session_date=YYYY-MM-DD/ticks.parquet
```

Required tick columns: `timestamp`, `price`, `volume`. Naive timestamps use
the configured timezone; aware timestamps preserve their instant. Original
row order is preserved when timestamps tie. Prices must be positive and on
the ES 0.25-point grid. Volume must be nonnegative whole contracts. Descending
timestamps, invalid values, empty partitions, and out-of-session ticks fail
preparation instead of being silently repaired.

The existing spliced archive's `old_sessions` and `new_sessions` manifest
fields identify price vintages. At a vintage change, MA state resets and an
open position cannot cross the boundary. If no manifest identifies separate
vintages, the supplied root is treated as one vintage: prepare rollover-safe
inputs before running. Different source schemas need an adapter; this is not
a universal raw-export reader.

Request only the series needed, for example:

```json
"bars": [
  {"kind": "time", "size": 30},
  {"kind": "time", "size": 900},
  {"kind": "tick", "size": 1000},
  {"kind": "volume", "size": 1000}
]
```

Time `size` is seconds; tick `size` is exported trade records, not volume or
price increments. Each selected series is built once. OHLC, total volume,
tick count, event indices, session, vintage, and completion flag are saved.
Volume size is accumulated traded volume. Whole events are retained: close
at or above the threshold, split no trade, and start the next bar at zero.
Partial volume bars cannot trigger signals or carry between sessions. See the
[file/schema contract](backtester_file_contract.md) for source semantics and commands.

Time buckets start at the session opening and are left-closed/right-open. A
tick exactly on the boundary belongs to the new bar. Empty intervals do not
produce invented bars. The final time bucket is excluded from signals unless
the recorded stream reaches its closing boundary. A partial tick-count bar
at session end is also excluded. Missing history at the start or inside a
partition cannot be inferred from trade timestamps alone; use complete source
partitions. Optional maximum tick-gap checks can flag trades spanning gaps.

## Signal and execution conventions

Entry rules belong to a selected strategy, not to the engine. For example:

```json
"strategy": {
  "name": "ma_cross",
  "parameters": {"fast": 9, "slow": 18, "reset_each_session": false}
}
```

`strategies/ma_cross.py` is an independent module owning MA logic and parameter
validation. It imports no backtester code. `strategies/base.py` defines the
shared interface, and `strategies/registry.py` maps a strategy name to its
import path. The backtester imports the selected strategy; it does not contain
its entry formula or interpret MA lengths.

`backtester/signals.py` passes completed bars through `on_bar(bar)` and maps
proposals to eligible ticks. To add another long-entry rule, create a module
inside `strategies/`, implement `on_session_start()` and `on_bar(bar)`, and add
its `strategies.module_name:ClassName` entry to the registry. Select its name
and parameters in configuration. No backtester changes are required. Only
`ma_cross` is supplied as a production strategy currently; the interface is
long-entry only, not a general multi-direction order interface.

The old `backtester/strategies.py` now only re-exports names for compatibility;
it contains no strategy implementation. Existing files below
`strategies/MA2CrossLE/` are untouched. The independent strategy can be imported
by other applications, but the live pipeline has not been rewired to use it.

Initial strategy: a long-only fast/slow simple-moving-average crossover,
defaults 9/18, one ES contract and one open position per policy. A signal
requires a completed bar: fast-minus-slow changes from nonpositive to positive.
MA state carries between sessions by default but never between vintages.

A time-bar signal becomes available at its closing boundary, before the first
tick at or after that boundary. A tick-bar signal becomes available after its
last tick; entry is the following record, even if both records have identical
timestamps. No entry uses its signal bar's closing tick as a fill.

Every stop/target/time combination has independent position state. A crossover
observed while its position is open is skipped, not queued. Thus different
policies can take different entries. Exits at a tick-bar's closing event precede
that bar's newly available signal; time-boundary signals precede that boundary
tick's exits. Signals lacking a next tick in the same session, stale signals,
and signals at/after the session entry cutoff are logged as skipped.

Profit targets fill at their limit when a subsequent trade touches or passes
it. Stop exits fill at the observed crossed price, with configured adverse
slippage. Time exits fill at the first tick at/after the deadline, with adverse
slippage. At an exact deadline tie, the time exit takes precedence over price
barriers. Entry is a market fill with the same adverse-slippage setting.

The price multiplier is $50 per ES point, or $12.50 per tick. The default
round-trip charge is $6.48, deducted once per completed trade. Slippage is
separate. Target-touch fills are an assumption: trade ticks do not reconstruct
bid/ask spread, queue priority, or guaranteed executable liquidity.

Default sessions run from 18:00 on the preceding calendar day to 17:00 on the
named session date, America/New_York. A flatten order is scheduled 60 seconds
before the configured close; it fills at the first subsequent tick, unless
another barrier exits earlier. No new entry is permitted from that cutoff.
`session_exit: "carry"` disables scheduled flattening; holding limits still use
elapsed wall-clock time, including closures. Supply `session_close_overrides`
for early-close dates; there is no automatic exchange holiday calendar.

A missing exit at end-of-data or vintage transition is marked unresolved.
It blocks subsequent entries and makes that policy ineligible. Delayed exits
and excessive configured tick gaps also make a policy ineligible. Realized
P&L may still be displayed for diagnostic purposes; it is not a valid ranking
score when `eligible` is false.

## Parameters

| Parameter | Meaning / default |
|---|---|
| `tick_root`, `output` | Prepared archive and distinct result directory |
| `start_session`, `end_session` | Inclusive session-date range |
| `bars` | Requested time/tick/volume series; default 30 seconds |
| `strategy` | Entry-strategy name and its own parameter object |
| `execution_mode` | `sweep` (default) or `preset`; preset bypasses exit analysis |
| `preset_policy` | Explicit profit ticks, stop ticks and hold seconds; required only in preset mode |
| `results` | Capital, sampling and conditional risk-statistics inputs described above |
| `timezone` | Naive source timezone; America/New_York |
| `session_open`, `session_close` | 18:00:00, 17:00:00 |
| `session_close_overrides` | Per-date early close, e.g. `{"YYYY-MM-DD":"13:00:00"}` |
| `session_exit`, `flatten_lead_seconds` | `flatten` or `carry`; flatten lead 60 seconds |
| `round_trip_cost`, `slippage_ticks` | $6.48 per trade; 0 ticks per market fill |
| `max_entry_delay_seconds` | Reject stale candidate entry; 30 |
| `max_exit_delay_seconds` | Flag delayed scheduled exit; 30 |
| `max_tick_gap_seconds` | Optional in-trade coverage warning/invalidity threshold; null |
| `profits`, `stops` | Sorted positive tick distances to search |
| `holds` | Sorted positive maximum holding times in seconds |
| `workers`, `policy_batch_size` | Processes and policies per task; 4, 4 |
| `max_evaluations` | Maximum sampled combinations per bar series; 64 |
| `max_seconds` | Soft search-time budget per series; 3600; excludes preparation/plots |
| `patience` | Unimproving neighboring rounds before a jump; 2 |
| `jump_factor` | Multiplier of search radius in grid indices; 3 |
| `failed_jumps` | Failed farther probes before abandoning a region; 2 |
| `search_regions` | Number of initial seeded regions pursued; 3 |
| `improvement_tolerance` | Minimum net-dollar improvement to advance; 0 |
| `min_trades`, `max_drawdown` | Eligibility constraints; 10 trades, no DD cap |
| `time_blocks` | Equal elapsed-time development blocks for stability summaries; 3 |
| `region_min_positive_blocks` | Positive blocks required for a positive-region node; 2 |
| `confirmation_start` | Optional first reserved session, fixed before the run; null |

The `ma_cross` strategy's parameters are `fast` (9), `slow` (18), and
`reset_each_session` (false). They are not global backtester parameters or exit
search axes. Legacy top-level `fast`, `slow`, or `reset_ma_each_session` values
are rejected with migration guidance. Existing result folders remain unchanged;
the new code/configuration identity requires a new output folder.

The stop/target/time lists define the finite domain, including its minimum,
maximum, and spacing. The coordinator samples corners and center, explores
neighbors of top seeds, and expands to farther probes after unimproving rounds.
Improvement restarts local exploration. Exhausted regions, evaluation budget,
or time budget stop the search. An in-flight batch finishes even if the time
budget has expired. This is a heuristic: it can miss a better distant region.

The objective is total net dollars over the same development dates, subject
to eligibility constraints. Each policy traverses that entire period; a bad
early date segment does not truncate its replay. Parallel processes own policy
groups, not independent date buckets. Read-only memory-mapped tick arrays are
shared through the OS cache; each worker replays policies sequentially within
its task with independent positions. Library thread counts are limited to one.

## Outputs and surface interpretation

```text
output/
  run.json                             effective config and input identity
  prepared/                            shared tick maps, bars, signals, metadata
  policies/<bar>/<phase>/<policy>/
    trades.parquet                     fills, barriers, P&L, MFE/MAE, validity
    skipped_signals.parquet             candidate IDs and skip reasons
    summary.json                       completed-policy cache marker and metrics
    statistics.json, results.html      independent per-backtest statistics/report
    equity.parquet                     sampled liquidation equity and positions
    session_returns.csv, drawdowns.csv  session marks/returns and underwater episodes
  search/<bar>.json                    evaluated coordinates, region state, trace
  reports/<bar>/
    index.html                         EXIT ANALYZER report (sweep only)
    policies.csv                       all evaluated policy metrics
    regions.json, selection.json        supported neighborhoods and chosen example
    surface_h*.png, surface3d_h*.png     each sampled holding-time slice
    equity.png                         selected policy's realized equity
  selections.json                      development choices across bar types
  backtesting_results.html             statistics-report catalog (both modes)
```

Metrics include accepted/closed trades, skipped-while-busy count, invalid and
unresolved trades, net/gross P&L, win fraction, average trade, profit factor,
tick-level estimated-liquidation drawdown, and chronological block P&L.
Profit factor is null when no gross losing net outcomes exist, rather than
serializing infinity. Every policy has timestamped trades from which its
realized equity can be reconstructed; the report plots the selected policy.

Gray heatmap cells are untested. A black X marks an ineligible policy.
3D mesh faces only connect cells with four sampled corners. Positive regions
require eligible positive nodes and the configured positive-block count.
Supported area counts rectangles with four qualifying neighboring corners,
using actual tick spacing. It is sampled support, not proof that every interior
value works. The largest supported region supplies a central representative.
If none exists, the report explicitly says so and displays the best eligible
sampled point only as an exploratory example, even if it loses money.

## Reserved evaluation and research limits

Set `confirmation_start` before the first run to prevent later sessions from
guiding search. Then, after development is complete:

```powershell
.\.venv\Scripts\python.exe -m backtester.run --config config\my_experiment.json --confirm
```

This freezes `confirmation_plan.json`, disables further searching in that run,
and evaluates only the selected policy per bar series on reserved sessions.
If interrupted, rerun `--confirm`: completed policies are reused. Results go
to `confirmation.json`. Confirmation starts flat, with causally accumulated
indicator history retained. Development positions still open at the split are
unresolved/ineligible, not assigned a hindsight close.

These chronological block summaries are descriptive, not purged/embargoed
combinatorial CV. No NN, adaptive per-cross exit learner, or live integration
is added by this module. Repeatedly inspecting reserved results compromises
their research role; an output freeze cannot undo that. Data already studied
elsewhere is not newly untouched just because this module calls it confirmation.

Run identity uses backtester and strategy-package code SHA256, configuration,
source manifest SHA256, and file
path/size/mtime/row counts. It does not hash every byte of the large tick archive;
source partitions must remain immutable. Outputs default to ignored
`.artifacts/backtester/`, keeping bulky caches and generated results out of Git.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_backtester.py tests/test_backtester_results.py tests/test_exit_module.py
```

45 tests passed in the repository's `.venv`, including the existing collector
regression tests. Tests cover causal event ordering, selected bars, independent policy occupancy,
three exit barriers, stop gaps, limit-gap equity, unresolved coverage, session
flattening, adaptive jumps and bounds, sampled-region area, and deterministic
serial/parallel/cached results. A real-data smoke run on June 15–16, 2026 used
1,560,519 ES ticks, two bar specifications, four workers, and 24 sampled policies
per specification. This is implementation verification, not a full study or
evidence of an investable strategy.

A separate uncached replay benchmark evaluated the same 48 policies on that
two-session tape. Trade, skip-log, and summary hashes agreed with one, two,
and four workers. Times including process startup were 1.14s, 0.97s, and 0.84s,
respectively; the largest individual worker peak working set was approximately
93 MB. These are small-tape measurements, not total application RAM or full-
archive scaling estimates. Re-benchmark larger runs before increasing workers.
