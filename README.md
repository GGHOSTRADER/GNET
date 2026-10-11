# GNET — Meta-Labeling ML Pipeline for Algorithmic Trade Filtering

Real-time end-to-end machine learning pipeline for ES (E-mini S&P 500)
futures. It calculates market features continuously, but runs a strategy's
model only when TradeStation sends an actual primary-signal candidate.

**GitHub:** [https://github.com/GGHOSTRADER/GNET](https://github.com/GGHOSTRADER/GNET)

---

## Customer installation

Install the delivered source tree at `C:\GNET`, open PowerShell there, and run:

```powershell
.\install.ps1
```

This creates an isolated `.venv`, installs the pinned live and training dependencies,
and verifies the DLL, EasyLanguage, registry, canonical 13-feature, scaler, and model
contracts. Docker Desktop and TradeStation remain separate manual installations.

See [the customer installation guide](documentation/customer_installation_guide.md) for
all prerequisites, TradeStation setup, Redis behavior, verification, and shutdown steps.
For routine daily operation after installation, use [Quick Start](documentation/guides/QUICK_START.md).
For the offline backtester (bar building, primary strategy, optional exit search
and backtest statistics), use [the Backtester Guide](documentation/guides/BACKTESTER_GUIDE.md).
For delivery validation and customer sign-off, use
[the customer acceptance checklist](documentation/guides/CUSTOMER_ACCEPTANCE.md).
For data preparation, leakage-controlled validation, retraining, and model promotion, use
[the training guide](documentation/guides/TRAINING_GUIDE.md).
For architecture, extension points, protocols, testing, DLL builds, and release practices,
use [the developer guide](documentation/guides/DEVELOPER_GUIDE.md).
For symptom-based recovery and diagnostic commands, use
[the troubleshooting guide](documentation/guides/TROUBLESHOOTING.md).
For the exact delivered baseline, exclusions, VP status, limitations, and final-release
conditions, use [the release notes](documentation/guides/RELEASE_NOTES.md).
The complete delivery-document map is in
[the documentation index](documentation/INDEX.md), and the operational/customer boundary is
summarized in [limitations and responsibilities](documentation/guides/LIMITATIONS_AND_RESPONSIBILITIES.md).
The non-exclusive source-code license discussion draft is in
[the source-code license discussion draft](documentation/legal/SOURCE_CODE_LICENSE_AGREEMENT_DRAFT_ES.md) and
must be reviewed by qualified Guatemalan counsel before signature.
The formal third-party component and license inventory is in
[the third-party component inventory](documentation/legal/THIRD_PARTY_COMPONENTS.md).

---

## System Overview

For independent offline ES tick replay, reconstructed bars, strategy entries,
and parallel adaptive stop/target/time searches, see the
[GNET Backtester guide](documentation/backtester.md). It does not require the
live services below and leaves the existing independent-entry collector intact.

```
TradeStation
  ├── BarBridge.dll  (port 9009)  →  tcp_to_redis_connection.py  →  validated_bar
  └── TickBridge.dll (port 9010)  →  tcp_to_redis_ticks.py       →  tick_data_raw
                                                                        ↓
                                                              tick_validator.py
                                                                        ↓
                                                              tick_data_validated
                                                                        ↓
                                                              volume_profile.py  →  features_volume_profile

validated_bar → transformer_features.py → features_transformer ─────┐
TradeStation strategies → StrategyBridge.dll (9012) → candidates ───┤
                                                                    ↓
                                      strategy_router.py → selected model
                                                                    ↓
                                      trade_decisions → TCP 9011
                                                                    ↓
                                      SignalBridge.dll → matching TS window
```

---

## Live Pipeline — Launch Order

The tested MA-13 customer runtime uses CPython 3.12.7 and the exact package
versions in `requirements-runtime-lock.txt`. Install them with:

```powershell
python -m pip install -r requirements-runtime-lock.txt
```

`requirements-development-lock.txt` adds the test tooling used by developers;
it is not required on a customer trading machine.

After launching the complete pipeline, run the automated installation checks
and complete the required TradeStation simulation attestation:

```powershell
.\verify_install.ps1
```

The script refuses to record manual acceptance unless files, x86 DLLs, pinned
Python runtime, model/scaler, registry, Docker, Redis, router readiness, and
ports 9009–9012 plus the registry page on 9020 all pass first. Use
`-AutomatedOnly` for a non-interactive result or `-SkipServiceChecks` while
validating a package before its services are launched.

### Step 1 — Infrastructure
```powershell
.\launch_grid.ps1
```

Starts Docker Desktop, Redis (`6381`), TradeStation, and all nine Python
services inside one Windows Terminal window with three tabs and three panes per
tab, then opens the local registry page. Use `.\launch.ps1` only when nine
independent PowerShell windows are preferred.

> [!WARNING]
> Do not enable the GNET EasyLanguage indicators or strategy until
> `launch_grid.ps1` reports `=== All services launched ===` and ports `9009`, `9010`,
> `9011`, and `9012` are all listening. Otherwise the DLL connection/retry loop
> can make TradeStation appear frozen.

Check all four TradeStation-facing ports at any time:

```powershell
.\check_gnet_ports.ps1 -Watch
```

The dashboard refreshes every ten seconds. Press `Ctrl+C` to stop it. Run
`.\check_gnet_ports.ps1` without `-Watch` for a single scriptable check.

For the bounded seven-day live-market test, first confirm TradeStation is using
a simulation account, then start the passive evidence recorder in a separate
terminal:

```powershell
.\start_live_test.ps1 -SimulationConfirmed
```

The observer never submits orders or connects to the four DLL-facing TCP
listeners. It writes health, stream, exact-candidate, decision, latency, and
pending-acknowledgement evidence under `live_test_runs\<timestamp>`. Follow
`documentation\seven_day_live_test.md` for the daily checks and stop criteria.

Stop or restart the PID-scoped GNET service trees without clearing Redis.
Plain `stop.ps1` leaves Docker Desktop, `redis1`, Redis data, and TradeStation
running:

```powershell
.\stop.ps1
.\restart.ps1
```

Stop GNET and Redis and close Docker Desktop to release its memory, without
deleting Redis data:

```powershell
.\stop.ps1 -StopDockerDesktop
```

Restart the Redis container too, without deleting its data:

```powershell
.\restart.ps1 -RestartRedis
```

Emergency force-close for a frozen TradeStation instance:

```powershell
cd C:\Users\g_med\python_new\GNET
.\kill_tradestation.ps1 -ListOnly
.\kill_tradestation.ps1
```

Destructive hard reset—remove `redis1` and all data, recreate it empty, then
shut down Docker Desktop and its engine:

```powershell
.\nuke.ps1 -ConfirmDataLoss -RecreateEmptyRedis
```

### Step 2 — Bar Ingestion
```powershell
python -m netwo_files.tcp_to_redis_connection
```

### Step 3 — Tick Pipeline (3 terminals)
```powershell
python -m netwo_files.tcp_to_redis_ticks   # drain kernel buffer
python -m netwo_files.tick_validator        # cast + validate + push
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600 --snapshot-interval-s 30 --snapshot-offset-s 29.925
```

The bar and tick TCP servers are persistent across TradeStation/chart
disconnects. Each closes the old client, discards any incomplete trailing line,
and returns to `accept()` so the hardened DLL can reconnect without relaunching
the Python terminal.

### Step 4 — Feature Pipeline
```powershell
python -m feat_files.transformer_features  # 13 features → features_transformer
```

### Step 5 — Candidate-Triggered Inference (3 terminals)
```powershell
python -m inference.candidate_tcp_server   # StrategyBridge → trade_candidates
python -m inference.strategy_router        # exact feature match → selected model
python -m inference.signal_tcp_server      # trade_decisions → TCP 9011
```

### Step 6 — TradeStation
- Apply bar indicator → `BarBridge.dll` → port 9009
- Send primary candidates → shared `StrategyBridge.dll` → port 9012
- Poll decisions by strategy instance ID → `SignalBridge.dll` → port 9011

### Optional — Local Model Registry

```powershell
python -m gnet_ui.server
```

Open `http://127.0.0.1:9020` to enable models and configure threshold/device.
Restart the strategy router after saving registry changes.

---

## Offline Training Pipeline

```powershell
cd training_mlp

# 1. Build labeled dataset from raw TradeStation exports
python study_pipeline.py

# 2. Train MLP with purged-embargo walk-forward CV
python 30_training_mlp.py

# 3. Evaluate on frozen test set (run once)
python 30_evaluate_mlp.py
```

Artifacts saved to `training_mlp/strategies/MA2CrossLE/model/mlp_baseline/`
by the default strategy configuration.

---

## Model Results

Trained on 17,761 labeled MA2CrossLE entries on ES 30-second bars. Evaluated on 1,776 held-out entries.

| Metric | Naive MA Crossover | MLP Meta-Model |
|---|---|---|
| Accuracy | 0.5058 | **0.5822** |
| F1 Score | — | **0.6123** |
| AUC | — | **0.6203** |

---

## Redis Streams

| Stream | Producer | Consumer | maxlen |
|---|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `transformer_features.py` | 1,000 |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` | 50,000 |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` | 50,000 |
| `features_transformer` | `transformer_features.py` | `strategy_router.py` | 1,000 |
| `features_volume_profile` | `volume_profile.py` | `consolidator.py` | 50,000 |
| `trade_candidates` | `candidate_tcp_server.py` | `strategy_router.py` | 5,000 |
| `trade_decisions` | `strategy_router.py` | `signal_tcp_server.py` | 5,000 |

Redis: `127.0.0.1:6381` (Docker)

---

## Key Files

| File | Role |
|---|---|
| `config/setting.py` | All TCP/Redis hosts, ports, stream names |
| `EL_files/dll.cpp` | C++ source — BarBridge.dll (SendBar, port 9009) |
| `EL_files/tick_dll.cpp` | C++ source — TickBridge.dll (SendTick, port 9010) |
| `EL_files/strategy_dll.cpp` | C++ source — StrategyBridge.dll (SendCandidate, port 9012) |
| `EL_files/signal_dll.cpp` | C++ source — SignalBridge.dll (per-instance decisions, port 9011) |
| `netwo_files/tcp_to_redis_connection.py` | Bar TCP server — parse + validate + push |
| `netwo_files/tcp_to_redis_ticks.py` | Tick TCP server — drain only, zero processing |
| `netwo_files/tick_validator.py` | Tick cast + validate + sequence check |
| `feat_files/transformer_features.py` | 13 features, 60-bar rolling window |
| `feat_files/volume_profile.py` | Stateful POC/Value Area; updates every tick and publishes once per interval at wall-clock offset 29.925 |
| `inference/candidate_tcp_server.py` | Validates candidates and publishes `trade_candidates` |
| `inference/strategy_router.py` | Exact symbol/date/time feature join, model selection, inference, decision publishing; bar number remains diagnostic |
| `inference/model_registry.py` | Discovers and validates directory-backed strategy models |
| `inference/signal_tcp_server.py` | Serves exact-candidate `trade_decisions` over TCP 9011 |
| `gnet_ui/server.py` | Local model-registry page on port 9020 |
| `training_mlp/study_pipeline.py` | Builds labeled dataset from raw TradeStation exports |
| `training_mlp/30_training_mlp.py` | Purged-embargo CV training |
| `training_mlp/30_evaluate_mlp.py` | Held-out test evaluation |
| `launch_grid.ps1` | Recommended one-window launcher: three service tabs plus a dedicated live GNET health-monitoring tab |
| `launch.ps1` | Legacy nine-window pipeline launcher and grid implementation core |

---

## Documentation

Full docs in `documentation/`. Key references:

- `documentation/project_control_center.md` — master reference
- `documentation/how_to_run_pipeline.md` — full live pipeline launch guide
- `documentation/how_to_train.md` — offline training pipeline guide
- `documentation/how_to_compile_dll.md` — compile all four TradeStation DLLs
- `documentation/strategy_candidate_integration.md` — candidate and decision API
- `documentation/model_registry_ui.md` — directory registry and local management page
- `documentation/features_list.md` — all 13 features with formulas
- `documentation/redis_setup.md` — Redis setup and stream reference
- `diagrams/gnet_online_high_level.mmd` — high-level live architecture with offline training compressed to its deployed artifacts
- `diagrams/gnet_offline_training.mmd` — historical preparation, canonical features, safe MA/VP merge, correlation, validation, and artifact production
- `diagrams/system_overview.mmd` — detailed live system architecture
