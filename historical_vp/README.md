# Historical Volume-Profile Data Preparation

This folder holds the large TradeStation tick exports and the generated,
compressed dataset used to reconstruct historical volume profiles. The
preparation module validates and deduplicates ticks. The replay module then
passes every prepared tick through `feat_files/canonical_volume_profile.py` and
writes the complete 32-feature VP contract once per 30-second interval.

## September 2026 continuous-contract adjustment

The September 21 export is a newer `@ES` price-adjustment vintage. Its August
13–14 ES-session overlap contains 1,343,790 ticks with identical timestamps,
tick order, Up, and Down values; every newer price is exactly 67.75 points
above the older prepared price. Keep both raw exports unchanged.

The selected paired history is a **session-boundary splice**: old ticks and
old 30-second bars through ES session 2026-08-14, then new ticks and new
30-second bars from session 2026-08-17 onward. Run
`python -m training_mlp.splice_historical_vintages` from the repository root
to create `prepared_spliced_2026_09_21/` and the matching spliced bar export.
No prices or volumes are changed, and the manifest records the provenance.
This is a price-scale break; reset rolling feature state at the handoff and
exclude the ensuing warm-up before training. The derived
`prepared_continuous_2026_09_21/` from an earlier adjustment experiment is
retained for audit only and is **not** the selected research input.

For every future rollover, perform the same handoff audit before replaying VP:
use old ticks with old 30-second bars through the last shared ES session, then
switch both streams together. Check the first and last bar OHLC, tick-derived
OHLC, and `Up`/`Down` totals at the boundary. The first new tick and first new
bar must be on the same price scale. If a large constant gap appears, stop and
record the cutoff and source manifests; do not adjust prices or train across
the boundary until the discrepancy is understood.

See the [preparation flow diagram](../diagrams/historical_vp_preparation.mmd)
for the complete data path.

## Prerequisites

- Run every command below from the GNET repository root.
- Use the Python environment in which GNET and `pyarrow` are installed.
- Export a **1-tick TradeStation chart** with Trade Volume and these columns:
  `Date, Time, Open, High, Low, Close, Up, Down`.
- Know the exact symbol represented by the exports, such as `@ES`.
- Keep enough free disk space for staging and final Parquet files. Parquet is
  compressed, but its exact size depends on the data.

## Folder Layout

```text
historical_vp/
├── README.md
├── raw/                         # TradeStation text exports; ignored by Git
│   ├── volumeprof_2026-03-15_to_2026-04-15.txt
│   ├── volumeprof_2026-04-15_to_2026-05-15.txt
│   ├── volumeprof_2026-05-17_to_2026-06-15.txt
│   ├── volumeprof_2026-06-15_to_2026-07-15.txt
│   └── volumeprof_2026-07-15_to_2026-08-14.txt
├── prepared/                    # Generated files; ignored by Git
    ├── parquet/
    │   └── session_date=YYYY-MM-DD/
    │       └── ticks.parquet    # One final file per 18:00 trading session
    ├── manifest.json
    ├── manifest_partitions.csv
    └── .staging/                # Retained only when intervention is needed
└── features/                    # Canonical VP features; ignored by Git
    ├── parquet/
    │   └── session_date=YYYY-MM-DD/
    │       └── vp_features.parquet
    ├── manifest.json
    └── manifest_partitions.csv
```

## Canonical Offline Feature Engineering

After preparation succeeds, run:

```powershell
python -m training_mlp.replay_historical_vp --workers 4
```

The profile updates on every tick. Within each interval, the replay retains the
freshest tick timestamped in the final second (`time_s % 30 == 29`) and commits
temporal history exactly once. This reproduces just-in-time freshness without
collapsing `recent_*`, POC velocity, or Value Area expansion features to a
tick-to-tick horizon.

See [historical VP feature replay](../documentation/historical_vp_features.md)
for output columns, validation, rerun behavior, and the current live-parity
follow-up.

## Merge VP With the MA Training Events

After canonical VP replay and the MA labeling pipeline have both completed,
build the leakage-safe combined training table from the repository root:

