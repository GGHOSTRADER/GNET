# GNET Developer Guide

This guide explains how to modify and extend the delivered GNET source safely. Read
`QUICK_START.md`, `CUSTOMER_ACCEPTANCE.md`, and `TRAINING_GUIDE.md` before changing a
production installation.

## 1. System boundary

GNET is a local TradeStation-to-Python meta-labeling pipeline for ES futures:

```text
TradeStation bar indicator
  -> BarBridge.dll :9009
  -> validated_bar
  -> canonical MA13 feature engine
  -> features_transformer

TradeStation tick indicator
  -> TickBridge.dll :9010
  -> tick_data_raw
  -> tick validator
  -> tick_data_validated
  -> canonical volume profile
  -> features_volume_profile

TradeStation strategy candidate
  -> StrategyBridge.dll :9012
  -> trade_candidates
  -> Python strategy router + model registry
  -> trade_decisions
  -> signal TCP server :9011
  -> SignalBridge.dll
  -> exact originating TradeStation strategy instance
```

Redis runs locally at `127.0.0.1:6381` in Docker container `redis1`. The TCP services bind
to loopback only. Do not expose these unauthenticated interfaces to another computer or the
public network.

## 2. Architectural layers

Keep changes within these boundaries:

| Layer | Responsibility | Examples |
|---|---|---|
| Domain | Pure data types, invariants, and calculations | `bar_contract.py`, canonical feature modules |
| Adapter | TCP/CSV/Redis conversion at system boundaries | codecs, TCP servers, Redis field conversion |
| Application | Orchestration and process loops | feature services, router, signal server |
| Configuration | Shared hosts, ports, stream names | `config\setting.py` |

Domain code must not connect to Redis, open sockets, or depend on TradeStation. Adapters
must validate external data before application code consumes it. Feature math belongs in a
canonical module, not independently in live and training scripts.

## 3. Important modules

| Module | Role |
|---|---|
| `config\setting.py` | Hosts, ports, Redis streams, groups, consumers, readiness key |
| `netwo_files\bar_contract.py` | Immutable bar type and validation invariants |
| `netwo_files\bar_codec.py` | CSV/Redis encoding and decoding |
| `netwo_files\tcp_to_redis_connection.py` | Bar TCP server and `validated_bar` producer |
| `netwo_files\tcp_to_redis_ticks.py` | High-throughput tick TCP drain |
| `netwo_files\tick_validator.py` | Tick validation and validated stream producer |
| `feat_files\canonical_features.py` | Canonical MA13 calculations used offline and live |
| `feat_files\transformer_features.py` | Live 60-bar feature process |
| `feat_files\canonical_volume_profile.py` | Transport-independent VP state and features |
| `feat_files\volume_profile.py` | Live Redis adapter for VP snapshots |
| `inference\model_registry.py` | Registry discovery and validation |
| `inference\candidate_tcp_server.py` | Candidate TCP validation and Redis publication |
| `inference\strategy_router.py` | Exact feature join, model selection, inference, decision publication |
| `inference\signal_tcp_server.py` | Exact-candidate decision delivery and acknowledgement |
| `gnet_ui\server.py` | Local registry browser/editor |
| `training_mlp\validation` | Shared event intervals, purged walk-forward, and CPCV |

