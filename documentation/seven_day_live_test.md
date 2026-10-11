# Seven-Day Live-Market Simulation Test

This procedure runs MA2CrossLE against live ES market data for seven calendar
days in a TradeStation **simulation account**. It validates operational
stability and exact-candidate routing; it is not evidence of profitability.

## Before the test

1. Confirm TradeStation is connected to a **simulation account**. Never select
   a live account for this test.
2. Use a specific, currently active ES futures contract (for example,
   `ESZ26`), not the continuous `@ES` symbol. Confirm the chart title does not
   contain `(D)`: TradeStation uses `(D)` for delayed market data, which can
   leave **Automate execution using...** unavailable. Both the 30-second and
   tick charts must use the same specific contract.
3. Use one ES 30-second chart with `g_cpp_dll_bar` and `G_MA_CROSS_NN`.
4. Use one separate ES 1-tick chart with `g_cpp_dll_tick`.
5. Set `StrategyId=MA2CrossLE` and a unique `InstanceId`.
6. Use one contract, disable pyramiding, and keep the strategy's embedded
   `StopLossAmount` and `ProfitTargetAmount` at `$50 per contract`. Do not add
   separate protective strategy components.
7. In TradeStation Strategy Properties, set **Commission** to **$ per
   Share/Contract** and enter **$3.24**. This is the September 2026 published
   all-in estimate per side for one CME ES contract in TradeStation's 0-500
   monthly-contract tier: $1.75 commission + $0.10 clearing + $1.38 CME ES
   exchange fee + $0.01 NFA fee. TradeStation applies it on entry and exit, so
   the modeled round trip is $6.48. An actual account execution confirmation
   overrides this estimate if the account has legacy, negotiated, or
   volume-tier pricing. Keep Position Slippage at $0 for this test so fees and
   execution slippage remain separately measurable.
8. Keep `ShowDecisionMarkers=true`: green `YES` marks approval, red `NO` marks
   normal rejection, and yellow `ERROR` marks a non-`ok` router result. Each
   label has a same-color line back to the exact decision bar; the Print Log
   retains the full router status.
9. Verify the enabled registry entry uses threshold `0.50`, device `cpu`, and
   stream `features_transformer`.
10. Launch GNET before enabling any TradeStation components:

```powershell
cd C:\Users\g_med\python_new\GNET
.\launch_grid.ps1
.\check_gnet_ports.ps1
```

All four ports must be ready. Then enable the bar indicator, tick indicator,
and strategy in that order. Allow 60 new 30-second bars for warm-up.

After warm-up, open **Studies > Edit Strategies**, select `G_MA_CROSS_NN`,
and check **Automate execution using...** with the simulation account selected.
Use confirmation **On** for manual confirmation or **Off** for unattended
simulation execution. This setting affects only future signals and must remain
disabled if the selected account is not explicitly a simulation account.

Keep the computer connected to power and configure Windows not to sleep during
the run. Screen lock is acceptable; sleep, hibernation, Windows restart, Docker
shutdown, or a TradeStation logout interrupts the observation window and must
be recorded. Start the seven-day recorder only after the 60-bar warm-up so
expected warm-up rejections are not mixed into the measured period.

## Start the seven-day evidence recorder

Open a separate PowerShell terminal and run:

```powershell
cd C:\Users\g_med\python_new\GNET
.\start_live_test.ps1 -SimulationConfirmed
```

The explicit switch is a safety acknowledgement, not an account check. The
operator must personally verify the TradeStation account is simulated.

The observer creates `live_test_runs/<timestamp>/` containing:

- `run_manifest.json`: start/end plan, registry hash, and initial Redis IDs;
- `heartbeat.csv`: Redis/router/port state, stream lengths, and pending counts;
- `events.jsonl`: every new candidate and decision with its exact GUID;
- `summary.json`: approvals, rejections, statuses, and latency percentiles.

It does not connect to the GNET TCP ports and cannot take the DLL client slots.
It never submits or changes orders. Pressing `Ctrl+C` stops only the observer.

## Daily review

At least once each trading day:

1. Confirm ports 9009-9012 remain ready.
2. Confirm `redis_ok=1` and `router_ready=1` in the newest heartbeat.
3. Confirm bar, raw-tick, validated-tick, and feature stream lengths advance.
4. Check `summary.json` for `missing_features`, `inference_error`, or
   `unknown_strategy`. Any occurrence requires investigation.
5. Match every TradeStation candidate GUID to one Redis decision and its
   TradeStation log result.
6. Record simulated order ID, entry, exit, stop/target behavior, and P&L in a
   separate daily note or TradeStation export.
7. Capture any TradeStation disconnect, chart reload, service restart, or
   manual intervention with local time and reason.

Weekends and the ES maintenance break can legitimately produce no events.
Absence of market activity is not a pipeline failure if health heartbeats stay
valid and streams resume afterward.

## Immediate stop conditions

Disable the TradeStation strategy before investigating if any of these occur:

- an order is created for a rejected, missing, or unmatched GUID;
- more than one order is created for one approved GUID;
- position size exceeds one contract or pyramiding occurs;
- the stop loss or profit target is absent from an open position;
- TradeStation becomes unresponsive;
- a decision is delivered to the wrong `InstanceId`;
- repeated `missing_features`, inference errors, or port loss occurs.

Use `Ctrl+C` to stop the observer. Use `stop.ps1` only when the pipeline itself
must be stopped:

```powershell
.\stop.ps1 -StopTradeStation
```

## Pass criteria after seven days

- No incorrect or duplicate routed order.
- Every observed candidate has one exact decision.
- All `status=ok` decisions reach the matching TradeStation instance.
- No unexplained pending decision remains after TradeStation acknowledgement.
- Protective stop and target are present for every simulated position.
- TradeStation remains responsive through ordinary reconnects.
- No unresolved inference error, unknown strategy, or persistent missing
  feature condition.
- The run folder and TradeStation order/trade export are retained together.

Model profitability is reported separately and is not a technical pass/fail
criterion for this operational test.
