# GNET Troubleshooting Guide

Use this guide by symptom. Keep TradeStation automation disabled until the required Python
services are healthy. Commands assume GNET is installed at `C:\GNET`.

## First-response checklist

Open PowerShell and run:

```powershell
cd C:\GNET
.\check_gnet_ports.ps1
docker ps -a
docker exec redis1 redis-cli PING
```

Expected TradeStation-facing listeners:

| Port | Service | Required state |
|---:|---|---|
| 9009 | Bar TCP | `LISTENING` |
| 9010 | Tick TCP | `LISTENING` |
| 9011 | Decision TCP | `LISTENING` |
| 9012 | Candidate TCP | `LISTENING` |

Redis must return `PONG`. If a port is missing, do not enable its TradeStation DLL client.

For a continuously refreshing view:

```powershell
.\check_gnet_ports.ps1 -Watch
```

The default refresh interval is 10 seconds. Press `Ctrl+C` to stop the monitor.

## TradeStation is frozen or not responding

Likely causes:

- A TradeStation DLL client started before its Python TCP server.
- A non-hardened or stale DLL binary is loaded.
- The Python services were stopped while TradeStation was connecting.
- TradeStation is processing an excessive Look-Inside-Bar history.

Recovery:

1. Do not repeatedly click or reapply the strategy.
2. Check ports 9009–9012.
3. Restart the Python pipeline before restarting TradeStation:

```powershell
cd C:\GNET
.\restart.ps1
```

4. If TradeStation remains unresponsive, close it with the verified process helper:

```powershell
.\kill_tradestation.ps1 -ListOnly
.\kill_tradestation.ps1
```

5. Start GNET first, wait for all ports, and launch/enable TradeStation last.

The hardened DLLs use bounded, non-blocking connection behavior. Stopping Python services
should not permanently freeze TradeStation; verify that TradeStation loaded the delivered
DLLs from `C:\GNET\EL_files`.

## A port is reported missing

Map ports to the process that must be restarted:

```text
9009 -> python -m netwo_files.tcp_to_redis_connection
9010 -> python -m netwo_files.tcp_to_redis_ticks
9011 -> python -m inference.signal_tcp_server
9012 -> python -m inference.candidate_tcp_server
```

Inspect a specific port:

```powershell
Get-NetTCPConnection -LocalPort 9011 -ErrorAction SilentlyContinue |
    Select-Object LocalPort,RemotePort,State,OwningProcess
```

`LISTENING` proves the server socket exists. `ESTABLISHED` additionally shows an active
client connection. A terminal printing market lines is not proof that the expected port is
listening; confirm the module name and port explicitly.

For a clean recovery:

```powershell
cd C:\GNET
.\stop.ps1
.\.venv\Scripts\Activate.ps1
.\launch_grid.ps1
```

## Port is listening but its data looks wrong

Confirm the correct EasyLanguage document calls the correct DLL:

```text
g_cpp_dll_bar  -> BarBridge.dll  -> port 9009
g_cpp_dll_tick -> TickBridge.dll -> port 9010
G_MA_CROSS_NN  -> StrategyBridge.dll and SignalBridge.dll -> ports 9012 and 9011
```

A previous failure was caused by tick-bridge EasyLanguage code being saved under the bar
indicator. This sent tick-shaped activity from the wrong chart and made terminal activity
misleading. Compare the TradeStation source with the matching `.els` backup in
`C:\GNET\EL_files`.

## Tick validator reports decreasing bar numbers

Example:

```text
SEQUENCE ERROR: bar_num must strictly increase: prev=3906 curr=1635
```

Possible causes:

- The tick indicator is active in more than one TradeStation chart/workspace.
- Historical bars were replayed through the tick DLL.
- TradeStation/chart history was reloaded and its local `CurrentBar` restarted.
- Redis or the validator retained state from a previous source session.
- The bar indicator contains tick DLL code.

Checks:

