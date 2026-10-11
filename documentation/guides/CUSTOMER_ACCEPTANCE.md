# GNET Customer Acceptance Procedure

This procedure verifies delivery of the GNET MA2CrossLE canonical 13-feature application
and training source. Complete it in a TradeStation simulation account before enabling any
live automation.

Acceptance confirms that the delivered release installs and performs the defined technical
workflow. It does not guarantee profitability, future model performance, uninterrupted
operation, or any particular trading result.

## 1. Acceptance record

Record these details before testing:

| Item | Value |
|---|---|
| Customer | |
| Tester | |
| Test date and time | |
| Computer name | |
| GNET release/version | |
| Git commit | |
| Release manifest SHA-256 | |
| TradeStation version | |
| Python version | |
| Docker Desktop version | |
| Redis image | `redis:7.4.2-alpine` |
| TradeStation account | Simulation only |
| Symbol and contract | |

## 2. Preconditions

All of the following must be true:

- The delivered source is installed at `C:\GNET`.
- `C:\GNET\install.ps1` completed successfully.
- Docker Desktop is running.
- TradeStation is installed, signed in, and receiving the required ES market data.
- TradeStation is connected to a simulation account; live automation is disabled.
- No duplicate GNET indicators or strategies are running in other workspaces.
- The tester understands that MA features require 60 completed bars after a fresh start.

If any precondition fails, stop and mark the acceptance run **Not Executed**.

## 3. Release-integrity check

The delivered `RELEASE_MANIFEST.sha256` contains the expected SHA-256 hash for every
delivered file. Preserve the original delivery archive and manifest with the acceptance
record.

Confirm that these required files exist:

```powershell
cd C:\GNET
Test-Path .\RELEASE_MANIFEST.sha256
Test-Path .\EL_files\BarBridge.dll
Test-Path .\EL_files\TickBridge.dll
Test-Path .\EL_files\StrategyBridge.dll
Test-Path .\EL_files\SignalBridge.dll
Test-Path .\model_registry\MA2CrossLE\registry.template.json
```

Every command must return `True`.

| Test | Pass criterion | Result |
|---|---|---|
| A-01 Required files | Every path returns `True` | Pass / Fail |
| A-02 Delivery manifest | Manifest is present and retained | Pass / Fail |

## 4. Automated installation verification

Run the verifier. It uses the installed GNET `.venv` directly:

```powershell
cd C:\GNET
.\verify_install.ps1 -AutomatedOnly
```

The command must end with `AUTOMATED VERIFICATION PASSED`. It checks the pinned Python
runtime, required files, x86 DLL architecture, EasyLanguage paths, model registry,
canonical feature order, scaler/model loading, synthetic inference, Docker, Redis,
router readiness, and required ports.

| Test | Pass criterion | Result |
|---|---|---|
| A-03 Automated verifier | Ends with `AUTOMATED VERIFICATION PASSED` | Pass / Fail |

Attach or save the complete terminal output.

## 5. Redis acceptance

Run:

```powershell
docker inspect redis1 --format "{{.Config.Image}}"
docker inspect redis1 --format "{{.State.Running}}"
docker exec redis1 redis-cli PING
```

Expected results are the pinned Redis image, `true`, and `PONG`.

| Test | Pass criterion | Result |
|---|---|---|
| A-04 Redis container | `redis1` is running | Pass / Fail |
| A-05 Redis response | Returns `PONG` | Pass / Fail |
| A-06 Redis persistence | Docker volume is mounted at `/data` | Pass / Fail |

## 6. Pipeline startup and ports

Start the system before enabling the TradeStation components:

```powershell
cd C:\GNET
.\launch_grid.ps1
```

In a separate PowerShell window, run:

```powershell
cd C:\GNET
.\check_gnet_ports.ps1
```

| Test | Pass criterion | Result |
|---|---|---|
| A-07 Bar TCP | Port 9009 is `LISTENING` | Pass / Fail |
| A-08 Tick TCP | Port 9010 is `LISTENING` | Pass / Fail |
| A-09 Decision TCP | Port 9011 is `LISTENING` | Pass / Fail |
| A-10 Candidate TCP | Port 9012 is `LISTENING` | Pass / Fail |

Do not enable the TradeStation DLL clients if any required port is missing.

## 7. TradeStation configuration

On the 30-second ES chart:

- Apply `g_cpp_dll_bar` once.
- Apply `G_MA_CROSS_NN` once.
- Set `StrategyId` to `MA2CrossLE`.
- Set a unique `InstanceId`.
- Use one contract and disable pyramiding.
- Confirm the strategy's embedded `StopLossAmount` is **$50 per contract**.
- Confirm the strategy's embedded `ProfitTargetAmount` is **$50 per contract**.
- Do not apply separate Stop Loss or Profit Target strategy components.

On a separate 1-tick ES chart:

- Apply `g_cpp_dll_tick` once.

| Test | Pass criterion | Result |
|---|---|---|
| A-11 Bar source | One bar indicator on the correct 30-second chart | Pass / Fail |
| A-12 Tick source | One tick indicator on the correct 1-tick chart | Pass / Fail |
| A-13 Strategy identity | Correct `StrategyId` and unique `InstanceId` | Pass / Fail |
| A-14 Position configuration | One contract; pyramiding disabled | Pass / Fail |
| A-15 Protection | Separate $50 stop and $50 target are applied | Pass / Fail |

