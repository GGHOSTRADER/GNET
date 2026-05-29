# How to Compile the TradeStation DLLs
> **What:** Step-by-step guide to compile C++ DLLs using Visual Studio and wire them up in TradeStation.

---

## Step 1 — Download Visual Studio Community

- Go to: https://visualstudio.microsoft.com/vs/community/
- Download and run the installer

---

## Step 2 — Install the C++ Package

- In the Visual Studio Installer, check **"Desktop development with C++"**
- Click Install
- Wait for it to finish (~5GB)

---

## Step 3 — Open Developer Command Prompt

- Press the **Windows key**
- Search for **"Developer Command Prompt"**
- Click to open it

> This is NOT regular PowerShell — it has the compiler paths set up automatically.

---

## Step 4 — Compile the DLLs

Navigate to the EL_files folder, then compile whichever DLL you need:

```bash
cd C:\Users\g_med\python_new\GNET\EL_files
```

### BarBridge.dll — sends bar data from TradeStation to Python (port 9009)
```bash
cl /LD /EHsc dll.cpp ws2_32.lib /Fe:BarBridge.dll
```

### TickBridge.dll — sends tick data from TradeStation to Python (port 9010)
```bash
cl /LD /EHsc tick_dll.cpp ws2_32.lib /Fe:TickBridge.dll
```

### SignalBridge.dll — receives trade signals from Python to TradeStation (port 9011)
```bash
cl /LD /EHsc signal_dll.cpp ws2_32.lib /Fe:SignalBridge.dll
```

You should see output ending with:
```
Creating library <Name>.lib and object <Name>.obj
```

The `.dll` file will appear in the `EL_files` folder.

---

## Step 5 — Apply the EasyLanguage Indicator

1. Open TradeStation EasyLanguage Editor
2. Create a new indicator
3. Paste the code from the relevant indicator doc:
   - Sending bars → [[easylanguage_bar_indicator]]
   - Sending ticks → [[easylanguage_tick_indicator]]
   - Receiving signals → [[easylanguage_signal_indicator]]
4. Save it and apply it to a chart

Make sure the `External` path in the indicator points to the compiled `.dll`, not the `.cpp` source.

---

## DLL Summary

| DLL | Source | Port | Direction | Function |
|---|---|---|---|---|
| `BarBridge.dll` | `dll.cpp` | `9009` | TS → Python | `SendBar()` |
| `TickBridge.dll` | `tick_dll.cpp` | `9010` | TS → Python | `SendTick()` |
| `SignalBridge.dll` | `signal_dll.cpp` | `9011` | Python → TS | `RecvSignal()` |

---

## Notes

- All DLLs connect to `127.0.0.1` — Python processes must be running before TradeStation loads the DLL
- `BarBridge` and `TickBridge` are persistent clients (connect once, stream data)
- `SignalBridge` is a persistent client that uses non-blocking recv — returns 0 immediately if no signal is ready, 1 when a signal arrives
- See [[how_to_run_pipeline]] for the correct start order
