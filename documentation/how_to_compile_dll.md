# How to Compile and Run the TradeStation DLL
> **What:** Step-by-step guide to compile `dll.cpp` into `BarBridge.dll` using Visual Studio and wire it up in TradeStation.

---

## Step 1 — Create the Indicator in TradeStation

1. Open TradeStation EasyLanguage Editor
2. Create a new indicator
3. Paste the contents of `el_dll.md` into it
4. Save it and apply it to a chart

---

## Step 2 — Download Visual Studio Community

- Go to: https://visualstudio.microsoft.com/vs/community/
- Download and run the installer

---

## Step 3 — Install the C++ Package

- In the Visual Studio Installer, check **"Desktop development with C++"**
- Click Install
- Wait for it to finish (~5GB)

---

## Step 4 — Open Developer Command Prompt

- Press the **Windows key**
- Search for **"Developer Command Prompt"**
- Click to open it

> This is NOT regular PowerShell — it has the compiler paths set up automatically.

---

## Step 5 — Compile the DLL

Run these two commands in the Developer Command Prompt:

```bash
cd C:\Users\g_med\python_new\GNET\EL_files
cl /LD /EHsc dll.cpp ws2_32.lib /Fe:BarBridge.dll
```

You should see output ending with:
```
Creating library BarBridge.lib and object BarBridge.obj
```

`BarBridge.dll` will now appear in the `EL_files` folder.

---

## Step 6 — Update the EasyLanguage Script

Make sure **both** paths in the indicator point to the compiled `.dll` (not the `.cpp`):

```
External: "C:\Users\g_med\python_new\GNET\EL_files\BarBridge.dll", int, "SendBar", ...
```

Save and reapply the indicator in TradeStation.

---

## Notes

- The DLL connects to `127.0.0.1:9009` — your Python TCP server must be running first
- Data is only sent on bar close (`BarStatus = 2`)
- See `netwo_files/how_to_run.md` for how to start Redis and the Python server