High-level diagrams are under `diagrams\`. Update them whenever a change modifies a
process, stream, protocol, artifact source, or deployment boundary.

## 4. Network and Redis contracts

### TCP ports

| Port | Direction | DLL | Python service |
|---:|---|---|---|
| 9009 | TradeStation to Python | `BarBridge.dll` | `netwo_files.tcp_to_redis_connection` |
| 9010 | TradeStation to Python | `TickBridge.dll` | `netwo_files.tcp_to_redis_ticks` |
| 9011 | Python to TradeStation | `SignalBridge.dll` | `inference.signal_tcp_server` |
| 9012 | TradeStation to Python | `StrategyBridge.dll` | `inference.candidate_tcp_server` |
| 9020 | Browser to Python | None | `gnet_ui.server` |

### Redis streams

| Stream | Producer | Primary consumer |
|---|---|---|
| `validated_bar` | Bar TCP server | MA feature process |
| `tick_data_raw` | Tick TCP server | Tick validator |
| `tick_data_validated` | Tick validator | VP process |
| `features_transformer` | MA feature process | Strategy router |
| `features_volume_profile` | VP process | Debug consolidator/current VP research path |
| `trade_candidates` | Candidate TCP server | Strategy router |
| `trade_decisions` | Strategy router | Signal TCP server |

The router and signal server use durable Redis consumer groups. Reading a message does not
mean it is safely completed. A pending entry remains recoverable until the responsible
consumer acknowledges it. The signal server acknowledges a decision only after the
matching TradeStation instance confirms receipt of the exact candidate GUID.

Never rename a stream, consumer group, field, TCP port, or readiness key in one module only.
Change the shared configuration, every producer/consumer contract, tests, DLL/EL protocol
when applicable, launchers, documentation, and diagrams together.

## 5. Bar and tick data contracts

Bars enter Python as:

```text
symbol,date,time_s,open,high,low,close,up,down,vwap,bar_num
```

Ticks enter Python as:

```text
symbol,date,time_s,high,low,up,down,bar_num
```

TradeStation `date` uses its packed integer representation. `time_s` is seconds since
midnight. External values must be cast and validated at the adapter boundary.

The bar DLL must be called by `g_cpp_dll_bar`; the tick DLL must be called only by
`g_cpp_dll_tick`. Applying tick code to both charts creates duplicate producers, invalid
tick ranges, and sequence conflicts.

Sequence identifiers are source-local observations, not reliable cross-chart join keys.
Candidate-to-feature matching uses the supported symbol/time contract and exact candidate
identity, not equality between unrelated TradeStation chart bar numbers.

## 6. Canonical feature development

The canonical MA13 names and order are defined in `feat_files\canonical_features.py`.
Live `transformer_features.py` and offline `training_mlp\study_pipeline.py` must both call
that implementation.

When adding or changing a feature:

1. Implement the math once in the appropriate canonical module.
2. Add unit tests for normal inputs, insufficient history, zero volume/range, and invalid
   values.
3. Update the canonical feature-name sequence.
4. Ensure live and offline adapters produce the same values from the same synthetic bars.
5. Rebuild every affected dataset.
6. Retrain the scaler and model; an old scaler/model is incompatible with a changed feature
   contract.
7. Update model configuration, verifier, registry expectations, documentation, and diagrams.
8. Perform leakage-controlled validation and full simulation acceptance.

Never silently change feature semantics while preserving an existing model version.

## 7. Adding a strategy that uses MA13

A strategy using the existing candidate fields and MA13 feature stream normally requires no
DLL change.

1. Create the EasyLanguage primary strategy logic.
2. Call the existing `StrategyBridge.dll` `SendCandidate` function.
3. Choose a stable `StrategyId` containing only letters, numbers, underscores, periods, or
   hyphens, with at most 64 characters.
4. Give every simultaneously running chart/window a unique `InstanceId`.
5. Build a strategy-specific labeled dataset and train its model/scaler.
6. Create:

```text
model_registry\NewStrategy\registry.json
```

7. Restart the router; models are loaded at process start.
8. Run an exact-candidate simulation acceptance test.

Example registry entry:

```json
{
  "schema_version": 1,
  "strategy_id": "NewStrategy",
  "display_name": "New Strategy",
  "enabled": true,
  "model_type": "pytorch_mlp",
  "artifact_dir": "training_mlp/strategies/NewStrategy/model/model_v1",
  "threshold": 0.5,
  "device": "cpu",
  "feature_stream": "features_transformer"
}
```

The registry directory name must exactly equal `strategy_id`. The artifact directory must
contain `model_best.pt`, `scaler_best.pkl`, and `config.json`.

The current registry/router accepts only `pytorch_mlp` and `features_transformer`. A strategy
requiring a different model type or feature stream needs an explicit Python registry/router
extension plus tests; changing JSON alone is insufficient.

## 8. Strategies with new candidate fields or features

Use the smallest necessary change:

- A different model trained on the same MA13 fields: registry/model change only.
- New feature math derived from existing bars/ticks: canonical feature and Python pipeline
  change; DLLs may remain unchanged.
- A new value that TradeStation must send: EasyLanguage, DLL protocol, Python TCP parser,
  validation, codec, and tests must change together.
- A different decision payload returned to TradeStation: router output, signal server,
  `SignalBridge.dll`, and EasyLanguage receiver must change together.

Protocol changes should introduce an explicit version or a coordinated release. Never deploy
a new DLL against an old server protocol or the reverse.

## 9. Model compatibility and promotion

The model, scaler, configuration, feature order, threshold, and registry entry form one
versioned unit. Do not mix artifacts from different training runs.

Before promotion:

1. Stop the pipeline.
2. Preserve the previous artifact directory and registry entry.
3. Confirm the configured feature count/order matches the live canonical contract.
4. Load the candidate scaler and model in the verifier.
5. Run synthetic inference.
6. Restart the router.
7. Complete exact-candidate simulation acceptance.

The registry UI may edit only `enabled`, `threshold`, and `device`. Artifact-path or schema
changes should be reviewed source changes, not casual browser edits.

## 10. C++ bridge development

Customers can operate and retrain GNET using the supplied binaries without installing C++.
Install Visual Studio C++ Build Tools only to modify/rebuild the DLL layer.

Required Visual Studio components:

- Desktop development with C++
- MSVC compiler toolset
- Windows SDK
- x86 build tools

The DLLs must be x86 because TradeStation loads 32-bit bridge binaries in this configuration.
The coordinated builder is:

```powershell
cd C:\GNET\EL_files
.\build_hardened.cmd
```

`build_hardened.cmd` currently points to the Visual Studio 2026 Community x86 environment.
If the customer installs Build Tools or another edition, update only its `VCVARS` path to the
corresponding `vcvars32.bat`.

It builds:

```text
EL_files\build_hardened\BarBridge.dll
EL_files\build_hardened\TickBridge.dll
EL_files\build_hardened\StrategyBridge.dll
EL_files\build_hardened\SignalBridge.dll
```

Close TradeStation completely before replacing loaded DLLs. Copy all coordinated outputs
together, not one protocol-dependent binary at a time. Then restart the Python services,
start TradeStation last, and repeat hardened-DLL and exact-candidate acceptance tests.

Recompile only when changing socket behavior, ports embedded in DLL code, exported functions,
or message fields. New model weights, thresholds, registry entries, and ordinary new
strategies do not require DLL recompilation.

## 11. EasyLanguage development

Repository backups correspond to these TradeStation documents:

| Document | Repository file |
|---|---|
| `g_cpp_dll_bar` | `EL_files\g_cpp_dll_bar.els` |
| `g_cpp_dll_tick` | `EL_files\g_cpp_dll_tick.els` |
| `G_MA_CROSS_NN` | `EL_files\G_MA_CROSS_NN.els` |

Keep `External:` declarations pointed to `C:\GNET\EL_files`. Every change made in
TradeStation must also be copied back into its matching `.els` source file and committed.

Preserve hardened non-blocking behavior and `LastBarOnChart` protections. The strategy uses
intrabar calculation to poll decisions. Its protection is provided by separate built-in
TradeStation Stop Loss and Profit Target components at $50 per contract; do not reintroduce
explicit `next bar` protective exits.

## 12. Python development workflow

Activate the isolated environment:

```powershell
cd C:\GNET
.\.venv\Scripts\Activate.ps1
```

Run the full test suite:

```powershell
python -m pytest
```

Run focused tests during development:

```powershell
python -m pytest tests\test_customer_release_contract.py
python -m pytest tests\test_volume_profile.py
python -m pytest tests\test_tcp_to_redis_connection.py
```

For tests that exercise actual Redis, Docker Desktop and the isolated `redis1` test target
must be available. Never point destructive test cleanup at a production Redis container that
contains required streams or offsets.

After structural Python edits:

- Confirm the module imports.
- Review the Git diff for accidental deletion of unrelated definitions.
- Run focused tests, then the full suite.
- Run `verify_install.ps1 -AutomatedOnly` before simulation.

## 13. Service-level debugging

Run services individually from `C:\GNET` with the `.venv` active:

```powershell
python -m netwo_files.tcp_to_redis_connection
python -m netwo_files.tcp_to_redis_ticks
python -m netwo_files.tick_validator
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600 --snapshot-interval-s 30
python -m feat_files.transformer_features
python -m inference.candidate_tcp_server
python -m inference.strategy_router
python -m inference.signal_tcp_server
python -m gnet_ui.server
```

Use `python -m feat_files.consolidator` only as a feature-stream debugging tool. It is not the
current live inference join.

Terminal interpretation:

- Candidate TCP receives the candidate and publishes it.
- Router selects the exact strategy model and returns status/approval.
- Signal TCP delivers and waits for exact TradeStation acknowledgement.

A `delivered` message means socket delivery occurred; TradeStation logs and acknowledgement
confirm that EasyLanguage consumed the matching decision. Always inspect the router status—an
approve/reject value is meaningful only when `status=ok`.

## 14. Source control and releases

Use a separate development branch for changes. Keep generated datasets, reports, credentials,
virtual environments, Redis state, and licensed historical data out of Git.

Before releasing:

1. Review every diff.
2. Run the full tests and automated verifier.
3. Complete TradeStation simulation acceptance.
4. Regenerate the sanitized customer tree and SHA-256 manifest.
5. Confirm no personal paths, credentials, raw data, caches, or Git history are present.
6. Commit the approved customer tree.
7. Tag the exact delivered commit.

Never edit a previously delivered manifest. Any source, model, scaler, DLL, EL, configuration,
or documentation change creates a new release and a new manifest.

## 15. Security and operational rules

- Keep all TCP and Redis bindings on `127.0.0.1` unless authentication, encryption, and a
  reviewed network design are added.
- Never commit `.env` files, credentials, brokerage identifiers, or customer data.
- Use simulation for every new strategy, model, DLL, protocol, or TradeStation configuration.
- Fail closed when features, model artifacts, exact candidate identity, or acknowledgements
  are missing.
- Preserve recoverable Redis offsets and pending entries during ordinary restarts.
- Do not use `nuke.ps1 -ConfirmDataLoss` unless permanent Redis deletion is intended.
- Maintain an independent trading-risk limit and kill procedure outside the ML decision path.

