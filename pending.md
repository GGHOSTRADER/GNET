# Pending Work

## 1. Implementation and Changes from the Last Session

1. Added a canonical MA feature module shared by live feature generation and offline training, eliminating duplicated feature formulas.
2. Removed the obsolete duplicate MA feature implementations after confirming they were no longer imported.
3. Added the strategy-candidate contract and codec with validation for strategy ID, candidate ID, symbol, bar identity, and direction.
4. Added `candidate_tcp_server.py` and the shared `trade_candidates` Redis stream on TCP port 9012.
5. Added `StrategyBridge.dll` source so all TradeStation strategy windows can send candidates through one shared TCP channel.
6. Added `strategy_router.py`, which:
   - loads the MA2CrossLE model and scaler once;
   - accepts features and candidates in either arrival order;
   - matches only exact `symbol + date + time_s + bar_num` records;
   - rejects missing features, unknown strategies, duplicates, and inference errors explicitly;
   - publishes correlated results to `trade_decisions`.
7. Changed the live path from inference on every bar to inference only when a primary strategy candidate arrives.
8. Updated `signal_tcp_server.py` to return correlated decisions rather than the old generic `trade_signal` payload.
9. Updated `SignalBridge.dll` with independent decision queues and candidate-ID retrieval; queues now use strategy-instance identity.
10. Compiled and verified 32-bit `StrategyBridge.dll` and `SignalBridge.dll` exports for TradeStation.
11. Reworked `launch.ps1` to:
    - wait for Redis `PING`;
    - reject occupied GNET ports;
    - start consumers before producers;
    - wait for router/model readiness;
    - verify TCP listeners without connecting to them;
    - launch TradeStation last.
12. Updated the Mermaid diagrams, README, launch guide, Redis reference, DLL instructions, EasyLanguage integration guidance, training paths, project control center, `AGENTS.md`, and `CLAUDE.md` for the candidate-router architecture.
13. Added router, protocol, and model-registry tests.
14. Added `instance_id` across the candidate and decision protocols, moved GUID candidate-ID generation into `StrategyBridge.dll`, and changed decision queues to route by strategy instance.
15. Anchored the decision server's Redis cursor at service startup and preserved it across DLL reconnects so a decision cannot be lost before the first TradeStation poll.
16. Replaced the router's hard-coded MA model mapping with a validated directory registry and added a local browser page for enabling models and configuring threshold/device.
17. Added the registry UI to `launch.ps1`, made its readiness check HTTP-based, opened it automatically, and allowed the launcher to reuse an already-running local UI.
18. Added `EL_files/MA2CrossLE_GNET.els`, a GNET-enabled copy of the TradeStation MA crossover strategy that sends one correlated candidate, polls by strategy instance, verifies the returned GUID, and submits the long order only after approval.
19. The GNET-enabled MA strategy was imported and compiled successfully in TradeStation.
20. Added correlated latency instrumentation from Python candidate receipt through feature matching, inference, Redis decision publication, and TCP delivery to `SignalBridge.dll`.
21. Added an opt-in Windows Scheduled Task and watchdog with explicit ON/OFF scripts; the watchdog launches GNET and restarts failed Python services while enabled.
22. Added durable Redis consumer groups: the router acknowledges candidates after decision publication, and the signal server acknowledges decisions after TCP delivery.
23. Audited and removed the unused `feat_eng_1.py` prototype and its isolated test. `consolidator.py` remains an optional print-only debugger and does not currently feed inference.
24. Installed the `GNET Pipeline Watchdog` Windows Scheduled Task successfully in its initial OFF state and documented the daily ON/OFF/status commands.
25. Changed the live VP session boundary from a calendar-date reset to the ES 18:00 session open; the profile now remains continuous across midnight and preserves each snapshot's calendar date for exact feature matching.
26. Added `training_mlp.prepare_historical_vp`, which validates the four TradeStation tick exports, converts them to Zstandard-compressed Parquet by 18:00 session, resolves identical overlapping sessions, rejects conflicting overlaps by default, and writes JSON/CSV manifests.
27. Moved the four large TradeStation exports out of the repository root into `historical_vp/raw/`; generated Parquet and manifests now default to `historical_vp/prepared/`.
28. Made historical preparation resumable: conflicting overlaps preserve compressed staging data and can be finalized with `--resume` without scanning or converting the 5 GB raw exports again.
29. Expanded `historical_vp/README.md` into a complete setup and operations guide and added a dedicated Mermaid diagram for validation, session partitioning, overlap handling, staging, and finalization.
30. Changed historical VP preparation to discover every numbered `volumeprof<number>.txt` export automatically and process the files in numeric order.
31. Optimized historical VP preparation with strict fixed-format date/time parsing, configurable process-parallel source staging (two workers by default), and throughput metrics in the completion summary.
32. Extracted canonical, transport-independent volume-profile state and mathematics into `feat_files/canonical_volume_profile.py`; the live Redis service now imports that engine through compatibility aliases, ready for historical Parquet replay to use the same code.
33. Expanded the canonical VP contract to 32 candidate features using TradeStation-classified Up/Down volume, including cumulative and price-level delta, recent divergence, Value Area dynamics, profile shape, acceptance, POC velocity, and grouped HVN/LVN measurements; scalar fields now publish live through Redis.
34. Added PID-scoped `stop.ps1` and `restart.ps1` commands; `launch.ps1` now records every managed service terminal, shutdown disables the watchdog and verifies GNET ports, and Redis data is preserved by default.
35. Expanded the workflow guide with normal and legacy shutdown behavior, watchdog elevation troubleshooting, and an explicit matrix of what happens to Docker Desktop, Redis, TradeStation, and stored stream data.
36. Added guarded `nuke.ps1` for an intentional hard reset: it requires explicit data-loss confirmation, verifies the exact `redis1` target, removes all Redis state, optionally recreates an empty container, and then gracefully shuts down Docker Desktop and its engine without deleting unrelated containers.
37. Added `kill_tradestation.ps1` with list-only inspection, path/company-scoped force termination, and post-kill verification for recovering from a frozen TradeStation instance.
38. Updated the setup workflow with the exact saved TradeStation document names: `g_cpp_dll_bar`, `g_cpp_dll_tick`, and `G_MA_CROSS_NN`, while preserving their source-file and DLL mappings.
39. Added same-named EasyLanguage backups under `EL_files/` for the installed TradeStation strategy and bar/tick indicators, plus a backup mapping README and direct setup-guide links.
40. Added prominent startup-order warnings to the main README and live workflow guide: all four Python TCP endpoints must be listening before enabling the TradeStation components, or DLL reconnection attempts can leave TradeStation stuck in a waiting loop.
41. Hardened all four TradeStation DLL sources with a shared fail-fast socket layer: 2 ms bounded non-blocking connection attempts, two-second failure backoff, non-blocking established sockets, and try-locks that return immediately rather than waiting on a chart thread. Added a coordinated x86 staging build script.
42. Hardened the three installed EasyLanguage backups with live-bar-only DLL traffic and transition-only connection logging; the MA strategy also times out lost pending candidates while keeping its protective exits independent of ML connectivity.
43. Added `check_gnet_ports.ps1`, a readiness check and continuously refreshing `-Watch` dashboard for ports 9009–9012 that defaults to a ten-second interval, shows the mapped service and owning process, warns against enabling TradeStation when any endpoint is missing, and retains a scriptable one-shot success/failure mode.
44. Added the live port monitor to the scoped shutdown allowlist, so `stop.ps1`, `restart.ps1`, and `nuke.ps1` also close PowerShell processes running `check_gnet_ports.ps1 -Watch` without targeting unrelated terminals.
45. Added non-destructive `stop.ps1 -StopDockerDesktop`: it stops GNET and `redis1`, preserves Redis data, and gracefully closes Docker Desktop and its engine to release memory.