## 8. Data-flow acceptance

After enabling the indicators, confirm Redis receives new records:

```powershell
docker exec redis1 redis-cli XLEN validated_bar
docker exec redis1 redis-cli XLEN tick_data_raw
docker exec redis1 redis-cli XLEN tick_data_validated
docker exec redis1 redis-cli XLEN features_transformer
```

Run the commands twice after waiting for new market activity. The bar, raw-tick, and
validated-tick stream lengths must increase. `features_transformer` begins increasing only
after the 60-bar warm-up.

| Test | Pass criterion | Result |
|---|---|---|
| A-16 Bar flow | `validated_bar` increases after a completed bar | Pass / Fail |
| A-17 Raw tick flow | `tick_data_raw` increases with market activity | Pass / Fail |
| A-18 Validated tick flow | `tick_data_validated` increases | Pass / Fail |
| A-19 MA feature flow | `features_transformer` increases after warm-up | Pass / Fail |

## 9. Exact-candidate decision acceptance

Wait for an actual MA crossover candidate after feature warm-up. Record the candidate GUID,
strategy ID, instance ID, date, and time from the terminals.

The same candidate GUID must appear through the complete sequence:

1. Terminal 3 receives the TradeStation candidate.
2. Terminal 2 returns `approved=0` or `approved=1` for that exact candidate.
3. Terminal 1 delivers that exact decision to the originating TradeStation instance.
4. TradeStation logs the same candidate as rejected or approved.

| Recorded item | Value |
|---|---|
| Candidate GUID | |
| StrategyId | |
| InstanceId | |
| Candidate timestamp | |
| Router status | |
| Approved value | |
| Probability | |
| Delivery timestamp | |
| TradeStation acknowledgement | |

| Test | Pass criterion | Result |
|---|---|---|
| A-20 Exact identity | One GUID matches in terminals 3, 2, 1, and TradeStation | Pass / Fail |
| A-21 Decision delivery | TradeStation receives the approve/reject result | Pass / Fail |
| A-22 Rejection behavior | A rejected candidate creates no order | Pass / Fail / Not Observed |

`missing_features`, timeout, or unmatched-candidate status does not satisfy this test. Resolve
the condition and observe a complete `status=ok` decision.

## 10. Simulated-order acceptance

Observe at least one `status=ok approved=1` candidate in the simulation account.

Confirm:

- Exactly one entry order is generated for the approved candidate.
- No entry is generated for another instance or unmatched GUID.
- The position size is one contract.
- The built-in stop loss and profit target protect the position.
- Either protective order can act during the entry bar under the configured TradeStation
  intrabar behavior.
- Closing or disabling the Python services does not freeze the TradeStation interface.

| Test | Pass criterion | Result |
|---|---|---|
| A-23 Approved entry | Exactly one simulated entry for one approved GUID | Pass / Fail |
| A-24 Correct routing | Entry occurs only in the matching strategy instance | Pass / Fail |
| A-25 Protective orders | $50 stop and target protect the same entry | Pass / Fail |
| A-26 Hardened DLL behavior | TradeStation remains responsive during service interruption | Pass / Fail |

Record the TradeStation order IDs and attach screenshots or exported logs.

## 11. Training-source acceptance

This delivery contains the training source and configuration, but not the licensor's bars,
trades, labeled data, weights, scaler, predictions, or evaluation artifacts. The licensee
must supply properly licensed local data. Confirm that the Python training modules import
successfully:

```powershell
cd C:\GNET
.\.venv\Scripts\Activate.ps1
python -c "import training_mlp.study_pipeline; import training_mlp.validation; print('TRAINING IMPORTS PASSED')"
```

| Test | Pass criterion | Result |
|---|---|---|
| A-27 Training imports | Prints `TRAINING IMPORTS PASSED` | Pass / Fail |
| A-28 Excluded reference assets | No licensor dataset, model weights, scaler, frozen holdout, or generated model artifacts are present before local training | Pass / Fail |

After A-28 passes, use customer-licensed data to train MA2Cross_Zona locally. The final
TradeStation acceptance tests require locally generated `model_best.pt`, `scaler_best.pkl`,
and `config.json`, plus an enabled `registry.json` created from the supplied disabled template.

## 12. Failure and retest rules

The release passes only when every required test A-01 through A-28 is marked **Pass**. A-22
may be **Not Observed** if no rejected candidate occurs during the agreed test window, but it
must be verified before live use.

If a test fails:

1. Record the failure, timestamp, logs, and screenshots.
2. Disable TradeStation automation.
3. Correct the installation or reproducible defect.
4. Repeat the failed test and every downstream test affected by it.
5. Do not alter the original release manifest; issue a new release/manifest if source files
   change.

## 13. Acceptance decision

Select one:

- [ ] **Accepted** — all required tests passed.
- [ ] **Conditionally accepted** — only the written exceptions below remain.
- [ ] **Rejected** — one or more required tests failed.
- [ ] **Not executed** — prerequisites were not satisfied.

Exceptions or observations:

```text


```

Customer representative:

```text
Name: ______________________________
Signature: _________________________
Date: ______________________________
```

Seller representative:

```text
Name: ______________________________
Signature: _________________________
Date: ______________________________
```
