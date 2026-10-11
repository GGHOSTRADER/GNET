# GNET Backtester — original implementation plan

Status: first implementation delivered September 30, 2026 as the separate
`backtester` package. See [the backtester guide](backtester.md) for actual
commands, parameters, execution conventions, verification, and limitations.
The sections below preserve the original design proposal; they are not a claim
that every proposed extension is implemented. In particular, volume bars,
additional strategies, and ML-based exit selection remain future extensions.

## Objective and agreed decisions

Build a reusable offline system that reads ordered ES ticks, constructs only
the requested bar specifications, generates strategy signals, and searches
profit-target, stop-loss, and time-barrier combinations. Each combination
executes its own chronological strategy, including skipping signals while a
position is open. Parallel workers own different combinations and process
the complete selected history.

The user has agreed to an adaptive search with local stopping and farther
probes after deterioration. Exhaustive enumeration is not required. The
result should identify promising regions of the exit surface and record
which combinations were actually evaluated.

The engine defines its own documented bar and execution conventions.
TradeStation exports are optional diagnostic inputs; matching TradeStation
is not a dependency for implementing or running this engine.

## Existing code and necessary extensions

`exit_module/collect.py` currently accepts prepared CSV or Parquet entries and
session-partitioned ticks. `exit_module/replay.py` provides independent-entry
three-barrier replay. Those are useful existing components, but the current
collector does not generate bars or signals, enforce position occupancy,
perform adaptive search, or distribute policies across workers.

Keep the existing collector available as an explicitly independent-entry
analysis. Add the chronological strategy runner as a separate command so
old artifacts retain their original meaning. Reuse fill arithmetic and tick
reading where their contracts fit the new runner.

## Data and selected bar construction

The canonical input is ordered trade ticks with timestamp, price, volume,
source order, and contract-vintage provenance. Volume remains available for
bar aggregation and later features; it does not replace the ordered prices
needed for exit replay.

Stream input partitions in bounded batches. Preserve original tick order
when timestamps tie; do not sort equal-time rows by price or remove distinct
trades merely because they share a timestamp and price. Use an event index
alongside timestamps to disambiguate small tick bars within one second.

One run selects one or more bar specifications. Build each selected series
once and cache it under a key containing the input identity, bar rules, and
session configuration. Initially support time bars and tick-count bars:

- Time bars: configured duration, such as 30 seconds or 15 minutes.
- Tick-count bars: configured number of exported trade records, such as 10
  or 1,000. A tick count is distinct from the number of contracts traded.
- Volume bars can be added through the same interface later; they require
  a separately specified rule for a trade that crosses the volume threshold.

The bar contract records start/end time, first/last event index, OHLC, total
volume, tick count, source vintage, session, and completion status. Document
interval boundaries, timezone, session calendar, empty intervals, and partial
bars. Proposed time intervals are left-closed/right-open. Missing intervals
must not silently become invented price observations. Partial bars are
identified and excluded from signals by default.

Do not carry prices or an open position across a contract-vintage handoff
without an explicit transition rule. Reject an unspecified transition in a
run that spans it. This is a data-consistency constraint, not a requirement
to reproduce platform charts.

## Signal generation and actual entries

Proposed initial strategy: long-only 9/18 simple-moving-average cross,
confirmed using completed bars, one ES contract, one open position per policy.
These are parameters and a starting strategy implementation, not restrictions
on future strategies.

Generate the complete potential-signal sequence once per bar specification
and strategy configuration. Record each signal's completed-bar identity and
earliest eligible entry event. The actual entry uses the next eligible tick
after signal availability under the documented event ordering. A tick-count
bar's closing tick cannot also be its next bar's opening tick.

Each exit policy maintains separate flat, pending-entry, and open-position
state. Signals observed while that policy is occupied are skipped and logged;
they are not queued for entry after a later exit. Different policies therefore
produce different subsets of trades from the same potential signals.

Specify the order of existing-position exits, bar completion, new signals,
and new entries at coincident timestamps. Use event indices where timestamp
precision alone cannot distinguish those operations. Test the rule explicitly
rather than deriving fills by subtracting a fixed bar duration.

## Chronological execution and outcome collection

Each policy contains profit ticks, stop ticks, and maximum holding seconds.
Process the full date range chronologically for that policy. Price barriers
are tested on eligible ticks after entry; the time barrier becomes executable
at its deadline according to a declared fill rule.

Expose cost and execution conventions in run configuration. The current
project round-trip cost is $6.48 per one-contract trade. Proposed initial fill
conventions are targets at the limit and stop/time market exits at an observed
eligible trade price, with configurable slippage. These are execution
assumptions; the archive does not supply limit queue position or a complete
bid/ask execution model.

Session-end treatment must be explicit: carry permitted positions with a
defined elapsed-time rule, or close under a specified session-end order rule.
The engine must not retrospectively choose the last tick of a session for an
order that did not yet exist. Flag missing coverage, delayed time exits, and
positions unresolved at the end of the available data. Never silently reset
an unresolved position to flat and accept later signals.

Store executed trades, skipped signals and their reasons, exit reason,
entry/exit events and prices, holding time, costs, and favorable/adverse
excursion during each actual holding period. Produce comparable chronological
equity and drawdown for every evaluated policy. Independent-entry outcomes
and executed strategy trades have different semantics and distinct outputs.

## Adaptive search

