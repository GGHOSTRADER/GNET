# TradeStation primary trades delivery

Recorded October 6, 2026. Source: `C:\Users\g_med\.codex\worktrees\guarded-research\GNET`, branch `codex/guarded-research`.

## Delivered implementation

A strategy can write its own files and metadata. This implementation provides a separate **GNET_Primary_Research_Export Strategy** with a historical MA crossover primary and combined export. It uses native EntryPrice/ExitPrice and EntryDateTime/ExitDateTime, captures explicit signal and execution-bar references, and exports its own bars, position ledger and complete rule/settings metadata in one snapshot. It cannot serve as a passive reader of another strategy. Custom primary code needs instrumentation in a reviewed research copy and an appropriate rule adapter.

Source defaults: close SMA fast9/slow18, long enabled, short disabled, one unit,4-tick target/stop,20-bar hold, declared cost0, continuous history. These are routine example settings. The source blocks automation and real-time order generation, fixes IOG=false and leaves platform fill-time, cost/slippage and bar-magnifier evidence unverified. It preserves the existing live strategy and services.

Versioned session3/producer3/bundle5 bind native trades to the exact bar snapshot. The broker independently validates identities, sequence, next-bar entry, crossover signals, occupancy, clocks, native price grid, OHLC fill bounds, quantity and fill-derived gross/cost/net P&L. Open and terminal-boundary positions are unresolved for training; zero-trade exports remain valid. Both payloads enter protected custody/quarantine with exact staging cleanup and bounded receipts.

The protected ID-only `prepare_ts_primary_source` job requires an accepted dataset and an existing protected review that pins bundle/code/settings/platform/cost/cutoff identities. It creates a private training_source artifact. Existing `build_training_dataset` in tradestation mode now supports the native contract: explicit signal-row causal MA13 features,60-bar warm-up, conservative exit-bar t1 and binary net-profit labels. It retains warm-up/open/boundary/cutoff reasons. Model fitting and final holdout remain separate actions.

## Verification

- **197 synthetic regression checks passed in61.21 seconds**.
- **62 focused final checks passed in35.92 seconds**, covering the final native comparison tolerance, reviewed feature/label path and client transport.
- Full synthetic accepted native source -> protected reviewed training_source -> training_dataset passed, with one positive and one negative net label.
- Existing definition inventories/imports were preserved. Native source is a new separate file. The installer WhatIf path and inbox JavaScript syntax passed.
- Initial fixture failures concerned crossover directions, a missing fixture release and a workspace outside its protected fixture root; they were corrected without loosening production checks.
- No real trades/bars/ticks/matrices were read by the agent; no model was fitted in this task.

## Actual deployment state

Active client: **gnet-client-v10-primary-trades-r2**. Browser: <http://127.0.0.1:9040/intake/>. Human and agent controls prepare the full Strategy and queue matched source preparation. Typed CLI fallback: `client_entry.py --config <installed config> prepare-primary`.

The installed configuration advanced to **guarded-v14-auto-custody** during this work. Bounded public receipts showed a fabricated custody delivery stored and staging removed under v14. That deployment is preserved. Its client config had a PowerShell UTF-8 BOM; the activation reader was corrected. Health now uses the live reloaded release rather than an old captured value.

Prepared only: **guarded-v15-primary-trades-r2** with the new trade contract and ML bridge. The primary producer hash is a review draft in the ordinary-user client root; its active inbox control/policy was not overwritten. Protected primary activation, installed native trade acceptance, TradeStation compilation/lifecycle and actual fill/report comparison remain pending. Full isolation remains uncertified.

## Local next step

From Administrator PowerShell:

```powershell
& 'C:\Users\g_med\python_new\GNET\.artifacts\Run-GNETPrimaryExportSetup.ps1'
```

This reviewed upgrade pins both the existing bar producer and the new primary Strategy producer. Credential entry stays local. It does not register real research datasets, migrate old sources, fit a model or activate live trading. Do not use the older v14 runner for the primary extension.

