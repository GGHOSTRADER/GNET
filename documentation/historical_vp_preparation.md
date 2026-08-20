# Historical Volume-Profile Preparation

The raw TradeStation exports remain unchanged under the dedicated raw-data
directory and are ignored by Git:

```text
historical_vp/raw/volumeprof1.txt
historical_vp/raw/volumeprof2.txt
historical_vp/raw/volumeprof3.txt
historical_vp/raw/volumeprof4.txt
historical_vp/raw/volumeprof5.txt
```

From the repository root, prepare every available
`historical_vp/raw/volumeprof<number>.txt` input with:

```powershell
python -m training_mlp.prepare_historical_vp --symbol "@ES"
```

The normal command stages independent exports with two worker processes.
Override this with `--workers 1` for minimum resource usage or `--workers 4`
when benchmarking a fast SSD and multi-core CPU.

Replace `@ES` if the chart export came from a specific contract. The text
export does not contain the symbol, so the command requires it explicitly.

The command performs one streaming pass over each large file. It validates the
header, chronological order, one-tick OHLC equality, prices, and volume. It
assigns ticks at or after 18:00 to the following ES trading-session date and
writes Zstandard-compressed Parquet partitions under:

```text
historical_vp/prepared/parquet/session_date=YYYY-MM-DD/ticks.parquet
```

Overlapping sessions with identical row counts and SHA-256 content hashes are
kept from one source only. If overlapping session content differs, preparation
stops by default, writes `overlap_conflicts.json`, and preserves the compressed
staging partitions. After manual inspection, finalize the copy with the most
rows without rereading the multi-gigabyte text exports:

```powershell
python -m training_mlp.prepare_historical_vp `
    --resume `
    --allow-conflicting-overlaps
```

The module never overwrites a completed output directory. `--resume` works only
with its preserved `.staging` directory and `staging_manifest.json`.

Successful output includes:

- `manifest.json`: full file coverage, settings, hashes, and overlap candidates.
- `manifest_partitions.csv`: one compact row per selected trading session,
  including its compressed Parquet byte size.
- `parquet/`: the deduplicated session partitions used by historical VP replay.

The next stage is now implemented. Run the prepared partitions through the
canonical VP engine with:

```powershell
python -m training_mlp.replay_historical_vp --workers 4
```

See [historical_vp_features.md](historical_vp_features.md) for snapshot
semantics and generated feature outputs.
