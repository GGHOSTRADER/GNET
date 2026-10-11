# Command Center browser regression acceptance — October 10

## Results

- Installed v62: 78 passed, 5 failed across 83 scenarios.
- Fresh verified v63-r2 candidate: 83 passed, 0 failed, retries disabled, 1.8 minutes.
- Browser: headless Microsoft Edge on Windows.
- Data/API: fabricated, stateful local responses; no installed broker jobs submitted.
- Client manifest: `abffdc1af1f473ff7faa8d2bf2d43df4d7d339c90a9ad2d451dd4fa9aba5ff2f`.
- V63-r2 is now installed; running HTTP health confirms V63 client / V42 broker and all client assets. Browser acceptance is separate from worker and platform acceptance.

## Defects reproduced and repaired in candidate

1. Non-MLP model selection displayed correctly but submitted MLP. The training handler
   captured a model selector that stage setup could detach. Candidate reads the live
   selector and uses that same value for family-specific parameters.
2. Initial progress loading populated native-source parents but left primary target
   controls disabled. Candidate refreshes target readiness after releasing metadata
   loading state. The combined browser workflow depends on this gate and now passes.

## Coverage

The suite exercises intake, source review/registration, inventory, time/tick/volume
sampling, primary candidate rules, exits, first-touch labels, native targets,
causal dataset joins, compatible feature selection, correlation/variance review,
four model families and RFE payloads, scoring, native replay, final reservation,
freeze/evaluation, saved-result statistics, recoverable Trash handoff and shared
context. It verifies outgoing payloads and visible outcomes, failure recovery,
three screen sizes and shared chart interaction.

The combined workflow uses real packaged browser code with synthetic responses:
native target → causal dataset → analysis/review → XGBoost → scores → native
replay → reservation/freeze → final evaluation. Its success does not prove actual
worker computation or broker enforcement. Native Windows password prompts and
visual baselines for every generated report template remain outside this suite.

## Reproduction and evidence

See `documentation/guides/GNET_COMMAND_CENTER_BROWSER_TESTS.md` for commands and
the coverage matrix. Current machine evidence lives in `.test_artifacts/browser/`:
`tested-package.json`, `junit.xml`, `report/index.html` and failure traces.
Run without `-Spec` or `-UpdateSnapshots` for the complete release check.

## Installed broker follow-through

The existing approved 300-bar/70-position fabricated TS fixture passed actual V42
scheduled broker admission, native preparation, target creation, causal dataset
construction, correlation/variance diagnostics, feature review, XGBoost fitting,
walk-forward scoring and native recorded-position replay through V63.

- Primary targets: 70; positive 35, negative 35.
- Training rows: 57; excluded 13; positive 29, negative 28.
- Variable inputs retained: 2 of 13; 11 fixture columns were constant.
- Purged folds: 2; unseen scores: 38; initial unscored rows: 19.
- Toy model approvals: 0; rejected: 38. This is execution evidence, not predictive quality.
- Training job: `job-20261011T010021Z-f15851a8fd42404ea96b59af8159ac5e`.
- Replay job: `job-20261011T010041Z-6b7c5e5086d44611974d6cbc140711ab`.
- Receipt: `.artifacts/v63-installed-synthetic-workflow-full.json`.

The two-position scaffold fixture also passed labels and dataset joining, then
correctly failed diagnostics with `feature_analysis_population` (no valid purged
training prefix). Its original failed job remains in the separate generic receipt.

Fresh synthetic final acceptance passed after local Administrator activation of
the exact new fabricated archive. The ordinary-user continuation reserved a
separate August 24 holdout, froze the saved model/scores, evaluated once, generated
saved-result statistics and verified rejection of a second evaluation attempt.

- Final population: 70 primary positions; 57 scored; 29 approved, 28 rejected.
- Final job: `job-20261011T010611Z-8352c8a7e1da4d4fac2a9bb83237637a`.
- Statistics job: `job-20261011T010623Z-dfbd9fab15e44153ba60e9a7b45e84f5`.
- Repeat job: `job-20261011T010626Z-856212e1da694d04a8abc5ccf3a5078d`;
  expected rejection: `final_evaluation_consumed`.
- Experiment: `browser-v63-native-final-r1`; receipt `final_passed: true`.

These are actual installed scheduled broker jobs using fabricated data. They
prove this tested research path executes through final evaluation, not predictive
quality or full account isolation. The synthetic seed did not exercise normal
custody ingestion; real TradeStation platform and native authentication acceptance
remain separate. No real data was used; isolation remains uncertified.

`scripts/build_browser_regression_client.py` preserves the installed package,
copies a fresh candidate, applies exact asserted patches and recomputes/verifies
its client manifest. Its final candidate revision is v63-r2.
