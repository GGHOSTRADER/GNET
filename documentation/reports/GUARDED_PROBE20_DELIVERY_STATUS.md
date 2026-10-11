# Twenty-bar exporter delivery status

Recorded: 2026-10-06.

## Delivered

- Implementation checkout: `C:\Users\g_med\.codex\worktrees\guarded-research\GNET`, branch `codex/guarded-research`.
- Generic EasyLanguage exporter buffers and validates the first 20 completed historical bars, freezes the filename once, and preserves every buffered row in source order.
- Native chart metadata supplies symbol, bar type, interval and clock mode. Volume inference is restricted to repeated quantities greater than one on one-tick charts; ambiguous observations remain unknown.
- Browser/client release `gnet-client-v7-probe20` was activated successfully. The activation receipt confirms browser verification and MCP host configuration update; it does not confirm refresh of this chat's tool catalog.
- Recorded synthetic test gate: 132 passed in 37.13 seconds. Python imports and definition inventory checks passed. Synthetic tests do not compile EasyLanguage.
- Human and agent export guides document the twenty-bar decision and separate compile, closure, sealing, admission and training evidence.
- No real market data was read in this change.

## User source and controls

Full local source:
`C:\Users\g_med\python_new\GNET\.artifacts\ts-export-test-kit-367dae68\GNET_Research_Export.els`.

Replace the complete generic indicator source in TradeStation and Verify it again. Inspect existing indicator Inputs because TradeStation may retain prior values. On a research chart, `ProbeBars` should reach 20 and `NameFrozen` should become true. Fewer than 20 completed historical bars cannot publish a complete export. Compilation and chart lifecycle of this revision remain unverified.

Command center: <http://127.0.0.1:9040/research/>.
Export inbox: <http://127.0.0.1:9040/intake/>.
Stable manual launcher: `C:\Users\g_med\python_new\GNET\.artifacts\client-delivery-installed\Open-GNETResearch.cmd`.

## Remaining gates

- Protected broker remains `guarded-v10-ml-replay`.
- Compatible `guarded-v12-probe20` package is prepared only; activation and installed-account acceptance remain pending.
- New exporter TradeStation compilation, actual export closure and sealing remain pending.
- Protected incoming-folder policy and actual TradeStation bundle admission remain pending.
- Direct accepted TradeStation aggregate bars to matched primary-report/training-label bridge remains pending.
- Full isolation/crash-recovery certification and final testing remain pending.

## Approval-review interruption

The final elevated command to run the new client's MCP verification and append the delivery summary to worktree/installed progress files was not executed. Automatic approval review could not complete because its usage limit was reached. This was a review failure, not a finding that the command was unsafe. No alternate identity or execution route was used to bypass it.

Fresh v7 MCP verification and the final append to the guarded worktree progress log therefore remain pending. This file records the confirmed result within the writable main repository. Evidence: `.artifacts/probe20-delivery.json` and `.artifacts/client-delivery-installed/v7-probe20-client-activation.json`.