1. Apply `g_cpp_dll_tick` exactly once, on the intended 1-tick chart.
2. Confirm its source uses `TickBridge.dll` and `LastBarOnChart`.
3. Confirm `g_cpp_dll_bar` uses `BarBridge.dll` and only sends completed last-chart bars.
4. Restart the tick validator after deliberately resetting/reloading the TradeStation tick
   source.
5. Do not delete Redis merely to hide a continuing duplicate producer.

## Tick validator says high must equal low

Example:

```text
INVALID: high must equal low for tick data
```

The payload came from an aggregated bar rather than a single tick, or the wrong indicator
code is active. Ensure the source is a 1-tick TradeStation chart and that only
`g_cpp_dll_tick` calls `TickBridge.dll`.

## Tick TCP continues after the validator stops

This is expected when only the downstream validator process was stopped. The services are
independent:

```text
TradeStation -> tick TCP -> tick_data_raw -> validator -> tick_data_validated
```

Stopping the validator does not stop the TCP receiver. Stop the complete GNET pipeline with:

```powershell
.\stop.ps1
```

## Features stay in warm-up

The MA feature engine needs 60 completed bars before publishing. With 30-second bars, a
fresh process requires approximately 30 minutes of new live bars.

Historical bars displayed inside TradeStation are not automatically loaded into the Python
process because `LastBarOnChart` prevents historical replay into TCP. During warm-up:

- `validated_bar` should increase.
- `features_transformer` may remain unchanged.
- Strategy candidates fail closed with `missing_features`.

Check stream lengths:

```powershell
docker exec redis1 redis-cli XLEN validated_bar
docker exec redis1 redis-cli XLEN features_transformer
```

Do not treat warm-up rejection as model rejection.

## Router returns `missing_features`

Example:

```text
status=missing_features approved=0
```

The router did not find a valid matching MA feature point within its feature wait window.
Common causes are warm-up, stopped feature engineering, wrong symbol/timestamp, delayed bars,
or a candidate arriving before the completed bar feature.

Check:

1. `validated_bar` is increasing.
2. The feature terminal has completed 60-bar warm-up.
3. `features_transformer` is increasing.
4. TradeStation and Windows clocks are correct.
5. The strategy and bar indicator use the same symbol and 30-second chart context.

The current wait is deliberately bounded. Do not increase it blindly; profile the actual
bar-to-feature-to-router latency first.

## Candidate times out in EasyLanguage

Example:

```text
GNET candidate timed out: candidate=<GUID>
```

The strategy sent a candidate but did not consume its matching decision before the configured
`CandidateTimeoutBars`. Possible causes:

- Signal TCP service on 9011 stopped or disconnected.
- Router returned no decision because it was down or not ready.
- TradeStation did not poll frequently enough.
- A stale/non-ACK DLL was loaded.
- Instance ID or candidate GUID did not match.

Inspect, in order:

1. Terminal 3: was the GUID received?
2. Terminal 2: was the same GUID decided, and what was `status`?
3. Terminal 1: was the same GUID delivered?
4. TradeStation log: was the same GUID acknowledged, rejected, or approved?

Never infer success from a similar timestamp. The GUID must match exactly.

## Signal server says delivered, but no TradeStation order appears

`delivered` means the decision bytes were sent to the socket. It does not by itself mean the
decision was approved or that EasyLanguage placed an order.

Check Terminal 2 for the same GUID:

- `status=ok approved=1`: an entry is eligible.
- `status=ok approved=0`: correct model rejection; no entry should occur.
- `status=missing_features`: fail-closed pipeline result, not model approval.
- Any other error status: no entry should occur.

Then check the TradeStation log for the exact candidate GUID and confirm:

- Decision candidate equals the pending candidate.
- `InstanceId` matches the originating window.
- The strategy was enabled and permitted to place simulated orders.
- No existing position or TradeStation order rule blocked the entry.
- The correct account and automation settings were selected.

## Signal server disconnects with WinError 10053

Example:

```text
ConnectionAbortedError: [WinError 10053]
```

