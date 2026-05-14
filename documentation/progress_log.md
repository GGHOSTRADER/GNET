# Progress Log
> **What:** Running log of completed work by session — what was built, fixed, or cleaned up.

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
