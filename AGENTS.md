# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What This Is

GNET is a real-time end-to-end meta-labeling ML pipeline for ES (E-mini S&P 500) futures. TradeStation streams bar and tick data over TCP into Redis, Python services engineer microstructure features and run a trained MLP, and trade/no-trade signals are sent back to TradeStation — all within one 30-second bar close.

## Commands

### Run Tests
```powershell
pytest
pytest tests/test_volume_profile.py          # single file
pytest tests/test_volume_profile.py::test_find_poc_returns_highest_volume_level  # single test
```

### Launch Full Pipeline (one command)
```powershell
.\launch.ps1
```
Opens 7 numbered PowerShell terminals, Docker, Redis, and TradeStation.

### Run Individual Services
```powershell
# Infrastructure — must be running before any service
docker start redis1   # Redis on 127.0.0.1:6381

# Bar ingestion (port 9009)
python -m netwo_files.tcp_to_redis_connection

# Tick pipeline — run in this order
python -m netwo_files.tcp_to_redis_ticks
python -m netwo_files.tick_validator
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600 --snapshot-interval-s 30

# Feature + inference
python -m feat_files.transformer_features
python -m inference.inference_engine
python -m inference.signal_tcp_server        # port 9011
```

### Offline Training
```powershell
cd training_mlp
python study_pipeline.py          # build labeled dataset from TradeStation CSV exports
python 30_training_mlp.py         # purged-embargo walk-forward CV
python 30_evaluate_mlp.py         # held-out test evaluation (run once)
```
Artifacts go to `training_mlp/experiments/mlp_baseline/` (`model_best.pt`, `scaler_best.pkl`, `config.json`).

### Debug: Monitor Two Feature Streams Together
```powershell
python -m feat_files.consolidator
```

## Architecture

### Data Flow
```
TradeStation
  ├── BarBridge.dll  (port 9009) → tcp_to_redis_connection.py → validated_bar (Redis stream)
  └── TickBridge.dll (port 9010) → tcp_to_redis_ticks.py → tick_data_raw
                                                               ↓
                                                       tick_validator.py → tick_data_validated
                                                                               ↓
                                                               volume_profile.py → features_volume_profile

validated_bar → transformer_features.py → features_transformer
                                                  ↓
                                        inference_engine.py (MLP)
                                                  ↓
                                            trade_signal
                                                  ↓
                                        signal_tcp_server.py (port 9011)
                                                  ↓
                                        SignalBridge.dll → TradeStation
```

### Module Map
| Module | Role |
|---|---|
| `config/setting.py` | Single source of truth for all hosts, ports, Redis stream names |
| `netwo_files/bar_contract.py` | `Bar` frozen dataclass + `validate_bar` + `validate_sequence` |
| `netwo_files/bar_codec.py` | CSV/Redis ↔ `Bar` encoding/decoding; `parse_xread_to_bars` |
| `netwo_files/tcp_to_redis_connection.py` | TCP server; parse + validate + push to `validated_bar` |
| `netwo_files/tcp_to_redis_ticks.py` | Tick TCP drain (zero processing, max throughput) |
| `netwo_files/tick_validator.py` | Cast + validate ticks, push to `tick_data_validated` |
| `feat_files/transformer_features.py` | 13 features from 60-bar rolling window; `FeaturePoint` dataclass |
| `feat_files/volume_profile.py` | Stateful incremental POC + Value Area; one snapshot per bar |
| `feat_files/consolidator.py` | Debugging tool: merges transformer + volume profile streams |
| `inference/inference_engine.py` | Loads MLP, scales features, writes signal to `trade_signal` |
| `inference/signal_tcp_server.py` | Serves `trade_signal` over TCP port 9011 |
| `EL_files/dll.cpp` | C++ source for BarBridge.dll (bar sender) |
| `EL_files/tick_dll.cpp` | C++ source for TickBridge.dll (tick sender) |
| `EL_files/signal_dll.cpp` | C++ source for SignalBridge.dll (signal receiver) |

### Redis Streams
| Stream | Producer | Consumer | maxlen |
|---|---|---|---|
| `validated_bar` | `tcp_to_redis_connection` | `transformer_features` | 1,000 |
| `tick_data_raw` | `tcp_to_redis_ticks` | `tick_validator` | 50,000 |
| `tick_data_validated` | `tick_validator` | `volume_profile` | 50,000 |
| `features_transformer` | `transformer_features` | `inference_engine` | 1,000 |
| `features_volume_profile` | `volume_profile` | `consolidator` | 50,000 |
| `trade_signal` | `inference_engine` | `signal_tcp_server` | 500 |

Redis is at `127.0.0.1:6381` (Docker container named `redis1`).

## Design Conventions

### Clean Architecture Layering (enforced throughout)
- **Domain** (`bar_contract.py`): pure types and invariants; no I/O, no Redis.
- **Adapter** (codec + TCP servers): transport ↔ domain conversion at the boundary only.
- **Application** (feature/inference loops): orchestration using domain types; delegates I/O to adapters.

### Bar Data Contract
- `Bar` is a frozen dataclass defined in `netwo_files/bar_contract.py`. All data entering the system is cast and validated into `Bar` before any processing.
- `date` field is TradeStation's packed integer format (`YYYYMMDD` as int, where the year component is years-since-1900, e.g., `1260412` = April 12, 2026).
- `time_s` is seconds since midnight (0–86399). Market open is 09:30 = 34200 seconds.
- `up`/`down` are bid/ask volume proxies (integer tick counts).
- Three error types are used at the boundary: `DecodeError` (parsing/casting failed), `ContractError` (invariant violated), `XReadShapeError` (malformed XREAD structure).

### Feature Engineering
- All 13 features in `transformer_features.py` are **pure functions**: no I/O, no globals, no mutation.
- The system waits for a 60-bar warm-up window before emitting any `FeaturePoint`.
- Feature functions use `_require_feature()` (always active, never disabled) not `assert`.
- Volume profile (`volume_profile.py`) uses stateful O(1) incremental updates per tick; derives POC, Value Area, and derived features once per bar in `_snapshot()`.

### No External ML Libraries
The feature engineering stack uses only `math`, `collections.deque`, and `numpy` (volume profile only). No pandas, no talib, no sklearn in the hot path. The trained MLP uses PyTorch.

### `bar_to_redis_fields` Encoding
Floats are encoded with `repr()` for stable round-trip precision. Integers use `str()`. The `date` field is zero-padded to 6 digits with `f"{b.date:06d}"`.
