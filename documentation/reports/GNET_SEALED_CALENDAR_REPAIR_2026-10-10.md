# Sealed calendar reconstruction regression

Selected export: `ts-20261009102110-415723136-460036011`.
Protected diagnostic identified failures in `verify_ready`, reached by both
`ts_review_template` and `ts_primary_trade_view` through `custody_snapshot`.

V39 replaced `ts_export_bundle.py` from a stale source checkout while adding
generic primary support. That replacement omitted the existing session-schedule
reconstruction and producer/metadata agreement check. V39 therefore reconstructs
a different source descriptor for exports sealed by the earlier calendar-aware
client. The regression test reproduces the same descriptor mismatch exception.

Candidate `.artifacts/GNET-Command-Center-v40-SealedCalendarRepair-r1` restores
that exact calendar block and the existing generated-date summary. It retains
generic primary support and current V54 UI behavior. No export is rewritten.
Top-level Python definition inventory is unchanged; the patched module imports.
Broker and client package manifest verification passed. Both PowerShell wrappers
parse and their plan modes passed.

Synthetic checks: 5-minute and 30-second old-client sealing, V39 failure
reproduction, repaired validation of the unchanged bundle, custody handoff and
review snapshot, rejection of tampered descriptors, legacy export without a
calendar. All passed using `.venv/Scripts/python.exe`.
Evidence: `.artifacts/sealed-calendar-repair-tests.json`.

Broker: `guarded-v40-sealed-calendar-repair`.
Manifest SHA-256: `f1ccd797bda213a60ac7c570c27c681234d451f33984bd075acbe082fc89a88f`.
Client: `gnet-client-v55-sealed-calendar-repair-r1`.
Manifest SHA-256: `0d30e69d576f32c5d289857f707cf063871c87c62ae8590d6022d9a52627d674`.

Installation and retry of the actual selected source are pending. This evidence
does not claim real-source validation, training, or isolation acceptance.

## Installed follow-up

The broker V40 deployment receipt reports installed, activated, audit passed,
and custody marker reconciled. Matching ordinary-user client V55 was installed
and reopened successfully on port 9040.

The selected real export was retried through the GUI under the user's existing
authorization:

- Automatic validation `job-20261010T151510Z-588f2df637e14c73952231cdb230ec52`
  published successfully: coverage, sessions, timestamps pass; 30,085 bars
  checked, 110 expected/observed sessions, zero missing sessions/off-grid bars.
  The incomplete terminal session has 193 bars and is excluded from the proposed
  research scope; 29,892 bars remain through October 8. Original preserved.
- Trade viewer `job-20261010T151625Z-acee728210684821b7f1717c496dbefc`
  published successfully and rendered the chart and first 20 of 924 positions.
  Zoom control exercised in the browser.
- Dataset viewer `job-20261010T151727Z-08831316f3044a2fbcda89719b068377`
  rendered 83 observations for May 10. Candles and zoom control verified.

Screenshots: `.artifacts/v40-trade-viewer-installed.jpg` and
`.artifacts/v40-candles-installed.jpg`. Research approval/registration and
training were not submitted during this verification. Isolation acceptance
remains separate. The earlier synthetic-only flags describe the package tests,
not these authorized real-source GUI checks.
