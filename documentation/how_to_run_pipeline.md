# How to Run the Pipeline
> **What:** Ordered steps to start the full data pipeline — Docker, Redis, Python servers, TradeStation, and feature pipelines.

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

# Terminal 3 — volume profile reads from tick_data_validated
python -m feat_files.volume_profile
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600
```

> The order matters: tcp_to_redis_ticks must run before tick_validator, and tick_validator before volume_profile.

---

## Step 4 — Apply EasyLanguage Indicators in TradeStation

- **Bar chart:** apply indicator from [[easylanguage_bar_indicator]] — uses `BarBridge.dll` → port 9009
- **Tick chart:** apply indicator from [[easylanguage_tick_indicator]] — uses `TickBridge.dll` → port 9010

---

## Step 5 (Optional) — Start Other Feature Pipelines

```bash
python -m feat_files.feat_eng_1      # modSlope5 — reads validated_bar
python -m transformer_features       # 8 features  — reads validated_bar
```

---

## Ports Reference

| Port | Used By |
|---|---|
| `9009` | Bar TCP server — TradeStation bar DLL connects here |
| `9010` | Tick TCP server — TradeStation tick DLL connects here |
| `6381` | Redis — Docker container (mapped from internal 6379) |

## Redis Streams Reference

| Stream | Written By | Read By |
|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `feat_eng_1.py`, `transformer_features.py` |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` |
