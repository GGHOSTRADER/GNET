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

The EasyLanguage backups send or poll only on `LastBarOnChart`, log connection
loss/recovery only when state changes, and never replay historical chart bars
through TCP. `G_MA_CROSS_NN` also releases a pending candidate after its
configurable `CandidateTimeoutBars` limit.
