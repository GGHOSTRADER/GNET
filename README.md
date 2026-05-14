# GNET — Live Market Data & Feature Pipeline

Real-time market data infrastructure for TradeStation. Streams bar and tick data into Redis, computes features, and consolidates them into a single output per bar.

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

validated_bar       →  transformer_features.py  →  features_transformer   ─┐
tick_data_validated →  volume_profile.py        →  features_volume_profile ─┤→  consolidator.py
```

---

## Launch Order

### Step 1 — Infrastructure
```powershell
.\launch.ps1
```
Starts Docker Desktop, waits for engine, starts Redis container (`redis1` on port `6381`), opens TradeStation.

---

### Step 2 — Bar Ingestion
```powershell
python -m netwo_files.tcp_to_redis_connection
```

---

### Step 3 — Tick Pipeline (3 terminals)
```powershell
# Terminal A — drain kernel buffer, zero processing
python -m netwo_files.tcp_to_redis_ticks

# Terminal B — cast + validate + push clean ticks
python -m netwo_files.tick_validator

# Terminal C — stateful volume profile (POC + Value Area)
python -m feat_files.volume_profile
# or with custom grid:
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600
```

---

### Step 4 — Feature Pipelines
```powershell
# 8 features over 60-bar rolling window
python -m feat_files.transformer_features

# slope feature (5-bar window)
python -m feat_files.feat_eng_1
```

---

### Step 5 — Consolidator
```powershell
# Merges transformer features + volume profile, prints one block per bar
python -m feat_files.consolidator
```

---

## Redis Streams

| Stream | Producer | Consumer | maxlen |
|---|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `transformer_features.py`, `feat_eng_1.py` | 1,000 |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` | 50,000 |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` | 50,000 |
| `features_transformer` | `transformer_features.py` | `consolidator.py` | 1,000 |
| `features_volume_profile` | `volume_profile.py` | `consolidator.py` | 50,000 |

Redis: `127.0.0.1:6381` (Docker)

---

## Key Files

| File | Role |
|---|---|
| `config/setting.py` | All TCP/Redis hosts, ports, stream names |
| `netwo_files/tcp_to_redis_connection.py` | Bar TCP server — parse + validate + push |
| `netwo_files/tcp_to_redis_ticks.py` | Tick TCP server — drain only, no processing |
| `netwo_files/tick_validator.py` | Tick cast + validate + sequence check |
| `feat_files/transformer_features.py` | 8 features, 60-bar rolling window |
| `feat_files/volume_profile.py` | Stateful incremental POC + Value Area |
| `feat_files/feat_eng_1.py` | modSlope5 feature |
| `feat_files/consolidator.py` | Merges both feature streams per bar |
| `launch.ps1` | One-shot infra launcher |

---

## Documentation

Full docs in `documentation/`. Key references:

- `documentation/project_control_center.md` — master reference
- `documentation/redis_setup.md` — Redis setup, streams, improvements
- `documentation/volume_profile_design.md` — volume profile design and API
- `diagrams/system_overview.mmd` — macro architecture diagram