Then create a new **Strategy** in TradeStation and paste/Verify:

`C:\Users\g_med\python_new\GNET\.artifacts\client-delivery-installed\GNET_Primary_Research_Export.els`

Use a separate research chart and check the actual inputs; retain automation OFF, MaxBarsBack=1 and fixed ExportInbox. If the intended primary is a different strategy, use a reviewed research copy and integrate the export hooks with its actual rules. Do not relabel another rule as this MA crossover template.

## Limits and remaining gates

Custody supports generic chart symbols, but the current native MA13 training contract still requires reviewed individual ES,30-second bars,trade volume,unadjusted prices,one contract and multiplier50. Custom strategies, scaling/partial fills/reversals/IOG and other-instrument training mappings need separate adapters. Native position datetimes do not prove tick-level fill timing or first barrier touch. Independent triple-barrier labels and actual trade exit outcomes remain separate.

Human/agent instructions: `GNET_TS_PRIMARY_TRADES.md` in the installed client root and browser <http://127.0.0.1:9040/help/ts-primary-trades.md>. Exact package/hash/status evidence: `.artifacts/native-primary-delivery.json`. All pending/untested gates remain incomplete in durable progress.

## Reported runtime at 09:52:23

The user's Strategy reached GnetAutoSession and reported file not found. Bounded filename/release checks confirmed v14 remains active, the bar/bootstrap and custody controls exist, the primary bootstrap `.gnet-primary-exporter.txt` is absent, and its reviewed draft exists in the client root. The v15 primary upgrade has not been activated. No market file was opened or changed. Run the reviewed primary setup runner locally, then recalculate the research Strategy. This runtime report demonstrates execution beyond the MaxBarsBack guard; it does not verify the full compiled source hash or export lifecycle.


## Actual export check — October 6, 2026, after primary setup

Metadata-only inspection found one real closed combined primary delivery:
`ts-20261006095824-116733298-847437971`. Source `@ES`,30-second bars;
producer reports29,466 completed rows,2026-09-21T18:00:30 through
2026-10-06T09:47:30. Named bars2,801,108 bytes and native ledger129,978 bytes
are staged,with settings and producer completion. No real CSV/ledger content
was opened. The settings declare fast9/slow18,long-only,one unit,4-tick
target/stop,20-bar holding,declared cost0;these remain declarations awaiting
protected row validation. Filename reports LOCAL,VUNK,PUNK;clock IANA,volume
and price basis remain undeclared. Continuous @ES training mapping is pending.
No separate bar-only indicator delivery was found in the configured fixed inbox;
the primary Strategy itself includes its own matching bars.

Client/configured boundary now pin guarded-v15-primary-trades-r2 and primary
bootstrap exists. HOWEVER both actual task actions still point to
guarded-v14-auto-custody. ResearchRun last result2,Ready;the25-row fabricated
setup acceptance and real primary custody job remainqueued. Private config and
runtime inspection was denied by OS permissions;v15 protected package/config
cannot be certified from this check. Client release labels are not proof of task
activation. Real source custody/cleanup,installed acceptance,admission and ML
remain incomplete. No real backtest or training was run.

Prepared focused recovery: main-root
`.artifacts/Repair-GNETPrimaryTaskActions.ps1 -Apply` in Administrator PowerShell.
It verifies the reviewed v15 runtime and protected config,requires existing idle
limited/password-logon GNETDataBroker tasks,changes only their actions,checks
identity/settings/triggers/ACL preservation,requires deployment audit pass,
then resumes existing queued custody. If preconditions fail,it stops;no claim of
installation or validation is made. Parse,plan and WhatIf passed;actual privileged
Apply remains untested. Microsoft supports action-only task updates:
https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/set-scheduledtask

