# How to Run the Pipeline
> **What:** Ordered steps to start the full data pipeline — Docker, Redis, Python servers, TradeStation, and feature/inference pipelines.

Run these steps **in order**, each in its own PowerShell terminal.

---

## Step 1 — Run the Launch Script

```bash
.\launch.ps1
```

Automatically starts Docker Desktop, waits for the engine, starts the Redis container, and opens TradeStation.

---

## Step 2 — Start the Bar TCP Server

```bash
python -m netwo_files.tcp_to_redis_connection
```

Expected output:
```
1) [bar_server] Connected to Redis1  -Host:127.0.0.1  -Port:6381
2) [bar_server] Listening TCP  -Host:127.0.0.1  -Port:9009
```

---

## Step 3 — Start the Tick Pipeline

Open **3 separate terminals**:

```bash
# Terminal 1 — ingest raw ticks from TickBridge.dll (port 9010)
python -m netwo_files.tcp_to_redis_ticks

# Terminal 2 — validate ticks and push to tick_data_validated
python -m netwo_files.tick_validator

# Terminal 3 — volume profile reads from tick_data_validated, snapshots once per bar
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600 --snapshot-interval-s 30
```

> The order matters: tcp_to_redis_ticks must run before tick_validator, and tick_validator before volume_profile.
> `--snapshot-interval-s` should match the live bar length in seconds (default 30) — the profile updates on every tick (O(1)) but only emits POC/VA/derived features 1 second before each bar close.

---

## Step 4 — Start the Transformer Feature Pipeline

```bash
python -m feat_files.transformer_features
```

This computes all 13 MLP features (including `day_of_week`) and publishes them to the `features_transformer` Redis stream.

Expected output once warmed up (60 bars):
```
ESM25 date=... t=... bar=60 pvol5=... ofi5=... signal=...
```

---

## Step 5 — Start the Inference Layer

Open **2 separate terminals**:

```bash
# Terminal 1 — loads model_best.pt, reads features_transformer, writes trade_signal
python -m inference.inference_engine

# Terminal 2 — reads trade_signal, serves persistent TCP connection on port 9011
python -m inference.signal_tcp_server
```

Start `inference_engine` before `signal_tcp_server`. The engine must be writing to `trade_signal` before the server has anything to forward.

Expected output from inference_engine:
```
[inference] Ready
  model   : training_mlp/experiments/mlp_baseline/model_best.pt
  device  : cpu
  threshold: 0.5
[inference] bar=61 prob=0.3821 signal=0 (no trade)
[inference] bar=62 prob=0.6140 signal=1 (BUY)
```

---

## Step 6 — Apply EasyLanguage Indicators in TradeStation

- **Bar chart:** apply indicator from [[easylanguage_bar_indicator]] — uses `BarBridge.dll` → port 9009
- **Tick chart:** apply indicator from [[easylanguage_tick_indicator]] — uses `TickBridge.dll` → port 9010
- **Signal receiver:** apply indicator from [[easylanguage_signal_indicator]] — uses `SignalBridge.dll` → port 9011

---

## Ports Reference

| Port | Used By | Direction |
|---|---|---|
| `9009` | Bar TCP server — TradeStation bar DLL connects here | TS → Python |
| `9010` | Tick TCP server — TradeStation tick DLL connects here | TS → Python |
| `9011` | Signal TCP server — TradeStation signal DLL connects here | Python → TS |
| `6381` | Redis — Docker container (mapped from internal 6379) | local |

## Redis Streams Reference

| Stream | Written By | Read By |
|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `feat_eng_1.py`, `transformer_features.py` |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` |
| `features_transformer` | `transformer_features.py` | `inference_engine.py`, `consolidator.py` |
| `features_volume_profile` | `volume_profile.py` | `consolidator.py` |
| `trade_signal` | `inference_engine.py` | `signal_tcp_server.py` |
