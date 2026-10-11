# Selected-source review and publication correction — October 11, 2026

Installed client: `gnet-client-v77-selected-source-review-r2`.
Installed broker remains `guarded-v43-native-browse-fix`.

The global review button beside Data cleaning and sampling was removed. Existing
per-source Review / register source links retain their exact export identity.
The review page loads the selected public receipt metadata before validation and
shows identity, symbol, interval, record count, coverage, timezone, transfer state,
import time and primary strategy counts when available. Successful validation
enriches this metadata; failed validation leaves the receipt summary visible.
Explicit recorded synthetic scope is included in the initial validation request.
No raw export content was inspected.

All 172 browser tests passed without snapshot updates in the installation gate.
Two new regressions cover retained metadata on validation failure and initial
recorded synthetic scope. Review and heading screenshots were inspected.
Installation receipt:
`.test_artifacts/release-gates/gnet-client-v77-selected-source-review-r2-20261011T070137806Z/installation-receipt.json`.

The reported job `job-20261011T065556Z-e96d918a6cf94b8eb91b6e61b120e885`
published only a failed `unsafe_output` receipt; no detailed validation results
were published. The receipt alone does not identify the offending field.
A fabricated regression reproduced the same error when pending calendar choices
included internal evidence text containing a filesystem path. V43 copies that
text into public calendar choices. The V44 correction publishes only calendar
ID, timezone and coverage dates; protected evidence remains internal and the
publication guard is unchanged. The regression fails on V43 and passes on V44.
This does not yet prove the reported job succeeds after the correction.

Prepared and verified; V44 activated on October 11, but deployment audit is incomplete:
`.artifacts/GNET-ReviewPublication-v44-r1`.
Broker: `guarded-v44-review-publication-fix`.
Broker manifest SHA256:
`12bc58c0e2da2e4389f2b1541bf6584f0e5b538cd1df1e345eb5f746e9b74a1b`.
The deployment plan and immutable package hashes verify successfully.

The protected wrapper requires Administrator PowerShell and prompts locally for
the existing GNETDataBroker credential. It checks idle tasks/queue, retains prior
releases and audits the deployment. Credentials must remain local.

From Administrator PowerShell:

```powershell
& 'C:/Users/g_med/python_new/GNET/.artifacts/GNET-ReviewPublication-v44-r1/Deploy-ReviewedCommandCenter.ps1' -Apply
```

After a successful protected deployment, from ordinary PowerShell:

```powershell
& 'C:/Users/g_med/python_new/GNET/.artifacts/GNET-ReviewPublication-v44-r1/Install-ReviewedCommandCenterClient.ps1' -Apply
& 'C:/Users/g_med/python_new/GNET/.artifacts/client-delivery-installed/Open-GNETResearch.ps1' -NoBrowser
```

The matching-client installer reruns the complete browser suite before shutdown.

The deployment audit checked 1,000,000 filesystem security descriptors with zero
findings, passed both task definition/ACL checks and package/hash rejection checks,
then stopped at its object limit. Retained runtime releases alone accounted for
992,880 objects. This is an incomplete scan, not a passed audit. The client still
pins V43. `Resume-GNETCommandCenterAudit.ps1` reruns all original checks with a
5,000,000-object limit and the same 1,200-second limit, then reconciles the custody
marker and receipt only on success. Its extended audit helper differs from the
original only in the accepted object-limit range; both scripts pass parser checks.
The elevated launch returned a process ID but no refreshed receipt was observed.
The user then ran the resume command in their Administrator terminal: all
1,021,699 objects were checked in 73.293 seconds, with zero findings, both task
checks and package verification passing. The deployment receipt now records
audit_passed=true, failure=null and custody_marker_reconciled=true.
The matching client installer passed all 172 browser tests without snapshot
updates (56.8 seconds), then updated the V77 client configuration to V44.
Command Center restarted successfully. Native authentication and two-identity
isolation acceptance remain separate; no real-source registration or training
was performed during this deployment.
Only after activation and client pin reconciliation can the exact selected
source's automatic validation be retried against V44. Source approval,
registration, training and live-order permissions were not performed.
