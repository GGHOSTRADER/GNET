# Project Control Center
> **What:** Master reference — full system component list, data flow overview, and step-by-step launch guide for the entire pipeline.

## System Flow

| Step | Description | Artifacts | Contract |
|---|---|---|---|
| 1 | TradeStation gets market data | TS Desktop | — |
| 2 | Docker fires Redis container | Docker Desktop | [[redis_setup]] |
| 3 | EasyLanguage calls DLL → binds TCP → exports data | [[easylanguage_bar_indicator]] / `dll.cpp` / `BarBridge.dll` | [[bar_data_contract]] |
| 4 | Python TCP server receives, parses, validates, pushes to Redis | `tcp_to_redis_connection.py` | [[bar_data_contract]] |
| 5 | Feature pipelines read from Redis and compute | `feat_eng_1.py` / `transformer_features.py` / `volume_profile.py` | — |

---

## System Components

### External Software

| Component | Description |
|---|---|
| **TradeStation** | Market data source. Runs the EasyLanguage indicator on bar close |
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

See `netwo_files/flow_tick.mmd` for the tick pipeline diagram.

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
| `transformer_features.py` | `validated_bar` | `parkinson_vol`, `ofi`, `volume_percentile`, `volume_momentum`, `amihud`, `vwap_distance`, `session flags` | 60 bars |
| `feat_files/volume_profile.py` | `tick_data_validated` | `poc_price`, `value_area_low`, `value_area_high`, `total_volume` | Full session |

See [[volume_profile_design]] for volume profile design and API.

---

### Tests

| File | Role |
|---|---|
| `tests/test_tcp_to_redis_connection.py` | Tests for bar parsing, casting, contract validation |
| `tests/test_feat.py` | Tests for `modSlope5` feature function |

---

## Ports

| Port | Used By |
|---|---|
| `9009` | Bar TCP server — TradeStation bar DLL connects here |
| `9010` | Tick TCP server — TradeStation tick DLL connects here |
| `6381` | Redis — Docker container (maps internal `6379` → Windows `6381`) |

## Redis Streams

| Stream | Written By | Read By |
|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `feat_eng_1.py`, `transformer_features.py` |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` |

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
python -m feat_files.volume_profile
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600
```

### 4. Apply EasyLanguage Indicators in TradeStation
- Bar chart: [[easylanguage_bar_indicator]] → `BarBridge.dll` → port 9009
- Tick chart: [[easylanguage_tick_indicator]] → `TickBridge.dll` → port 9010

> Need to compile a DLL? See [[how_to_compile_dll]].

### 5. (Optional) Start Other Feature Pipelines
```bash
python -m feat_files.feat_eng_1      # modSlope5
python -m transformer_features       # transformer features
```

---

## Key Documentation

| File | Description |
|---|---|
| [[bar_data_contract]] | All 11 bar fields, types, invariants |
| [[tick_data_contract]] | All 8 tick fields, types, invariants |
| [[redis_setup]] | Redis setup and Docker commands |
| [[how_to_compile_dll]] | How to compile `BarBridge.dll` and `TickBridge.dll` |
| [[how_to_run_pipeline]] | Detailed pipeline launch instructions |
| [[volume_profile_design]] | Volume profile design and API |
| [[features_list]] | All engineered features reference table |
