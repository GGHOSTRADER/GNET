# Progress Log
> **What:** Running log of completed work by session — what was built, fixed, or cleaned up.

---

## 2026-06-15 (session 7)

### Fixed feature-formula mismatch causing inference to always output prob=0

- `feat_files/transformer_features.py` — `_ofi(bars, window)` and `_amihud_illiquidity(bars)` used different formulas than `training_mlp/study_pipeline.py`, which built the dataset that fit `scaler_best.pkl` and trained `model_best.pt`. The mismatch produced feature z-scores up to +25,078, saturating `sigmoid()` to exactly 0.0 on every bar — `inference_engine.py` never fired a buy signal regardless of market conditions.
- `_ofi(bars, window)` — was `sum(up - down)` (raw, unbounded). Now `(sum(up)-sum(down)) / sum(up+down)`, bounded `[-1, 1]`, matching `study_pipeline.py`'s `order_flow_imbalance()`. Returns `0.0` if total volume is `0`.
- `_amihud_illiquidity(bars, window=30)` — was a single-bar `|log_return| / volume` (missing price scaling and averaging). Now a 30-bar rolling mean of `|pct_change(close)| / (close * volume)`, matching `study_pipeline.py`'s `amihud_illiquidity()`. Window requirement goes from 2 bars to 31 bars (still ≤ 60, no warm-up change).
- Updated the module docstring's "Features emitted", "Window requirements", and "Function Summary" sections (entries 4 and 7) to match.
- `documentation/features_list.md` — updated `ofi_{5,15,30}` and `amihud_illiquidity` descriptions to the corrected formulas.

---

## 2026-06-14 (session 6)

### Fixed SignalBridge.dll — "invalid number of parameters passed" crash on TS

- `EL_files/signal_dll.cpp` — `RecvSignal()` previously took `Lpstr, int ref, double ref` out-params. EasyLanguage's `External:` declaration does not support `int ref` / `double ref` for DLL parameters, which crashed TS with "invalid number of parameters passed" (this was unverified/untested syntax from when the file was first written).
- Redesigned to plain value-only exports (same pattern as the proven-working `BarBridge.dll`/`SendBar`): `RecvSignal()` (`int`, no params) polls the socket and caches the parsed line; `GetSignal()` (`int`), `GetProb()` (`double`), `GetSymbol()` (`Lpstr`) read back the cached values.
- `documentation/easylanguage_signal_indicator.md` — updated EL code and "How It Works" for the new four-function interface (`ok = RecvSignal()`, then `GetSignal()`/`GetProb()`/`GetSymbol()` when `ok = 1`).
- Requires recompiling: `cl /LD /EHsc signal_dll.cpp ws2_32.lib /Fe:SignalBridge.dll`

---

## 2026-06-13 (session 5)

### Volume Profile — derived POC features + snapshot cadence

- `feat_files/volume_profile.py` — new pure function `_compute_derived_features()` computes 8 new features from the live profile: `poc_distance`, `poc_concentration`, `va_width`, `va_position`, `vol_above_poc_ratio`, `profile_entropy`, `profile_kurtosis`, `poc_migration`. All distance-like features expressed in ticks for scale-invariance.
- `_SessionState` gained `last_price` (current price for distance calcs) and `prev_poc_price` (persisted across snapshots, drives `poc_migration`).
- New `snapshot_interval_s` hyperparameter (default 30, matches bar length). `_update()` still runs on every tick (O(1)); `_snapshot()` now only fires when `tick.time_s % snapshot_interval_s == snapshot_interval_s - 1` — once per bar, 1 second before bar close. Resolves the tick-rate vs bar-rate mismatch without a second stream: the profile is session-cumulative, so missing the last second of ticks is negligible, and snapshotting early guarantees `features_volume_profile` is fresh before `features_transformer` fires for that bar.
- `stream_volume_profile()` and `run_publish_loop()` signatures updated to take `snapshot_interval_s`; added `--snapshot-interval-s` CLI flag.
- `VolumeProfileResult` and `_vp_result_to_redis_fields()` extended with all 8 new fields.
- `feat_files/consolidator.py` — `_print_consolidated()` now prints all 8 derived VP fields.

### Tests
- `tests/test_volume_profile.py` — 8 new tests covering each derived feature plus snapshot gating via `monkeypatch` (61 stub ticks, `snapshot_interval_s=30` → 2 yields at `time_s=29,59`). 18/18 in this file, 111/111 full suite passing.

### Documentation and diagrams updated
- `documentation/volume_profile_design.md` — major rewrite: snapshot cadence section, updated tick inputs, full `VolumeProfileResult` table, stateful-fields table, function summary.
- `feat_files/volume_profile_documentation.txt` — mirrored the same updates (inputs, outputs, storage, function summary), fixed long-standing `run_print_loop` → `run_publish_loop` naming bug.
- `documentation/features_list.md`, `documentation/redis_setup.md`, `documentation/project_control_center.md`, `documentation/how_to_run_pipeline.md`, `README.md` — updated for the 8 new features, `snapshot_interval_s` CLI flag, and `features_volume_profile` now publishing once per bar instead of every tick.
- `diagrams/volume_profile.mmd`, `diagrams/flow_tick.mmd`, `diagrams/system_overview.mmd` — added snapshot gate node and derived-features step, updated stream cadence labels.

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