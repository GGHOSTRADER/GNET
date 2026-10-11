# Engineered bars from imported tick or volume bars

[Human guide](guides/BACKTESTER_GUIDE.md) · [File schemas](backtester_file_contract.md)
· [Implementation](../backtester/source_bars.py)

## The operation requested

Choose the raw source type, its size, and **how many source bars to combine**:

| Raw source | Group count | Engineered output |
|---|---:|---|
| 1-tick bars | 100 | One OHLCV bar per 100 source tick bars |
| 1-volume bars | 100 | One OHLCV bar per 100 source volume bars |
| 10-volume bars | 20 | One OHLCV bar per 20 source volume bars |

`source_size` describes the exported bars. `groups` counts rows, not price
increments or summed traded contracts. Thus 100 source volume bars are grouped
even if their actual total volume differs from 100. Total volume is always the
sum actually observed, never inferred as `source_size * groups`.

This differs from the existing `BarSpec(kind="volume", size=100)` operation,
which reads individual tick events and closes a bar at a **traded-volume
threshold**. Both operations are available and must not share an ambiguous name.

## Files and commands

Use separate raw-source folders under the existing historical archive:

```text
historical_vp/raw/ES/tick/
  ES_tick_1_<first-date>_to_<last-date>_export_<stamp>.txt
historical_vp/raw/ES/volume/
  ES_volume_1_<first-date>_to_<last-date>_export_<stamp>.txt
```

Source size is part of the filename and is also passed explicitly. The builder
does not guess the source kind from a filename. Existing archives are not
renamed. Use a new output directory for each build.

From GNET, these are command templates: replace the angle-bracket fields with
your real filenames/dates before running.

```powershell
# Construct groups of 10 and 1,000 imported one-tick bars in one pass.
.\.venv\Scripts\python.exe -m backtester.source_bars --input 'historical_vp/raw/ES/tick/<export>.txt' --source-kind tick --source-size 1 --groups 10 1000 --output '.artifacts/backtester/bars/ES_tick_<build-stamp>'

# Construct groups of 100 and 1,000 imported one-volume bars in one pass.
.\.venv\Scripts\python.exe -m backtester.source_bars --input 'historical_vp/raw/ES/volume/<export>.txt' --source-kind volume --source-size 1 --groups 100 1000 --output '.artifacts/backtester/bars/ES_volume_<build-stamp>'
```

The default timezone is `America/New_York`; pass `--timezone` if the export
uses another timezone. Session rollover is defined as 18:00 in that configured
source-local timezone, so normalize ES exports to New York time for the intended
ES boundary. Never relabel timestamps without converting them.

## Import schema

UTF-8 comma-separated data with the exact header:

```csv
Date,Time,Open,High,Low,Close,Up,Down
```

Dates are `MM/DD/YYYY`, times `HH:MM:SS`. Prices must be valid ES quarter-point
prices and OHLC must be consistent. Up/Down must be nonnegative integers and
`volume=Up+Down`. Confirm Trade Volume was used in the export. A one-tick row
must have equal OHLC. Volume-source and larger tick-source bars retain their
full OHLC range; they are **not reduced to their closing price**.

Only export completed source bars. Rows must be chronological; tied timestamps
retain original file order. Use one audited price vintage per input file;
this builder does not infer hidden rollovers or deduplicate overlapping exports.

## Aggregation rules

- Open: first source bar's open.
- High/low: maximum high and minimum low across the group.
- Close: last source bar's close.
- Volume, Up and Down: sums of all source bars in the group.
- Count: exactly N source bars for a complete group.
- Session change or end of file: save any remainder with `complete=false`.
- Never join source bars across session boundaries, split a source bar, or
  duplicate it to fill a group.

## Output and provenance

For source kind volume, source size 1, groups 100 and 1,000:

```text
<output>/
  manifest.json
  aggregated_volume_src1_n100.parquet
  aggregated_volume_src1_n1000.parquet
```

Each Parquet row contains OHLC, Up, Down, volume, `source_bar_count`, `session`,
`complete`, `first_source_row`, `last_source_row`, `first_source_close_ns` and
`end_ns`. Source row numbers include the CSV header as row 1. Timestamps are
UTC nanoseconds. `first_source_close_ns` is **not a known bar-opening time**:
the exporter only supplied a timestamp for the source bar's close.

The manifest records source kind/size, group counts, input path/size/mtime,
timezone and output counts. It is not a content-hash audit. Reading is streamed
with bounded output batches; the original input stays unchanged. Existing
output directories are refused. A failed run retains `INCOMPLETE.txt` and must
not be consumed.

## Backtesting boundary

This command is a working **bar-construction module**. Its source-row IDs are
not tick-event IDs. `backtester.run` currently builds its own bars from the
prepared tick archive; it does not yet import these independent OHLC exports
and align them to a separate execution tape. That adapter remains pending.
Do not put these engineered Parquet files under `tick_root` or fabricate
within-bar prices. The existing end-to-end tick workflow and its volume-
threshold bars remain available.
