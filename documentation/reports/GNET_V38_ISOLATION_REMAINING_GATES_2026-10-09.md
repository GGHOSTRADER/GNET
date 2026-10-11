# V38 isolation continuation

Consolidated acceptance criteria and evidence status:
[V38 isolation checklist](../guides/GNET_V38_ISOLATION_ACCEPTANCE_CHECKLIST.md).
The actual installed-task invalid-pin test is now prepared as
`.artifacts/Test-GNETV38InstalledTaskRejection.ps1`; parsing and its non-mutating
plan passed. Local Administrator Apply subsequently passed: valid control exit
0, invalid-pin task exit 2, restored control exit 0, exact config restored and
tasks unchanged. Receipt: `.artifacts/v38-installed-task-rejection.json`.
It has idle-work guards,
a protected config backup, byte/ACL restoration, bounded exact-instance waits,
valid-pin controls before and after rejection, and a crash-recovery switch.
It neither submits a research job nor changes task definitions or credentials.

## Completed in this continuation

- All 52 ordinary-user mutation-handle checks passed across eight protected/ancestor
  directories and five fixed files. DELETE, WRITE_DAC, WRITE_OWNER and directory
  DELETE_CHILD or file-write rights were denied. No contents read or writes made.
  Receipt: `.artifacts/v38-ancestor-access.json`.
- Seven packaged V38 verifier fixture checks passed: unchanged control accepted;
  altered/missing source, altered manifest, wrong pin, dependency mismatch and
  interpreter mismatch rejected. Verifier hash matched the packaged release.
  Receipt: `.artifacts/v38-integrity-rejection.json`.
- These checks supplement the passing V38 deployment audit, both identity access
  checks, installed interruption recovery and active cancellation. They do not
  certify every file or actual installed-task tampering behavior.

New Python probes compiled/executed successfully. The copied verifier preserves
the original top-level definition inventory. Existing source definitions were not
edited. Account inspection and access probes required ordinary-user execution
outside the sandbox; sandbox account queries failed before native inspection.

## Actual account metadata

Read-only local account/group inspection found:

- GNETDataBroker is enabled; SID ends 1006 and agrees with the tested process.
- It is not a direct member of the local Administrators group.
- Initial inspection found PasswordRequired=false, UserMayChangePassword=true
  and a non-null PasswordExpires. The subsequent local Administrator correction
  passed: PasswordRequired=true, UserMayChangePassword=false and
  PasswordExpires=null. The current password and task definitions were preserved.
  Receipt: `.artifacts/v38-account-policy-repair.json`.
- GUILLE\g_med belongs to Administrators, but native acceptance ran under its
  non-elevated token. Local elevated administrators can override the protected
  boundary; this evidence establishes non-elevated researcher restrictions.

## Still open

The local Administrator batch-policy audit subsequently passed: explicit broker
SID allowance, no applicable denial, enabled account and no administrator
membership. This policy result does not itself verify task execution; the earlier
installed synthetic job receipts provide separate execution evidence.

`Repair-GNETV38AccountPolicy.ps1` now provides a development-machine-only plan
and explicit Administrator Apply for the remaining password flags. It requires
a password, disables automatic password expiry and prevents broker-initiated
password changes without replacing the existing password or task definitions.
PowerShell parsing and the non-mutating plan passed. The human subsequently ran
Apply; its postconditions passed. A fresh public capabilities job then published
through the scheduled broker with no error:
`job-20261010T034729Z-2f3b47a5a2444fb6b9787930860ee947`.
Receipt: `.artifacts/v38-after-policy-execution.json`. Capabilities reports have
validation_status=unavailable; this verifies execution, not data validation.

1. Local logon-rights inspection completed under the human's Administrator
   session. Batch is allowed for the exact broker SID; interactive is allowed
   through Users; network is allowed through Users and Everyone; remote
   interactive has no applicable allowance. No applicable denials were found.
   Receipt: `.artifacts/v38-logon-rights.json`. The account is not an
   administrator. Actual interactive/network logons and remote authentication
   settings were not tested. This establishes policy visibility, not an ACL
   isolation failure or aggregate certification. Restricting these additional
   logon modes would be a separate reviewed hardening change; none was made.
2. Installed verifier acceptance passed under the human's Administrator session:
   all 184 manifest-listed files matched the reviewed pin, package verification
   passed and the wrong pin was rejected. Receipt:
   `.artifacts/v38-installed-integrity.json`. Runtime/configuration were not
   modified. This is not a scheduled-task tampering test.
   Ordinary-user idle reboot acceptance also passed: boot time changed from
   `2026-09-29T13:28:37.5000000Z` to `2026-10-10T03:57:09.5000000Z`, and new
   scheduled capabilities job
   `job-20261010T035936Z-406c25bf94cf425196f1e1ea4706f87b` published successfully.
   Receipt: `.artifacts/v38-reboot-acceptance.json`. Actual installed-task
   wrong-pin rejection now passed separately; runtime-file tampering, additional
   installed publication crash windows and interruption during reboot remain
   distinct untested scenarios. Idle reboot success does not establish them.
3. Native researcher-password acceptance remains deferred by the user; protected
   Trash authentication must not be represented as tested.
4. Produce the aggregate certification only after required checks pass. Current
   `isolation_certified` remains false.
5. Real final evaluation needs a separately approved untouched archive beyond the
   development cutoff. Current development outcomes are not a fresh holdout.

No credentials collected, protected runtime altered, real data read, training
run or final evaluation performed. The human applied the documented account
password-policy flags; the agent verified the receipt and scheduled execution.
