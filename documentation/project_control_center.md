# Project Control Center
> **What:** Master reference — full system component list, data flow overview, and step-by-step launch guide for the entire pipeline.

## System Flow

| Step | Description | Artifacts | Contract |
|---|---|---|---|
| 1 | TradeStation gets market data | TS Desktop | — |
| 2 | Docker fires Redis container | Docker Desktop | [[redis_setup]] |
| 3 | EasyLanguage calls DLL → binds TCP → exports data | [[easylanguage_bar_indicator]] / `dll.cpp` / `BarBridge.dll` | [[bar_data_contract]] |
| 4 | Python TCP server receives, parses, validates, pushes to Redis | `tcp_to_redis_connection.py` | [[bar_data_contract]] |
| 5 | Feature pipelines read from Redis and compute | `transformer_features.py` / `volume_profile.py` | [[features_list]] |
| 6 | A strategy sends a candidate only when its primary signal fires | `StrategyBridge.dll` / `candidate_tcp_server.py` | [[strategy_candidate_integration]] |
| 7 | Router joins the exact symbol/date/time feature row, selects the model, and writes a decision | `inference/strategy_router.py` | [[features_list]] |
| 8 | Decision TCP server returns the exact candidate's result to the correct strategy window | `signal_tcp_server.py` / `SignalBridge.dll` | [[strategy_candidate_integration]] |

---

## System Components

### External Software

| Component | Description |
|---|---|
| **TradeStation** | Market data source. Runs EasyLanguage indicators on bar close and polls for signals |
| **Docker Desktop** | Runs the Redis container on Windows |

---

### Bar Data Ingestion

| File | Role |
|---|---|
| [[easylanguage_bar_indicator]] | EasyLanguage indicator — calls `SendBar()` on every bar close |
| `EL_files/dll.cpp` | C++ Win32 DLL source — opens TCP socket to `127.0.0.1:9009`, sends CSV |
| `EL_files/BarBridge.dll` | Compiled DLL loaded by TradeStation |
| `netwo_files/tcp_to_redis_connection.py` | Persistent Python TCP server — accepts replacement DLL clients, receives CSV, parses, validates, writes to `validated_bar` |
| `netwo_files/bar_contract.py` | `Bar` dataclass + `validate_bar()` + `validate_sequence()` |
| `netwo_files/bar_codec.py` | Parse/encode — `parse_csv_line()`, `bar_from_redis_fields()`, `parse_xread_to_bars()` |

---

### Tick Data Pipeline

Separate high-frequency pipeline. Ingest and validation are split into two processes so the TCP server never blocks.

| File | Role |
|---|---|
| [[easylanguage_tick_indicator]] | EasyLanguage indicator — calls `SendTick()` on every tick |
| `EL_files/tick_dll.cpp` | C++ Win32 DLL source — opens TCP socket to `127.0.0.1:9010`, sends CSV |
| `EL_files/TickBridge.dll` | Compiled DLL loaded by TradeStation |
| `netwo_files/tcp_to_redis_ticks.py` | Persistent ultra-lean TCP server on 9010 — accepts replacement DLL clients, drains the kernel buffer, and pushes raw CSV to `tick_data_raw`. Zero processing. |
| `netwo_files/tick_validator.py` | Separate process — reads `tick_data_raw`, casts, validates, pushes clean ticks to `tick_data_validated` |
| `netwo_files/tick_contract.py` | `Tick` dataclass + `validate_tick()` (enforces `high == low`) + `validate_tick_sequence()` |
| `netwo_files/tick_codec.py` | Parse/encode — `parse_raw_tick_line()`, `tick_from_redis_fields()`, `tick_to_redis_fields()`, `parse_xread_to_ticks()` |

---

### Network / Config

| File | Role |
|---|---|
| `config/setting.py` | Central config — all TCP hosts/ports, Redis host/port/stream names |
| `netwo_files/redis_tool.py` | Redis connection helper — `get_redis_connection()` |

---

### Feature Pipelines

| File | Reads From | Features | Window |
|---|---|---|---|
| `feat_files/transformer_features.py` | `validated_bar` | `parkinson_vol`, `ofi`, `volume_percentile`, `volume_momentum`, `amihud`, `vwap_distance`, `session flags`, `day_of_week` | 60 bars |
| `feat_files/volume_profile.py` | `tick_data_validated` | Canonical 32-feature VP contract: classified delta, Value Area dynamics, shape, acceptance, POC velocity, and HVN/LVN groups | Full 18:00 ES session; one committed snapshot per interval at wall-clock offset 29.925 |

See [[volume_profile_design]] for volume profile design and API. See [[features_list]] for full feature reference.

---

### Inference Layer

Features continue to publish every bar. Models run only after a primary
strategy candidate arrives. The router requires an exact symbol, date, time,
match; it never substitutes the latest feature record. TradeStation bar number
is retained as study-local diagnostic metadata and is not part of the join key.