```powershell
python -m training_mlp.merge_ma_vp_features
```

The merge selects the freshest VP snapshot at or before each MA entry within
the same symbol and 18:00 ES session. The default rejects snapshots older than
30 seconds and drops events outside VP coverage. It writes:

```text
training_mlp/strategies/MA2CrossLE/processed/
├── df_features_labeled_vp.parquet
└── df_features_labeled_vp.manifest.json
```

The Parquet contains the 13 canonical MA features, all 32 canonical VP
features, `Label`, `t1`, and four audit-only columns: `symbol`, `session_date`,
`vp_snapshot_timestamp`, and `vp_age_ms`. `Label` is the target; `t1` is used
for purging; the audit columns are not model inputs. Use `--keep-unmatched` to
retain null diagnostic rows, or `--max-vp-age-s` to test another explicitly
bounded freshness policy.

For a fair baseline diagnostic on the same 4,432 merged events, run the
canonical 13-feature correlation report with:

```powershell
python -m training_mlp.analyze_ma_correlations `
  --input training_mlp\strategies\MA2CrossLE\processed\df_features_labeled_vp.parquet `
  --output training_mlp\strategies\MA2CrossLE\reports\correlation_13_vp_overlap
```

## Setup and Normal Run

Confirm that all numbered raw exports are present:

```powershell
Get-ChildItem .\historical_vp\raw\volumeprof*.txt
```

Run the preparation command, replacing `@ES` if the chart used another exact
symbol:

```powershell
python -m training_mlp.prepare_historical_vp --symbol "@ES"
```

When no explicit input paths are provided, the command automatically discovers
every file named `volumeprof<number>.txt` or
`volumeprof_YYYY-MM-DD_to_YYYY-MM-DD.txt`. Existing numbered exports are
processed in numeric order, followed by dated exports in date-range order.
Use the actual first and last calendar dates in each new export's filename;
do not overwrite an existing file. Overlap validation still applies.
The default uses two worker processes so independent exports are staged on two
CPU cores. Use `--workers 1` for the lowest disk/CPU load or benchmark
`--workers 4` if the storage device can sustain more parallel reads.

The module reads the text files incrementally, validates each row, assigns
ticks to the ES trading session that begins at 18:00, and writes
Zstandard-compressed Parquet. It does not load all 5 GB into memory.

On success, inspect the run summary and partition list:

```powershell
Get-Content .\historical_vp\prepared\manifest.json
Get-Content .\historical_vp\prepared\manifest_partitions.csv -TotalCount 10
Get-ChildItem .\historical_vp\prepared\parquet -Recurse
```

The completed output is deliberately not overwritten. To create a separate
fresh dataset, supply another directory:

```powershell
python -m training_mlp.prepare_historical_vp --symbol "@ES" --output .\historical_vp\prepared_v2
```

## Overlapping Export Files

Adjacent exports may share a trading session:

- If row count and normalized content hash match, the overlap is identical.
  The module keeps one deterministic owner and completes automatically.
- If the same session has different rows or values, the module preserves its
  staged Parquet, writes diagnostics, and stops so no raw files must be read a
  second time.

Inspect a conflicting overlap:

```powershell
Get-Content .\historical_vp\prepared\overlap_conflicts.json
Get-Content .\historical_vp\prepared\INCOMPLETE.txt
```

After reviewing it, finalize the staged run. The conflict policy selects the
source containing the most rows for that session:

```powershell
python -m training_mlp.prepare_historical_vp --resume --allow-conflicting-overlaps
```

Do not use the conflict flag without inspecting the report: equal timestamps
with different prices or volumes can indicate an export or data-quality issue.

## Useful Options

```powershell
python -m training_mlp.prepare_historical_vp --help
```

Use `--timezone` if the TradeStation timestamps are not in the configured
market timezone, `--batch-rows` to tune conversion memory use, and
`--compression` to choose a supported Parquet compression codec. Use
`--workers` to control parallel source-file staging.

For implementation details and validation rules, see
[`documentation/historical_vp_preparation.md`](../documentation/historical_vp_preparation.md).
