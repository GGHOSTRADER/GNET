# Customer installation: delivery choice and next stage

## Unified customer research installation packet — October 9

Customer reported base r2 installed: matching broker V37/client V41, MCP connected,
metadata jobs published, empty catalog/progress as expected. Installed synthetic
custody reported tested=false because the release marker/private policy was not
configured. This is an intake gate, not proof of an isolation failure or missing
runtime code. Full isolation remains untested.

Latest matching follow-up: `.artifacts/GNET-Custody-Boundary-Update-2026-10-09-r4.zip`.
ZIP SHA256: `d3c34ca954fd839d544332512aee4eb4808225308d4f3e00302930e08643a4e9`.
Update manifest SHA256: `34e2f633db9fe9e0862f3750edcea755adaae9bee512ca8984e9239a74a8dc2a`.
Customer r2 validation found the ordinary client still used its default local
exports directory. r4 adds Prepare-GNETCustodyClient.ps1: normal-user plan/apply,
exports-only config correction to the fixed broker inbox, exact original backup,
no data read/migration, idempotent repeat, rejection of custom paths. Six checks
passed in PowerShell Core and Windows PowerShell 5.1 against separate fixtures;
installed configuration untouched. Use r4 instead of the earlier r2 update.
Update verifies the original r2 package and matching installed runtime, generates
reviewed configured producers, enables the private custody policy and protects
intake controls/import parent. Accounts, tasks and runtime are retained; no client
pin/config replacement or credential entry. Administrator confirmation includes
explicit real-custody permission; research use remains separately gated. Agent
instructions run fabricated custody acceptance afterward from normal-user MCP.
Update ZIP hash/CRC verification and both PowerShell syntax/forbidden mutation
checks passed. Customer native update/acceptance has not yet run.

Prepared `GNET-Client-Installation-2026-10-09-r2.zip` in `.artifacts` with one
customer release name. Use this packet for the already-prepared customer machine.
It bundles the matching protected broker and ordinary-user Command Center,
fresh standard account creation/prepared-account enabling, folder/task/batch
permission setup and deployment audit. Component identities are internal to
system-release.json: guarded-v37-agent-gui-guide and gnet-client-v41-agent-gui-guide-r2.

- ZIP SHA256: `c38ec07f9afd28169e03181f3564d277a27b7394ee955ceedff5b1abf6401520`.
- System manifest SHA256: `ee505c958dad4ac375c947ab6ad83ae862ec6e41d1b9e64eeea353da2feea4d2`.
- 354 files verified; ZIP CRC and every payload hash passed.
- All packaged PowerShell scripts parsed. Simulated success and failed-audit
  rejection passed; nonprivileged machine-plan preparation passed.
- Root AGENTS.md requires GUI human/agent guides before customer assistance.
- START_HERE.md documents machine-specific plan, client install, Administrator
  handoff, launch/MCP, approval meanings, research steps and pending acceptance.
- Libraries download into the protected release venv; no library binaries or
  market data are included. Third-party inventory and methodology attribution included.
- Customer privileged deployment/native credentials/isolation/GUI acceptance
  have not been tested. Real custody setup/source approval are separate reviewed
  steps; live weight promotion remains unimplemented.

Earlier Command-Center candidate ZIPs are development continuation packets
requiring an existing broker; do not give those as the fresh customer installer.
The preparation r7 package below remains the environment stage for new machines.

## Package to deliver for new machines

Use **GNET-New-Machine-Preparation-r7.zip** for new Windows machines. It is
standalone: no older preparation package or update ZIP is required.

- Location: `C:\Users\g_med\python_new\GNET\.artifacts\GNET-New-Machine-Preparation-r7.zip`
- ZIP SHA256: `204b3402fde3cd9d5ffc3e942419cc01aed0a163791c0be62e33c1ca7ac378d4`
- Preparation manifest SHA256: `a7424569aec9f02c9b3f785a11196ea953d8e106385ab12e0ac2a5da53934666`
- Includes human/agent guides and machine-specific Administrator handoff.
- Downloads and installs Python 3.12.7 x64 and 21 pinned libraries, prepares a
  missing disabled standard GNETDataBroker account and twelve folder boundaries.
- Broker activation, full research client, tasks, MCP and research acceptance
  are subsequent deployment work. Do not confuse preparation with deployment.

The user explicitly selected this package for future new-machine deliveries.
Keep delivered ZIPs immutable. Later changes require a new release and hashes.

