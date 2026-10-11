# EasyLanguage DLL Indicator
> **What:** EasyLanguage indicator code that bootstraps a bounded chart history after initialization/reload and then sends completed live bars through `BarBridge.dll`.

Sends bar data from TradeStation to the Python TCP server through `BarBridge.dll` (compiled from `dll.cpp`).

## EasyLanguage Code

The authoritative, importable source is `EL_files/g_cpp_dll_bar.els`. It uses
the `SendBarMode` export so Python can distinguish `BOOTSTRAP`,
`BOOTSTRAP_END`, and `LIVE` records. Configure the chart for 65 loaded bars.
The older excerpt below documents the legacy live-only interface and must not
be pasted over the current TradeStation document.

```pascal
{ GNET live 30-second bar sender through BarBridge.dll }

using elsystem;

Vars:
    yyyymmdd(0), // Date
    bar_num (0),
    ok(0),
    last_connection_state(-1),
    TimeSpan hhmmss(null);

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

{ Send only the completed live bar; never replay historical chart bars. }
If LastBarOnChart and BarStatus(1) = 2 Then Begin
    yyyymmdd = Date;
    hhmmss = bardatetime.timeofday;
    bar_num = Currentbar;
    ok = SendBar(Symbol, yyyymmdd, Intportion(hhmmss.TotalSeconds), Open, High, Low, Close, Upticks, Downticks, Vwap, bar_num);

    If ok <> last_connection_state Then Begin
        If ok = 1 Then
            Print(Time, " GNET bar bridge connected")
        Else
            Print(Time, " GNET bar bridge unavailable; retry is throttled");
        last_connection_state = ok;
    End;
End;

plot1(bar_num,"bar num",red);
```

## Notes

- Bootstrap is bounded by the chart's configured 65-bar history; do not configure an unbounded historical range
- After bootstrap, `LastBarOnChart` and `BarStatus(1) = 2` send once per newly completed live bar
- The `External` path must point to the compiled `BarBridge.dll`, not the `.cpp` source
- `SendBarMode()` connects to `127.0.0.1:9009` (your Python TCP server must be running)
- The installed backup is `EL_files/g_cpp_dll_bar.els`
- See [[how_to_compile_dll]] for the coordinated x86 DLL build
