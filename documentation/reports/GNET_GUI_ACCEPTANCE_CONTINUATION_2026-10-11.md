# GUI acceptance continuation — October 11, 2026

Scope: fabricated source metadata, actual V43 chart report templates and
ordinary-client release tooling. No private market data, model promotion,
credential testing or protected deployment was performed.

## Tested package and installed baseline

Installed broker: `guarded-v43-native-browse-fix`.
Installed client: `gnet-client-v72-gui-acceptance-fixes-r2`.

Verified client candidate: `gnet-client-v72-gui-acceptance-fixes-r2`.
Directory: `.artifacts/GNET-GUIAcceptance-Client-v72-r2/gnet-client-v72-gui-acceptance-fixes-r2`.
Manifest SHA-256:
`e24945dca82725ce99507284edaa45864131437fcac3d5166f9b843e08968ad9`.
Automatic approval review initially rejected `-Apply` because the request to work
on pending items did not explicitly authorize client installation. GateOnly
acceptance was completed first. The user subsequently explicitly approved
installation and restart, and the exact tested client is now installed.

The approved installer reran all **115 browser tests successfully**, checked
package hashes, installed the ordinary client and launched it on port 9040.
Health confirms V72 client, unchanged V43 broker and all client assets passing.
The prior V70 release is retained. Installed GUI Apply filters → All · paged
now finishes with “Inventories refreshed. Source contents remain private.”

Installation receipt and its full browser report:
`.test_artifacts/release-gates/gnet-client-v72-gui-acceptance-fixes-r2-20261011T055929996Z/installation-receipt.json`.
Installed screenshot: `.test_artifacts/v72-installed-filter-success.png`.

## Findings and fixes

1. Installed Source inventory → Apply filters displayed “Unknown fields are
   forbidden.” The V70 client sent `assets` and `source_types`, absent from the
   pinned V43 payload schema, plus local sort names absent from its closed enum.
   The candidate sends supported catalog fields and maps UI sorts. Asset/type/import
   filtering remains explicitly limited to loaded public metadata. Oldest data
   coverage is sorted locally; the catalog has no global coverage-oldest operation.
   Six regressions check the actual exported V43 schema, request and visible outcome.
   All six fail against V70 and pass against the corrected candidate.
2. The actual internal-primary `viewer.html` template styles all SVGs white.
   This also painted the new chart overlay white and hid the price canvas.
   The shared adapter now scopes transparent SVG backgrounds/borders to its chart
   shell. Original report diagrams and styles are retained. Actual-template tests
   assert transparent SVGs, chart visibility and outcome duration markers.

## Browser and renderer evidence

The full V72 suite passed 115/115 without updating snapshots. The eight existing
native worker regressions passed. Full final gate output is retained under
`.test_artifacts/release-gates/gnet-client-v72-gui-acceptance-fixes-r2-20261011T053832652Z/`.
The final GateOnly receipt binds that tested package to the manifest above,
records browser_gate_passed=true and installed=false. The earlier passing run is retained in
`.test_artifacts/gui-v72-full-115/`.

`scripts/build_generated_chart_fixtures.py` creates 1,200 observations and renders
the actual native/internal report functions and dataset HTML template, using
the V43 pagination calculations. It never discovers or opens an external dataset.
`.test_artifacts/generated-chart-fixtures/receipt.json` records report hashes,
the broker manifest hash and the local-only scope.

`tests/browser/generated-reports.spec.cjs` exercises those generated reports with
the same asset injection as the installed view server. It checks desktop/narrow
chart screenshots, source windows of 500/500/200 and navigation back, payload
identity, last-page disabling, zoom, scrollbar, reset and line/candle switching.
Full-page screenshots are attached to the Playwright report. The six chart
baselines were visually reviewed; the corrected internal-primary screenshots
show the formerly obscured candles and duration lane.

This is report-template/browser evidence. It does not certify installed custody,
1,200-bar broker execution or all feature/model/statistics report templates.
Daily/weekly/monthly axis acceptance and complete installed chart acceptance remain.

## Enforced ordinary-client release gate

`scripts/Install-GNETAcceptedBrowserClient.ps1` validates the supplied package
manifest/files and V43 broker pin. `-Apply` runs the full browser suite without
snapshot updates, rechecks package hashes, retains evidence and only then stops
the matching ordinary client and installs the candidate. `-GateOnly` runs and
retains acceptance without any client stop or installation. A failure throws
before the installation block. Historical and protected deployment wrappers
remain outside this new gate.

The non-mutating V70 negative run produced **8 failed / 107 passed**, proving the
new filter/actual-template checks reject its defects. Configuration remained V70/V43.
Evidence: `.test_artifacts/v70-release-gate-rejected/`.

An earlier proposed negative test using `-Apply` was rejected by automatic approval
review because a malfunctioning gate could reinstall the known-failing V70 release.
It was not executed; `-GateOnly` was added and used instead.

## Installed GUI review and remaining workflow gate

Existing fabricated export: `acceptance-client-delivery-oct09-fresh-r1`.

- Initial automatic page load submitted job
  `job-20261011T052801Z-62139ff8103a4d94b4007777f27c5584` without explicit fabricated
  scope and failed publication with `unsafe_output`. No usable output was published.
- Selecting Fabricated source in Technical references and clicking Run automatic
  validation submitted `job-20261011T053108Z-5816c5e635d543bbbbb54c8debac011f`.
  It returned a usable template: 300 rows, one scheduled/observed session,
  zero missing/incomplete sessions and off-grid bars. Timestamp, coverage and
  session checks passed.
- Captured evidence reported `chart_snapshot_incomplete`: this older fixture has
  no captured weekly session hours. Review approval stayed closed. Passing row
  checks do not replace missing captured evidence or local reviewer activation.

Bounded typed reports:
`.test_artifacts/gui-acceptance-validation-oct11.json`.
Screenshot: `.test_artifacts/gui-review-missing-session-hours.png`.

Next: prepare a fresh complete fabricated development export plus a separate fresh final archive,
activate exact reviewed proposals locally, and record the full GUI workflow
receipt. Do not claim full installed GUI acceptance from this template/browser run.
