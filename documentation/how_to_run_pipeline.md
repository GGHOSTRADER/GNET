# How to Run the Pipeline
> **What:** Ordered steps to start the full data pipeline — Docker, Redis, Python servers, TradeStation, and feature/inference pipelines.

The recommended path is the one-command launcher. It opens all nine Python
services in the correct order; the manual commands below are for debugging.

---

## Step 1 — Run the Launch Script

```bash
.\launch.ps1
```

Automatically starts Docker Desktop, waits for the engine, starts Redis,
opens all nine Python service terminals, launches TradeStation, and opens the
registry page at `http://127.0.0.1:9020`.

If this succeeds, skip directly to Step 6. Steps 2–5 show the equivalent
manual service startup for debugging.

### Windows watchdog — installation and daily ON/OFF control

The task is already installed on this machine. The installation command is
shown only for rebuilding the task after moving the repository or setting up
another computer. Run it once from an Administrator PowerShell; installation
leaves the task disabled:

```powershell
.\automation\install_gnet_scheduler.ps1
```

#### Turn GNET automatic startup ON

Run this when GNET should start now, start again at the next Windows logon,
and restart failed Python services:

```powershell
.\automation\gnet_scheduler_on.ps1
```

#### Turn GNET automatic startup OFF

Run this before shutdown when GNET should not start at the next Windows
logon. It also stops the watchdog immediately:

```powershell
.\automation\gnet_scheduler_off.ps1
```

`OFF` stops and disables the watchdog task but deliberately leaves services
that are already running untouched. Close those service terminals normally
when the current session is finished. The task is created for the current
Windows user and runs only in an interactive logon session.

#### Check whether it is ON or OFF

```powershell
Get-ScheduledTask -TaskName "GNET Pipeline Watchdog" |
    Select-Object TaskName, State
```

`Running` means the watchdog is ON and active. `Ready` means it is enabled but
not presently running. `Disabled` means automatic startup is OFF.

If Windows returns `Access denied`, run the status command from an
Administrator PowerShell. Normal ON/OFF commands may also require the same
elevation depending on the permissions Windows assigned during installation.

---

## Step 2 — Start the Bar TCP Server

```bash
python -m netwo_files.tcp_to_redis_connection
```

Expected output:
```
1) [bar_server] Connected to Redis1  -Host:127.0.0.1  -Port:6381
2) [bar_server] Listening TCP  -Host:127.0.0.1  -Port:9009
```

---

## Step 3 — Start the Tick Pipeline

Open **3 separate terminals**:

```bash
# Terminal 1 — ingest raw ticks from TickBridge.dll (port 9010)
python -m netwo_files.tcp_to_redis_ticks

# Terminal 2 — validate ticks and push to tick_data_validated
python -m netwo_files.tick_validator

# Terminal 3 — volume profile reads validated ticks and snapshots on qualifying final-second ticks
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600 --snapshot-interval-s 30
```

> The order matters: tcp_to_redis_ticks must run before tick_validator, and tick_validator before volume_profile.
> `--snapshot-interval-s` should match the live bar length in seconds (default 30) — the profile updates on every tick (O(1)) but only emits POC/VA/derived features 1 second before each bar close.

---

## Step 4 — Start the Transformer Feature Pipeline

```bash
python -m feat_files.transformer_features
```

This computes all 13 MLP features (including `day_of_week`) and publishes them to the `features_transformer` Redis stream.

Expected output once warmed up (60 bars):
```
ESM25 date=... t=... bar=60 pvol5=... ofi5=... signal=...
```

---

## Step 5 — Start Candidate Routing and Decisions

Open **3 separate terminals**:

```bash
# Terminal 1 — receives candidates from every strategy window on port 9012
python -m inference.candidate_tcp_server

# Terminal 2 — matches candidates to exact features and invokes the mapped model
python -m inference.strategy_router

# Terminal 3 — returns correlated decisions to TradeStation on port 9011
python -m inference.signal_tcp_server
```

Start the candidate server before applying the TradeStation strategies. Start
the router after `transformer_features.py` so it can cache each new feature
record. The old `inference.inference_engine` is not part of the live launch:
it infers on every bar, while the router infers only for actual candidates.

Expected output from the router:
```
[router] strategies=MA2CrossLE feature_timeout_ms=250
[router] MA2CrossLE instance=MA-ES-30S-01 candidate=<GUID> status=ok approved=1
```

---

## Step 6 — Create the Required EasyLanguage Components

The Python terminals are only one side of the system. The following three
EasyLanguage components must exist in TradeStation. Create them in the
EasyLanguage Development Environment and paste the referenced source into
each document.

