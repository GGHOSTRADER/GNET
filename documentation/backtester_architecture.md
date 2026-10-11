# Backtester module boundaries — revised design

The human-facing organization is: (1) bar builder, (2) primary model builder,
(3) optional exit finder, and (4) analyzer of the primary model plus exit.
Stage 4 contains the execution engine and independent statistics module;
stage 3 invokes it for each trial. See the [user guide](guides/BACKTESTER_GUIDE.md)
for the four-stage diagram, operating instructions and current inventory.

Status: exit-analyzer / backtest-results separation implemented September 30,
2026. Preset and sweep modes both produce per-run statistics and reports.
The five-strategy inventory, native strategy-specific exit interface, and
combined bars/trades viewer remain planned; they are not implemented here.
The earlier diagram's dashed boundaries describe the proposal before this
implementation. Existing source data and previous results were not overwritten.

Implementation boundaries:

- `backtester/run.py`: run routing, identity, preparation and confirmation.
- `backtester/exit_analyzer.py`: optional adaptive-search coordinator.
- `backtester/report.py`: exit analyzer's surfaces, rankings and selection report.
- `backtester/replay.py` / `workers.py`: independent chronological policy execution.
- `backtester/results.py`: equity reconstruction and pure per-run statistics.
- `backtester/results_report.py`: per-run persistence, HTML and report catalog.

## Two distinct analysis modules

### Exit module analyzer: optional

Owns adaptive exploration of stop, target, and time-barrier combinations,
search patience, farther probes, finite budgets, comparisons, and supported
regions. It requests complete chronological backtests from the engine and
uses their results to choose subsequent combinations. Each configuration keeps
independent positions, so accepted entries may differ between configurations.

It owns the exit-analysis HTML report: surfaces, tested/untested combinations,
rankings, parameter sensitivity, and region summaries. The existing HTML
report demonstrated in this conversation belongs to this category. This is
not the general backtest-results report.

### Backtesting results: used for every run

Consumes executed trades, positions, a consistently sampled marked-to-market
equity/return series, execution references, costs, and run metadata. Produces
statistics for an individual configuration whether preset or sweep-generated.
It does not generate trades, choose exit parameters, or modify past results.

Produces a separate backtesting-results report. The exit analyzer may consume
its machine-readable metrics; the statistics module does not require the exit
analyzer to be enabled.

## Execution routes

- Preset: configuration -> engine with one preset -> run outputs -> backtesting
  results -> statistics report. The exit analyzer is not instantiated.
- Sweep: configuration -> exit analyzer -> engine per proposed configuration
  -> run outputs -> backtesting results -> metrics returned to exit analyzer.
  The analyzer additionally produces its own comparison/surface report.

Strategy triggers and future strategy-specific exits belong in the strategy
inventory. Reusable tick-level stop/target/time evaluation remains execution logic.
Preset exits are fully specified rules; sweep-generated exits vary only the
declared settings. Whether a strategy's native exit remains active during a
sweep must be explicit, not a hidden combination of rules.

## Statistics specification

Use Chapter 14, **Backtest Statistics**, of Marcos Lopez de Prado's *Advances
in Financial Machine Learning* as the organizing reference. The publisher's
[detailed contents](https://catalogimages.wiley.com/images/db/pdf/9781119482086.toc.pdf)
identifies the chapter's performance, concentration, drawdown, execution,
risk-adjustment, classification, and attribution topics.

Implemented output groups (conditional metrics are explicitly unavailable
when required inputs are absent):

| Group | Proposed measurements |
|---|---|
| Activity | Coverage dates, trade count, holding duration, closed-trade notional turnover and calendar-time exposure |
| Performance | Gross/net P&L, return on declared capital, win rate and payoff distribution |
| Path and concentration | Drawdown depth and duration, time below prior equity highs, concentration of gains/losses across trades and time |
| Execution | Closed-trade fees, modeled slippage and entry shortfall against the completed signal-bar close |
| Risk-adjusted evidence | Sharpe, probabilistic Sharpe and deflated Sharpe when required inputs and assumptions are available |
| Attribution | Strategy identity; exit reason, elapsed holding-time buckets and exit month. Benchmark/factor inputs not implemented |
| Classification, if applicable | Unavailable: no ML prediction/label inputs in this implementation |

Do not manufacture unavailable statistics. Return calculations require an
explicit capital/cash-flow convention and consistent return sampling. Futures
notional is not automatically the return denominator. Execution shortfall is
not synonymous with commissions. Deflated Sharpe needs research-trial history
and assumptions about dependence between trials, not merely the best run's
trade list. Preserve those inputs across searches, including unsuccessful
trials. See the authors' [deflated Sharpe paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

Purging, embargo and combinatorial cross-validation are experiment/training
procedures, not statistics that a reporting module can retroactively claim.
If those procedures are used, their split metadata and results must be passed
to reporting explicitly.

## Saved outputs and viewer

Keep reconstructed bars and actual executed trades as separate reusable
outputs. Candidate signals and skipped signals remain distinguishable from
executed entries. Position/equity series are now saved as `equity.parquet` per
policy. Session-end returns and sampled underwater episodes are also saved.
A separate planned viewer consumes saved bars and trades, with Bars / Trades /
Both views and explicit strategy/run/exit-configuration selection. It is neither
the exit-analysis HTML report nor the general statistics report.

The [interface and trade-viewer specification](research_interfaces_and_trade_viewer.md)
adds candlestick/price-line modes, executed entry/exit markers, bounded chart
requests through the broker, and protected artifact handoffs. This viewer is
planned; the existing equity/statistics reports do not implement it.

## Verification

45 focused tests pass, including analytical cost, equity, HHI, PSR and DSR
fixtures, equal-timestamp events, missing coverage, preset bypass, confirmation,
report rebuilding and parallel execution. A two-session real-tape regression
replayed 1,560,519 ES ticks: all 48 sweep policy summaries (except run identity),
trade tables and skip logs match the pre-separation run. Preset mode ran both
bar types without constructing an exit analyzer. This verifies engineering
behavior, not trading edge. Browser rendering QA was blocked by the local-file
URL policy; report content and links were checked without browser execution.
