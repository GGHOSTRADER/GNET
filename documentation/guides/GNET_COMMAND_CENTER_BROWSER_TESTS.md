# Command Center browser test suite

## Run

From the GNET repository, in ordinary PowerShell:

```powershell
& '.\scripts\Test-GNETCommandCenterBrowser.ps1'
```

No Administrator credentials or researcher password is needed. The runner uses
the installed client's package by default. A release candidate can be tested
before installation:

```powershell
& '.\scripts\Test-GNETCommandCenterBrowser.ps1' -PackageRoot 'C:\path\to\client-package'
```

The current development machine has bundled Node and Playwright. On another
machine, install Node, then run `npm install` inside `tests/browser`. The pinned
dependency is Playwright 1.62.1. Tests use installed Edge by default. For a
Playwright Chromium installation, run `npx playwright install chromium`, then
set `$env:GNET_BROWSER_CHANNEL='chromium'`.

## What is tested

| Area | Assertions |
| --- | --- |
| Source review | Automatic findings render; source selection required; authorization required; submitted processes and evidence match controls; release pin refreshes after update |
| Asynchronous buttons | Progress appears; duplicates prevented; worker failure appears beside approval; retry works |
| Registration | Closed gates before activation; exact source/policy submitted; pending admission stays blocked; preparation unlocks the right next module |
| Intake | Exporter preparation, primary exporter preparation, transfer/retry payloads, synthetic custody outcome, matched-source preparation, stored/staged content badges, source-type filters, unknown-type handling |
| Bar construction | Seconds/minutes conversion, tick and volume units, source/date boundaries, failed build recovery, data tabs |
| Internal primary | Entry parameters/session reset, invalid crossover rejection, baseline exit policy, bounded grid search, first-touch barrier settings |
| Native labels | Exact reviewed native source parent, standalone primary targets, causal feature/target dataset join |
| Features | Compatibility restrictions, selected pool persistence, empty-pool training rejection, diagnostic parent/columns, pass/reject review prerequisites |
| Models | MLP/XGBoost/LR/RF payloads and settings, fold-local RFE, feature pool, shared purge/embargo controls, report link, failure recovery |
| Scoring/replay | Walk-forward/future modes, model/dataset parent matching, threshold, native recorded-fill replay, unavailable outputs |
| Final evaluation | Exact reservation interval, freeze identities/hash, capability gates, one-use attempt, failure consumes attempt, saved-result statistics |
| Trash | Metadata inventory, restore hash and local confirmation handoff, missing authentication and final-reservation blocking; no password collected |
| Browser workflow | Native targets → causal dataset → diagnostics → feature pass → XGBoost → scores → native replay → reserve/freeze → one-time final |
| Unified source inventory | One row for a received/registered export, exact action links, approval/content filters, current-route sorting, asset/type/import-date filtering, hash navigation without duplicate controls, responsive screenshot comparisons |
| Legacy primary bookmarks | Collapsed/numbered rows and filters on the retained `/imported-primaries/` route; compatibility coverage only |
| Shared chart adapter | Dataset/native/internal DOM contracts; 500-bar view, zoom, slider, reset, mode switch, outcome lane, cash reference markers, consecutive native window request |
| Dataset chart form | Selected date range, mode, point limit and pagination offset sent to the API; worker failure displayed |
| Rendering | Review screenshot baselines at 1440/768/390px; five module/resource views check visible controls at those widths; browser exceptions fail the test |

These are browser integration tests with fabricated API responses. They test
real packaged review/inventory/form HTML and JS. Shared chart tests provide
fabricated report DOM/data contracts to the actual packaged chart library and
adapter. `generated-reports.spec.cjs` additionally exercises the actual V43
dataset, native-primary and internal-primary report templates with fabricated
observations. The runner builds these fixtures using
`scripts/build_generated_chart_fixtures.py`; the repository Python environment
and pinned V43 candidate package must be present. It compares reviewed chart
screenshots at 1440/390px, asserts transparent overlays and navigates source
windows of 500, 500 and 200 bars. These are local renderer/template tests,
not installed custody or worker acceptance. They do not certify every report
template or protected broker
calculation. The harness blocks all external requests and fails unhandled APIs.
It never sends work to the actual broker or opens real market exports.

## Evidence and failure handling

Fetch timings and repeated screen-readiness regression budgets now run with the
suite. See [performance checks](GNET_COMMAND_CENTER_PERFORMANCE_TESTS.md) for
per-request, job and readiness timing reports, thresholds and the separate
installed read-only HTTP probe.