## 2. TODO / Next Steps

1. Validate the compiled strategy's DLL calls and intrabar decision polling at runtime in TradeStation; compilation is complete, but runtime behavior still needs the live pipeline.
2. Run a full live end-to-end test with TradeStation, all eight Python services, Redis, and the four DLLs. Unit tests do not yet validate the complete external system.
3. Test several TradeStation strategy windows firing simultaneously and measure candidate-to-decision latency, ordering, and cross-strategy isolation.
4. Replace the router's current in-process sequential inference with independent per-strategy workers if simultaneous-strategy benchmarks show material queueing. The current router is race-safe but inference calls are still sequential within one Python process.
5. Add and validate a Zona registry directory once its production artifact set and live feature contract are finalized.
6. Decide the volume-profile publication rule: keep every qualifying final-second tick, emit only the first qualifying tick, or publish the completed interval at the next boundary.
7. Turn the current print-only `consolidator.py` concept into a production feature join only if a registered strategy requires volume-profile inputs. The join must match exact symbol/date/time/bar identity and route the combined feature contract only to that strategy; the current MA model must remain on its trained 13-feature contract.
8. Design historical volume-profile storage or deterministic reconstruction so VP-dependent strategies can be trained and backtested with the same VP formulas used live.
9. Tune and validate the router's 250 ms exact-feature timeout using measured live arrival timing.
10. Add Redis/TCP integration tests for candidate ingestion, routing, decision publication, reconnection, malformed payloads, consumer-group recovery, and service restarts.
11. Perform a TradeStation soak test covering DLL reconnects, chart reloads, workspace reloads, market disconnects, and duplicate candidate submissions.
12. Define and enforce a unique, stable `instance_id` convention for every TradeStation strategy window. Candidate IDs are now GUIDs generated by the DLL.
13. Benchmark CPU versus GPU inference for the actual small MLP and choose the deployment device from measurements.
14. After the new route is proven live, remove or archive the legacy `inference_engine.py`, `trade_signal` configuration, and remaining historical setup paths so there is only one supported live inference path. Keep `consolidator.py` only if its manual debugging output remains useful or it becomes the basis for the production VP join.
15. Align the live scikit-learn version with the 1.8.0 version used to serialize `scaler_best.pkl`, or regenerate and verify the scaler under the deployment environment. The current 1.5.1 runtime emits an incompatibility warning.
16. After installing the staged hardened DLLs and recompiling the updated EasyLanguage documents, run a deliberate Python-outage test and confirm TradeStation remains responsive while ports 9009–9012 are unavailable and later reconnects cleanly.
