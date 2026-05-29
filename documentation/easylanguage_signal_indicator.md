# EasyLanguage Signal Indicator
> **What:** EasyLanguage indicator code that runs inside TradeStation and receives trade signals from the Python inference layer via `SignalBridge.dll` on every bar close.

Receives signals from `inference/signal_tcp_server.py` through `SignalBridge.dll` (compiled from `signal_dll.cpp`).

## EasyLanguage Code

```pascal
{ Receiving trade signals from Python inference layer via SignalBridge.dll }

using elsystem;

Inputs:
    DllPath("C:\Users\g_med\python_new\GNET\EL_files\SignalBridge.dll");

Vars:
    sig_symbol(""),   { output: ticker symbol }
    sig_int(0),       { output: 1 = buy, 0 = no trade }
    sig_prob(0.0),    { output: model sigmoid probability }
    ok(0);

{ EasyLanguage DLL declaration }
External: "C:\Users\g_med\python_new\GNET\EL_files\SignalBridge.dll", int, "RecvSignal",
    Lpstr,      { out: symbol  }
    int ref,    { out: signal  }
    double ref; { out: prob    }

{ Poll for a signal on every bar close }
If BarStatus(1) = 2 Then Begin
    ok = RecvSignal(sig_symbol, sig_int, sig_prob);

    If ok = 1 Then Begin
        { New signal received }
        If sig_int = 1 Then Begin
            { BUY signal }
            Buy next bar at market;
        End;
    End;
End;

{ Optional: plot the probability for debugging }
plot1(sig_prob, "prob", blue);
plot2(sig_int,  "signal", red);
```

## How It Works

- `RecvSignal()` returns `1` when a new signal line is available, `0` if nothing is ready yet
- The DLL maintains a persistent TCP connection to `127.0.0.1:9011` — connects once, stays open
- Non-blocking: if no signal has arrived since the last call, it returns `0` immediately without blocking the chart
- `sig_int = 1` means **buy**. `sig_int = 0` means no trade — do nothing

## Notes

- Apply this indicator to the **same bar chart** as the [[easylanguage_bar_indicator]]
- `signal_tcp_server.py` must be running and connected before TradeStation calls `RecvSignal()`
- The signal is keyed to the same bar that the model received features for — no look-ahead
- See [[how_to_compile_dll]] to compile `SignalBridge.dll`
- See [[how_to_run_pipeline]] for the full startup order
