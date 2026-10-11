# AGENTS.md

## Command Center browser regression suite

Before changing Command Center controls, read
`documentation/guides/GNET_COMMAND_CENTER_BROWSER_TESTS.md`.
Run `scripts/Test-GNETCommandCenterBrowser.ps1` against the changed client package.
Use fabricated responses, assert button request payloads and visible outcomes,
and inspect screenshot differences. Browser checks do not replace protected
installed integration or end-to-end research acceptance.

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What This Is

GNET is a real-time end-to-end meta-labeling ML pipeline for ES futures. TradeStation streams bars and ticks into Redis, Python continuously engineers features, and an actual primary-strategy candidate triggers the mapped model. An approve/reject decision matched to the exact candidate is returned to the originating strategy window.

## Commands

### Run Tests
```powershell
pytest
pytest tests/test_volume_profile.py          # single file
pytest tests/test_volume_profile.py::test_find_poc_returns_highest_volume_level  # single test
```

### Launch Full Pipeline (one command)
```powershell
.\launch_grid.ps1
```
Opens one Windows Terminal window with 3 tabs/9 panes, Docker, Redis, TradeStation, and the local registry page. Use `launch.ps1` for the legacy nine-window layout.

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

# Feature + candidate-triggered inference
python -m feat_files.transformer_features
python -m inference.candidate_tcp_server     # port 9012
python -m inference.strategy_router
python -m inference.signal_tcp_server        # port 9011
```

### Offline Training
```powershell
cd training_mlp
python study_pipeline.py          # build labeled dataset from TradeStation CSV exports
python 30_training_mlp.py         # purged-embargo walk-forward CV
python 30_evaluate_mlp.py         # held-out test evaluation (run once)
```
Default artifacts go to `training_mlp/strategies/MA2CrossLE/model/mlp_baseline/` (`model_best.pt`, `scaler_best.pkl`, `config.json`).

### Debug: Monitor Two Feature Streams Together
```powershell
python -m feat_files.consolidator
```

### Optional Local Model Registry UI
```powershell
python -m gnet_ui.server   # http://127.0.0.1:9020
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

validated_bar → transformer_features.py → features_transformer ─┐
TradeStation strategy → StrategyBridge.dll (9012) → candidates ─┤
                                                               ↓
                                                strategy_router.py (MLP)
                                                               ↓
                                                     trade_decisions
                                                               ↓
                                        signal_tcp_server.py (port 9011)
                                                               ↓
                                        SignalBridge.dll → matching strategy
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
| `feat_files/canonical_volume_profile.py` | Transport-independent total/Up/Down VP state, POC, Value Area, and 32 candidate features |
| `feat_files/volume_profile.py` | Live Redis adapter; updates every tick and commits once per interval at wall-clock offset 29.925 |
| `feat_files/consolidator.py` | Debugging tool: merges transformer + volume profile streams |
| `inference/candidate_tcp_server.py` | Validates candidates from shared TCP port 9012 and writes `trade_candidates` |
| `inference/strategy_router.py` | Exact feature join, strategy-model selection, inference, `trade_decisions` output |
| `inference/model_registry.py` | Validated discovery of `model_registry/*/registry.json` |
| `inference/signal_tcp_server.py` | Serves exact-candidate decisions over TCP port 9011 |
| `EL_files/dll.cpp` | C++ source for BarBridge.dll (bar sender) |
| `EL_files/tick_dll.cpp` | C++ source for TickBridge.dll (tick sender) |
| `EL_files/signal_dll.cpp` | C++ source for SignalBridge.dll (signal receiver) |
| `EL_files/strategy_dll.cpp` | C++ source for StrategyBridge.dll (shared candidate sender) |

### Redis Streams
| Stream | Producer | Consumer | maxlen |
|---|---|---|---|
| `validated_bar` | `tcp_to_redis_connection` | `transformer_features` | 1,000 |
| `tick_data_raw` | `tcp_to_redis_ticks` | `tick_validator` | 50,000 |
| `tick_data_validated` | `tick_validator` | `volume_profile` | 50,000 |
| `features_transformer` | `transformer_features` | `strategy_router` | 1,000 |
| `features_volume_profile` | `volume_profile` | `consolidator` | 50,000 |
| `trade_candidates` | `candidate_tcp_server` | `strategy_router` | 5,000 |
| `trade_decisions` | `strategy_router` | `signal_tcp_server` | 5,000 |

Redis is at `127.0.0.1:6381` (Docker container named `redis1`).

## Design Conventions

