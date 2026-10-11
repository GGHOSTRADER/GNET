# V38 installed ordinary-user access acceptance

The actual ordinary researcher identity `GUILLE\g_med` (SID ending 1001,
not elevated) passed native access checks against the installed V38 boundary.
Both scheduled task actions were checked for the V38 working directory before
collecting their current security descriptors.

- Vault and V38 runtime directory listing and mutation rights were denied.
- Task-file write, owner and DACL handles were denied.
- All ten native Authz task checks passed: invocation allowed; write, delete,
  owner and DACL modification denied for ResearchRun and DataReport.
- Protected content was not read; no permissions or installed files changed.

Receipts: `.artifacts/v38-native-access-probe.json` and
`.artifacts/v38-task-access-metadata.json`. The sandbox initially denied Task
Scheduler connection; the ordinary-user check outside the sandbox succeeded.
The generated probe preserves the original top-level definition inventory and
both preparation/probe modules import successfully. These new artifact files
have no tracked HEAD baseline; the original probe is the comparison baseline.

## Administrator step

`.artifacts/Test-GNETV38BrokerToken.ps1` is prepared, parses successfully and
its plan reports the exact V38 release. Inspection helper hashes match their
pinned values. It submits eight bounded capability queries, verifies the exact
idle task actions and SID, and binds token inspection to the launched task
instance. Its local Administrator requirement comes from Windows process-token
inspection. This development-machine script is pinned to the local broker SID.

Run in Administrator PowerShell:

```powershell
& 'C:\Users\g_med\python_new\GNET\.artifacts\Test-GNETV38BrokerToken.ps1' -Apply
```

## Running-token result

The Administrator run passed all 21 native access checks against the actual V38
broker process (PID 27472), bound to task instance
`{1907152F-8FDA-406D-A8D7-ED43C305EF4F}` and broker SID ending 1006.
Vault/state read and write, runtime/config/review-store read and Python execution
were allowed. Runtime/config/Python/review-store mutation and scheduled-task
mutation were denied. No private content was read, permissions changed or token
impersonated. Inspection privilege restoration passed.

Receipts: `.artifacts/v38-broker-token-supervision.json` and
`.artifacts/v38-broker-token-access.json`. Both receipts were inspected and agree
with the user-supplied output. This is V38 evidence; the V36 result is historical.
Installed interruption recovery, broader isolation, native password acceptance
and final combined certification remain separate; `isolation_certified` remains
false.
