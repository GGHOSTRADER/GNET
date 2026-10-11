# Automatic protected custody delivery

Recorded October 6, 2026. Implementation checkout:
`C:\Users\g_med\.codex\worktrees\guarded-research\GNET`, branch `codex/guarded-research`.

## Implemented and verified in development

- One fixed incoming root outside all source checkouts: `C:\GNET_Import\incoming`.
- Generic TradeStation indicator automatically allocates temporary export children using atomic Windows directory creation. Each run gets a distinct ID; earlier snapshots cannot be overwritten. The full source is generated once by the installed client with the fixed ExportInbox.
- Client pump checks bounded control metadata, queues closed deliveries and never opens market records. Human browser, typed CLI and MCP expose equivalent preparation, transfer, retry, status and synthetic-test controls.
- Protected broker snapshots and independently validates all source bytes. Valid sources enter private custody; closed invalid sources can enter private quarantine. Both retain exact original bytes without research admission.
- After a private receipt is committed and private hashes verified again, cleanup deletes exact opened Windows file objects and removes only the empty staging child. Open, changed, linked, unexpected or inaccessible files are preserved and reported for retry.
- Public receipts remain available after source staging disappears, including bounded symbol, interval, dates, clock, volume, price-basis and validation metadata. No source records, matrices or model weights are returned.
- Valid sources can subsequently enter the dataset catalog from private custody under a separately reviewed intake policy. Quarantine does not grant research eligibility.
- Reviewed setup protects both the dedicated import parent and root controls, pins the producer hash and reloads the existing ordinary-user client. It does not launch an elevated browser client, create an account or migrate earlier exports.

## Actual test evidence

- **223 synthetic regression checks passed in 45.34 seconds**.
- **38 focused final checks passed in 28.49 seconds**, including the final bounded receipt fields and installed client transport.
- One genuine local supervised broker worker processed **25 fabricated 30-second bars**. Expected and returned source SHA-256 matched; custody committed, staging removed, **zero active staging children**, no dataset registration, no research permission and no raw records returned.
- Three PowerShell scripts parsed successfully. The reviewed installer plan and `-Apply -WhatIf` paths passed without account, ACL, task or credential changes. Inbox JavaScript syntax check passed.
- Python imports and top-level definitions were checked against HEAD. Existing EasyLanguage methods were preserved. Synthetic tests do not compile EasyLanguage.

## Active and prepared versions

Browser/client **gnet-client-v9-auto-custody** is active at <http://127.0.0.1:9040/intake/>. Its fixed inbox is prepared with metadata controls only. The boundary is deliberately disabled until protected installation. MCP host transport was updated; a fresh initialized stdio session verified all **33 tools** and a read-only custody-status call. Refresh of this chat's injected tool catalog is unverified.

Protected broker remains **guarded-v10-ml-replay**. The compatible **guarded-v14-auto-custody** package is prepared and verified only. Protected activation and installed-account custody acceptance have not run. Full isolation certification is false. This new indicator's TradeStation Verify and chart lifecycle remain pending.

## Local deployment step

From Administrator PowerShell, run:

```powershell
& 'C:\Users\g_med\python_new\GNET\.artifacts\Run-GNETAutoCustodySetup.ps1'
```

The runner pins the reviewed package and producer hashes. Confirm its action, then enter the existing GNETDataBroker password locally. It activates the reviewed runtime and fixed incoming boundary, reloads the ordinary-user client, and runs one fabricated installed custody test with a bounded wait. It does not backtest, train, register real datasets or migrate earlier source files. A failed or untested result remains incomplete.

After successful deployment, paste and Verify:

`C:\Users\g_med\python_new\GNET\.artifacts\client-delivery-installed\GNET_Research_Export.els`

Keep AutoSessions=true, use the prefilled ExportInbox, MaxBarsBack=1 and Update value intra-bar. No manual per-run folder or local real-data finalizer is required in automatic mode. The indicator will refuse to write market rows while the protected boundary is disabled.

## Remaining work

Protected activation/installed acceptance and TradeStation platform testing remain pending. Continuous/other-instrument training policies, the TS report-to-label bridge, full isolation/crash certification and final evaluation remain separate unfinished gates. Prior releases, old export sessions, unrelated files, live trading and terminal hotkeys are preserved. Open/incomplete snapshots remain transiently staged until closure or explicit recovery; this delivery has not erased earlier real exports.

Evidence: `.artifacts/automatic-custody-delivery.json`, `.artifacts/automatic-custody-synthetic-drive.json`, `.artifacts/client-delivery-installed/v9-auto-custody-client-activation.json` and the guarded worktree progress log. No real market data was read by the agent in this task.