Setup and automatic-custody installer source now independently assert exact task
interpreter,arguments and working directory before reporting activation/enabling
the producer boundary.10 mocked valid/mismatched-action cases passed;existing
setup plan/WhatIf regression1 passed. Available HEAD function inventory unchanged;
automatic-custody installer is untracked and has no HEAD baseline. Immutable
installed releases were not edited. Evidence:
`.artifacts/primary-export-check-20261006.json`. Existing source changes/releases
and public staging are preserved;no account/task/ACL mutation was performed.

## Primary task repair credential correction — October 6, 2026

The operator's first privileged repair verified the reviewed v15 package, then
Set-ScheduledTask returned HRESULT0x8007052e. The repair supplied no password;
this error does not establish that the operator entered an incorrect password.
The task action postcondition rejected the unchanged launch and queued jobs were
not resumed. Activation/custody/native trade validation remain incomplete.

Corrected main-root .artifacts/Repair-GNETPrimaryTaskActions.ps1 now prompts
locally for the existing GNETDataBroker PSCredential after runtime/task checks.
It resolves the supplied account SID against BOTH existing task principals before
any update. The new Set-GNETReviewedTaskAction helper passes the password directly
to the local Windows cmdlet with explicit ErrorAction Stop and clears its temporary
reference in finally. No credential is placed on a command line, sent to the
client API, serialized, or printed. Existing principal/settings/triggers/ACL
postconditions and the audit gate before task start remain enforced.

Verification: PowerShell parser passed; plan and Apply-WhatIf passed without
credential prompts/provisioning. Mocked success verified password forwarding and
no output. Mocked nonterminating authentication error became terminating, preventing
continuation. No actual task/account/ACL changes or market reads were performed.
The standalone repair script is an untracked artifact with no HEAD baseline; its
definition inventory deliberately adds one helper. Actual privileged Apply with
local human credential entry remains pending. Prior immutable releases unchanged.

Rerun the same repair command in Administrator PowerShell, confirm Y, and enter
the existing GNETDataBroker password in the local credential prompt. Do not
re-export existing completed snapshots while their queued transfer is pending.


## Native task update revision — October 6, 2026

Second operator repair attempt verified v15 but Set-ScheduledTask failed with
HRESULT0x8007025c (invalid variant structure). Task start/audit did not execute.
Native Scheduler metadata inspection confirmed BOTH tasks remain Ready,v14,
password logon1,limited runlevel0,one executable action0,account GNETDataBroker.
Public transfer receipts still show synthetic acceptance and primary delivery
queued. No native trade validation/custody completion is asserted.

The focused repair now replaces the CIM Set-ScheduledTask update with the native
TaskFolder.RegisterTaskDefinition call. It copies the existing definition and
changes only executable/arguments/working directory;passes original account,
local password,logon1 and original SDDL explicitly. Flags52 combine UPDATE4,
DONT_ADD_PRINCIPAL_ACE16 and IGNORE_REGISTRATION_TRIGGERS32. Existing tasks only;
no task creation,new rights,principal upgrade or triggered registration run.
The same account-SID checks,package/config verification,post-update definition/
ACL checks and deployment-audit gate remain. Credential input stays local;no
API/log/command-line credential is generated. Invalid native preconditions or
registration failure stop before the queued jobs are resumed.

Source reference:
https://learn.microsoft.com/en-us/windows/win32/taskschd/taskfolder-registertaskdefinition
The exact underlying CIM parameter-conversion cause has not been established;
the native path avoids that update call. It does not establish password validity.

Verification: parser/Apply-WhatIf passed;8 synthetic native mock cases passed
(success,authentication failure,running task,wrong logon,elevated principal,
multiple actions,non-executable action,missing user). Success emits no credential
or registration object;failure prevents continuation;unchanged settings/triggers
and original ACL plus registration flags/explicit credentials verified. Native
read-only Scheduler access was verified against the two actual task definitions.
Actual privileged RegisterTaskDefinition remains untested until operator reruns
the same main-root .artifacts/Repair-GNETPrimaryTaskActions.ps1 -Apply command.
Repair script has no HEAD baseline;one helper function is retained with revised
parameters/body. Immutable packages and market exports unchanged.


