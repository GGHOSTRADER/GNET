# Project Control Center
> **What:** Master reference — full system component list, data flow overview, and step-by-step launch guide for the entire pipeline.

## System Flow

| Step | Description | Artifacts | Contract |
|---|---|---|---|
| 1 | TradeStation gets market data | TS Desktop | — |
| 2 | Docker fires Redis container | Docker Desktop | [[redis_setup]] |
| 3 | EasyLanguage calls DLL → binds TCP → exports data | [[easylanguage_bar_indicator]] / `dll.cpp` / `BarBridge.dll` | [[bar_data_contract]] |
| 4 | Python TCP server receives, parses, validates, pushes to Redis | `tcp_to_redis_connection.py` | [[bar_data_contract]] |
| 5 | Feature pipelines read from Redis and compute | `feat_eng_1.py` / `transformer_features.py` / `volume_profile.py` | [[features_list]] |
| 6 | Inference engine scales features, runs MLP, writes trade signal | `inference/inference_engine.py` | [[features_list]] |
| 7 | Signal TCP server forwards signal to TradeStation | `inference/signal_tcp_server.py` / `SignalBridge.dll` | — |

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
| `netwo_files/tcp_to_redis_connection.py` | Python TCP server — receives CSV, parses, validates, writes to `validated_bar` |
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
| `netwo_files/tcp_to_redis_ticks.py` | Ultra-lean TCP server port 9010 — drains kernel buffer, pushes raw CSV to `tick_data_raw`. Zero processing. |
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
| `feat_files/feat_eng_1.py` | `validated_bar` | `modSlope5` | 5 bars |
| `feat_files/transformer_features.py` | `validated_bar` | `parkinson_vol`, `ofi`, `volume_percentile`, `volume_momentum`, `amihud`, `vwap_distance`, `session flags`, `day_of_week` | 60 bars |
| `feat_files/volume_profile.py` | `tick_data_validated` | `poc_price`, `value_area_low`, `value_area_high`, `total_volume` | Full session |

See [[volume_profile_design]] for volume profile design and API. See [[features_list]] for full feature reference.

---

### Inference Layer

Reads engineered features from Redis, runs the pretrained MLP, and sends buy signals back to TradeStation.

| File | Role |
|---|---|
| `inference/inference_engine.py` | Reads `features_transformer`, scales with `scaler_best.pkl`, runs `model_best.pt`, writes `signal` + `prob` to `trade_signal` |
| `inference/signal_tcp_server.py` | Reads `trade_signal`, serves one persistent TCP connection on port 9011, sends `symbol,signal,prob\n` per bar |
| `EL_files/signal_dll.cpp` | C++ Win32 DLL source — connects to port 9011, non-blocking `RecvSignal()` EL calls each bar close |
| `EL_files/SignalBridge.dll` | Compiled DLL loaded by TradeStation |
| `training_mlp/experiments/mlp_baseline/` | Trained artifacts — `model_best.pt`, `scaler_best.pkl`, `config.json` |

Signal protocol: `symbol,signal,prob\n` — `signal=1` means buy, `signal=0` means no trade.

---

### Tests

| File | Role |
|---|---|
| `tests/test_tcp_to_redis_connection.py` | Tests for bar parsing, casting, contract validation |
| `tests/test_feat.py` | Tests for `modSlope5` feature function |

---

## Ports

| Port | Used By | Direction |
|---|---|---|
| `9009` | Bar TCP server — TradeStation bar DLL connects here | TS → Python |
| `9010` | Tick TCP server — TradeStation tick DLL connects here | TS → Python |
| `9011` | Signal TCP server — TradeStation signal DLL connects here | Python → TS |
| `6381` | Redis — Docker container (maps internal `6379` → Windows `6381`) | local |

## Redis Streams

| Stream | Written By | Read By | maxlen |
|---|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `feat_eng_1.py`, `transformer_features.py` | 1,000 |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` | 50,000 |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` | 50,000 |
| `features_transformer` | `transformer_features.py` | `consolidator.py`, `inference_engine.py` | 1,000 |
| `features_volume_profile` | `volume_profile.py` | `consolidator.py` | 50,000 |
| `trade_signal` | `inference_engine.py` | `signal_tcp_server.py` | 500 |

---

## How to Launch

### 1. Run the Launch Script
```bash
.\launch.ps1
```
Starts Docker Desktop, waits for engine, starts Redis container, opens TradeStation.

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

### 5. Start the Inference Layer (2 terminals)
```bash
# Terminal 1 — runs model, writes to trade_signal
python -m inference.inference_engine

# Terminal 2 — serves signal over TCP to TradeStation
python -m inference.signal_tcp_server
```

### 6. Apply EasyLanguage Indicators in TradeStation
- Bar chart: [[easylanguage_bar_indicator]] → `BarBridge.dll` → port 9009
- Tick chart: [[easylanguage_tick_indicator]] → `TickBridge.dll` → port 9010
- Signal receiver: [[easylanguage_signal_indicator]] → `SignalBridge.dll` → port 9011

> Need to compile a DLL? See [[how_to_compile_dll]].

---

## Key Documentation

| File | Description |
|---|---|
| [[bar_data_contract]] | All 11 bar fields, types, invariants |
| [[tick_data_contract]] | All 8 tick fields, types, invariants |
| [[redis_setup]] | Redis setup and Docker commands |
| [[how_to_compile_dll]] | How to compile `BarBridge.dll`, `TickBridge.dll`, `SignalBridge.dll` |
| [[how_to_run_pipeline]] | Detailed pipeline launch instructions |
| [[volume_profile_design]] | Volume profile design and API |
| [[features_list]] | All engineered features reference table |
| [[easylanguage_signal_indicator]] | EasyLanguage code to receive signals from `SignalBridge.dll` |
