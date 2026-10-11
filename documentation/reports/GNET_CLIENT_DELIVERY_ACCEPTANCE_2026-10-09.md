# Client delivery acceptance — October 9

Acceptance scope: TradeStation bars plus recorded native primary positions,
source approval, inspection, primary targets, feature diagnostics/review,
XGBoost training/validation and final comparison through the installed system.
Overall acceptance is **incomplete**.

Actual installed client: `gnet-client-v32-session-calendars-r4`.
Actual broker: `guarded-v30-session-calendars`.
The chat's injected MCP connection remains on an older release; this run used
the active installed ordinary-user CLI and existing protected scheduled task.
The browser on port 9040 showed the current broker identity.

## Passed installed checks

Using the exact pre-existing fabricated source
`acceptance-workflow-r4-oct09-dev` and its existing activated review:

- Admission and native-source validation: 300 synthetic bars, 70 closed positions.
- Standalone primary targets before feature construction.
- Feature construction: 57 eligible samples, 13 warm-up exclusions.
- Training-prefix variance/correlation diagnostics and feature review.
- XGBoost: two retained variable inputs, two chronological validation folds,
  38 out-of-sample scores, 19 initial unscored samples.
- Scoring and native recorded-position comparison completed.
- Browser training report includes classifier statistics, ROC/log-loss charts,
  gain importance and walk-forward permutation-importance charts.

Training accuracy is 0.5. At the fixed threshold 0.5 all 38 scored positions
were rejected. This fixture demonstrates execution and lineage, not useful
predictive performance. Purge/embargo are configured; this fixture removed zero
rows through those checks and therefore does not prove overlap-removal behavior.
This is chronological walk-forward validation, not CPCV.

Evidence: `.artifacts/client-delivery-ts-acceptance.json` preserves each job ID,
counts and artifact/report identities. The normal broker operations were used;
the runner only coordinates them and does not compute research results itself.

## Concrete incomplete checks

1. Native viewer failed with `custody_producer`. The administrator-seeded fixture's
   producer is absent from the reviewed custody allowlist. No allowlist was relaxed.
2. A fresh automatic review was not activated on the installed broker. The older
   fixture's calendar lacks a matching chart scope. Initial preflight also omitted
   the explicit synthetic declaration; the correct next call must set it true.
3. Browser button-by-button research acceptance remains pending. Opening a report
   verifies report rendering, not the entire browser submission workflow.
4. A fresh, separately reserved final source/evaluation was not run. Existing
   development comparisons must not be presented as untouched final testing.
5. Full Windows isolation acceptance, actual TradeStation platform export
   acceptance, and client-machine installation acceptance remain separate gates.

## Prepared local review step

`.artifacts/Review-GNETDeliveryAcceptance.ps1 -Apply` verifies the helper hash and
requires local Administrator approval. It reviews only the known synthetic
producer, installs the fixture's exact short synthetic calendar, asks the normal
broker to recompute automatic validation/draft, and activates the returned exact
proposal hash. Existing real-source authorization settings are preserved.
It does not reinstall a release, create accounts or register scheduled tasks.

The calendar and generated review payload were verified against a disposable
fabricated catalog using current source code. All 300 expected bar-close slots
were present, timestamps/coverage/sessions passed, and draft plus synthetic
activation passed. This is source verification of the prepared step; the installed
Administrator step itself has not run.

After local review: retry the viewer as a new job, admit the new automatically
generated review, exercise the browser controls and prepare a separate unexposed
synthetic final archive before claiming full delivery acceptance.

## Continuation after local reviewer activation

The local step activated its proposal. Two subsequent installed checks revealed
limitations of the pre-existing administrator-seeded fixture:

- Viewer job `job-20261009T161409Z-c2e0f9919ab2412b886627452802eb4c`
  failed `no_primary_report`: its old seed copied the transport receipt without
  the primary semantic-validation summary that normal custody produces.
- Attempting to admit that already accepted export under a new policy failed
  `intake_immutable`, correctly preserving its earlier source/policy identity.
  Reusing the old export was the wrong way to test fresh automatic approval.

A new fabricated bundle, `acceptance-client-delivery-oct09-fresh-r1`, was generated
without reading existing data and published through the normal incoming boundary.
It passed the installed custody worker, automatic timestamp/coverage/session checks,
and native trade viewing. The short synthetic calendar installed by the user was
reused; no new custody permissions or calendar changes were made for this bundle.

