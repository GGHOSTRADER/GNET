# GNET Release Notes

## v1.0.0 release candidate — 2026-09-03

Status: **Release candidate; not yet approved or tagged for final customer delivery.**

This release candidate contains the complete GNET application and local-training source for the
MA2Cross_Zona canonical 13-feature deployment. It excludes the licensor's datasets and trained-model
artifacts. Final `v1.0.0` status requires local training and a clean installation
at `C:\GNET` and completion of `CUSTOMER_ACCEPTANCE.md` in a TradeStation simulation account.

## Delivered production baseline

| Item | Delivered value |
|---|---|
| Primary strategy | `MA2Cross_Zona` long-entry candidate |
| TradeStation strategy document | `MA2Cross_Zona` |
| Feature contract | Canonical MA13 |
| Live feature stream | `features_transformer` |
| Model type | PyTorch MLP |
| Model artifacts | Created locally from customer-licensed data; not included in the source package |
| Registry threshold | Supplied as a disabled `0.50` template pending local validation |
| Inference device | CPU |
| Position acceptance configuration | One ES contract; pyramiding disabled |
| Protective configuration | Separate built-in $50 stop and $50 profit target per contract |
| Redis | Docker container `redis1` on `127.0.0.1:6381` |
| Standard installation path | `C:\GNET` |
| Python | 64-bit CPython 3.12.7 |

The deployed model configuration contains 13 ordered inputs:

```text
parkinson_vol_5
parkinson_vol_15
parkinson_vol_30
ofi_5
ofi_15
ofi_30
volume_percentile
volume_momentum
amihud_illiquidity
vwap_distance
minutes_since_open
is_first_last_30min
day_of_week
```

## Included application source

- Bar TCP ingestion and validated bar contract.
- Tick TCP ingestion and independent tick validation.
- Canonical MA13 feature engine shared by live and offline workflows.
- Canonical volume-profile engine and live VP snapshot adapter.
- Candidate TCP server and Redis candidate publication.
- Directory-backed model registry and local registry browser.
- Exact feature/candidate strategy router.
- Decision TCP server with exact-candidate delivery acknowledgement.
- Launch, restart, shutdown, port-monitoring, TradeStation process, watchdog, and verification
  scripts.
- All four C++ bridge sources and tested x86 binaries.
- The three current EasyLanguage source backups.

## Included training and research source

- TradeStation bar/trade parsing and meta-label generation.
- Shared canonical offline MA13 feature calculation.
- Actual trade-exit timestamp (`t1`) preservation.
- Event-interval purging and chronological holdout.
- Purged expanding walk-forward validation.
- Combinatorial Purged Cross-Validation.
- Hyperparameter search across architecture, learning rate, weight decay, dropout, batch size,
  and decision threshold.
- Historical bar overlap/conflict auditing and merging.
- Historical tick preparation, partitioned Parquet generation, and manifest creation.
- Offline VP replay and MA/VP feature merging.
- Pearson/Spearman correlation analysis.
- Trade-distribution, execution-anomaly, and out-of-sample trading-statistics tools.
- Pinned live and complete training dependency files.

## TradeStation and DLL configuration

| Document | DLL responsibility | Port |
|---|---|---:|
| `g_cpp_dll_bar` | `BarBridge.dll` sends completed bars | 9009 |
| `g_cpp_dll_tick` | `TickBridge.dll` sends live ticks | 9010 |
| `G_MA_CROSS_NN` | `StrategyBridge.dll` sends candidates | 9012 |
| `G_MA_CROSS_NN` | `SignalBridge.dll` receives/acknowledges decisions | 9011 |

The hardened DLLs use bounded connection attempts, non-blocking established sockets, and
throttled retries so unavailable Python services do not indefinitely block TradeStation.
Unacknowledged Redis decisions remain recoverable until exact EasyLanguage receipt.

The supplied strategy intentionally does not contain obsolete explicit `EntryPrice +/-`
next-bar protective exits. TradeStation's separate built-in Stop Loss and Profit Target
components provide entry-bar-capable protection.

## Installation and operation improvements

- Added `install.ps1` for isolated `.venv` creation and pinned dependencies.
- Added automatic persistent Redis installation with:
  - Pinned `redis:7.4.2-alpine` image.
  - Docker volume `gnet-redis-data` mounted at `/data`.
  - Loopback-only `127.0.0.1:6381` mapping.
  - Append-only persistence.
  - `unless-stopped` restart policy.
  - Required Redis `PONG` health check.
- Added automatic MA13 runtime/model verification.
- Added port monitoring with a 10-second watch interval.
- Added coordinated Windows Terminal grid launching.
- Added safe shutdown options for TradeStation and Docker Desktop.
- Added explicit protection against destructive Redis reset without confirmation.

## Documentation included

