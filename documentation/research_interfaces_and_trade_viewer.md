# Research interfaces and trade viewer specification

Status: proposed implementation contracts, October 2, 2026.
See the [integration audit](reports/guarded_backtester_integration_audit_2026-10-02.md),
[guarded runtime](guarded_research_runtime_architecture.md),
[backtester architecture](backtester_architecture.md), and
[validation/provenance requirements](research_validation_and_provenance_requirements.md).

Use the [implementation phases](guarded_research_implementation_phases.md)
for the delivery order and acceptance checks linking these contracts.

## 1. Interfaces to implement

An interface is a defined input, output and error contract between components.
Use versioned Python types plus JSON schemas at the job boundary; internally,
reuse the existing strategy/config/execution types where suitable.

| Interface | Input | Output | Owner |
|---|---|---|---|
| Job submission | Schema version, operation, payload, limits, approved release | Job ID, receipt, status reference | Agent client and protected broker |
| Dataset resolution | Immutable dataset ID/revision | Protected paths plus source/contract manifest | Protected catalog adapter |
| Artifact resolution | Artifact ID, expected type, consumer release | Protected location and compatibility metadata | Broker artifact registry |
| Bar construction | Dataset/source ID, sessions, bar specification | Bar artifact ID, counts and provenance | Bar builder adapter |
| Candidate generation | Bar artifact ID, strategy and parameters | Candidate artifact ID, counts and availability convention | Strategy adapter |
| Policy execution | Bars/candidates, execution tape, preset policy and costs | Trades/equity artifact IDs, outcome summary | Execution adapter |
| Exit search | Prepared artifacts, search axes, budgets, stopping settings | Search artifact ID, tested policies and selection evidence | Exit analyzer |
| Validation | Operation, artifact IDs, configuration and identities | Per-check status/evidence plus usability gate | Validation coordinator |
| Publication | Validated result IDs, allowed output tier | Bounded JSON, plots and safe HTML references | Result publisher |
| Trade visualization | Run/policy/bar-series IDs and bounded viewport | Chart artifact plus compact viewport summary | Viewer adapter |

Canonical engine operation names: `build_bars`, `generate_candidates`,
`backtest_preset`, `backtest_sweep`. Supporting jobs include `data_inventory`,
`provenance_summary`, `validation_preflight`, `validation_postflight`, and
`trade_view`. `status`/`report` are client reads of published job output.

These names supersede inconsistent proposed aliases such as `backtest_run`.
The existing `python -m backtester.run` command remains the engine entry point;
the protected adapter maps typed jobs into its internal configuration.

## 2. Shared request/result envelope

Client submission must contain `schema_version`, `operation`, `payload`,
`release_id` and requested `limits`. The client generates a collision-resistant
job ID before atomically submitting the envelope. The broker validates and
claims it, resolves trusted IDs and computes the effective configuration/hash.
User-supplied paths, class/module names or shell/Python code are not accepted.
Limits are capped by protected broker policy.

Every published result contains the job ID, operation/schema version, execution
status, validation status, data/config/release identities, counts, warnings,
unavailable metrics, safe report references and a structured error when needed.
Human-readable errors must be short; full tracebacks remain protected.

States: queued -> claimed -> preparing -> preflight -> running -> postflight
-> published. Failed/cancelled states include stage and completed artifact IDs.
Execution completion and usable research are separate fields. Resubmission of
the same job ID must not silently run it twice.

## 3. Internal artifacts

Register every artifact with its ID, type, schema version, parent IDs,
dataset/revision, original source filenames/hashes, contract segments,
coverage, bar specification, code/config identity and validation reference.
Only the broker resolves its physical path. Full bars/candidates/trades/equity
stay in the protected job workspace.

Bar specifications must distinguish time interval, event-count threshold,
traded-volume threshold, and grouping N imported source bars. Imported bars
need an audited mapping to a compatible execution tick tape before they can
drive replay. Stable bar IDs and tick sequence references are required for
entry-bar/exit-bar mapping and same-timestamp diagnostics.

## 4. Trade viewer

The separate trade viewer is currently missing. It must display executed
entries/exits on either candlestick bars or a price line. It is accessed from
backtest results and can also be requested by the agent through `trade_view`.

Required selection controls:

- Run, phase, policy and engineered bar series.
- Date/session range or a selected trade ID.
- Outcome: all, winners, losers, breakeven, or unresolved.
- Minimum/maximum P&L in dollars, with an explicit net/gross selector (net
  after configured costs by default).
- Sort matching trades by entry date, exit date, P&L or holding duration; use
  a stable trade ID to break ties. Select a match to center the chart around
  its full entry-to-exit interval with context before and after.
