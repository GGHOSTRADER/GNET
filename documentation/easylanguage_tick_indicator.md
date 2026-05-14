// EasyLanguage Tick DLL Indicator
// **What:** EasyLanguage indicator code that runs inside TradeStation and sends tick data to the Python TCP server via `TickBridge.dll` on every tick.



// EasyLanguage Code


{ Sending Tick Data from TS to Python server through TickBridge.dll }

using elsystem;

Vars:
    yyyymmdd(0),
    bar_num(0),
    ok(0),
    TimeSpan hhmmss(null);

{ EasyLanguage DLL declaration }
{ 8 fields: symbol, date, time, high, low, up, down, bar_num }
External: "C:\Users\g_med\python_new\GNET\EL_files\TickBridge.dll", int, "SendTick",
    Lpstr,      { symbol  }
    int,        { yyyymmdd }
    int,        { hhmmss  }
    double,     { high    }
    double,     { low     }
    int,        { up      }
    int,        { down    }
    int;        { bar_num }

{ Fire on every tick - no BarStatus filter }
yyyymmdd = Date;
hhmmss   = bardatetime.timeofday;
bar_num  = Currentbar;

ok = SendTick(
    Symbol,
    yyyymmdd,
    Intportion(hhmmss.TotalSeconds),
    High,
    Low,
    Upticks,
    Downticks,
    bar_num
);


plot1(bar_num,"bar num",red);

---

## Key Differences from Bar Indicator

| | Bar `el_dll.md` | Tick (this file) |
|---|---|---|
| DLL | `BarBridge.dll` | `TickBridge.dll` |
| Port | `9009` | `9010` |
| Fields | 11 (OHLCV + VWAP) | 8 (no Open, Close, VWAP) |
| Fires on | Bar close only | Every tick |
| Function | `SendBar()` | `SendTick()` |

---

## Compile the DLL

```bash
cd C:\Users\g_med\python_new\GNET\EL_files
cl /LD /EHsc tick_dll.cpp ws2_32.lib /Fe:TickBridge.dll
```

---

## Notes

- Apply this indicator to a **tick chart** in TradeStation
- `high == low` for every tick — single price point per tick
- `TickBridge.dll` must be compiled before applying the indicator
- `SendTick()` connects to `127.0.0.1:9010` — `tcp_to_redis_ticks.py` must be running first