### Terminal Hotkeys
- Never add, remove, remap, or otherwise modify terminal or Windows Terminal keyboard shortcuts unless the user explicitly requests the exact hotkey change.
- Terminal layout and launcher work must preserve all existing user keybindings. In particular, keep `Alt+Enter` available to terminal applications for multiline input.

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
- Canonical volume-profile math (`canonical_volume_profile.py`) uses stateful O(1) incremental updates per tick; the live adapter's current final-second gate can request more than one snapshot per interval.

### No External ML Libraries
The feature engineering stack uses only `math`, `collections.deque`, and `numpy` (volume profile only). No pandas, no talib, no sklearn in the hot path. The trained MLP uses PyTorch.

### `bar_to_redis_fields` Encoding
Floats are encoded with `repr()` for stable round-trip precision. Integers use `str()`. The `date` field is zero-padded to 6 digits with `f"{b.date:06d}"`.

## Large Market-Data Access

- Do not open, scan, parse, or load raw trade, bar, or tick exports unless the user explicitly asks for that dataset to be inspected or used.
- File names, paths, timestamps, and sizes may be inspected to locate a requested dataset without reading its contents.
- Avoid broad repository searches that traverse raw market-data directories. Scope searches to code, configuration, documentation, or an explicitly authorized dataset.

## Offline Backtester Runbooks

For offline bar construction, primary strategies, exit search and statistics,
read [the agent runbook](documentation/guides/BACKTESTER_AGENT_GUIDE.md) before launching a job.
The [human guide](documentation/guides/BACKTESTER_GUIDE.md) links the diagram, strategy/data
inventories, report examples and commands. Discover registered strategies and
prepared archives with:

```powershell
.\.venv\Scripts\python.exe -m scripts.backtester_inventory strategies
.\.venv\Scripts\python.exe -m scripts.backtester_inventory data --asset ES
```

Do not confuse the independent-entry `exit_module` collector with the
position-aware `backtester.run`. This workflow does not authorize live changes.

## Guarded research workbench — agent discovery

The guarded implementation currently lives on `codex/guarded-research` at
`C:\Users\g_med\.codex\worktrees\guarded-research\GNET`.
Before operating it, read the
[guarded agent operating guide](C:/Users/g_med/.codex/worktrees/guarded-research/GNET/documentation/guides/GUARDED_RESEARCH_AGENT_GUIDE.md)
and that checkout's `AGENTS.md`. The guide maps human controls to typed broker
tools, source/parent identities, visibility, architecture, defaults and unfinished
gates. Check actual MCP tool exposure each session; use its typed CLI fallback
when missing. Do not read private market data or grant deployment permissions.
Preserve the independent live pipeline and existing terminal hotkeys.


## Customer preparation package and deployment state

For new Windows machines, deliver the standalone
`GNET-New-Machine-Preparation-r7.zip`, not an update ZIP. Read
[GNET_CUSTOMER_INSTALLATION_STATUS.md](documentation/guides/GNET_CUSTOMER_INSTALLATION_STATUS.md)
for its hashes, human/agent entry points, customer-reported preparation status and
the next protected broker deployment gate. Preparation does not activate the
broker or install the full research command center. Reuse the prepared broker
account; credentials stay local and privileged transitions require approval.

## Customer TradeStation export procedure

For customer-facing EasyLanguage/chart/export guidance,read the guarded
checkout's documentation/guides/GNET_TS_CHART_EXPORT_HUMAN_GUIDE.md and
GNET_TS_CHART_EXPORT_AGENT_GUIDE.md. Follow installation-relative paths from
client-config.json,one common inbox with fresh per-export children,and separate
compile/closure/sealing/admission/training evidence. Customer packages include
these guides;the agent must check actual installed gates before promising an
automatic TS-to-training flow. Preserve live services and hotkeys.

## Command-center continuation candidate

Read documentation/guides/GNET_COMMAND_CENTER_OCT09_STATUS.md for the staged
October 9 workflow changes and current delivery hashes. The r4 candidate lives
in .artifacts/GNET-Command-Center-v27-Candidate-r4.
Broker r4 and matching client v28 are now installed on this development machine;
the deployment audit passed after Resume-GNETCommandCenterAudit.ps1 corrected
the wrapper's unsupported audit limit. Consult the status guide for evidence.
Its matching client includes GNET_COMMAND_CENTER_AGENT_GUIDE.md and
GNET_COMMAND_CENTER_HUMAN_GUIDE.md. Primary meta-label targets precede feature
construction in the new UI. Trash is recoverable retirement with local human
Windows researcher-password confirmation; never collect passwords in chat or
tool arguments. Native Windows and browser visual acceptance remain pending.
Actual installed capabilities and identities take precedence over staged code.