- Custody: `job-20261009T161648Z-33a5e2d6311a4924b0ec31b6a0717cba`.
- Automatic preflight: `job-20261009T161650Z-dd93de37805840db84158c8fc04c87b0`.
- Native viewer: `job-20261009T161702Z-a7987fa2ffd74eb59d6fdedf131f44d4`.
- Fresh draft: `job-20261009T161708Z-8cc3b07842db45d7b265078ab29b44c2`.

All 300 expected bar slots were present; zero missing sessions, duplicates or
off-grid timestamps. IDs were generated by the system. The fresh proposal awaits
local reviewer activation; `.artifacts/Approve-GNETFreshDeliverySource.ps1 -Apply`
invokes the existing pinned installed review CLI for only its exact proposal hash.
The completed older-source training is retained, but fresh-source admission and
training have not yet run. Separate final testing and browser button-by-button
acceptance are still pending.

Evidence: `.artifacts/client-delivery-fresh-ts-acceptance.json`.

## Fresh approved-source pipeline completed

After the human activated the fresh proposal, installed admission, native-source
validation, standalone primary targets, training dataset, diagnostics, feature
review, XGBoost fitting, scoring and recorded-position replay all passed.
There are 70 targets, 57 eligible samples, two variable selected features,
two validation folds and 38 out-of-sample scores. The fixed 0.5 threshold rejects
all scored positions; accuracy is 0.5. No real data was processed.

- Training: `job-20261009T162040Z-dcd67f55276140e5a548067828d2678b`.
- Comparison: `job-20261009T162052Z-604102c8bab34c999ecf222b8adee0c1`.

Browser inventory inspection found a real UI defect: a catalog-only source's
primary-trades link used its dataset ID as an export ID. The source link now uses
the recorded `origin_export_id`; an unknown origin links to the primary inventory
instead of inventing an export identity. Three identity cases and existing JS
function preservation passed, and changed JS parses.

A new immutable ordinary-user client, `gnet-client-v33-native-source-links-r1`,
was built from the installed r4 package with only two UI asset changes. Its manifest
SHA256 is `bc8a0766a39a15f786867bc060e5ae023c691d1fa6bc19fcf30e83906cd5db4d`.
The verified package is `.artifacts/GNET-Client-v33-NativeSourceLinks/client`.
It was installed and launched against the existing v30 broker. The old running
server was r2 despite the active configuration naming r4; the installer stopped
that exact verified old server through its own matching stop endpoint. No broker
release or permissions changed, and MCP host settings were not modified.

The current synthetic import-to-development-comparison path is verified through
installed typed operations. Separate untouched final testing, complete manual
browser submission, client-machine installation and account-isolation acceptance
remain incomplete. Do not claim the full delivery is certified from this result.

The restarted v33 server's HTTP health identity was verified. Browser inspection
confirmed that the freshly registered source's primary-trades link now resolves
to `acceptance-client-delivery-oct09-fresh-r1`, and that Open research pipeline
preserves the selected dataset ID. The comparison report was opened in Codex.

## Manual UI continuation and separate final preparation

Manual browser inspection found that dynamically built feature selection and
correlation/variance controls were inserted into the hidden legacy labels section
after the five-module layout had been constructed. Feature controls now attach
to the visible feature module when it exists, retaining the legacy host only
before the layout transition. Browser verification confirmed visible sections
3.1 and 3.3 with feature checkboxes and analysis/pass/reject controls.

The correction is installed as `gnet-client-v34-visible-features-r1` against
the same broker v30. Its immutable package manifest SHA256 is
`8af326197d6b1895930ecf3eab96e6739135acd19c1b26df706159c6aff7f973`.
Package: `.artifacts/GNET-Client-v34-VisibleFeatures/client`. No broker or MCP
host configuration changed. Manual browser diagnostics/review/training testing
is ongoing; visibility alone is not complete browser submission acceptance.

A separate generated final bundle, `acceptance-client-delivery-oct09-final-r1`,
has synthetic July 27 coverage after the development source's July 20 coverage.
Its bundle hash is `5cca5d6ea3c001a214ee091d998b74d2c8666d548c2e867e98060fe6ee190805`.
It was generated into the normal inbox without reading existing market data.
No final chart, feature selection or training was performed. The normal custody
pump may validate and retain it; that does not approve research or reserve a holdout.