Results are in `.test_artifacts/browser/`:

- `report/index.html`: searchable Playwright report, including layout screenshots.
- `junit.xml`: machine-readable results for a release gate or CI.
- `results/`: failure screenshots, error context and replayable traces.

The command exits unsuccessfully if a check fails. Retries are disabled so flakes
remain visible. Do not accept a release just because screenshot generation passed:
run once without `-UpdateSnapshots` to verify the baseline comparisons.

For an intentional visual change, inspect screenshots and use
`-UpdateSnapshots` explicitly. Baselines are stored alongside the specs. Their
browser/platform suffix means Edge-on-Windows baselines should be reviewed again
when changing the browser or OS; never silently update them to hide a regression.

## Release acceptance layers

1. Pure/component tests: schemas, calendars, labels, feature calculations and models.
2. This browser suite: browser controls, requests, transitions and rendering.
3. Protected installed integration: scheduled tasks, contract rejection, worker
   publication and actual synthetic calculations under the broker identity.
4. Installed synthetic end-to-end acceptance: custody → human approval → source
   registration → labels → features → diagnostics → XGBoost → scores → replay →
   separate frozen final evaluation.
5. Human platform acceptance: TradeStation compile/export and native Windows
   credential prompts.

The suite is a required browser check before handing off a changed client.
`scripts/Install-GNETAcceptedBrowserClient.ps1` now enforces the full suite,
without snapshot updates, before stopping or installing the ordinary-user client.
It checks manifest/file hashes before and after testing and retains the complete
report under `.test_artifacts/release-gates/`. Historical installers and protected
broker deployment wrappers still need equivalent integration.
The workflow test covers the browser with a stateful synthetic API;
it does not execute protected worker computations. Native Windows password UI,
other generated report-template visual comparisons, interrupted installed workers and
actual installed broker end-to-end acceptance remain separate. Module rendering
checks are not screenshot baselines for every possible report or control state.

## October 10 regression findings

The expanded 83-scenario run against installed client v62 found five failures
(78 passed): three non-MLP model payloads incorrectly submitted MLP, native target
controls stayed disabled after initial progress loading, and the combined native
workflow stopped at that same target gate. These are release failures, not skipped
tests. A fresh v63 candidate fixes live model-selector reads and refreshes primary
target readiness when metadata loading finishes. It must pass the unchanged
regressions before client installation; the installed v62 package is preserved.

The full candidate run passed **83/83 in 1.8 minutes**, with retries disabled.
Tested client: `gnet-client-v63-browser-regressions-r2`; manifest SHA-256:
`abffdc1af1f473ff7faa8d2bf2d43df4d7d339c90a9ad2d451dd4fa9aba5ff2f`.
The candidate is verified; browser tests do not install it. V63-r2 was subsequently
installed through `scripts/Install-GNETBrowserRegressionClient.ps1`. Actual
scheduled broker development acceptance passed; see the October 10 acceptance
report for counts. Fresh synthetic final reservation, freeze, evaluation,
saved-result statistics and second-attempt rejection subsequently passed through
the installed scheduled broker. Full account isolation and real-platform
acceptance remain separate.

```powershell
& '.\scripts\Test-GNETCommandCenterBrowser.ps1' -PackageRoot 'C:\Users\g_med\python_new\GNET\.artifacts\GNET-BrowserRegression-Client-v63-r2\gnet-client-v63-browser-regressions-r2'
```

Run a focused group while repairing failures:

```powershell
& '.\scripts\Test-GNETCommandCenterBrowser.ps1' -Spec pipeline.spec.cjs,workflow.spec.cjs
```

The `-Spec` option limits execution; a successful focused run is not evidence that
the full suite passed. The final release check runs without `-Spec`.

## Agent instructions

- Read this guide before changing Command Center controls.
- Add a user-behavior regression for every reported button or rendering defect.
- Assert the outgoing payload and the visible result; a click alone is not a test.
- Keep data fabricated and explicit. Do not point this harness at production APIs.
- Preserve local human approval boundaries. Never collect passwords in test code.
- Record the tested package/release with results. Run against the fresh candidate,
  rather than an older installed package, before deployment.
- Exercise the current main UI route for workflow coverage. Legacy pages can pass
  even when the active navigation is broken. Check controls themselves, not only
  their wrappers, after metadata loading and in-page navigation.
- Review screenshots before updating baselines; keep failure traces.
