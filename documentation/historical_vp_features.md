# Historical Canonical Volume-Profile Features

`training_mlp.replay_historical_vp` converts the cleaned session tick Parquets
into an offline feature dataset using the exact mathematics in
`feat_files/canonical_volume_profile.py`.

## Run

From the repository root:

```powershell
python -m training_mlp.replay_historical_vp --workers 4
```

Defaults:

- input: `historical_vp/prepared/parquet`;
- output: `historical_vp/features`;
- symbol: `@ES`;
- tick size: `0.25`;
- initial grid: `600` ticks;
- interval: `30` seconds;
- compression: Zstandard.

The command refuses to overwrite an existing output directory. Move or rename
the previous directory before intentionally generating a replacement dataset.

## Snapshot Semantics

The canonical profile updates on every tick. For each 30-second interval, the
offline adapter tracks ticks during the final second and retains the freshest
one. It commits and writes one result when the following interval begins:

```text
second 29, first tick  → eligible preview
second 29, later ticks → replace with fresher preview
next interval          → commit freshest state once and write one row
```

The implementation skips materializing redundant intermediate previews because
they do not mutate canonical state; calculating only the freshest state is
mathematically equivalent. Committing once preserves interval-scale semantics
for recent delta, Value Area expansion, POC migration, and five-snapshot POC
velocity.

## Output

Each session produces:

```text
historical_vp/features/parquet/
└── session_date=YYYY-MM-DD/
    └── vp_features.parquet
```

Every row contains interval identity and provenance, core POC/Value Area fields,
and all 32 names from `VOLUME_PROFILE_FEATURE_NAMES`. The output includes 51
columns total. `manifest.json` records settings and aggregate counts;
`manifest_partitions.csv` records input rows, feature rows, coverage, output
bytes, runtime, and throughput per session.

## Completed Dataset (2026-08-19)

- 110 session partitions;
- 115,879,384 input ticks;
- 184,120 unique interval rows;
- 35,361,522 compressed Parquet bytes;
- coverage from `2026-03-15 18:00:29` through `2026-08-14 16:59:59`;
- all 32 canonical features finite;
- no duplicate `session_date + calendar_date + interval_start_s` keys;
- four-worker wall time: 207.218 seconds.

## Correlation and Redundancy Report

After feature replay completes, calculate pooled Pearson and Spearman matrices
across every historical feature snapshot:

```powershell
python -m training_mlp.analyze_vp_correlations
```

The default report directory is `historical_vp/features/correlation/`. It
contains `pearson_matrix.csv`, `spearman_matrix.csv`,
`correlation_pairs.csv`, `high_correlation_pairs.csv`,
`feature_diagnostics.csv`, and `summary.json`. The default thresholds classify
absolute correlations from 0.90 through 0.95 as high and correlations of 0.95
or greater as severe. These classifications identify feature-selection
candidates; they do not remove features automatically.

## Live-Parity Follow-up

Offline temporal state now commits once per interval. The live adapter still
calls a committing snapshot on every qualifying final-second tick. Before a
VP-dependent model is trained or deployed, update live publication to emit
fresh previews throughout the final second but commit temporal history only
once. The current MA model remains correctly isolated on its trained 13-feature
contract and does not consume this dataset.
