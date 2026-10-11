# File locations, naming, schema and merge compatibility

[Human guide](guides/BACKTESTER_GUIDE.md) · [Agent guide](guides/BACKTESTER_AGENT_GUIDE.md)
· [Data inventory](backtester_data_inventory.md)

## 1. Where to save files and what to name them

All locations are relative to `C:\Users\g_med\python_new\GNET`.

| Stage | Path / naming convention | Created by |
|---|---|---|
| New original ES tick-bar export | `historical_vp/raw/ES/tick/ES_tick_<size>_<first>_to_<last>_export_<stamp>.txt` | You |
| New original ES volume-bar export | `historical_vp/raw/ES/volume/ES_volume_<size>_<first>_to_<last>_export_<stamp>.txt` | You |
| Prepared delivery | `historical_vp/prepared_ES_<first-session>_to_<last-session>_v<stamp>/` | Preparation command |
| Merged snapshot | `historical_vp/merged_ES_<first-session>_to_<last-session>_v<stamp>/` | Merge/splice command |
| Experiment configuration | `config/backtester.<strategy>_<bars>_<stamp>.json` | Human or agent |
| Experiment output | `.artifacts/backtester/<strategy>_<bars>_<stamp>/` | Backtester |
| Source registration | [backtester.data_sources.json](../config/backtester.data_sources.json) | Human or agent |

Use `YYYY-MM-DD` for dates and `YYYYMMDDTHHMMSS` for the export/version stamp.
For example, save a future export as:

```text
C:\Users\g_med\python_new\GNET\historical_vp\raw\ES\tick\ES_tick_1_2026-09-21_to_2026-09-30_export_20261001T090000.txt
```

That is an illustrative filename, not an existing input. Its dates describe
calendar coverage; session dates come from actual records. The export stamp
distinguishes repeated downloads and price-adjustment vintages. Record actual
symbol/contract, timezone, session hours and Trade Volume setting alongside
the collection. Never extend an old file by replacing its contents.

Existing `historical_vp/raw/volumeprof_*.txt` files stay unchanged. New names
and the `ES` subfolder require **explicit input paths**: legacy discovery scans
only the top-level raw folder for `volumeprof<number>.txt` and
`volumeprof_YYYY-MM-DD_to_YYYY-MM-DD.txt`. Folder names are conventions;
the partition structure and schemas below are parser requirements.

## 2. Raw tick schema — exact accepted format

This section describes the individual-tick importer used by the execution
pipeline. Imported volume-bar OHLC is handled by the separate
[source-bar builder](source_bar_aggregation.md), which groups a chosen number
of source bars without flattening their OHLC ranges.

Comma-separated UTF-8 text (BOM accepted), with this exact header order:

```csv
Date,Time,Open,High,Low,Close,Up,Down
09/30/2026,09:30:00,6700.00,6700.00,6700.00,6700.00,3,0
09/30/2026,09:30:00,6700.25,6700.25,6700.25,6700.25,0,2
```

| Field | Meaning / constraint |
|---|---|
| `Date` | Calendar date, exactly `MM/DD/YYYY` |
| `Time` | Source-local time, exactly `HH:MM:SS`; specify timezone separately |
| `Open,High,Low,Close` | Equal positive finite price on each **one-tick** row |
| `Up,Down` | Nonnegative integers; prepared volume is their sum |

Export a **1-tick chart with Trade Volume**. If Up/Down contains tick counts
instead of traded contracts, volume-bar sizes will mean the wrong thing;
verify the export setting. Multiple records may have the same timestamp:
preserve their original order and **never deduplicate by timestamp alone**.
Rows must be chronological. Pass the symbol with `--symbol '@ES'` or the actual
contract symbol; adding a Symbol column changes the required header. Other
provider formats need an adapter. A volume-bar or 1,000-tick chart export is
not interchangeable with the one-tick source needed to replay exits.

## 3. Prepared and merged data contract

```text
<tick_root>/
  manifest.json
  parquet/
    session_date=YYYY-MM-DD/
      ticks.parquet
```

Set `tick_root` to the directory containing `manifest.json` and `parquet`,
not a raw file, a single partition or the `parquet` directory itself.
Prepared schema from [the importer](../training_mlp/prepare_historical_vp.py):

| Column | Arrow type | Meaning |
|---|---|---|
| `timestamp` | timestamp[us] | Naive source-local event time; timezone in manifest |
| `calendar_date` | date32 | Original calendar day |
| `session_date` | date32 | ES session label |
| `time_s` | int32 | Seconds since midnight |
| `price` | float64 | Trade price |
| `up`, `down` | int64 | Preserved source values |
| `volume` | int64 | `up + down` |
| `source_file` | string | Original filename |
| `source_row` | int64 | Original row reference |

The backtester requires `timestamp`, `price`, `volume`; other columns preserve
provenance and support other consumers. It checks those columns before creating
an output, then validates chronology, finite ES quarter-point prices,
nonnegative integer volume and session bounds while reading. Equal timestamps
retain stored row order. **`INCOMPLETE.txt` makes the archive unusable.**

An ES session label refers to the day ending normally at 17:00 New York time;
it starts at 18:00 on the preceding calendar day. Configure shortened-session
close overrides where needed. Folder dates do not prove complete sessions.

