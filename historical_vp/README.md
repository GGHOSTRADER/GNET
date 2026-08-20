# Historical Volume-Profile Data Preparation

This folder holds the large TradeStation tick exports and the generated,
compressed dataset used to reconstruct historical volume profiles. The
preparation module validates and deduplicates ticks. The replay module then
passes every prepared tick through `feat_files/canonical_volume_profile.py` and
writes the complete 32-feature VP contract once per 30-second interval.

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
│   ├── volumeprof1.txt
│   ├── volumeprof2.txt
│   ├── volumeprof3.txt
│   ├── volumeprof4.txt
│   ├── volumeprof5.txt
│   └── ...                       # Any volumeprof<number>.txt is discovered
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
every file named `volumeprof<number>.txt` and processes them in numeric order.
For example, files 1 through 5 are all included, and file 10 sorts after file 9.
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