TradeStation or host software closed an established socket. The hardened server should treat
this as a client disconnect, retain an unacknowledged Redis decision, accept reconnection,
and redeliver it only to the matching instance/candidate.

Restart Terminal 1 if it exited, verify port 9011, then confirm the same GUID is either
acknowledged or remains pending. Do not delete the Redis consumer group to clear the symptom.

## Decision is repeatedly delivered

The signal server retains a decision until it receives the exact application ACK from
EasyLanguage through `SignalBridge.dll`. Repeated delivery usually means:

- Old `SignalBridge.dll` without the ACK protocol is loaded.
- TradeStation received the bytes but did not poll/consume the decision.
- Candidate or instance identity differs.
- The connection closed before ACK transmission.

Close TradeStation, copy the coordinated hardened DLLs into `C:\GNET\EL_files`, reopen
TradeStation only after the services are ready, and repeat simulation acceptance.

## Strategy receives a decision but does not trade

This can be correct. Confirm all conditions:

```text
status = ok
approved = 1
decision GUID = pending candidate GUID
matching InstanceId
strategy enabled
account/order settings allow entry
no position rule blocks entry
```

Probability alone does not indicate approval without comparing it with the registry threshold.
The supplied MA2CrossLE threshold is 0.50.

## Trade appears but stop/target behaves incorrectly

The working configuration uses separate TradeStation built-in Stop Loss and Profit Target
components, each at $50 per contract for one ES contract.

Do not use only explicit code such as:

```text
Sell next bar at EntryPrice - 1 stop
```

That order may not protect the entry bar and can fill at the following bar's open after a
large gap. Confirm the two built-in components are applied and that the repository strategy
contains no obsolete `EntryPrice +/-` next-bar exits.

## Historical report contains huge profits or losses

Likely causes:

- Next-bar protective orders instead of entry-bar-capable built-in stops/targets.
- Insufficient intrabar history to determine whether stop or target occurred first.
- Continuous-contract adjustment mismatch.
- A real gap/slippage event.

Run the anomaly report before training:

```powershell
python -m training_mlp.audit_trade_anomalies `
  --trades .\training_mlp\strategies\MA2CrossLE\inputs\trades_30_master.csv `
  --bars .\training_mlp\strategies\MA2CrossLE\inputs\data_30_master_merged.txt `
  --signal-name MA2CrossLE `
  --absolute-pnl-limit 70 `
  --expected-move-points 1 `
  --point-value 50 `
  --output .\training_mlp\strategies\MA2CrossLE\reports\trade_execution_anomalies.csv
```

Inspect evidence; do not automatically remove outliers from training.

## TradeStation cannot allocate memory for historical data

One-tick Look-Inside-Bar back-testing over months can require enormous memory. Intrabar Order
Generation and Look-Inside-Bar are different settings: disabling IOG does not solve the
underlying historical tick volume.

Recovery:

1. Reduce the requested historical range.
2. Export/test in short date chunks.
3. Close other TradeStation workspaces and memory-heavy applications.
4. Use historical tick Parquets for offline reconstruction where appropriate.
5. Validate offline reconstruction against a manageable one-tick LIBB sample.

## Docker command cannot connect to the engine

Example:

```text
failed to connect to the docker API ... dockerDesktopLinuxEngine
```

Docker Desktop is stopped or still starting. Open Docker Desktop and wait until its engine is
ready, then run:

```powershell
docker version
docker ps -a
```

Both client and server information must be available.

## Installer rejects an existing `redis1`

The existing container does not match the safe customer configuration:

```text
127.0.0.1:6381 -> 6379/tcp
Docker volume mounted at /data
```

The installer intentionally refuses to delete it because it may contain streams, consumer
groups, pending decisions, and durable offsets. Inspect and back up the existing container.
Only remove it manually when its data is confirmed unnecessary.

## Redis is stopped or missing

Check:

```powershell
docker ps -a --filter "name=redis1"
docker start redis1
docker exec redis1 redis-cli PING
```

If the customer has never installed GNET, rerun `install.ps1` with Docker
Desktop running; it creates the pinned persistent Redis configuration automatically.

## `stop.ps1` says Docker/Redis is already unavailable

If Docker Desktop is already closed, Docker commands cannot inspect or stop `redis1`. This is
not evidence that Redis is still consuming memory—the Docker engine is already unavailable.
The stop script must not treat an already-stopped Docker engine as Redis data corruption.

## `stop.ps1` cannot disable the watchdog

Example:

```text
WARNING: Could not disable the watchdog: Access is denied.
```

The scheduled task was created with permissions the current shell cannot modify. Open an
elevated PowerShell window to manage that task, or leave it disabled during manual operation.
Confirm it will not immediately relaunch services you are trying to stop.

## PowerShell says a script is not recognized

PowerShell does not execute scripts from the current directory without `.` and `\`.

Wrong:

```powershell
stop.ps1
```

Correct:

```powershell
.\stop.ps1
```

If execution policy blocks the installer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\GNET\install.ps1
```