## Actual v15 task repair success; audit capacity gate — October 6, 2026

Operator output and subsequent independent native Scheduler metadata confirm both
DataReport and ResearchRun now launch guarded-v15-primary-trades-r2 with exact
entry/config arguments and working directory. The operator's task identity,
settings,triggers and ACL postconditions passed. Native registration is now
installed-account tested successfully;earlier task-update errors are resolved.

Deployment audit remained incomplete:50,000-object cap reached after84.743seconds
while scanning retained runtime releases. No findings observed,but later scopes
were not checked. No assertion of audit pass/full isolation is made. Existing
queued synthetic25-bar acceptance and real primary export remain queued;no raw
records opened or protected primary row validation performed by this agent.
ResearchRun last_result2 is the prior run result,not evidence of a new v15 run.

The focused repair now uses the already documented ML/replay audit bounds:
MaximumObjects200000 and MaximumSeconds600. Same scopes and invariants;no checks
removed or permission broadening. Both task actions are compared before credential
entry;already-correct actions bypass credentials and registration entirely. Rerun
of the same Apply command should only finish the metadata audit and,if it passes,
start ResearchRun to process the existing custody queue. An incomplete/failed
audit still stops before task start. No reinstall or re-export required.

Verification: parser/WhatIf passed;explicit audit plan returned200000/600 bounds.
Eight existing native mock cases passed plus already-correct task gate check:
zero credential calls or task registrations. Helper definition inventory unchanged
(one function;untracked script has no HEAD baseline). Actual expanded privileged
audit and subsequent v15 custody validation remain pending. No OS settings/tasks/
ACLs or market records were changed by these development checks.



## Installed v15 native primary custody acceptance — October 6, 2026

Operator repair rerun returned audit_passed=true,task_actions_verified=true,
task_actions_updated=false and queued_custody_resumed=true. No new account or
permission changes reported. Independent bounded public broker report confirms
handoff_ts_export published with validation_status=pass under v15-primary-trades-r2.

Real combined primary delivery ts-20261006095824-116733298-847437971 is stored in
protected custody;bar row contract passed,29,466 verified30-second @ES bars and
910 received/closed native trades,zero open and boundary trades. Exact bar parent
passed;MA-cross signals independently verified;trade contract passed. Bundle SHA:
770484af1437095495247fc6d010eee6672f08ea0b6e220868f1027e06bfa28d.
Settings SHA:beb2f0c8e18a62c3df07d78526b253ec4ef136b83de48223712d0f14c2818c43.
The broker reports custody_committed=true and staging_cleaned=true. Client inbox
contains zero active deliveries;raw_records_returned=0. Original private custody
is retained. No agent CSV/ledger read occurred.

Installed25-fabricated-bar acceptance qa-53c01ecab9364c73a2b4bdff96cae085 also
stored under v15 with contract pass and staging cleanup. Thus installed custody
and this actual native trade-contract validation now have completed evidence;
prior prepared/queued notes are superseded for these specific gates.

NOT completed:research admission,dataset registration,label review/model training,
complete platform fill/bar-magnifier/cost acceptance,full account crash/restart
isolation,final holdout. This source iscontinuous @ES,chart clock mode0(Local),
unknown IANA timezone,volume mode and price basis;training_ready=false. Existing
native MA13 training policy remains reviewed individual ES30 only;continuous-
series training requires further supported mapping/review. No metadata is inferred
or rewritten and no trade timestamps/costs are certified from producer claims.
Source approval and explicit protected label/fill/cost/cutoff review are separate
from custody. No real-data backtest,feature build,fit or score was triggered.

Latest evidence:main .artifacts/primary-installed-custody-success.json.
Browser receipts:http://127.0.0.1:9040/intake/. One combined primary delivery was
observed;no separate bar-only indicator delivery has been established.
