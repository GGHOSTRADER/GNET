# How to Run the Pipeline
> **What:** Ordered steps to start the full data pipeline — Docker, Redis, Python servers, TradeStation, and feature/inference pipelines.

The recommended path is the one-command launcher. It opens all nine Python
services in the correct order; the manual commands below are for debugging.

> [!WARNING]
> **Start Python before enabling anything in TradeStation.** Wait until
> `launch.ps1` prints `=== All services launched ===` and verify that TCP ports
> `9009`, `9010`, `9011`, and `9012` are all listening. If the bar indicator,
> tick indicator, or strategy is enabled while its Python endpoint is down, the
> DLLs repeatedly wait and reconnect. This can trap TradeStation in a waiting
> loop and make `ORPlat.exe` appear frozen. Disable the TradeStation analyses,
> restore the Python services, and only then enable the components again.

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

### Stop or restart all GNET services

`launch.ps1` records the exact service-terminal PIDs it creates. Stop those
GNET process trees, attempt to disable the watchdog, and verify ports 9009,
9010, 9011, 9012, and 9020 are released:

```powershell
.\stop.ps1
```

The normal stop command intentionally leaves all of the following running:

- Docker Desktop;
- the `redis1` container;
- every retained Redis stream and consumer-group offset;
- TradeStation.

It stops the GNET Python services, their PowerShell hosts, and any active
`check_gnet_ports.ps1 -Watch` dashboard. It never calls `FLUSHDB`, removes the
Redis container, or deletes Redis data.

Stop and immediately relaunch the pipeline:

```powershell
.\restart.ps1
```

Optional full-infrastructure restart, still without deleting Redis data:

```powershell
.\restart.ps1 -RestartRedis
```

`-RestartRedis` stops only the `redis1` container before `launch.ps1` starts it
again. Docker Desktop remains running and the container's persisted data is
preserved. To stop GNET plus Redis without relaunching:

```powershell
.\stop.ps1 -StopRedis
```

Stop GNET, stop `redis1` without deleting its data, and fully close Docker
Desktop and its engine to release memory:

```powershell
.\stop.ps1 -StopDockerDesktop
```

The next `launch.ps1` run starts Docker Desktop and the preserved `redis1`
container again.

Request a graceful TradeStation close before relaunching it:

```powershell
.\restart.ps1 -StopTradeStation
```

TradeStation is never force-killed: if it needs a save or confirmation, finish
that interaction manually. `stop.ps1` never flushes or deletes Redis data.

If TradeStation is frozen and cannot close gracefully, inspect the exact
processes that would be targeted. Run these commands from the GNET repository
root:

```powershell
cd C:\Users\g_med\python_new\GNET
.\kill_tradestation.ps1 -ListOnly
```

Force-close every process verified by TradeStation installation path or company
metadata, then confirm none remain:

```powershell
cd C:\Users\g_med\python_new\GNET
.\kill_tradestation.ps1
```

This emergency command can discard unsaved TradeStation workspace changes. It
does not stop GNET, Docker, Redis, or unrelated applications.

For service terminals created before PID tracking was introduced, `stop.ps1`
uses a narrow compatibility fallback: it stops only Python/PowerShell command
lines matching the exact nine GNET module names. Unrelated Python processes are
not targeted. After the next `launch.ps1`, normal shutdown uses the recorded
PID plus process start time to protect against PID reuse.

If shutdown prints `Could not disable the watchdog: Access is denied`, the
service stop still proceeds, but Windows did not permit Scheduled Task control.
Open an Administrator PowerShell and run:

```powershell
cd C:\Users\g_med\python_new\GNET
.\automation\gnet_scheduler_off.ps1
```

Then run `stop.ps1` again if the watchdog had already restarted any service.

### Destructive Redis hard reset

Normal stop and restart commands preserve Redis. When a deliberately clean
Redis state is required, `nuke.ps1` stops GNET, verifies the Docker target is
exactly `redis1`, and permanently removes that container together with every
stream, consumer group, pending entry, offset, and readiness key inside it.

The script refuses to run without the explicit data-loss acknowledgement:

```powershell
.\nuke.ps1 -ConfirmDataLoss
```

Remove the old container and immediately create a fresh empty `redis1` mapped
to host port 6381:

```powershell
.\nuke.ps1 -ConfirmDataLoss -RecreateEmptyRedis
```

This operation cannot be undone unless the Redis container data was separately
backed up. After resetting Redis, the script gracefully shuts down Docker
Desktop and its engine. That stops every running container, but only `redis1`
is removed; unrelated containers and their stored data are not deleted. The
next `launch.ps1` starts Docker Desktop again.

After removal without recreation, normal `launch.ps1` cannot start Redis until
the container is recreated:

```powershell
docker run -d --name redis1 -p 6381:6379 redis
```

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

## Step 6 — Required TradeStation EasyLanguage Components

The Python terminals are only one side of the system. The following three
EasyLanguage documents must exist in TradeStation under these exact saved
names. The source/documentation column identifies the corresponding repository
code; the TradeStation name is not the DLL filename.

| TradeStation component | Type | Source | Apply to | DLL / port |
|---|---|---|---|---|
| `g_cpp_dll_bar` | Indicator | `EL_files/g_cpp_dll_bar.els` | One 30-second bar chart for the traded symbol | `BarBridge.dll` → 9009 |
| `g_cpp_dll_tick` | Indicator | `EL_files/g_cpp_dll_tick.els` | One tick chart for the same symbol | `TickBridge.dll` → 9010 |
| `G_MA_CROSS_NN` | Strategy | `EL_files/G_MA_CROSS_NN.els` | Every chart/window that runs the MA strategy | `StrategyBridge.dll` → 9012 and `SignalBridge.dll` ← 9011 |

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
2. Apply the `g_cpp_dll_bar` indicator once.
3. Confirm its bar interval matches the model's live feature interval.

This chart supplies OHLC, VWAP, tick-volume proxies, symbol, date, time, and
bar number. It is a centralized data producer; do not add one copy for every
strategy window unless a different symbol or bar series needs its own data.

### Central tick chart

1. Open a tick chart for the same symbol.
2. Apply the `g_cpp_dll_tick` indicator once.

This chart supplies the tick stream used by the volume-profile process. The
current MA model does not consume volume-profile features, but the tick sender
is required when running that part of the pipeline.

### MA strategy windows

1. Open the saved TradeStation strategy `G_MA_CROSS_NN`.
2. Its repository backup is `EL_files/G_MA_CROSS_NN.els`; re-paste and compile that source when restoring or updating the strategy.
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

**Do not enable any GNET TradeStation component yet.** Start `launch.ps1` first
and wait until it prints `=== All services launched ===`. Confirm all four DLL
endpoints before proceeding:

```powershell
.\check_gnet_ports.ps1 -Watch
```

The live dashboard refreshes every ten seconds until `Ctrl+C` is pressed. It
must show `READY` before TradeStation is enabled. Run the same command without
`-Watch` for a one-time check that exits with status `0` when ready or `1` when
one or more ports are missing. Seeing only one or some endpoints is not ready.
Enabling the EasyLanguage components before all four endpoints are available
can leave TradeStation stuck in the DLL connection/retry loop.

After the four-port check passes, enable the TradeStation charts in this order:

1. `g_cpp_dll_bar`
2. `g_cpp_dll_tick` when the volume-profile pipeline is required
3. Each `G_MA_CROSS_NN` strategy window

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
