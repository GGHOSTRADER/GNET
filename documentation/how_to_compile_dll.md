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

### ⚠️ Switch to the x86 (32-bit) toolchain

TradeStation is a **32-bit process** and can only load **32-bit (x86) DLLs**. The default "Developer Command Prompt" may launch the **x64** compiler (`cl ... for x64`), which produces a DLL TS reports as `Cannot find DLL library file` (it's actually a bitness mismatch, not a missing file).

If a dedicated "x86 Native Tools Command Prompt for VS" shortcut isn't available, switch the current prompt to x86 by running:

```bash
"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"
```

(Adjust the path/version if your Visual Studio install differs.) After running this, `cl /?` should print `for x86` instead of `for x64`.

---

## Step 4 — Compile the DLLs

### Preferred coordinated build

The four bridges share `fail_fast_socket.hpp`, so rebuild them together from
the repository root whenever that socket layer changes:

```powershell
.\EL_files\build_hardened.cmd
```

This selects the x86 toolchain and stages all four results under
`EL_files\build_hardened\`. Close TradeStation before copying the staged DLLs
over the active files in `EL_files`; Windows will not safely replace a DLL that
is loaded in `ORPlat.exe`.

The individual compiler commands below remain useful for isolated development.

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

### SignalBridge.dll — receives exact-candidate decisions from Python (port 9011)
```bash
cl /LD /EHsc signal_dll.cpp ws2_32.lib /Fe:SignalBridge.dll
```

### StrategyBridge.dll — sends candidates from every strategy window (port 9012)
```bash
cl /LD /EHsc strategy_dll.cpp ws2_32.lib ole32.lib /Fe:StrategyBridge.dll
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
| `SignalBridge.dll` | `signal_dll.cpp` | `9011` | Python → TS | `RecvDecision(instance_id)` |
| `StrategyBridge.dll` | `strategy_dll.cpp` | `9012` | TS → Python | `SendCandidate()` / `GetLastCandidateId()` |

---

## Notes

- All DLLs connect to `127.0.0.1`.
- The hardened socket layer uses non-blocking established sockets, caps each
  connection attempt at 2 ms, and waits 2 seconds after a failure before
  retrying. A missing Python endpoint therefore returns control to TradeStation
  instead of trapping its chart thread in a connection loop.
- The sender DLLs intentionally drop a payload when the endpoint or socket is
  unavailable; they do not create an unbounded queue inside TradeStation.
- `BarBridge` and `TickBridge` are persistent clients (connect once, stream data)
- `SignalBridge` queues decisions by strategy-instance ID and uses non-blocking recv — each window can retrieve only its own decision
- See [[how_to_run_pipeline]] for the correct start order

### Troubleshooting: "Cannot find DLL library file"

This usually means the DLL exists but is the **wrong bitness** (x64 instead of x86). Check with PowerShell:

```powershell
foreach ($f in "BarBridge.dll","TickBridge.dll","SignalBridge.dll","StrategyBridge.dll") {
    $bytes = [System.IO.File]::ReadAllBytes($f)
    $peOff = [BitConverter]::ToInt32($bytes, 0x3C)
    $machine = [BitConverter]::ToUInt16($bytes, $peOff + 4)
    "$f -> " + $(switch ($machine) { 0x014c {"x86 (32-bit)"} 0x8664 {"x64 (64-bit)"} default {"unknown"} })
}
```

All four DLLs must report **x86 (32-bit)**. If one shows x64, recompile it after running `vcvars32.bat` (see Step 3).
