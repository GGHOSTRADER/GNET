# GNET pending work — October 11, 2026

This is the continuation checklist for the research Command Center. It combines
the recorded acceptance results and the installed V43 browsing verification.
Unchecked items mean missing implementation or missing acceptance evidence;
the distinction is stated for each item. Historical status documents can describe
older releases and should not override the current installed identities.

## Current baseline

- Broker: `guarded-v43-native-browse-fix` — installed, activated, deployment audit passed.
- Client: `gnet-client-v72-gui-acceptance-fixes-r2` — installed and running on port 9040; 115-test browser release gate passed.
- TS bars + recorded primary positions → labels → features → diagnostics → XGBoost → scoring → native replay → separate synthetic final evaluation has passed installed synthetic execution.
- Final evaluation's second-use rejection has passed on the synthetic acceptance experiment.
- Browse bars now returns all 120 bars of the synthetic viewer fixture; selecting a trade retains focused viewing.
- Eight browsing worker regressions passed. The existing 100 browser scenarios passed; the subsequently expanded 10-test chart suite passed separately.
- Real TS development research has run. A fresh untouched real final evaluation is still pending.
- Full isolation acceptance remains incomplete. Native researcher-password acceptance was explicitly deferred.

### October 11 continuation — GUI acceptance fixes installed

The protected broker identity remains unchanged. GUI acceptance found two client
defects: Apply filters sent fields/sort values rejected by the V43 catalog
schema, and legacy internal-primary report SVG styling obscured the shared price
chart. Both are corrected in the verified, now installed client
`gnet-client-v72-gui-acceptance-fixes-r2`, built from
`.artifacts/GNET-GUIAcceptance-Client-v72-r2`. The user explicitly approved
installation/restart. Installed Apply filters now returns “Inventories refreshed.
Source contents remain private.” Installation evidence is retained under
`.test_artifacts/release-gates/gnet-client-v72-gui-acceptance-fixes-r2-20261011T055929996Z/`.

Actual V43 chart templates now have desktop/narrow screenshot checks, transparent
overlay assertions and fabricated 1,200-bar pagination coverage. The suite has
115 scenarios. The new ordinary-client installer enforces the full suite before
stopping/installing the client; its non-mutating gate rejected V70 with eight
failures and left installation unchanged. Historical protected deployment wrappers
still need the same release gate.

Full installed GUI acceptance remains pending: the existing fabricated development
export passes timestamp/coverage/session checks but lacks captured weekly session
hours, so the current review correctly keeps approval closed. Prepare a fresh
complete fabricated export and obtain exact local reviewer activation before
continuing registration through final testing. Do not reuse a consumed final claim.

See [continuation evidence](GNET_GUI_ACCEPTANCE_CONTINUATION_2026-10-11.md).

### Exact disk locations

Repository: `C:\Users\g_med\python_new\GNET`

Current protected release candidate code, used to build the installed broker:
`C:\Users\g_med\python_new\GNET\.artifacts\GNET-Command-Center-v43-NativeBrowseFix-r1\guarded-v43-native-browse-fix`

Current installed client code:
`C:\Users\g_med\python_new\GNET\.artifacts\client-delivery-installed\releases\gnet-client-v72-gui-acceptance-fixes-r2`

Installed configuration:
`C:\Users\g_med\python_new\GNET\.artifacts\client-delivery-installed\client-config.json`

Launcher:
`C:\Users\g_med\python_new\GNET\.artifacts\client-delivery-installed\Open-GNETResearch.ps1`

Configured exchange, published results, and export inbox:
`C:\GNET_Exchange`, `C:\GNET_Results`, `C:\GNET_Import\incoming`.
These are configured locations, not permission to inspect private data.