The search domain is finite: minimum, maximum, and resolution for stop ticks,
profit ticks, and holding time. An evaluation budget and wall-time budget
bound total search work. The time barrier bounds an individual trade and is
separate from the user's requested search-stopping rule.

1. Evaluate a configured coarse set across the bounded domain, with known
   coordinates and a reproducible sampling order.
2. Expand or refine promising neighborhoods using smaller coordinate steps.
3. After a configured number of deteriorating neighboring bands, probe farther
   away using a configured jump distance or multiplier.
4. If a farther probe improves, resume expansion around it. After the allowed
   failed probes, stop expanding that region and continue other queued regions.
5. Stop when the queue is exhausted or a declared budget is reached. Persist
   the reason, evaluated coordinates, and remaining unexplored regions.

Patience, improvement tolerance, jump size, failed-probe allowance, and budgets
are configuration values. A local stopping decision is a heuristic, not proof
that no better policy exists beyond the sampled region. Each proposed policy
is evaluated over the complete designated development history before its
score guides spatial search; a bad early date segment is not itself a reason
to terminate its historical replay.

Proposed initial comparison objective: net P&L after configured costs over the
same calendar period, subject to explicit trade-count and drawdown criteria.
Report per-trade expectancy as a secondary metric, because policies can take
different numbers of trades. Keep entry parameters fixed during an exit search.

Use development periods to guide exploration and region selection. Evaluate
the frozen selected rule on reserved later data. Boundary positions and warmup
must have declared treatment; later-period outcomes must not choose the grid,
search settings, or selected region. Future ML training can consume the
recorded events under its own purging/embargo scheme.

## Parallel execution

A coordinator proposes batches of policies. Start with a configurable four
worker processes. Each worker receives a batch of policies and the entire
selected time range, maintaining a separate position state for each policy.
Workers can read the same chronological tick batch and update several policies
without rereading it once per policy.

Cache immutable bars and potential signals once. Initially allow workers to
read the same source files; benchmark disk throughput and peak RAM before
adding shared-memory or memory-mapped representations. Control library thread
counts to avoid multiplying CPU threads inside every worker.

Do not divide one strategy into independent date buckets when a position can
span those boundaries. Workers return complete policy results; the coordinator
updates the adaptive search and schedules the next batch. Persist results by
policy identity so failed workers can be retried and completed policies can
be reused on resume. Policy identity includes input and execution configuration.

Use deterministic batch boundaries for search decisions so worker completion
order does not silently change which region is explored. Allow graceful pause
and resume with the queued candidates and search state preserved.

## Surfaces and region selection

Plot stop distance against target distance with separate slices for holding
time and bar specification. Provide both a readable heatmap and an optional
3D surface. Untested locations remain explicitly unknown; interpolation for
display must not become evidence of profitable area.

Identify connected neighborhoods of evaluated policies that meet configured
performance criteria. Report neighbor stability, observed parameter coverage,
trade counts, drawdown, and results across chronological blocks. Unequal grid
spacing must not make densely sampled cells look like a larger physical region.
Report supported coverage separately from an interpolated area estimate.

Prefer well-supported regions over a single isolated high result, but allow
the report to conclude that no suitable region was found. Preserve the complete
search trail so the result can be reviewed for selection effects.

## Proposed components and delivery sequence

1. Input contracts and selected bar builder: add pure bar aggregation and tick
   adapters, with deterministic session and event ordering.
2. Signal generator and serial strategy runner: generate crosses and prove
   that different exits cause different eligible entry subsets.
3. Configurable policy batches and chronological trade outputs: run a small
   declared set to verify execution and reporting before adaptive selection.
4. Parallel workers, bounded memory, progress reporting, checkpoints, and resume.
5. Adaptive search with local patience, farther probes, and finite budgets.
6. Heatmaps/surfaces, connected-region summaries, and reserved-period evaluation.

Suggested new modules under `exit_module/`: `bars.py`, `signals.py`,
`strategy_replay.py`, `search.py`, `workers.py`, `report.py`, and `run.py`.
Keep pure state and aggregation separate from file reading and orchestration.
Write large caches and results below ignored `.artifacts/exit_module/`; version
source, configuration examples, and documentation.

## Verification criteria

- Synthetic time/tick bars recover expected OHLC, volume, and event membership,
  including same-second ticks, partial bars, boundaries, and missing intervals.
- Signals depend only on completed bars; next-event entries never use a future
  bar close or high/low.
- A narrow exit can free a policy for a later crossover while a wide exit skips
  it. Skipped signals and actual trades reconcile with the potential-signal log.
- Profit, stop, deadline, gaps, and session-end behavior follow declared rules.
- Serial and parallel runs of the same policies produce identical trade logs
  and metrics; restart does not duplicate results or change candidate ordering.
- Search tests demonstrate deterioration, successful distant recovery, failed
  probes, and budget exhaustion. Reports distinguish evaluated from untested space.
- Benchmark one, two, and four workers for throughput and peak RAM; add workers
  only when measurements support it.

## Choices to set before the first full experiment

Planning can proceed with configurable fields. A full run needs selected bar
specifications; stop/target/time bounds and step sizes; session/overnight rules;
cost/slippage assumptions; development and reserved dates; performance criteria;
search patience, jump rules, and budgets. Proposed starting engineering defaults
are 30-second bars, 9/18 long-only crossover, one contract/position per policy,
$6.48 round-trip cost, and four workers. These are proposals, not tuned parameters.
