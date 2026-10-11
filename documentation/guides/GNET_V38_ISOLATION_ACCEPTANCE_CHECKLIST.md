# V38 isolation acceptance checklist

This consolidates the acceptance conditions discussed with the user and the
recorded V38 results. No earlier single signed checklist was found. It is not a
new certification or proof that every scenario below has passed.

Terminology: `isolation_certified` is an internal aggregate test-status flag,
not an external certificate, accreditation or compliance requirement. Individual
checks can pass while that aggregate flag remains false. It does not by itself
mean that research execution is unavailable; actual source/process permissions
and installed capabilities determine what the system can run.

Scope: `guarded-v38-feature-diagnostic-units`, development Windows machine,
ordinary non-elevated researcher and actual scheduled GNETDataBroker identity.
Elevated local administrators are trusted and can override Windows protections.
Use synthetic fixtures or bounded metadata only. No live services or real-data
final evaluation are part of isolation acceptance.

| ID | Required evidence | Current result |
|---|---|---|
| I-01 | Exact release pin, audited task actions/accounts/ACLs; enabled non-admin broker with batch-logon permission | Passed deployment/account audits |
| I-02 | Ordinary researcher cannot read private vault/runtime or mutate protected files, parents, config, task actions/ACLs | Passed native access and 52 ancestor/file checks |
| I-03 | Actual scheduled broker token can read required private inputs/write state, but cannot mutate runtime/config/review authority/tasks | Passed 21 token-bound checks |
| I-04 | All installed manifest files/dependencies/interpreter match approved release; wrong pin rejected by installed verifier | Passed 184-file verification and wrong-pin invocation |
| I-05 | Actual installed scheduled task rejects an invalid protected integrity pin; config restored exactly; normal task succeeds afterward | Passed: control exit 0, invalid pin exit 2, restored control exit 0; task definitions/ACL unchanged |
| I-06 | Cancellation publishes no usable partial artifact; interrupted installed job recovers the same job safely | Passed installed active cancellation and attempt-2 recovery |
| I-07 | Publication crash points cannot expose partial usable results; ownership fencing prevents stale commits | Passed packaged component injections; installed publication-boundary crash evidence pending |
| I-08 | Ordinary researcher can invoke broker successfully after an idle Windows restart | Passed changed boot timestamp and fresh published job |
| I-09 | Native protected Trash approval accepts correct local researcher credentials and rejects invalid/wrong-identity approval without leaking credentials | Deferred by user; not tested |
| I-10 | Consolidated receipts match this release, identities and required scopes; all required checks passed | Pending; isolation_certified=false |

## Evidence

Receipts live under `C:\Users\g_med\python_new\GNET\.artifacts`:

- I-02: `v38-native-access-probe.json`, `v38-task-access-metadata.json`, `v38-ancestor-access.json`.
- I-03: `v38-broker-token-access.json`, `v38-broker-token-supervision.json`.
- I-04: `v38-installed-integrity.json`, `v38-integrity-rejection.json`.
- I-05: `v38-installed-task-rejection.json` when execution completes.
- I-06: `v38-installed-recovery.json`, `v38-interrupted-output.json`, `v38-active-cancellation.json`.
- I-08: `v38-reboot-acceptance.json`.
- Account policy: `v38-account-policy-repair.json`, `v38-logon-rights.json`.

I-05 tests invalid manifest-pin rejection with unchanged installed code, not
every possible runtime corruption. I-08 tests an idle reboot, not power loss or
reboot during active computation. Component fault injection must not be renamed
installed-process crash acceptance. Desktop/network logon restrictions are a
separate hardening choice. Real TS platform acceptance, untouched final holdout
evaluation and live model promotion are separate research/product gates.

## Installed-task check

Run `Test-GNETV38InstalledTaskRejection.ps1 -Apply` in local Administrator
PowerShell. It uses the existing task and preserves its definition, ACL and
credentials. It refuses non-idle work. The protected config is backed up with
its original ACL before changing only the manifest pin. A finally block restores
the original bytes. If the shell/machine stops during the test, run the same
script with `-Recover -Apply` before starting research. The recovery path verifies
the backup's reviewed pin and refuses restoration while a task is active.

Certification remains incomplete while required checks are pending or deferred.
