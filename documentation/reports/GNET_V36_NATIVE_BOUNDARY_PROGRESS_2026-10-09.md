# V36 installed Windows boundary acceptance progress

October 9, 2026, America/New_York. Development machine only; these results do
not certify the customer's computer.

## Passed under actual unelevated researcher identity

Identity `GUILLE\g_med`, SID ending 1001; Administrator token membership false.
Probes were repeated outside the Codex filesystem sandbox to establish native
Windows access results. No ACL, account, task, configuration or runtime mutation.

- Vault and exact protected V36 runtime directory: list, add-file,
  add-directory, delete-child, write-DACL and write-owner handles denied with
  Windows error 5. Protected content was not read.
- Both task files: write, DACL and owner handles denied. Task definition reads
  are allowed, as expected for public operational metadata.
- Native Authz using the actual researcher token and Task Scheduler descriptors:
  invoke allowed; write, delete, write-DACL and write-owner denied for both tasks.
  All ten Task Scheduler token-access checks passed without mutation attempts.
- Fixed actions for ResearchRun and DataReport point to installed V36; configured
  principal is GNETDataBroker. This is configuration evidence, not running-token
  identity proof.
- Synthetic custody acceptance: tested=true, passed=true, real_data_used=false;
  25 fabricated rows, exact expected source hash, custody committed and staging
  cleaned. No dataset registration or research-use authorization.
  Job: `job-20261010T004944Z-be19e9b2de4b4df785751109bb04f7e2`.

Native probe receipt: `.artifacts/gnet-native-access-probe.json`.

## Next concrete probe

`.artifacts/Test-GNETV36BrokerToken.ps1 -Apply` is prepared for local
Administrator execution. It checks both exact idle task actions and broker SID,
pins inspection-helper hashes, submits eight capability metadata jobs, binds
the running process to the launched task instance, inspects its real token,
evaluates existing ACLs, and checks restoration of temporary inspection privilege.
No private content read, market-data job, grant, account or task change.
Eight requests keep the short-lived broker available for bounded inspection.
The supervisor retains job IDs even if inspection fails; broker jobs are not killed.
PowerShell parsing and dry-run plan passed. The user subsequently ran Apply in
local Administrator PowerShell. Actual running token SID ended 1006, process
56524, bound to task instance DD120FF1-7B92-4EDF-8D9E-906EABD0AF25. All 21 broker
access checks passed: vault/state access allowed, protected runtime/config/Python
and reviewed-policy writes denied, and both task modification rights denied.
Inspection privilege restoration passed; no impersonation, broker-token change,
permissions change, private content read or real data use occurred.
Receipts: `.artifacts/v36-broker-token-supervision.json` and
`.artifacts/v36-broker-token-access.json`.

The token helper has a historical V17 filename but inspects the current supplied
process ID and the collected current descriptors. It does not invoke a V17
runtime, stale research fixture or old deployment. Its pinned SID matches the
current local broker principal; this development-specific script is not a
portable customer installation script.

## Installed synthetic cancellation and interruption recovery

Current-release controllers were adapted from the existing V26 controllers with
definition inventories preserved. They use only public exchange/report operations
and the existing verified 16-event synthetic fixture. The V36 controller imports;
PowerShell parsing and dry-run plan passed. No protected runtime update occurred.

- Active cancellation passed for
  `job-20261010T005712Z-82f6653881a1403b9fa365a0829c4b58`: observed running attempt 1,
  then cancelled with cancel=1, unusable result and no published artifacts.
- Interruption/restart passed for
  `job-20261010T005736Z-b8a718ad73d84bc59d16e1f5a092b0d7`: only its exact owned
  ResearchRun instance was stopped, with both tasks and unrelated active work
  checked. No usable partial public result existed after interruption.
- After the 32-second lease wait, the same job ID resumed on attempt 2 and
  published a usable validated result: 16 domain nodes, 16 tested policies and
  zero failed policies. Cancellation was not carried into recovery.
- All inputs were fabricated. No real data, account/ACL/task-definition changes,
  protected-file reads or interrupted real jobs.

Receipts: `.artifacts/v36-active-cancellation.json`,
`.artifacts/v36-installed-recovery.json`, `.artifacts/v36-interrupted-output.json`.
This exercises an explicitly stopped task instance and stale-lease recovery,
not a machine power loss, reboot or every possible publication crash window.

## Packaged verifier integrity rejection

The exact V36 packaged verifier matched its release manifest hash and passed
seven isolated fixture checks: unchanged control, altered source, missing source,
altered manifest, wrong approved manifest pin, dependency mismatch and interpreter
version mismatch. Every altered fixture was rejected. Dependency/interpreter cases
use fabricated declarations and a mocked dependency inventory, not an installed
environment mutation. Receipt: `.artifacts/v36-integrity-rejection.json`.

This is component acceptance of the packaged verifier. It does not establish
installed task behavior after tampering. No installed runtime, configuration,
permissions, tasks or real data were changed. Missing files raise FileNotFoundError
and stop verification; they do not produce the structured ContractError receipt
used for hash mismatches.

## Remaining certification gates

Broader individual-file and
ancestor boundary coverage, account-policy restrictions, altered-runtime/hash
rejection through the installed task, additional publication crash windows and reboot acceptance, native
researcher-password acceptance and final combined certification remain separate.
`isolation_certified` remains false. A passed deployment audit or custody job alone
cannot close those gates.