In the entries below, `Broker code` means the exact protected candidate directory
above, followed by `\gnet_broker\`. All other paths are written in full.

## 1. Complete installed manual GUI acceptance

- [ ] Run the full supported TS bars + primary positions workflow through browser controls on the current installed release, recording each request, job, visible outcome and report.

**Type:** acceptance work. Installed synthetic computation and fabricated browser
tests have passed separately; a complete current-release human GUI run is a
distinct acceptance record.

**Scope:** select an export, run automatic validation, approve its exact review,
register/prepare the source, inspect bars and trades, generate primary targets,
build canonical features, run diagnostics, pass/reject features, train XGBoost,
score, replay and inspect statistics. Use a separate fabricated final archive
for reservation, freeze and one-time evaluation.

**Done when:** each browser action produces the intended visible outcome and
matches the correct source/model parents; errors and publication delays are
visible and recoverable. Save a single receipt linking all jobs and screenshots.

**Locations:**
- Browser tests: `C:\Users\g_med\python_new\GNET\tests\browser`
- Workflow test: `C:\Users\g_med\python_new\GNET\tests\browser\workflow.spec.cjs`
- Runner: `C:\Users\g_med\python_new\GNET\scripts\Test-GNETCommandCenterBrowser.ps1`
- Test guide: `C:\Users\g_med\python_new\GNET\documentation\guides\GNET_COMMAND_CENTER_BROWSER_TESTS.md`
- Prior installed evidence: `C:\Users\g_med\python_new\GNET\.artifacts\v63-installed-synthetic-workflow-full.json`
- Prior final evidence: `C:\Users\g_med\python_new\GNET\documentation\reports\GNET_BROWSER_REGRESSION_ACCEPTANCE_2026-10-10.md`

## 2. Extend report and chart acceptance

- [x] Add visual regression coverage for actual dataset, native-primary and internal-primary price-report templates with fabricated data (1440/390px).
- [ ] Extend generated-template visual coverage to diagnostics, training, importance, replay, statistics and final reports.
- [ ] Verify installed browsing on a fabricated source longer than 500 bars: next/previous windows, final partial window, zoom, scrollbar, line/candle mode and outcome markers.
- [ ] Exercise every chart entry point: dataset, imported native trades and internal primary reports. Verify sub-hour cash reference markers and intraday/daily/weekly/monthly time-axis formatting.

**Type:** additional tests and installed acceptance. The 120-bar native browsing
bug is fixed; these items cover broader populations and report surfaces.

**Done when:** source windows contain the expected bars without gaps or duplicates,
navigation does not scroll the whole document instead of the chart, and labels
remain readable at desktop and narrow widths. Save reviewed screenshots.

**Locations:**
- Worker regressions: `C:\Users\g_med\python_new\GNET\tests\test_native_browse_window.py`
- Browser chart tests: `C:\Users\g_med\python_new\GNET\tests\browser\charts.spec.cjs`
- Broker code: `ts_primary_view.py`, `ts_primary_view.html`, `dataset_chart.py`, `dataset_chart_report.html`, `scrolling_bar_viewer.js`
- Completed fix evidence: `C:\Users\g_med\python_new\GNET\documentation\reports\GNET_NATIVE_BROWSE_FIX_2026-10-11.md`
- Installed screenshot: `C:\Users\g_med\python_new\GNET\.test_artifacts\native-browse-installed.png`

## 3. Make browser tests a release gate

- [x] Enforce the full browser suite in the new ordinary-client acceptance installer; a failing run stops before client shutdown/installation and successful evidence is retained.
- [ ] Integrate that gate into historical/protected package and deployment wrappers so every delivery path enforces it.
- [ ] Keep test names/selectors current as UI sections change; update screenshot baselines only after reviewing intentional changes.

**Type:** release tooling implementation. The suite exists and runs, but its guide
states that deployment scripts do not yet enforce it automatically.

**Done when:** a deliberately failing browser regression blocks the release step,
and a passing run records the tested package identity and retained report.

**Locations:**
- `C:\Users\g_med\python_new\GNET\scripts\Test-GNETCommandCenterBrowser.ps1`
- `C:\Users\g_med\python_new\GNET\tests\browser\playwright.config.cjs`
- `C:\Users\g_med\python_new\GNET\.test_artifacts\browser`
- Current deployment wrapper: `C:\Users\g_med\python_new\GNET\.artifacts\GNET-Command-Center-v43-NativeBrowseFix-r1\Deploy-ReviewedCommandCenter.ps1`

## 4. Finish isolation and protected recovery acceptance

- [ ] Test actual installed publication crash boundaries and stale-worker ownership fencing under the broker identity.
- [ ] Reconcile earlier V38 identity/access/integrity/recovery evidence against the current V43 installed release. Reuse applicable evidence with explicit scope; rerun checks whose code or boundary changed.
- [ ] Test native researcher-password Trash approval when the user elects to resume it: valid local identity succeeds, invalid/wrong identity fails, recoverable restore works.
- [ ] Produce the internal aggregate isolation status only after its required checklist is satisfied.

**Type:** acceptance work; native password testing remains deferred. The internal
`isolation_certified` flag is a consolidated test result, not an external certificate.

**Already passed historically:** both identity access probes, ancestor mutation
denial, invalid installed task pin rejection with exact restoration, active
cancellation/recovery, and idle reboot followed by scheduled execution.

**Done when:** required current-scope receipts show safe failure and recovery,
no usable partial results, and correct Windows identity restrictions.

**Locations:**
- Checklist: `C:\Users\g_med\python_new\GNET\documentation\guides\GNET_V38_ISOLATION_ACCEPTANCE_CHECKLIST.md`
- Remaining-gates record: `C:\Users\g_med\python_new\GNET\documentation\reports\GNET_V38_ISOLATION_REMAINING_GATES_2026-10-09.md`
- Fault fixtures: `C:\Users\g_med\python_new\GNET\.artifacts\test_v38_publication_crash_windows.py`
- Existing receipts: `C:\Users\g_med\python_new\GNET\.artifacts\v38-installed-task-rejection.json`, `v38-installed-recovery.json`, `v38-active-cancellation.json`, `v38-reboot-acceptance.json` in that same directory.
- Broker code: `publication.py`, `queue.py`, `worker.py`, `windows_source_auth.py`, `source_management.py`

## 5. Complete real-data final testing and platform evidence

- [ ] Obtain a separate untouched, nonoverlapping real final archive; approve it, reserve it, freeze the selected model/settings and evaluate once.
- [ ] Record actual TradeStation fill/cost settings and export assumptions: commissions, slippage, Bar Magnifier, fill timing, continuous-contract adjustment/roll basis and chart sessions.
- [ ] Keep recorded-position filtering clearly described in reports. It does not recreate the TS engine's changed position occupancy or candidates absent from the export.

**Type:** research/platform acceptance. Real development results exist; synthetic
final acceptance also exists. Neither establishes predictive performance on a
fresh real holdout. Previously exposed development outcomes cannot be renamed
an untouched final test.

**Done when:** the final report references the frozen model and untouched source,
includes the selected primary/ML/buy-and-hold comparisons and drawdowns, and
records the actual execution assumptions and one-use evaluation receipt.

**Locations:**
- Real development evidence: `C:\Users\g_med\python_new\GNET\documentation\reports\GNET_REAL_TS_DEVELOPMENT_ACCEPTANCE_2026-10-09.md`
- Real comparison evidence: `C:\Users\g_med\python_new\GNET\documentation\reports\GNET_V38_REAL_TS_MODEL_COMPARISON_2026-10-09.md`
- Broker code: `final_evaluation.py`, `experiment_ledger.py`, `ts_ml_replay.py`, `comparison_reports.py`, `comparison_curves.py`, `statistics.py`

## 6. Refresh the customer delivery package

- [ ] Build a new reviewed standalone customer installation package containing the chosen current broker/client fixes, matching custody preparation, GUI guide and agent guide.
- [ ] Test installation on a prepared customer machine: reuse/create the intended broker account, correct task identity/ACLs, fixed inbox, launch, MCP identity and synthetic workflow.
- [ ] Provide one unambiguous entry point, external ZIP/manifest hashes and exact ordinary-user versus Administrator commands. Verify scripts also launch under the customer's execution-policy conditions.

**Type:** packaging and customer acceptance. The October 9 r2 installation and
r4 custody update are historical deliveries; do not assume they contain V43/V70.

**Done when:** a fresh-machine/prepared-machine receipt identifies every installed
component, and the included agent can guide the GUI workflow using the same
documented controls as the human.

**Locations:**
- Historical bundle: `C:\Users\g_med\python_new\GNET\.artifacts\GNET-Client-Installation-2026-10-09-r2.zip`
- Historical custody update: `C:\Users\g_med\python_new\GNET\.artifacts\GNET-Custody-Boundary-Update-2026-10-09-r4.zip`
- Customer status: `C:\Users\g_med\python_new\GNET\documentation\guides\GNET_CUSTOMER_INSTALLATION_STATUS.md`
- Deployment tooling: `C:\Users\g_med\python_new\GNET\automation\guarded_research`
- Current candidate package: `C:\Users\g_med\python_new\GNET\.artifacts\GNET-Command-Center-v43-NativeBrowseFix-r1`

## 7. Complete the other research paths and strategy extensions

- [ ] Audit and accept the two internal-primary paths separately: internal bars constructed from one-tick data, and imported TS bars without imported primary trades.
- [ ] Exercise strategy creation/save, parameter capture, internal backtest viewing, labels, feature joins and training for both paths; fix specific failures discovered by those runs.
- [ ] Implement separately defined execution support for reversal, pyramiding, partial exits/fills or concurrent positions when required. The simple single-position generic scaffold does not prove these execution models.

**Type:** broader product acceptance and planned execution extensions. Do not
classify the internal paths as absent merely because their complete installed
acceptance is missing. Generic custom inputs/families and EL scaffolds already
have implementation and synthetic evidence.

**Done when:** each supported path has its own complete installed receipt; new
execution models have explicit contracts, validation, replay and tests.

**Locations:**
- Internal engine: `C:\Users\g_med\python_new\GNET\backtester`
- Runbook: `C:\Users\g_med\python_new\GNET\documentation\guides\BACKTESTER_AGENT_GUIDE.md`
- EL agent guide: `C:\Users\g_med\python_new\GNET\documentation\guides\GNET_EL_PRIMARY_STRATEGY_AGENT_GUIDE.md`
- Custom strategy guide: `C:\Users\g_med\python_new\GNET\documentation\guides\GNET_CUSTOM_PRIMARY_STRATEGY_AGENT_GUIDE.md`
- EL examples: `C:\Users\g_med\python_new\GNET\EL_files\GNET_Primary_Generic_MA_Example.els`, `GNET_Primary_ThreeDown_Example.els` in that same directory.
- Broker code: `builders.py`, `execution.py`, `primary_labels.py`, `ts_primary_trades.py`, `ts_primary_source.py`

## 8. Broaden model/validation acceptance

- [ ] Run installed synthetic acceptance for logistic regression, random forest and MLP, including their importance reports and supported RFE behavior. Browser payload tests alone do not prove their worker results.
- [ ] Use deliberately overlapping synthetic label intervals to verify purge and embargo remove the expected samples; retain fold-level counts and causal preprocessing/selection evidence.
- [ ] Decide whether CPCV belongs in the guarded Command Center delivery; if included, connect and accept it explicitly. The recorded TS development run used chronological walk-forward CV and no CPCV.

**Type:** additional acceptance; CPCV UI/product integration is a separate scope
decision. Do not present a zero-removal synthetic fixture as proof of purge removal.

**Done when:** each model produces valid reports and lineage, and overlap fixtures
show the expected exclusions without training on validation/final information.

**Locations:**
- Broker code: `ml_jobs.py`, `secondary_jobs.py`, `model_importance_report.py`, `training_charts.py`, `feature_research.py`
- Browser model tests: `C:\Users\g_med\python_new\GNET\tests\browser\pipeline.spec.cjs`
- Existing independent CPCV research code: `C:\Users\g_med\python_new\GNET\training_mlp\cpcv_hyperparameter_search.py`
- Its tests: `C:\Users\g_med\python_new\GNET\tests\test_cpcv_hyperparameter_search.py`

## 9. Model promotion from research to live inference

- [ ] Audit the existing registry/router contract and design the supported promotion path from a frozen research model to live inference.
- [ ] Implement validated model/preprocessing/feature-order export, supported model-family loading, exact strategy/candidate mapping, rollback and offline parity tests before enabling promotion.
- [ ] Expose promotion in the Command Center only after that path has explicit acceptance and human authorization.

**Type:** planned integration. Existing live inference and its MLP registry are
present; an accepted automatic Command Center-to-live promotion path has not
been demonstrated in this continuation.

**Done when:** identical offline/live input features produce matching scores,
the exact candidate receives its decision, and a failed promotion cannot replace
the active model. Live deployment needs its own authorized acceptance.

**Locations:**
- `C:\Users\g_med\python_new\GNET\inference\model_registry.py`
- `C:\Users\g_med\python_new\GNET\inference\strategy_router.py`
- `C:\Users\g_med\python_new\GNET\model_registry`
- `C:\Users\g_med\python_new\GNET\feat_files\transformer_features.py`

## Recommended order

1. Finish current installed GUI/report acceptance and add regressions for any failures.
2. Make browser tests a release gate and refresh the customer package.
3. Complete remaining isolation/recovery checks; native password testing stays deferred until resumed.
4. Run fresh real final testing when an untouched archive is available.
5. Accept the other internal-primary paths and additional model families.
6. Add complex execution models and research-to-live promotion as separate implementations.

Keep this checklist updated with dated receipts. Do not rerun a consumed final
evaluation or claim all releases are accepted from an older release's evidence.
