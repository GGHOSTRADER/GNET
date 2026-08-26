# GNET — Meta-Labeling ML Pipeline for Algorithmic Trade Filtering

Real-time end-to-end machine learning pipeline for ES (E-mini S&P 500)
futures. It calculates market features continuously, but runs a strategy's
model only when TradeStation sends an actual primary-signal candidate.

**GitHub:** [https://github.com/GGHOSTRADER/GNET](https://github.com/GGHOSTRADER/GNET)

---

## System Overview

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
| `launch_grid.ps1` | Recommended one-window, three-tab pipeline launcher |
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
- `diagrams/system_overview.mmd` — full architecture diagram
