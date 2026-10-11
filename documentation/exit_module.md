# ES exit-outcome collection (offline research)

`exit_module` replays the **existing long MA-cross entries** against a configurable
grid of three-barrier exit policies. Every policy has a profit target, a loss
stop, and a maximum holding time. It writes one outcome per entry and policy;
it does not train a model, choose the best policy, or change live trading.

The input is the corrected 5,905-entry June–September TradeStation dataset.
The tick source is the paired, **unadjusted** old/new ES vintage splice, not
the separate price-adjusted exploratory tick history. Entry occurs at the
start of the 30-second bar whose end timestamp is recorded as `entry_time`.
The completed preceding bar is the signal; no entry-bar feature is used to
make a decision.

## Run

From the GNET repository root:

```powershell
python -m exit_module.collect `
  --profits 1,2,3,4,6,8 `
  --stops 1,2,3,4,6,8 `
  --times 30,60,120,300 `
  --output .artifacts/exit_module/ma2cross_three_barrier_v2
```

These grid values are **research examples**, not selected exit settings. The
default makes 144 policies per entry. Other `--entries` and `--ticks` paths
can be passed. An existing output path is never overwritten. `--max-trades`
is only for a smoke test. `--exclude-entry-timestamp` is available to audit
the alternative convention for ticks exactly on the entry boundary.

To reuse the module with the older, point-in-time-correct MA-cross export and
its matching **unadjusted old-contract ticks**:

```powershell
python -m exit_module.collect `
  --entries training_mlp/strategies/MA2CrossLE/processed/ma2cross_old_libb_prior_bar_13.csv `
  --ticks historical_vp/prepared `
  --output .artifacts/exit_module/old_libb_prior_bar_13
```

The entry reader accepts a prepared `.parquet` or `.csv`. An older CSV with
`feature_time` but no `candidate_time` uses `feature_time` as the already-closed
signal-bar timestamp. This does **not** ingest a raw TradeStation Trades List:
that list must first be paired with its entry bars and validated. The collector
requires ES long entries on 30-second bars, the documented trade fields, and
timestamped ES tick partitions. Keep each contract vintage paired with its own
unadjusted ticks; do not mix price-adjusted and unadjusted sources. Review the
new run's mismatch audit before treating its outcome rows as training labels.

## Files and interpretation

- `entries.parquet`: frozen input rows, including candidate-time features.
- `outcomes/entry_session=.../outcomes.parquet`: long-form outcome matrix.
  Join to entries by `(vintage, trade_number)`. `exit_reason` is `profit`,
`loss`, `time`, `unavailable_time`, or `censored`; the monetary result includes
  $6.48 round-trip cost when an exit is measurable. A time exit may be
  positive **or** negative. `unavailable_time` has no assigned P&L.
- `baseline_audit.parquet`: independent no-time-limit four-tick/four-tick
  replay against each recorded TradeStation exit, including the first-tick
  entry-price gap and a strict match flag.
- `descriptive_summary.csv`: counts and sums by policy, **not** validated
  model performance or an investable portfolio result.
- `manifest.json`: inputs, hashes, conventions, policy grid, coverage,
  baseline match count, and an explicit training-readiness flag.

Ticks with the same timestamp retain export row order. Profit targets fill at
the target limit; stop orders fill at the first observed crossing trade price
(including an adverse gap); the time barrier exits at the first observed tick
at or after its deadline and wins an exact-time tie. The delay between the
deadline and an executable tick is recorded. By default, a delay exceeding
30 seconds is `unavailable_time`, with no invented return. This limit can be
changed with `--max-time-exit-delay-seconds`. These are price-path proxies:
the export does not establish bid/ask liquidity, limit-order queue priority,
or actual slippage. Every entry is replayed independently, so overlapping
counterfactual positions are **not** resolved as a portfolio.

## First source audit

The initial full four-tick/four-tick audit matched **5,778 of 5,905** recorded
TradeStation outcomes. It flagged **127** differences: 108 stop/target
direction disagreements and 19 same-direction price/P&L disagreements.
The tick export and TradeStation's historical execution simulation therefore
are not interchangeable for every event. The collector preserves every row
and flags mismatches; its manifest sets `dataset_ready_for_training=false`.
The first unrestricted collection also found time exits delayed across market
closures, so its output was superseded by the version that flags those rows.
In the corrected full output, **908 policy rows spanning 39 entries** are
`unavailable_time` because no tick arrived within 30 seconds of the deadline.
Before using this for model training, investigate the discrepant events and
decide a documented, non-cherry-picked treatment. Filtering to only matching
events would change the sample and must be reported as such.
