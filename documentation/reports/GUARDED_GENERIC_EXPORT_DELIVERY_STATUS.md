# Generic TradeStation export correction

Recorded October 6, 2026. Guarded checkout: `C:\Users\g_med\.codex\worktrees\guarded-research\GNET`, branch `codex/guarded-research`.

## Actual delivery

The reported `@ES(D)` 30-second chart failed because the producer required an individual ES contract. That restriction has been removed from export capture, filename generation and portable row/bundle validation. Stocks, other futures, FX-like prices and continuous-series symbols now use their actual symbol and native MinMove/PriceScale. Windows-unsafe symbol characters are reversibly escaped only in filenames; original symbols remain in metadata. No asset class, exchange, adjustment method or rollover mapping is invented.

The twenty-bar probe, one-time filename decision, first-row preservation, timestamps, quantity checks, bounded resources, exclusive handles and source hashes remain enforced. Negative/zero prices are supported in the new native-grid metadata contract. Supported chart types remain tick, seconds and intraday minutes. Prices must round-trip within eight decimal places; symbols must be bounded printable ASCII.

Synthetic evidence: **160 passed in 37.87 seconds**, plus **56 focused follow-up checks passed in 4.95 seconds** after final filename and EL initializer adjustments. Python imports and top-level definition inventories were checked against HEAD. The first test attempt failed fixture setup on temporary-folder permissions; the rerun used a fresh writable directory. Tests did not read real market records and do not compile EasyLanguage.

Active browser client: **gnet-client-v8-generic-export**, verified through its health endpoint. MCP host configuration was updated; this chat's injected tool catalog refresh remains unverified. Protected broker remains **guarded-v10-ml-replay**. Compatible **guarded-v13-generic-assets** was packaged and verified only. A prior incomplete package made with stock Python lacking dependency metadata was preserved.

## User's next step

Replace the full generic indicator with:

`C:\Users\g_med\python_new\GNET\.artifacts\ts-generic-export-kit\GNET_Research_Export.els`

Then Verify it in TradeStation and apply it to the same `@ES(D)` 30-second research chart. The local copy has a new reserved ExportFolder and ExportEnabled=true. It retains the established Chicago source clock and Trade Vol declaration for this test; PriceBasis is unknown because continuous-series adjustment evidence was not supplied. Portable source defaults remain unknown. Existing TradeStation Inputs may persist: explicitly use the new ExportFolder or remove/reinsert this research indicator so its new defaults apply. Keep MaxBarsBack=1 and Update value intra-bar enabled.

Watch ProbeBars=20, NameFrozen=true, RowsWritten>0 and ExportClosed=true. This revision's TradeStation Verify, actual chart lifecycle and producer closure remain pending. Do not manually rename partial files or create completion markers.

## Remaining gates

Generic bundles use version 4 and preserve continuous/unclassified series identities. Existing ES envelopes remain version 2/3. The updated browser inbox displays actual symbols and the reason instrument/series research approval is unavailable. Portable sealing does not approve a source for training.

Protected incoming-folder policy, v13 activation/installed acceptance, continuous/other-instrument training mappings, TS primary-report/label bridge, full isolation/crash acceptance and final testing remain pending. No real-data admission, migration, backtest, training, live-service change or hotkey change occurred in this correction.

Delivery hashes and paths: `.artifacts/generic-export-delivery.json`. Activation evidence: `.artifacts/client-delivery-installed/v8-generic-export-client-activation.json`. Command center: <http://127.0.0.1:9040/research/>; inbox: <http://127.0.0.1:9040/intake/>.

## Reported reservation error at 07:05:40

The user supplied a TradeStation screenshot reporting "Session already used: prepare a NEW export folder". Bounded control/file-metadata inspection found the old `ts-30s-test-367dae68` reservation claimed at 07:05:40, with its previous exporter hash and no CSV. The new `export-es-seconds-30-20261006-ce0d6f65` reservation remained prepared and unused, bound to the corrected local source. No market payload was read, rewritten or deleted. The next action is to explicitly set the existing chart indicator's ExportFolder Input to this already prepared new path and Apply once. TradeStation may retain old Inputs after source replacement; re-compilation does not itself update the chart instance's settings. Actual export closure remains pending.