Prepared manifests record symbol, timezone, session start and source ownership.
The paired-splice manifest instead links source manifests and records
`old_sessions`/`new_sessions`; preserve those lists. They trigger strategy-state
resets and prevent positions crossing the unadjusted price-vintage handoff.
Inspect linked source manifests for symbol/timezone. The adjusted merger
records its measured offset and ownership; its prices are already adjusted
and are **not adjusted again** by the backtester.

## 4. Existing merge modules and compatibility

| Tool | Inputs / behavior | Output consumed by backtester |
|---|---|---|
| [prepare_historical_vp](../training_mlp/prepare_historical_vp.py) | One or more raw tick exports; validates and selects whole-session ownership for overlaps | Its completed output root |
| [splice_historical_vintages](../training_mlp/splice_historical_vintages.py) | Old/new prepared ticks **plus matching old/new bar exports**; explicit cutoff; no adjustment | Its `--output-ticks` root; selected research approach |
| [merge_adjusted_tick_history](../training_mlp/merge_adjusted_tick_history.py) | Two prepared roots; identical overlapping tick sequences except constant price offset; adjusts older-only prices | Its `--output` root; audit alternative, not the selected splice |

All three share the partition format above. They are not interchangeable
policies: preparation chooses an owner, not a union of partial sessions;
the adjusted merger requires overlap to establish the offset; the paired
splice requires bar/tick session coverage to agree. A generic unadjusted
tick-only append service for arbitrary partial deliveries is **not implemented**.

[Integration tests](../tests/test_backtester_merge_integration.py) exercise
raw export → preparation → each actual merge/splice → all three bar types →
strategy → tick exits → statistics. The adjusted merge now reads each Parquet
file without inferring a conflicting session-date column from its folder.

## 5. Commands

Run from GNET using `.venv`. This concrete example uses two **existing** raw
exports and a **new** output directory. It is a large optional preparation job,
not required to use the already prepared archive:

```powershell
.\.venv\Scripts\python.exe -m training_mlp.prepare_historical_vp 'historical_vp/raw/volumeprof_2026-06-15_to_2026-07-15.txt' 'historical_vp/raw/volumeprof_2026-07-15_to_2026-08-14.txt' --symbol '@ES' --timezone America/New_York --output 'historical_vp/prepared_ES_jun_aug_v20261001_example' --workers 2
```

For future deliveries substitute exact new filenames and a fresh destination.
Do not use conflict overrides to bypass an unexplained rollover.
To reproduce the selected splice into new destinations:

```powershell
.\.venv\Scripts\python.exe -m training_mlp.splice_historical_vintages --old-bars 'training_mlp/strategies/MA2CrossLE/inputs/data_30_master.txt' --new-bars 'training_mlp/strategies/MA2CrossLE/inputs/data_30_update_2026-03-23_to_2026-09-21.txt' --old-ticks 'historical_vp/prepared' --new-ticks 'historical_vp/prepared_new_2026_09_21' --cutoff-session 2026-08-14 --output-bars 'training_mlp/strategies/MA2CrossLE/inputs/data_30_spliced_example_20261001.txt' --output-ticks 'historical_vp/merged_ES_spliced_v20261001_example'
```

Inspect the alternative adjusted merger without running it:

```powershell
.\.venv\Scripts\python.exe -m training_mlp.merge_adjusted_tick_history --help
```

After a new output is complete, add an object to the catalog's `datasets` list:

```json
{
  "id": "es_spliced_example_20261001",
  "asset": "ES",
  "symbol": "@ES",
  "timezone": "America/New_York",
  "root": "../historical_vp/merged_ES_spliced_v20261001_example",
  "status": "candidate_snapshot",
  "notes": "Unadjusted paired splice, cutoff 2026-08-14; ownership in manifest."
}
```

Register that example only if its output exists. Inspect registered coverage:

```powershell
.\.venv\Scripts\python.exe -m scripts.backtester_inventory data --asset ES
```

Then choose the root in an experiment JSON's `tick_root`, inclusive session
dates and a fresh output path. Relative paths resolve against the JSON file,
not the shell. The backtester accepts a path, not a catalog ID.

## 6. Tick input supports time, tick-count AND volume bars

Tick records contain **time, price and traded volume**. Keeping that detail
allows all these bar types and preserves the event order for exits:

| Kind | Size unit | Example |
|---|---|---|
| `time` | Seconds | `{"kind":"time","size":30}`; 900 means 15 minutes |
| `tick` | Original trade records | `{"kind":"tick","size":1000}` |
| `volume` | Accumulated traded contracts | `{"kind":"volume","size":1000}` |

Volume bars close when volume reaches/exceeds the threshold, retaining the
whole final trade. At threshold 10, volumes 3 then 8 produce one bar of 11;
the next starts from zero. One trade of 25 produces one bar, not artificial
split events. Zero-volume rows preserve price/order but add no volume.
Incomplete tails are saved but cannot trigger signals. Partial tick/volume
bars do not carry across sessions. Entries occur after the final bar event,
never on that same event, even if the next event shares its timestamp.

Run the [three-type preset example](../config/backtester.multibar.example.json):

```powershell
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.multibar.example.json
```

It builds time-30, tick-1000 and volume-1000 separately over two sessions,
with independent strategy state and tick-level exits. Outputs include
`prepared/bars_volume_1000.parquet`, `signals_volume_1000.parquet` and per-policy
statistics. To search exits, use that `bars` block in a sweep configuration;
each series gets its own exit surface. See [report locations](backtester_reports.md).