## Current customer

Latest user correction: the customer installed the environment, but has **not
created GNETDataBroker**. Treat this as the current target state. Earlier pasted
receipts reporting an existing disabled account and twelve boundaries must not
be applied to this machine. Current account/ACL/task completion is unverified.
No remote installation, current-machine audit or isolation certification has
been performed in this session. Check the actual target's bounded receipts
before deployment. Never infer machine state from this development computer.

## Next stage: protected broker deployment

Create the missing standard GNETDataBroker account during approved deployment;
reuse an existing standard account only if the target actually has one. Another
Windows account is not required for the secondary ML model. Broker code lives
under `C:\ProgramData\GNETBroker\runtime\releases\<reviewed-release>`.
The broker runs that pinned code and accesses the private vault. The ordinary
researcher runs the browser/agent client, submits typed requests and receives
bounded public reports. Do not put protected code in a user-writable profile.

1. Prepare a new reviewed deployment packet with the chosen protected broker,
   matching research client, hashes, human/agent guides and target-specific plan.
   The old combined v3 packet contains guarded-v10-ml-replay; it does not represent
   the later TS primary/source-workbench implementation. Source-workbench v16 is
   an available candidate, not proof of customer installed acceptance.
2. Verify current preparation receipts and actual Python/account/ACL metadata.
   Preserve the prepared environment and any existing account. Reuse dependencies only after
   independent trusted metadata and exact locked-version/import checks.
3. Human approves Administrator deployment and enters the new/existing broker
   credential securely locally. Create the missing account or explicitly enable
   a prepared disabled standard account after approval, then review/grant the
   account-specific batch-logon right when missing (never override denial),
   install/protect the pinned runtime/config and register the two fixed tasks.
   Setup-GNETBroker.ps1 alone must not be assumed to enable an existing disabled
   account; the deployment orchestrator needs an explicit verified transition.
4. Install/configure the ordinary-user command center and agent gateway with
   installation-relative paths and matching pinned release. Verify actual MCP
   tool exposure; settings alone are not a connected tool catalog.
5. Audit deployment metadata and run installed-account synthetic jobs covering
   request execution, reports, feature/label bridge, training/scoring, replay,
   cancellation/restart and isolation. Keep unavailable/failed/untested gates
   visible. Only then consider separately authorized real-data admission.

The agent can prepare/verify the packet, generate plans/commands, install ordinary
client files, discover tools and run authorized synthetic jobs. The human must
approve privileged account/task/permission transitions and supply credentials
locally. No remote access to the customer's computer is available here.

No deployment, account enabling, batch right, task registration, customer data
admission, migration, model training or live trading was performed by recording
these next steps. Human and agent must use the same reviewed deployment boundary.

## Operational deployment status checked in this session

- Protected computation, command-center UI and MCP gateway code exist. The
  installed v9 development-machine report documents actual synthetic training/
  scoring through Task Scheduler and both browser/MCP. That evidence does not
  certify a new customer or the later v16 deployment candidate.
- Current local MCP exposure contains 36 GNET tools. A real gnet_client_health
  call returned client v13-preparation, configured broker v16-source-workbench,
  assets passed, and broker_execution_verified=false / isolation_certified=false.
  This confirms local gateway communication only, not customer connectivity or
  protected execution. No market-data records were read.
- A refreshed operational deployment packet has not been delivered. The earlier
  combined packet pins v10 and should not be presented as the latest delivery.
- Before delivering it, correct the older Install-GNETSystemBroker.ps1 resolver:
  it still hardcodes the direct LocalAccounts manifest rejected on the customer.
  Add explicit, approved handling of a prepared disabled account; the current
  sequence rejects it. Existing Install-GNETBrokerRelease.ps1 also creates its
  own release venv and installs its lock; do not promise private environment reuse
  across preparation/deployment without implementing and testing that path.
- Then test complete fresh deployment orchestration, dependency handling,
  current matching release/config identities, cancellation/resume and generated
  customer-specific commands. Privileged acceptance must run on the actual target.
- Customer remaining gates: account creation, private runtime installation,
  permissions/batch right/tasks, active UI, MCP host registration/tool discovery,
  installed-account synthetic pipeline and cancellation/restart/isolation checks.
- Research beyond deployment still has separate unfinished final holdout/freeze
  and TS admission/policy gates. Do not equate operational broker deployment with
  completion of every research feature.