| TradeStation component | Type | Source | Apply to | DLL / port |
|---|---|---|---|---|
| `GNET Bar Sender` | Indicator | [[easylanguage_bar_indicator]] | One 30-second bar chart for the traded symbol | `BarBridge.dll` → 9009 |
| `GNET Tick Sender` | Indicator | [[easylanguage_tick_indicator]] | One tick chart for the same symbol | `TickBridge.dll` → 9010 |
| `MA2CrossLE GNET` | Strategy | `EL_files/MA2CrossLE_GNET.els` | Every chart/window that runs the MA strategy | `StrategyBridge.dll` → 9012 and `SignalBridge.dll` ← 9011 |

The MA strategy already contains both candidate sending and decision polling.
Do **not** apply the old `RecvSignal` connection-test indicator as a separate
receiver; it uses the obsolete protocol and is not part of the live pipeline.

Before compiling, confirm that every `External:` declaration points to the
current DLL directory:

```text
C:\Users\g_med\python_new\GNET\EL_files
```

All four x86 DLLs must exist there:

```text
BarBridge.dll
TickBridge.dll
StrategyBridge.dll
SignalBridge.dll
```

See [[how_to_compile_dll]] if any DLL needs to be rebuilt.

---

## Step 7 — Configure the TradeStation Charts

### Central bar chart

1. Open a 30-second chart for the symbol used by the strategy.
2. Apply `GNET Bar Sender` once.
3. Confirm its bar interval matches the model's live feature interval.

This chart supplies OHLC, VWAP, tick-volume proxies, symbol, date, time, and
bar number. It is a centralized data producer; do not add one copy for every
strategy window unless a different symbol or bar series needs its own data.

### Central tick chart

1. Open a tick chart for the same symbol.
2. Apply `GNET Tick Sender` once.

This chart supplies the tick stream used by the volume-profile process. The
current MA model does not consume volume-profile features, but the tick sender
is required when running that part of the pipeline.

### MA strategy windows

1. Create a new TradeStation Strategy document named `MA2CrossLE GNET`.
2. Paste the contents of `EL_files/MA2CrossLE_GNET.els` and compile it.
3. Apply it to every chart that should run the MA crossover strategy.
4. Keep `StrategyId` set to `MA2CrossLE`; this selects the model registry entry.
5. Give every applied strategy window a unique, stable `InstanceId`.

Example instance IDs:

```text
MA-ES-30S-01
MA-ES-30S-02
MA-NQ-30S-01
```

Never reuse an `InstanceId` across simultaneously running strategy windows.
The ID is how the return DLL sends each decision to the correct chart. The
candidate GUID identifies the individual trade and is generated automatically
by `StrategyBridge.dll`.

The strategy has intrabar order generation enabled so it can poll for the
asynchronous decision between bar closes. Review TradeStation's automation and
order settings before enabling live orders.

---

## Step 8 — Start and Verify the Complete System

Start `launch.ps1` first and wait for the service-readiness checks. Then open
or enable the TradeStation charts in this order:

1. `GNET Bar Sender`
2. `GNET Tick Sender` when the volume-profile pipeline is required
3. Each `MA2CrossLE GNET` strategy window

After the 60-bar feature warm-up, an MA crossover should follow this path:

```text
MA crossover → candidate + GUID → matching bar features → MA model
             → approved/rejected decision → matching strategy window
```

For an approved candidate, the TradeStation Print Log should show the
candidate GUID followed by a matching approval and probability. A rejection,
missing feature, connection error, or nonmatching GUID must not place an order.

See [[strategy_candidate_integration]] for the complete candidate and decision
field contracts.

---

## Ports Reference

| Port | Used By | Direction |
|---|---|---|
| `9009` | Bar TCP server — TradeStation bar DLL connects here | TS → Python |
| `9010` | Tick TCP server — TradeStation tick DLL connects here | TS → Python |
| `9011` | Decision TCP server — `SignalBridge.dll` connects here | Python → TS |
| `9012` | Candidate TCP server — shared `StrategyBridge.dll` connects here | TS → Python |
| `6381` | Redis — Docker container (mapped from internal 6379) | local |

## Redis Streams Reference

| Stream | Written By | Read By |
|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `transformer_features.py` |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` |
| `features_transformer` | `transformer_features.py` | `strategy_router.py` |
| `features_volume_profile` | `volume_profile.py` | optional `consolidator.py` debugging tool only |
| `trade_candidates` | `candidate_tcp_server.py` | `strategy_router.py` |
| `trade_decisions` | `strategy_router.py` | `signal_tcp_server.py` |

The router acknowledges a candidate consumer-group entry only after its
decision is published. The signal server acknowledges a decision only after
the line is delivered over TCP. A watchdog restart therefore resumes pending
messages instead of starting from the newest Redis entry.
