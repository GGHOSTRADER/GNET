# EasyLanguage DLL Indicator
> **What:** EasyLanguage indicator code that runs inside TradeStation and sends bar data to the Python TCP server via `BarBridge.dll` on every bar close.

Sends bar data from TradeStation to the Python TCP server through `BarBridge.dll` (compiled from `dll.cpp`).

## EasyLanguage Code

```pascal
{ Sending Data from TS to Python server through .dll created in C++ }

using elsystem; // Needing for TIMESPAN class

// Lets the User modify the path of the .dll inside TS
Inputs:
    DllPath("C:\Users\g_med\py_scripts\ts_infra\BarBridge.dll");

Vars:
    yyyymmdd(0), // Date
    bar_num (0),
    ok(0),
    TimeSpan hhmmss (null); // Used for time in seconds of the day, must be timespam class

{ EasyLanguage DLL declaration }
//          1                                                2        3
//          LOCATION OF .DLL                               , RETURN, DEFINITION OF FUNCTION TO USE BELLOW
External: "C:\Users\g_med\python_new\GNET\EL_files\BarBridge.dll", int, "SendBar",
    Lpstr,     { symbol }
    int,        { yyyymmdd }
    int,        { hhmmss }
    double,     { open }
    double,     { high }
    double,     { low }
    double,     { close }
    int,        { up }
    int,        { down }
    double,     { vwap }
    int;        { bar num }

{ Only send on bar close so we don't spam per tick update }
If BarStatus(1) = 2 Then Begin
    // Date comes in TS propietary format, in YYMMDD but YY is years since 1900
    yyyymmdd = Date;
    // Time is HHMM (or HHMMSS depending on settings); safest to use Time_s for seconds if available
    hhmmss = bardatetime.timeofday;
    // Bar number
    bar_num = Currentbar;
    // Send information through DLL
    ok = SendBar(Symbol, yyyymmdd, Intportion(hhmmss.TotalSeconds), Open, High, Low, Close, Upticks, Downticks, Vwap, bar_num);
End;

plot1(bar_num,"bar num",red);
```

## Notes

- `BarStatus(1) = 2` means bar close — data is only sent once per bar, not per tick
- The `External` path must point to the compiled `BarBridge.dll`, not the `.cpp` source
- `SendBar()` connects to `127.0.0.1:9009` (your Python TCP server must be running)
- See `how_to_compile_and_run.md` for how to compile the DLL
