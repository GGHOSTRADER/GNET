# TradeStation EasyLanguage Backups

These files mirror the exact document names saved in TradeStation:

| TradeStation document | Type | Repository backup | DLLs |
|---|---|---|---|
| `G_MA_CROSS_NN` | Strategy | `G_MA_CROSS_NN.els` | `StrategyBridge.dll`, `SignalBridge.dll` |
| `g_cpp_dll_bar` | Indicator | `g_cpp_dll_bar.els` | `BarBridge.dll` |
| `g_cpp_dll_tick` | Indicator | `g_cpp_dll_tick.els` | `TickBridge.dll` |

Paste the matching `.els` file into its same-named TradeStation document when
restoring or updating a component. All `External:` paths currently target:

```text
C:\Users\g_med\python_new\GNET\EL_files
```

`g_cpp_dll_bar` retains the saved document's unused `DllPath` input pointing to
`dll.cpp`; the actual DLL loaded by EasyLanguage is the `BarBridge.dll` path in
its `External:` declaration.

## Hardened bridge behavior

All four C++ bridges import `fail_fast_socket.hpp`. Failed connections are
retried at most once every two seconds, connection attempts are bounded to two
milliseconds, established sockets are non-blocking, and a busy DLL lock returns
immediately to TradeStation. Run `build_hardened.cmd` to stage a coordinated x86
build, then close TradeStation before installing the staged DLLs.

`SignalBridge.dll` also sends an exact application acknowledgement only after
`RecvDecision(instance_id)` hands a queued candidate to EasyLanguage. The Python
signal server keeps that Redis decision pending until it receives the matching
instance and candidate GUID, so a socket disconnect cannot silently lose it.

The EasyLanguage bar backup sends one bounded bootstrap pass whenever the chart
initializes or is reloaded with Ctrl+R, then sends only newly completed
`LastBarOnChart` bars. Configure the 30-second chart to load 65 bars. Bootstrap
messages rebuild feature state but cannot create TradeStation strategy candidates.

The remaining EasyLanguage backups send or poll only on `LastBarOnChart`, log connection
loss/recovery only when state changes, and never replay historical chart bars
through TCP. `G_MA_CROSS_NN` also releases a pending candidate after its
configurable `CandidateTimeoutBars` limit.

`G_MA_CROSS_NN` contains the filtered entry plus TradeStation's built-in
`SetStopLoss` and `SetProfitTarget` protection, both defaulted to **$50 per
contract** for ES (one index point). Do not apply separate protective strategy
components on the same chart. The repository backup intentionally contains no
explicit `EntryPrice +/-` next-bar exit orders because those produced incorrect
next-open historical fills.

The strategy also draws an optional live marker on the bar where EasyLanguage
receives an exact decision: green `GNET YES` for approval, red `GNET NO` for a
normal model rejection, and yellow `GNET ERROR` for a non-`ok` router status.
The marker includes probability for normal decisions. Control it with
`ShowDecisionMarkers` and `DecisionMarkerOffsetPoints`; markers visualize live
decision receipt and are not reconstructed from historical bars.

## Intrabar execution versus historical tick reconstruction

`G_MA_CROSS_NN.els` declares `[IntrabarOrderGeneration = TRUE]`. TradeStation
may consequently show Intrabar Order Generation as already selected. Preserve
that declaration for live trading; it lets the strategy poll for an ML decision
and manage state between 30-second bar closes.

IOG is not the same as either of these Strategy Properties settings:

- **IOG optimization with Look-Inside-Bar** only reduces redundant historical
  calculations. It does not enable IOG or provide historical ticks.
- **One-tick Look-Inside-Bar back-testing** supplies the historical tick order
  inside a bar and is the setting that can exhaust RAM over a multi-month range.

Protective stops intended to operate on the entry bar should use TradeStation's
built-in `SetStopLoss`/`SetProfitTarget` behavior or the equivalent prebuilt
strategy components. An explicit `Sell ... next bar ... stop/limit` order may
not protect the entry bar and can be filled at the following 30-second open
after price has moved far beyond one point. Never remove IOG merely to work
around Look-Inside-Bar memory use; shorten/chunk the historical range instead.
