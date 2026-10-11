# Command Center fetch performance regression checks

Run the full browser suite:

```powershell
./scripts/Test-GNETCommandCenterBrowser.ps1
```

Run repeated screen-readiness checks alone:

```powershell
./scripts/Test-GNETCommandCenterBrowser.ps1 -Spec screen-performance.spec.cjs
```

Every test using the shared browser fixture profiles requests automatically.
The profile includes screen path, endpoint, method, duration, failures and broker
operation where identifiable. Job submission-to-result durations are reported
separately so polling/scheduling wait is not confused with HTTP response time.
No request payloads or response bodies are included in the performance output.

`screen-performance.spec.cjs` repeats each readiness scenario three times across
source inventory, source review, export intake, retained primary inventory,
primary/features/training/final/shared-resource modules, dataset chart fetching,
native viewer source lookup and client help/health. Existing behavior tests also
profile actual button fetches, report pagination and generated-report windows.
The warm inventory scenario measures three reloads and requires exactly one
catalog job across initial loading and those reloads.

Budgets in `tests/browser/performance-profile.cjs`:

| Measurement | Maximum |
| --- | ---: |
| Individual successful fabricated API request | 2,000 ms |
| Visible readiness of a fetching screen | 1,500 ms |
| Warm cached inventory readiness | 750 ms |

These are initial regression ceilings, not target user-experience timings.
The screen measurement starts before navigation and ends when the relevant
metadata or result is visible. All samples must pass; averages cannot hide a
slow sample. A guard test verifies that an over-budget request is classified as
a failure and that the tail percentile exposes slow samples.

`.test_artifacts/browser/performance.json` contains per-test request records,
job timings, readiness samples and grouped p50/p95/max HTTP timings. The HTML
report retains `data-fetch-performance` and `screen-readiness` attachments.
`tested-package.json` in that same folder identifies the package under test.
The normal acceptance installer copies these artifacts into release evidence.
Each run overwrites the current browser report; retained release evidence is
separate. Three samples provide a repeatable regression check, not a statistical
guarantee of production latency.

Measure actual installed, read-only HTTP endpoints separately:

```powershell
./scripts/Test-GNETCommandCenterLatency.ps1 -Samples 5 -BudgetMs 2000
```

This calls only local GET endpoints for config, client health, receipt summaries
and inbox metadata. It submits no broker jobs and reads no raw market data.
It writes `.test_artifacts/installed-client-latency.json` and fails on errors,
non-200 responses or any sample above the budget. It includes connection startup
overhead in the first sample. Full protected-worker scheduling, computation and
real installed end-to-end screen latency require separate authorized acceptance;
fabricated browser results do not certify them.