`.artifacts/Prepare-GNETDeliveryFinal.ps1 -Apply` prepares its exact reviewed
synthetic calendar and source proposal using the installed local reviewer.
The plan and PowerShell parser passed; its calendar/payload shape passed automatic
validation, drafting and synthetic activation in a separate disposable catalog.
The user reported that the installed command failed, but no preparation receipt
was created. Exact PowerShell error text has been requested before diagnosing or
retrying the privileged step. Final reservation, freeze and evaluation have not run.

The reported preparation failure was a missing backslash in the invocation path;
the helper did not start. With the corrected path, exact July 27 custody, calendar,
automatic review/draft and local approval all passed. After explicit user permission
to consume the synthetic final evaluation, admission passed but reservation failed
with `unknown_experiment` before any freeze/evaluation or claim consumption.
Failed reservation: `job-20261009T164016Z-44f3587e3c7d4145b5b5e6ae7b98d9f8`.

Cause: the Trash guard tried to resolve an existing experiment binding for a
brand-new reserve request. The staged correction skips that binding lookup only
for reserve_experiment; it still guards the explicitly named dataset and its
origin export. Three dispatch regression checks passed: new reservation creation,
trashed-source rejection and existing-experiment requirement for freeze.

Reviewed immutable candidate: `.artifacts/GNET-Command-Center-v31-ReservationGuard`.
Broker `guarded-v31-reservation-trash-guard`, manifest SHA256
`572529816b67adb5cb30640fe664f1d3605e1b9ebb37ad9168645de2ff345454`.
Matching client `gnet-client-v35-reservation-guard-r1`, manifest SHA256
`41ab5559efb6546ce2ec7c75531460f2361f3916ae72bbd0b8b2341cc5083e99`.
The broker candidate differs from v30 in one code file plus release identity;
dependency lock is unchanged. Package verification and PowerShell parser/plan
passed. It is not installed. A reviewed broker deployment is required before the
installed acceptance can resume. Development artifacts must be rebuilt under
the corrected runtime before freeze; existing approved sources and old failed
reservation evidence are retained.

## V31 installed follow-up

V31 installed/activated successfully. Its audit initially could not save to the
missing delivery `.artifacts` directory. Independent audit-only recovery passed:
606,190 objects, zero findings, 40.325 seconds, both scheduled-task checks passed.
No reinstall, credential entry or ACL change was required for recovery.
Matching client v35 was installed and launched. The approved development source
was rebuilt through labels/features/diagnostics/XGBoost/scoring/replay under v31.
Evidence: `.artifacts/client-delivery-fresh-ts-acceptance-v31.json`.

The July 27 final source admitted under its existing exact approval. Reservation
then reached historical exposure reconciliation and failed `experiment_history_unknown`
before freeze/evaluation. The failed request was
`job-20261009T165849Z-f68b3761b24f40338e2dc0140ce4a421`.
No final-evaluation claim was consumed. Earlier failed receipts remain unchanged.

The history classifier omitted metadata-only source management, Trash catalog
and source-availability operations, even though their dispatcher paths do not
read market records. The staged classifier correction excludes those operations.
Eight regression checks passed, including unresolved actual data-bearing history
still preventing reservation, trashed sources remaining blocked and freeze still
requiring an existing experiment.

Reviewed candidate: `.artifacts/GNET-Command-Center-v32-HistoryMetadataGuard-r2`.
Broker `guarded-v32-history-metadata-guard`, manifest
`f9dfcb1340abdcbe26321b2832d20d3f7f7354b6c50501b05344a0617d2c78d5`.
Matching client `gnet-client-v36-history-metadata-guard-r1`, manifest
`7228845bb4080b8e6d309e19e5e25d08b372bcc5ca5f164910afbb8ac7d8448a`.
The new broker differs from v31 in one code file plus its release identity.
Dependencies are unchanged. R2's deployment wrapper creates the audit output
directory before writing, preventing recurrence of the missing-folder defect.
Package verification and wrapper parser/plan checks passed. The candidate has
not been installed; final testing remains blocked until its reviewed deployment.

The prepared ordinary-user runner is `.artifacts/Run-GNETDeliveryFinalAcceptance.py`.
It uses the existing saved development model/predictions, retains operation IDs,
does not refit, and tests second-evaluation rejection. It must only run after
successful exact final-source approval; failed or consumed claims are never reset.