| File | Role |
|---|---|
| `EL_files/strategy_dll.cpp` | Shared candidate DLL source — all strategy windows send through port 9012 |
| `inference/candidate_tcp_server.py` | Validates candidate payloads and writes `trade_candidates` |
| `inference/strategy_router.py` | Joins candidates to exact features, selects the configured model, writes `trade_decisions` |
| `inference/model_registry.py` | Discovers and validates enabled models from `model_registry/*/registry.json` |
| `gnet_ui/server.py` | Optional local registry page on `127.0.0.1:9020`; outside the inference path |
| `inference/signal_tcp_server.py` | Reads `trade_decisions` and forwards exact-candidate decisions on port 9011 |
| `EL_files/signal_dll.cpp` | Queues decisions by strategy-instance ID for non-blocking TradeStation polling |
| `EL_files/SignalBridge.dll` | Compiled DLL loaded by TradeStation |
| `training_mlp/strategies/MA2CrossLE/model/mlp_baseline/` | MA model, scaler, and configuration loaded once by the router |

Candidate and decision schemas are documented in [[strategy_candidate_integration]].

---

### Tests

| File | Role |
|---|---|
| `tests/test_tcp_to_redis_connection.py` | Tests for bar parsing, casting, contract validation |
| `tests/test_ingestion_reconnect.py` | Proves bar/tick servers accept replacement clients, survive resets, and never combine partial bytes across TCP sessions |

---

## Ports

| Port | Used By | Direction |
|---|---|---|
| `9009` | Bar TCP server — TradeStation bar DLL connects here | TS → Python |
| `9010` | Tick TCP server — TradeStation tick DLL connects here | TS → Python |
| `9011` | Decision TCP server — TradeStation SignalBridge connects here | Python → TS |
| `9012` | Candidate TCP server — shared StrategyBridge connects here | TS → Python |
| `6381` | Redis — Docker container (maps internal `6379` → Windows `6381`) | local |

## Redis Streams

| Stream | Written By | Read By | maxlen |
|---|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `transformer_features.py` | 1,000 |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` | 50,000 |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` | 50,000 |
| `features_transformer` | `transformer_features.py` | `strategy_router.py`; optional `consolidator.py` debugger | 1,000 |
| `features_volume_profile` | `volume_profile.py` | optional `consolidator.py` debugger only | 50,000 |
| `trade_candidates` | `candidate_tcp_server.py` | `strategy_router.py` | 5,000 |
| `trade_decisions` | `strategy_router.py` | `signal_tcp_server.py` | 5,000 |

---

## How to Launch

### 1. Run the Launch Script
```bash
.\launch_grid.ps1
```
Starts Docker Desktop and Redis, launches all nine services in consumer-first
order inside one Windows Terminal window with three tabs, then opens
TradeStation and the registry page after the TCP listeners are ready. Use
`.\launch.ps1` for the legacy nine-window layout.

### 2. Start the Bar TCP Server
```bash
python -m netwo_files.tcp_to_redis_connection
```

### 3. Start the Tick Pipeline (3 terminals)
```bash
# Terminal 1 — ingest raw ticks, port 9010
python -m netwo_files.tcp_to_redis_ticks

# Terminal 2 — validate and push to tick_data_validated
python -m netwo_files.tick_validator

# Terminal 3 — volume profile reads tick_data_validated
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600
```

### 4. Start the Transformer Feature Pipeline
```bash
python -m feat_files.transformer_features
```

### 5. Start Candidate Routing (3 terminals)
```bash
# Terminal 1 — receives all strategy candidates on shared port 9012
python -m inference.candidate_tcp_server

# Terminal 2 — exact symbol/date/time feature join and model inference
python -m inference.strategy_router

# Terminal 3 — serves exact-candidate decisions to TradeStation
python -m inference.signal_tcp_server
```

### 6. Apply EasyLanguage Indicators in TradeStation
- Bar chart: [[easylanguage_bar_indicator]] → `BarBridge.dll` → port 9009
- Tick chart: [[easylanguage_tick_indicator]] → `TickBridge.dll` → port 9010
- Candidate sender: [[strategy_candidate_integration]] → `StrategyBridge.dll` → port 9012
- Decision receiver: [[easylanguage_signal_indicator]] → `SignalBridge.dll` → port 9011

> Need to compile a DLL? See [[how_to_compile_dll]].

---

## Key Documentation

| File | Description |
|---|---|
| [[bar_data_contract]] | All 11 bar fields, types, invariants |
| [[tick_data_contract]] | All 8 tick fields, types, invariants |
| [[redis_setup]] | Redis setup and Docker commands |
| [[how_to_compile_dll]] | How to compile all four TradeStation DLLs |
| [[how_to_run_pipeline]] | Detailed pipeline launch instructions |
| [[volume_profile_design]] | Volume profile design and API |
| [[features_list]] | All engineered features reference table |
| [[easylanguage_signal_indicator]] | EasyLanguage code to receive signals from `SignalBridge.dll` |
| [[strategy_candidate_integration]] | Candidate payload, exact matching, and per-instance decision API |
| [[model_registry_ui]] | Directory-backed model discovery and local browser configuration |

---

## Open TODOs

- **Volume-profile snapshot cadence:** the live adapter now publishes once at wall-clock offset `29.925` in every 30-second interval. Continue profiling live p99 latency and move the configurable gate earlier if the current 75 ms allowance proves insufficient.