## Installer selects the wrong Python

Check:

```powershell
Get-Command py.exe
py -3.12 -c "import platform,sys; print(platform.python_implementation(), platform.python_version(), sys.executable)"
```

GNET requires the Python.org CPython 3.12.7 distribution and rejects Conda interpreters.
The installer creates `C:\GNET\.venv`; daily launchers select it automatically. Activate it
only when running manual training commands:

```powershell
cd C:\GNET
.\.venv\Scripts\Activate.ps1
```

## Training script cannot import `wandb`

Run the complete default installer, not an installation made with `-RuntimeOnly`:

```powershell
cd C:\GNET
.\install.ps1
```

For local experiment records without a W&B cloud login:

```powershell
$env:WANDB_MODE = "offline"
```

## Training cannot find input files

The delivered baseline bars, trades, and labeled 13-feature dataset are already present.
Place properly licensed new exports for subsequent updates under:

```text
training_mlp\strategies\MA2CrossLE\inputs
```

Follow `TRAINING_GUIDE.md` for exact names, schemas, merge commands, and explicit paths.

## Historical bar merge reports conflicts

The same timestamp exists with different OHLC/Up/Down values. This often occurs when continuous
contract exports were generated under different rollover adjustments.

Do not force a value choice automatically. Inspect the conflict/overlap reports and explicitly
select the authoritative compatible export using repeated `--source` arguments. Source files
are preserved.

## New model fails verification

Treat these as one indivisible artifact set:

```text
model_best.pt
scaler_best.pkl
config.json
registry.json settings
canonical feature order
```

Common causes are a mismatched scaler, different feature count/order, incorrect model
architecture, wrong artifact path, unsupported feature stream, or missing file. Restore the
previous registry entry and complete simulation acceptance before another promotion attempt.

## DLL changes do not appear in TradeStation

TradeStation keeps DLLs loaded. To install rebuilt binaries:

1. Stop GNET and fully close TradeStation.
2. Confirm no TradeStation DLL-host processes remain.
3. Build all four x86 DLLs with `EL_files\build_hardened.cmd`.
4. Copy the coordinated outputs to `C:\GNET\EL_files`.
5. Start the Python pipeline.
6. Start TradeStation last.
7. Repeat hardened-DLL and exact-candidate simulation tests.

Retraining or adding a strategy with the existing protocol does not require DLL rebuilding.

## Collect evidence before requesting support

Record:

- Date/time and time zone.
- GNET release and Git commit.
- Exact candidate GUID and `InstanceId` when applicable.
- Output from `check_gnet_ports.ps1`.
- `docker ps -a` and Redis `PING` result.
- Terminal 1, 2, and 3 lines for the same GUID.
- TradeStation log/order screenshot.
- The command that failed and its complete traceback.
- Whether the issue occurs in simulation or live mode.

Never send brokerage passwords, API keys, account credentials, or unrestricted historical
market data as troubleshooting attachments.
