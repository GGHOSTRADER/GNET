# Where are the statistics, surfaces and numbers?

[Human guide](guides/BACKTESTER_GUIDE.md) · [Agent runbook](guides/BACKTESTER_AGENT_GUIDE.md)

There are two separate report owners. The backtest analyzer reports on **one
strategy/bar/exit configuration**. The exit finder compares **many exit
configurations**. Preset mode runs the first without the second.

## Open existing examples now

These are June 15–16, 2026 engineering demonstrations, not a full-period
research conclusion or a trading recommendation.

| What to inspect | Direct link |
|---|---|
| All backtest configurations in the sweep | [Backtesting statistics catalog](../.artifacts/backtester/smoke_results_split_20260930/backtesting_results.html) |
| One fixed-exit backtest: time-30, target 4, stop 4, timeout 120 seconds | [Readable statistics report](../.artifacts/backtester/smoke_results_preset_20260930/policies/time_30/development/pt4_sl4_h120/results.html) |
| The same backtest's machine-readable metrics | [statistics.json](../.artifacts/backtester/smoke_results_preset_20260930/policies/time_30/development/pt4_sl4_h120/statistics.json) |
| Actual accepted entries and exits | [trades.parquet](../.artifacts/backtester/smoke_results_preset_20260930/policies/time_30/development/pt4_sl4_h120/trades.parquet) |
| Time underwater / drawdown episodes | [drawdowns.csv](../.artifacts/backtester/smoke_results_preset_20260930/policies/time_30/development/pt4_sl4_h120/drawdowns.csv) |
| Exit search on 30-second bars | [Exit-finder HTML](../.artifacts/backtester/smoke_results_split_20260930/reports/time_30/index.html) |
| Exit search on 1,000-tick bars | [Exit-finder HTML](../.artifacts/backtester/smoke_results_split_20260930/reports/tick_1000/index.html) |
| Numerical stop/target/time results for 30-second bars | [policies.csv](../.artifacts/backtester/smoke_results_split_20260930/reports/time_30/policies.csv) |
| Connected positive regions | [regions.json](../.artifacts/backtester/smoke_results_split_20260930/reports/time_30/regions.json) |
| Selection and reason | [selection.json](../.artifacts/backtester/smoke_results_split_20260930/reports/time_30/selection.json) |
| Heatmap, 120-second time barrier | [surface_h120.png](../.artifacts/backtester/smoke_results_split_20260930/reports/time_30/surface_h120.png) |
| Three-dimensional view of the same tested combinations | [surface3d_h120.png](../.artifacts/backtester/smoke_results_split_20260930/reports/time_30/surface3d_h120.png) |

The linked files are local ignored artifacts; they will not appear in a fresh
Git clone. Parquet links identify the data file, not an interactive chart.
Use the HTML or PNG links for readable output. The combined candlestick-and-
trades viewer is not implemented.

## Reading the exit surface

Each image fixes one time barrier. Horizontal position is profit-target ticks,
vertical position is stop-loss ticks, and color/height is net dollars after
configured costs. Gray cells are **untested**, not zero-profit. Black crosses
mark ineligible results. Three-dimensional faces only connect fully sampled
cells. The finder searches a bounded grid adaptively; it does not prove a
global optimum or infer profitability inside unsampled regions.

The CSV contains tested policies and their numerical outcomes. Region output
describes sampled connected groups, including support across configured time
blocks. A least-bad selected policy can still lose money; selection does not
authorize deployment.

## Statistics inventory and source files

Direct answers to the requested statistics:

| Requested | Current status |
|---|---|
| Return concentration | Yes: normalized HHI of positive/negative net trade contributions; monthly exit-count concentration |
| Time-weighted return | Yes, conditional on supplied capital and valid equity; no external cash flows |
| Drawdown and time underwater | Yes: exact replay maximum dollar drawdown plus sampled underwater episodes |
| Sharpe | Yes, conditional on valid capital and sufficient nonconstant session returns |
| Probabilistic / deflated Sharpe | Both supported conditionally; deflated Sharpe requires research-trial inputs, not just grid size |
| Efficiency statistics | Partial: payoff, profit factor, exposure, costs and turnover; not the complete book suite |
| Buy and hold | Not implemented yet |

“Polished Sharpe” is not a statistic name used by this implementation; the
available variants are ordinary, probabilistic and deflated Sharpe. Unavailable
values are explicitly reported rather than fabricated.

A new [three-bar-type engineering report](../.artifacts/backtester/multibar_example_20261001/backtesting_results.html)
covers time-30, tick-1000 and volume-1000 on June 15–16 using 1,560,519 ticks.
This verifies execution/reporting, not strategy profitability. Its volume
configuration has [its own statistics](../.artifacts/backtester/multibar_example_20261001/policies/volume_1000/development/pt4_sl4_h120/results.html).

The implementation is [results.py](../backtester/results.py); rendering and
output are [results_report.py](../backtester/results_report.py). For exact
metric scope and unavailable cases, see the human guide's
[statistics inventory](guides/BACKTESTER_GUIDE.md#module-4--statistics-inventory).

It includes net/gross profit, win rate, profit factor, return concentration,
drawdown, sampled time underwater, exposure, costs and holding-time
distributions. TWR and Sharpe-family statistics require additional valid
inputs; the default config leaves capital unspecified. Deflated Sharpe also
requires documented research-trial inputs. Buy-and-hold comparison is **not
implemented**. Do not describe missing metrics as zero or imply this is the
entire book's statistics suite.

The independent exit analyzer is [exit_analyzer.py](../backtester/exit_analyzer.py),
the adaptive search is [search.py](../backtester/search.py), and its surface/
comparison report is [report.py](../backtester/report.py).

## Commands and output locations

From the repository root, after reviewing the example config and choosing a
fresh output directory:

```powershell
# Preset policy: backtest statistics only.
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.preset.example.json
# Sweep: statistics for each tested policy plus exit-comparison reports.
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.example.json
```

For an already completed, unchanged sweep, regenerate its comparison report:

```powershell
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.example.json --report-only
```

Use the config belonging to the run you want, not an unrelated example config.
`--report-only` is not a migration tool for changed code or missing per-policy
statistics. Run identity must still match; it does not replay missing trades.

Under the configured output directory:

```text
backtesting_results.html                         all backtest reports
policies/<bar>/<phase>/<policy>/results.html      one backtest
policies/<bar>/<phase>/<policy>/statistics.json   its statistics
reports/<bar>/index.html                         exit analysis (sweep only)
reports/<bar>/policies.csv                       combination numbers
reports/<bar>/surface_h<seconds>.png             heatmap
reports/<bar>/surface3d_h<seconds>.png            3D sampled surface
reports/<bar>/regions.json                       region analysis
```
