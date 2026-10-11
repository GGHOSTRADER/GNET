# Feature diagnostic units correction

## Defect

The installed real-data run classified Amihud as constant because its original-unit
variance was below 1e-12. Changing measurement units could change this decision,
and the passing feature-review gate rejected that column. Small variance alone
does not prove a feature has identical observations or lacks predictive value.

## Source correction

Staged source: `.artifacts/command-center-oct09-source`.

- `gnet_broker/feature_research.py`: constant means every observed value is
  exactly equal. Variance is still reported in original units. Correlation
  normalizes centered columns before covariance and standard deviation, allowing
  varying tiny-unit columns to retain defined Pearson correlations.
- `gnet_broker/feature_review.py`: rejection text now describes exact constants.
- Reports distinguish exact constants from variable features. No automatic
  near-constant cutoff or predictive-importance claim is introduced.
- Existing first-training-prefix restriction and immutable review ancestry remain.

## Verification

Six focused regression cases passed in 0.28 seconds: rescaling across 1e-200,
1e-10, 1 and 1e10; very small variation around 1; exact constant report labels;
JSON finite-output checks and correlation invariance. Both modules import.
The staged module's five top-level definitions match its pre-edit inventory.
These staged files are not tracked at HEAD, so HEAD inventory comparison is
unavailable; the pre-edit source inventory was used instead.

An older test could not collect because its imported test_training_input_modes
fixture module is missing from this staged checkout. No claim that the wider
suite passed. All regression inputs are fabricated; no market data was loaded.

## Deployment and research status

Correction is installed on the development machine as broker V38/client V42.
Delivered customer ZIPs, source approvals, prior analysis/model artifacts and
previous results are unchanged. The customer installation has not been upgraded.
The previous 11-feature baseline remains a declared development experiment;
its Amihud omission must not be described as proof that the feature is constant.
Reanalysis/refitting is a new development run, not an overwrite or final test.

## Reviewed continuation package

- Folder: `.artifacts/GNET-Command-Center-v38-DiagnosticUnits-r1`.
- Broker: `guarded-v38-feature-diagnostic-units`.
- Client: `gnet-client-v42-feature-diagnostic-units-r1`.
- Built from verified V37/V41 delivery, retaining its human/agent GUI guides.
- Only two broker Python files changed; their top-level inventories match the
  previous package and both import. Dependencies and client runtime code unchanged.
- Six regression cases passed against staged source (0.36s), then against the
  actual packaged module (0.06s). Both PowerShell plans and parsing passed.
- Delivery file hashes, broker manifest and client manifest verification passed.
- ZIP SHA-256: `ba1652530ca942c9b65173d2a540b11ef3293b6ac34a8665e825fcd9e54236da`.
- Broker manifest SHA-256: `23be0476f0dd7916ae1de09212125b318e114cd32ea8d3c7a595728600d60c41`.
- Client manifest SHA-256: `91d39029b5573d42031d710434a39bb101aec085f7a5b7ca712708a9d4717005`.
- External hashes: `.artifacts/GNET-Command-Center-v38-DiagnosticUnits-r1.sha256.json`.

Run the packaged `Deploy-ReviewedCommandCenter.ps1 -Apply` in local Administrator
PowerShell, entering the existing broker password locally. After deployment audit
passes, run `Install-ReviewedCommandCenterClient.ps1 -Apply` as the ordinary user
and reopen the installed launcher. Privileged deployment requires the local human
credential transition; packaging does not activate the release or certify isolation.

## Installed development acceptance

Human deployment receipt: V38 installed and activated, deployment audit passed,
custody marker reconciled, failure null. Matching V42 ordinary-user client installed
and launcher restarted (PID 53336). Host MCP configuration was not changed.

The existing approved TS source was processed through typed broker jobs with new
V38 parents. Source preparation retained 170 positions, labels yielded 163 eligible
targets and the training dataset yielded 162 eligible observations with 13 features.
Analysis job `job-20261010T011201Z-9c78d0b647a5456e89d785053de5262c` published
a usable result from the same 41-observation first purged training prefix:

- Zero constant features; Amihud is correctly retained as variable despite its
  original-unit variance of approximately 6.46e-22.
- 15/30-bar Parkinson volatility correlation remains approximately 0.94818.
- No model was fitted, no final holdout was used and previous results were preserved.
- Recorded TS simulation limitations remain; executable price-basis verification
  still fails the optional replay check on provider-adjusted continuous prices.
- Full isolation certification and native researcher-password acceptance remain pending.

Receipts: `.artifacts/v38-real-ts-diagnostic-acceptance.json` and
`.artifacts/v38-real-ts-analyze_features-report.json`.