- Candlestick or price-line mode.
- Optional candidate/skipped-signal overlay, visually distinct from fills.

Required chart content:

- Chronological price, asset, actual contract/series, timezone and date range.
- Signal marker, actual entry marker and actual exit marker at their recorded
  times/prices, with a trade connector and exit reason.
- Optional stop/target levels active for the selected trade.
- Contract boundaries, partial coverage and validation warnings.
- Selected-trade details: ID, timestamps/prices, gross/net result, costs,
  elapsed seconds, entry/exit bar IDs and bar offset, source filename references.
- For an open/unresolved trade, an open-position marker and explicit status;
  no invented exit or realized profit.

### Winner/loser distinction and time placement

Classify closed trades by net P&L after the configured costs: positive is a
winner, negative is a loser, and zero is breakeven. Unknown P&L remains
unresolved. The P&L search selector can use gross dollars without silently
changing the outcome classification; show both amounts for a selected trade.

Use green for winners, red for losers, and separate neutral styles for
breakeven/unresolved trades. Pair color with outcome labels and different
connector/marker styles so meaning is still clear without color. Entry/exit
marker shapes identify their roles independently of trade outcome.

Render each trade from its actual entry time to its actual exit time on the
price chart. Add a compact aligned trade-duration lane below the chart, with
the same outcome styles, so winners and losers are distinguishable across
time even where price connectors overlap. Selecting either representation
highlights both and displays exact timestamps, duration and result. Preserve
zero-duration and equal-timestamp events as separately selectable marks using
their sequence/trade IDs; avoid implying a duration the source does not establish.

### Date and P&L search behavior

Run, phase and policy identify the population being searched. Date filters
must name their basis: entry time, exit time or position overlapping the
selected range. Default to entry time; use timezone-aware half-open intervals
`[start, end)` internally. UI end dates include the selected calendar date by
converting to the next local midnight, accounting for DST.

Apply date, outcome and P&L filters together within the broker before returning
matches. P&L bounds are inclusive and validated as finite dollars. Unresolved
trades do not match numerical P&L bounds. Return total matching count, shown
count and pagination/truncation status so a limited chart is not mistaken for
the entire population. Filters affect visualization only, never execution,
validation populations or the original run's statistics.

A bounded match list supplies trade IDs and approved summary fields. Selecting
a trade requests its bounded chart window. Broader search operates over
protected artifacts; the browser must not download the full trade table to
filter locally. If a trade interval is too large for full-resolution display,
return an explicitly reduced-resolution overview preserving its fill markers.

Display modes: bars/line without trades, trade-focused view with price context,
or both. A price line defaults to engineered-bar closes. A tick-price detail
view requires a separately bounded request and advertises any aggregation.

The browser and agent have no direct raw-folder access. The protected viewer
adapter reads the internal artifacts and renders a bounded viewport. V1 may
publish self-contained HTML with controls over that viewport; fetching a new
range creates a new broker job. A later local UI can use the same job client
to request ranges without becoming a raw-file server.

Do not embed the entire history or full trade table in HTML/JavaScript. Define
protected caps on range, candles/points, trade markers and output bytes. If a
requested window exceeds them, return an explicit reduced-resolution overview
or require a smaller range. Aggregate OHLC correctly; never average candles.
Preserve selected-trade entry/exit markers through downsampling. Events sharing
a timestamp retain sequence identity even if their marks visually overlap.
Chart success does not imply that exact tick-path execution was visually shown.

An agent result contains the chart reference and compact counts/coverage/status.
Trade details are an explicitly requested bounded diagnostic output. A chart
may necessarily expose selected market prices to its reader; this limited
visualization exception does not authorize publishing complete derived tables.

## 5. Implementation sequence and acceptance

1. Define envelopes, artifact IDs, dataset resolver and synthetic broker adapter.
2. Add protected workspaces, safe publisher and preflight/postflight hooks.
3. Connect one preset backtest through the interfaces; verify provenance and
   diagnostic/usable result status end to end.
4. Build the viewer using a small synthetic bars/trades fixture. Verify both
   candle and line modes, exact fill markers, winner/loser/breakeven styling,
   aligned duration lane, unresolved trades, combined date/P&L filters,
   timezone boundaries, stable sorting/pagination, ties, source references
   and output limits.
5. Connect the exit analyzer to the same execution/validation/publication path.
6. Add source-bar/tape mapping and additional capabilities independently.

The end-to-end acceptance fixture must verify agent submission -> broker
execution -> validation -> safe report and chart. It must reject incompatible
dataset/artifact IDs and prevent published links from exposing protected files.
The viewer must visibly distinguish candidate events from actual executed trades.
