# Progress Log
> **What:** Running log of completed work by session — what was built, fixed, or cleaned up.

---

## 2026-05-22 (session 4)

### Inference Layer — built from scratch

- `inference/inference_engine.py` — reads `features_transformer` Redis stream, scales with `scaler_best.pkl`, runs `model_best.pt` MLP forward pass, writes `signal` + `prob` to `trade_signal` stream. Threshold injectable (default 0.5).
- `inference/signal_tcp_server.py` — reads `trade_signal`, maintains one persistent TCP connection on port 9011, sends `symbol,signal,prob\n` per signal to TradeStation.
- `EL_files/signal_dll.cpp` — `SignalBridge.dll`. EL calls `RecvSignal(symbol, signal, prob)` on each bar close. Non-blocking: returns 0 immediately if no signal ready, 1 on new signal. Persistent TCP client to port 9011.
- `config/setting.py` — added `TCP_SIGNAL_PORT=9011` and `REDIS1_SIGNAL_STREAM="trade_signal"`.

### day_of_week feature added to transformer pipeline

- `feat_files/transformer_features.py` — added `_day_of_week()` pure function (YYYYMMDD → Python weekday int, Monday=0), added `day_of_week` to `FeaturePoint` dataclass and `_feature_point_to_redis_fields()` encoder.
- Feature is now published in the `features_transformer` Redis stream alongside the other 12 features.
- Inference engine reads it directly from the stream — no derivation at inference time.

### Documentation and diagrams updated

- `diagrams/flow_bar.mmd` — extended to show full inference loop: `features_transformer` → `inference_engine` → `trade_signal` → `signal_tcp_server` → `SignalBridge.dll` → TradeStation
- `diagrams/system_overview.mmd` — added inference layer and signal return path back to TS
- `documentation/features_list.md` — added `day_of_week` row, MLP feature order table, VP features noted as not yet used
- `documentation/project_control_center.md` — added Inference Layer component section, updated System Flow (steps 6-7), ports table with direction column, Redis streams table with `trade_signal`, updated launch steps
- `documentation/how_to_run_pipeline.md` — added Step 4 (transformer features), Step 5 (inference layer), updated ports and streams reference tables
- `documentation/how_to_compile_dll.md` — refactored to cover all three DLLs with a summary table
- `documentation/easylanguage_signal_indicator.md` — new file with EasyLanguage code for `RecvSignal()` integration

---

## 2026-05-14 (session 3)

### Consolidator
- `feat_files/consolidator.py` — merges `features_transformer` (clock) and `features_volume_profile` (latest xrevrange) into a single print per bar
- Symbol mismatch guard — logs warning and skips if TF and VP symbols differ
- Time display fixed — `time_s` (seconds since midnight) now formatted as `HH:MM:SS` in output

### Volume Profile
- Moved to tick pipeline — reads from `tick_data_validated` instead of `validated_bar` (one update per tick, not per bar close)
- `run_publish_loop()` pushes scalar fields to `features_volume_profile` stream (maxlen 50,000)
- Documentation (`volume_profile_design.md`) updated: corrected stream name, added **What Is Stateful** section detailing every field in `_SessionState` and that POC/VA are derived on demand, not stored

### Redis maxlen policy locked in
- Tick streams (`tick_data_raw`, `tick_data_validated`, `features_volume_profile`) → 50,000
- Bar streams (`validated_bar`, `features_transformer`) → 1,000
- `redis_setup.md` updated with full streams table and maxlen rationale

### Kernel TCP receive buffer
- `tcp_to_redis_ticks.py` — added `SO_RCVBUF = 1MB` next to `SO_REUSEADDR`
- Gives ~50 seconds of tick backlog at 400 ticks/s vs ~3 seconds on Windows default
- Documented in `redis_setup.md` with before/after table

### GIL documentation
- Added GIL note to `tcp_to_redis_ticks.py` docstring — redis-py holds GIL during `xadd`, costs ~20ms/s at 400 ticks/s, SO_RCVBUF absorbs bursts while GIL is locked

### Diagrams updated
- `diagrams/flow_tick.mmd` — added Volume Profile subgraph consuming `tick_data_validated` and pushing to `features_volume_profile`
- `diagrams/system_overview.mmd` — consolidator node added showing both feature streams merging

### Documentation
- `README.md` created — project overview, ASCII system diagram, ordered launch commands, Redis streams table, key files index
- `documentation/redis_setup.md` — added **Kernel TCP Receive Buffer** section and **Potential Improvements** (Unix domain socket + tick batching with pipeline code example)
- `documentation/redis_setup.md` — added **Streams on Redis 1** table

### Git hygiene
- `.gitignore` created — covers `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.obsidian/`, `*.dll`, `*.obj`, `*.exp`, `*.lib`, `.env`

---

## 2026-05-13 (session 2)

### Tick Data Pipeline — built from scratch
- `netwo_files/tick_contract.py` — `Tick` dataclass + `validate_tick()` (enforces `high == low`) + `validate_tick_sequence()`
- `netwo_files/tick_codec.py` — `parse_raw_tick_line()`, `tick_from_redis_fields()`, `tick_to_redis_fields()`, `parse_xread_raw_ticks()`
- `netwo_files/tcp_to_redis_ticks.py` — ultra-lean TCP server on port 9010, drains kernel buffer, pushes `{"raw_tick": line}` to `tick_data_raw` with zero processing
- `netwo_files/tick_validator.py` — separate process reads `tick_data_raw`, casts + validates + sequence checks, pushes clean ticks to `tick_data_validated`
- `netwo_files/flow_tick.mmd` — Mermaid diagram of the full tick pipeline

### Architecture decision
Tick pipeline intentionally splits ingest and validation into two separate processes. TCP server only drains kernel buffer — no parsing, no blocking. Validator runs independently so it can never slow down ingest.

### Config updated
Added `TCP_TICK_HOST`, `TCP_TICK_PORT=9010`, `REDIS1_TICK_RAW_STREAM=tick_data_raw`, `REDIS1_TICK_VALIDATED_STREAM=tick_data_validated` to `config/setting.py`

---

## 2026-05-13 (session 1)

### Pipeline Running
- Full data flow working: TradeStation → `BarBridge.dll` → TCP → `tcp_to_redis_connection.py` → Redis stream `validated_bar`
- Redis running via Docker container on port `6381`
- `launch.ps1` automates: Docker Desktop + Redis container + TradeStation on startup

### New Files
- `feat_files/volume_profile.py` — stateful incremental volume profile, O(1) per bar, pre-allocated grid with 15% boundary extension
- `transformer_features.py` — rebuilt from pandas/CSV to Redis streaming, 8 features over 60-bar rolling window
- `launch.ps1` — one-shot launch script for Docker + Redis + TradeStation
- `feat_files/volume_profile_documentation.md` — full API and design docs
- `feat_files/volume_profile.mmd` — Mermaid flow diagram
- `netwo_files/flow.mmd` — full pipeline Mermaid diagram

### Cleaned Up
- Removed redundant re-validation from all feature pipelines — data is already validated at ingestion
- All `.txt` docs converted to `.md` for Obsidian
- `project_control_center.md` rewritten with component table, system flow, Obsidian wiki links, and launch guide