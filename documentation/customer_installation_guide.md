# GNET Customer Installation Guide

This guide installs the complete GNET application and training environment for the
MA2CrossLE canonical 13-feature release.

## 1. Customer-installed prerequisites

Install these products before running the GNET installer:

1. **64-bit CPython 3.12.7** from Python.org. Install the Windows Python launcher
   when prompted. The installer uses `py -3.12` and rejects Conda distributions.
2. **Docker Desktop for Windows.** Start Docker Desktop and wait until its engine is
   running.
3. **TradeStation Desktop.** Sign in with the customer's TradeStation account and
   confirm that the required ES market data is available.

The customer does not need Conda. GNET creates its own isolated `.venv` environment.

Visual Studio is not required to operate GNET. Install Visual Studio Build Tools with
the Desktop development with C++, Windows SDK, MSVC, and x86 components only if the
customer intends to modify and rebuild the supplied bridge DLLs.

## 2. Required installation location

Copy the complete delivered source directory to:

```text
C:\GNET
```

The supplied EasyLanguage documents reference DLLs under `C:\GNET\EL_files`. Do not
run the production installation from Downloads, Desktop, or another source checkout.

## 3. Confirm prerequisites

Open a new PowerShell window and run:

```powershell
py -3.12 -c "import platform; print(platform.python_implementation(), platform.python_version())"
docker version
```

The first command must report `CPython 3.12.7`. The second must show both Docker client
and server information. If it reports that the daemon or engine is unavailable, start
Docker Desktop before continuing.

## 4. Install the complete application and training environment

Run:

```powershell
cd C:\GNET
.\install.ps1
```

If PowerShell blocks local scripts, run the installer without changing the machine's
permanent execution policy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\GNET\install.ps1
```

The installer performs these actions:

- Validates the required source, model, scaler, registry, and DLL files.
- Uses the Windows `py -3.12` launcher and requires Python.org CPython 3.12.7.
- Rejects Conda, Anaconda, and Miniconda interpreters.
- Creates `C:\GNET\.venv`.
- Installs the exact pinned live and training dependencies by default. Use
  `-RuntimeOnly` only when intentionally omitting training tools.
- Creates the local non-secret `training_mlp\.env` and required working directories.
- Runs Python dependency and synthetic model-inference checks.
- Downloads the pinned Redis Docker image.
- Creates the persistent `gnet-redis-data` Docker volume.
- Creates or validates the `redis1` container.
- Maps Redis only to `127.0.0.1:6381`.
- Starts Redis and requires a successful `PONG` response.

The installer will not delete or replace an existing incompatible `redis1` container.
This prevents accidental Redis data loss.

## 5. TradeStation EasyLanguage setup

The delivered EasyLanguage source is in `C:\GNET\EL_files`.

Create or import these three TradeStation documents using these exact names:

| TradeStation document | Type | Apply to |
|---|---|---|
| `g_cpp_dll_bar` | Indicator | The MA strategy's 30-second ES chart |
| `g_cpp_dll_tick` | Indicator | A separate 1-tick ES chart |
| `G_MA_CROSS_NN` | Strategy | The MA strategy's 30-second ES chart |

The four supplied x86 DLLs remain in `C:\GNET\EL_files`:

- `BarBridge.dll` — sends completed bars to TCP port 9009.
- `TickBridge.dll` — sends live ticks to TCP port 9010.
- `StrategyBridge.dll` — sends strategy candidates to TCP port 9012.
- `SignalBridge.dll` — receives exact-candidate decisions from TCP port 9011.

For each strategy window:

- Keep `StrategyId` as `MA2CrossLE` for the locally trained model.
- Give every simultaneously running strategy window a unique `InstanceId`.
- Use one contract and disable pyramiding for the supplied acceptance configuration.
- Confirm the strategy inputs `StopLossAmount` and `ProfitTargetAmount` are each
  **$50 per contract**. The supplied strategy embeds TradeStation's built-in
  `SetStopLoss` and `SetProfitTarget` protection.
- Do not apply duplicate separate Stop Loss or Profit Target strategy components.

The distinction between built-in protective components and explicit `next bar` stop or
limit code is important. Explicit next-bar protection can miss the entry bar and create
large gap losses in backtests. Look-Inside-Bar Back-testing may consume substantial RAM
over very large histories; use only the history required for the current test or export.

## 6. Startup order

Always start the Python/Redis pipeline before enabling the TradeStation indicators and
strategy. Starting TradeStation DLL clients first can leave TradeStation waiting for
unavailable TCP services.

Start GNET from `C:\GNET`:

```powershell
.\launch_grid.ps1
```

Wait until the port monitor confirms the required services are listening before applying
or enabling the TradeStation documents.

Decision-terminal summary:

- Terminal 3 receives the TradeStation candidate.
- Terminal 2 makes the model decision.
- Terminal 1 delivers the exact decision to TradeStation.

The MA feature process requires a 60-bar warm-up. On a 30-second chart, a fresh start can
require approximately 30 minutes before MA features are available. Candidates received
before warm-up completes fail closed rather than trading without features.

## 7. Verification and simulation acceptance

With Docker, Redis, and the pipeline running, run:

```powershell
cd C:\GNET
.\verify_install.ps1
```

Complete every displayed TradeStation simulation check. Type `YES` only after confirming:

- The bar and tick indicators are applied once to their correct charts.
- The strategy uses `MA2CrossLE` and a unique `InstanceId`.
- One approved candidate produces exactly one simulated entry.
- Rejected candidates do not produce entries.
- The $50 stop and $50 target protect the entry correctly.
- The simulation account is selected and live automation remains disabled.

Do not enable live trading until the automatic verification and simulation acceptance
both pass.

## 8. Normal shutdown

Stop GNET while preserving Redis data:

```powershell
cd C:\GNET
.\stop.ps1
```

To also close TradeStation and Docker Desktop:

```powershell
.\stop.ps1 -StopTradeStation -StopDockerDesktop
```

The destructive `nuke.ps1 -ConfirmDataLoss` command removes Redis state and is not a
normal shutdown command.

## 9. Training and model replacement

Activate the installed training environment when running training commands manually:

```powershell
cd C:\GNET
.\.venv\Scripts\Activate.ps1
```

Retraining a model does not require recompiling any DLL. A compatible retrained strategy
normally replaces its model, scaler, and configuration and updates the model registry.
Adding a new strategy also normally reuses `StrategyBridge.dll` and `SignalBridge.dll`.
Recompile a DLL only when changing its exported function or TCP message protocol.

The source delivery does not include the licensor's bars, TradeStation trades, labeled
datasets, trained weights, scaler, predictions, or evaluation artifacts. The customer must
supply properly licensed exports for the initial local training, later retraining, and
historical VP preparation.

## 10. Common installation failures

### Python version rejected

Install 64-bit CPython 3.12.7 and open a new PowerShell window. Confirm which executable
is selected with:

```powershell
py -3.12 -c "import sys; print(sys.executable)"
python --version
```

### Docker command exists but the engine is unavailable

Start Docker Desktop and wait until `docker version` displays server information.

### Existing redis1 configuration is rejected

Do not delete it blindly. It may contain Redis streams and offsets. Inspect or back it up,
then remove it manually only if its data is no longer required.

### TradeStation becomes unresponsive

Confirm ports 9009, 9010, 9011, and 9012 are listening and restart the Python services
before restarting or re-enabling the TradeStation DLL clients. Use:

```powershell
.\check_gnet_ports.ps1
```

For complete operating details, see `documentation\how_to_run_pipeline.md`.