- `README.md` — project entry point and documentation index.
- `documentation\customer_installation_guide.md` — first-time prerequisites and setup.
- `QUICK_START.md` — normal daily startup and shutdown.
- `CUSTOMER_ACCEPTANCE.md` — technical delivery and simulation sign-off.
- `TRAINING_GUIDE.md` — data preparation, validation, training, evaluation, and promotion.
- `DEVELOPER_GUIDE.md` — architecture, extensions, protocols, builds, and tests.
- `TROUBLESHOOTING.md` — symptom-based diagnosis and recovery.

## Volume-profile status

The release includes VP source for tick ingestion, validation, canonical incremental profile
math, historical preparation, offline replay, MA/VP merging, feature analysis, purged
walk-forward comparison, and CPCV research.

VP is **not part of the v1.0.0 live model decision contract**. The active registry uses the
canonical MA13 model and `features_transformer`. The current router validates only that live
feature stream. VP42/VP45 research outputs must not be represented as live-deployed models.

A future VP production release still requires:

- Selection and freezing of the production VP feature contract.
- A deployable final-training runner for that contract.
- Versioned model/scaler/config artifacts.
- Registry/router support for the joined live feature contract.
- Explicit freshness, missing-feature, and timeout behavior.
- End-to-end TradeStation simulation acceptance.

## Intentionally excluded from delivery

- All historical TradeStation/CME exports, trade labels, processed data, and labeled datasets.
- All reference-model weights, scalers, predictions, frozen holdouts, metrics, and generated artifacts.
- Generated Parquet partitions and analysis reports.
- Redis container contents, streams, groups, pending entries, and offsets.
- Brokerage/customer credentials and `.env` files.
- Local virtual environments, caches, logs, temporary files, and acceptance records.
- Seller's development Git history and personal development-tool configuration.
- Third-party installers and licenses.

The customer must provide properly licensed data to train MA2Cross_Zona locally and for all
subsequent updates, VP research, or additional models. The resulting local weights, scaler,
parameters, metrics, and reports belong to the customer subject to the governing contract and
applicable third-party data rights.

## Required third-party software

The customer installs and licenses these separately:

- TradeStation Desktop and required market-data access.
- Docker Desktop for Windows.
- 64-bit CPython 3.12.7.

Visual Studio C++ Build Tools are optional and required only to modify/recompile bridge DLLs.
Normal operation, model retraining, threshold changes, and new strategies using the existing
protocol do not require C++ compilation.

## Known limitations and operational constraints

1. The MA feature process requires 60 newly received completed bars after a fresh process
   start, approximately 30 minutes on a 30-second chart. Historical chart bars are not replayed
   automatically into Python.
2. Candidates without a valid matching feature point fail closed as `missing_features`.
3. The current registry/router supports only `pytorch_mlp` models using
   `features_transformer`.
4. The current router is one CPU inference process. Multiple candidates arriving together are
   handled by that process rather than by dedicated per-strategy worker processes.
5. TradeStation EasyLanguage `External:` paths require the production source at `C:\GNET`.
6. All operational launch, grid-pane, watchdog-recovery, and verification paths resolve
   `C:\GNET\.venv\Scripts\python.exe` directly; shell activation is not required for daily use.
7. The Redis automation has passed script/contract verification but still requires a clean
   Docker Desktop installation test before final acceptance.
8. One-tick Look-Inside-Bar back-testing over long histories can exhaust TradeStation memory;
   use bounded chunks or offline tick reconstruction.
9. The software is local-only and does not add authentication or encryption to its loopback
   TCP/Redis protocols.
10. Historical/backtest performance does not guarantee future results. Slippage, gaps, outages,
    data errors, platform behavior, and model drift can cause losses.

## Verification state

At release-candidate generation:

- Required application, local-training template, and DLL files were present.
- All four supplied DLLs passed x86 PE verification.
- EasyLanguage paths matched the standardized customer installation path.
- The canonical feature order and disabled local-training registry template passed pre-training verification.
- Customer release-contract tests passed.
- Personal paths, credentials, raw datasets, generated reports, caches, and Git history were
  excluded by the sanitized release builder.

These checks do not replace the clean-machine and TradeStation simulation procedure in
`CUSTOMER_ACCEPTANCE.md`.

## Conditions before final v1.0.0 tag

- [x] Make every launcher and verifier call the packaged `.venv` interpreter directly.
- [ ] Install from the customer repository at a clean `C:\GNET` location.
- [ ] Run the complete pinned dependency installation.
- [ ] Create/validate Redis through `install.ps1` with Docker Desktop running.
- [ ] Run the full automated verifier with live service checks.
- [ ] Complete every required TradeStation simulation acceptance check.
- [ ] Record the final customer-repository commit.
- [ ] Generate and retain the final file manifest and delivery archive checksum.
- [ ] Tag the accepted customer commit as `v1.0.0`.

Any source, DLL, EasyLanguage, model, scaler, registry, or documentation change after final
acceptance requires a new version and regenerated manifest.
