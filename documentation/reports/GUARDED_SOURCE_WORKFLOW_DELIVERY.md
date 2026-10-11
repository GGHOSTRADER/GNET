# Source workflow and received TS primary trade viewer

## Delivered browser controls

Current client: **gnet-client-v12-source-workflow** on <http://127.0.0.1:9040/research/>.
The source inventory combines received deliveries and registered raw datasets.
It joins only exact export IDs AND source hashes. Fabricated tests are hidden by
default. Each card shows received,registered and approved-process statuses.

An always-visible legend explains the stages and their triggers. Expand
**Register using a reviewed approval policy**,provide an existing protected policy
ID,and press **Register & apply reviewed policy**. The agent uses the same
`gnet_ingest_ts_export` job. Protected policy authoring still requires a reviewer;
there is no client/agent action to grant it. Current @ES remains in custody,
unregistered/unapproved,with continuous-series and metadata/platform review gaps.

The real source card has **View TS primary trades**,linking directly to:
<http://127.0.0.1:9040/ts-trades/?export_id=ts-20261006095824-116733298-847437971>.
It displays the exact received source and910 closed positions,then checks the
installed broker capability. V15 lacks the detailed viewer;the UI explains this
upgrade gate. The entry point itself does not admit data or fit a model.

## Implemented native viewer

New `ts_primary_trade_view` / `gnet_ts_primary_trade_view` publishes at most20
curated positions per page and500 original chart bars (default200) from a verified
private custody snapshot. It supports combined entry-date,outcome and net P&L
filters,selected-position candles/close line,actual timestamp labels,signal/entry/
exit markers on exact bar observations,outcome colors and matching duration lane.
Unknown clocks and unverified platform fill/cost/bar-magnifier evidence remain
explicit. Its public JSON exposes counts and a report reference,not trade rows.
No arbitrary paths,full trade table or client CSV read is introduced.

23 new synthetic native-view tests passed;focused regression total**114 passed
in53.92 seconds**. Existing8 card-presentation checks,exact source-ID/hash merge
checks and native SVG alignment checks passed. Candle/line/fill/duration positions
and irregular actual timestamps were tested. Scripts passed Node syntax checks;
imports and top-level definition inventories were preserved. New/untracked modules
have no HEAD baseline. Existing publisher path/output restrictions remain intact.

One actual supervised LOCAL synthetic worker job published a2-position/13-chart-
point native report. This is fabricated developer acceptance,not installed-account
or real-source acceptance. Preview:
<http://127.0.0.1:9052/reports/job-20261006T152659Z-bff02c950faf48a0b676bed0bb295fb1/native_trades.html>.

## Protected deployment still required

Installed protected broker remains **guarded-v15-primary-trades-r2**. Prepared
and verified: **guarded-v16-source-workbench**,132 source files,dependency identity
unchanged. Manifest SHA256:
`06273ac5f02c507d61c6f5d13b8fba9e4f7b0ad49a88a7073d16ff578d001a10`.
Client package:75 files,manifest SHA256:
`b21bacfa2faf8078bc69df1840cc5ad02a20caedfb0f6f695b0465d2c1e4221b`.

The combined upgrade uses native Task Scheduler registration with explicit local
credentials,preserves task principal/settings/triggers/ACLs and existing custody/
intake policies,changes only reviewed runtime/config/task actions/boundary pin,
requires complete metadata audit,and requests one bounded read-only view for the
named export. Failed activation attempts restore prior definitions/configuration
when possible;failure or rollback uncertainty is recorded. Prior releases remain.

Administrator PowerShell:

```powershell
& 'C:\Users\g_med\python_new\GNET\.artifacts\Run-GNETSourceWorkbenchUpgrade.ps1'
```

ConfirmY and enter the existing broker password locally. No new account,ACL grant,
dataset admission,training,real-data backtest or source migration is requested.
Plan,WhatIf and parsing passed. Actual privileged Apply/rollback and installed
native viewer acceptance remain untested until the operator runs it. Full account
isolation/platform/final testing remain incomplete. The audit ceiling500000/1200
reflects190182 already retained objects plus another ML venv;defaults unchanged,
and an incomplete scan still fails. No runtime ACL audit scope was removed.

## Human and agent instructions

Client help: <http://127.0.0.1:9040/help/source-lifecycle.md>.
Source guide:guarded `documentation/guides/GNET_TS_SOURCE_LIFECYCLE.md`.
Configured stdio gateway verified**36 tools** and read-only custody status on the
matching v12 client. Current chat injection refresh remains unverified;use typed
CLI fallback when needed. Browser and agent use identical policy/release gates.
Human guide,agent guide,primary guide and guarded agent entry point link the new
lifecycle instructions. Stable open-command-center launchers follow active config.

Evidence:main `.artifacts/source-workflow-client-activation.json`,
`source-workflow-packages.json`,`native-view-demo-receipt.json`,
installed-root `v12-source-workflow-mcp-verification.json`. Installed-account
deployment receipt will be guarded `.artifacts/guarded-v16-source-workbench-admin.json`.


## Final source workflow state — October6,2026

Active clientv12-source-workflow verified in browser:always-visible received/
registered/approved legend,one source inventory,reviewed-policy admission control
and direct received TS trade link. Configured stdio36 tools verified;chat injection
refresh unverified. Existing source recipes/registered profiles remain separate
from process approvals. Review-policy authoring controller is still not implemented.
Actual @ES has910closed positions in custody,not registered/approved/trained.

Installed brokerv15 retained. Final prepared v16 review:
06273ac5f02c507d61c6f5d13b8fba9e4f7b0ad49a88a7073d16ff578d001a10,132files,dependency identity unchanged.
Earlier prepared reviews preserved and superseded. The one admin runner points
to the final reviewed package. Privileged install/rollback and actual real-data
viewer acceptance remain pending;no claim of those gates complete.

114focused regressions passed53.92sec;23native tests passed after publication/
pagination/unresolved-position corrections.8card checks and exact ID/hash joins
passed. SVG tests verify candle/line/signal/fill/duration alignment,irregular actual
timestamp labels,requested page size,unresolved exits without false endpoints,and
the narrow in-app viewport. Parser/plan/WhatIf passed for reviewed installer;
expanded read-only audit bounds retain incomplete-scan failure.

Final supervised local synthetic viewer2positions/13points published,then verified
in browser with explicit FABRICATED TEST DATA label. Final demo:
http://127.0.0.1:9052/reports/job-20261006T162220Z-b8e9193f4fa74c77bd429e9a5b6354fc/native_trades.html.
Screenshots:main.artifacts/source-workflow-legend.jpg and
native-ts-viewer-synthetic-preview.jpg. Guide:/help/source-lifecycle.md.
Evidence:main.artifacts/source-workflow-final-delivery.json.
No real CSVs/ledgers/matrices/models were read by the agent,no live/hotkey/ACL or
policy grant,no data migration,real backtest or training run. Full isolation,
source/platform/continuous mapping and final testing remain incomplete.
