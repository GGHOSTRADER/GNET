# EasyLanguage primary strategies: agent authoring guide

## Purpose and current status

Build TradeStation EasyLanguage research **strategies** from the installed
primary-export scaffold. Strategies place simulated historical orders and
export their bars, candidate references and observed trades. The bar-only
exporter is an **indicator**, not a replacement for the primary strategy.

The first source implementation adds primary contract 3, typed fixed Inputs,
observed-trade validation, input display and
`EL_files/GNET_Primary_Generic_Scaffold.els`. Synthetic source-to-XGBoost/scoring
tests passed; this is not yet an installed or TradeStation-verified release.
See [implementation evidence](../reports/GNET_GENERIC_PRIMARY_IMPLEMENTATION_2026-10-10.md).

The desired extensible behavior is described in
[the revised extension policy](GNET_PRIMARY_STRATEGY_EXTENSION_REVISION.md).
The installed V38 receiver still assumes MA-cross inputs. Generic fixed Inputs
now work in source tests; arbitrary per-bar series and complex positions remain
unimplemented end to end.
Discover actual installed capabilities before promising import or training.
This guide does not authorize live trading or protected deployment changes.

## Before writing code

- Read the installed agent/export guides and the actual primary scaffold.
- Resolve client-config.json and its exports path; never copy a developer's
  username, source directory or installation path into a customer's commands.
- Establish entry/exit rules, long/short behavior, quantities, costs, execution
  timing, session resets, intrabar behavior and position model.
- Identify chart symbol, interval, time zone, price basis and session settings.
  Export actual chart metadata; never infer minutes/ticks from timestamp spacing.
- Distinguish imported recorded trades from GNET independent strategy execution.
  Importing a new EL rule does not require GNET to implement that same entry rule.

## Editable sections

- Strategy identity, full name, revision and optional nickname.
- Actual EasyLanguage Inputs and their explicit parameter descriptors.
- Entry and exit logic, within scaffold-supported execution hooks.
- Declared per-bar diagnostics, once supported by the installed export schema.

Preserve transport, session capture, metadata resolution, bar/candidate identity,
closure/sealing and custody code. Do not change shared column meanings or bypass
validation gates. Do not disguise an RSI/breakout strategy as ma_cross.

Compile as a TradeStation Strategy. Follow the actual scaffold's MaxBarsBack and
calculation settings; do not assume every strategy needs the same value or that
an error message changes the chart setting automatically. Inspect actual attached
chart Inputs, since TradeStation can retain earlier values after source updates.

## Inputs versus per-bar values

| Value | Record it as | Example |
|---|---|---|
| Fixed user input | Typed run configuration, linked to every observation | RSILength=14 |
| Fixed execution input | Typed run configuration with units | StopTicks=6 |
| Calculated series | Explicit value on each relevant bar | RSIValue=47.2 |
| Dynamic decision/state | Explicit causal bar/candidate/position value | active_stop_price=6001.25 |
| Setting changed between exports | New run/configuration identity | RSILength changes from 14 to 20 |
| Genuine effective setting change within a supported run | Versioned setting event with effective bar | risk setting changes at bar B120 |

GNET reads declared names, types and values. It cannot infer a calculated series
from the Input name, scrape arbitrary chart internals or understand arbitrary EL
source. A new source compilation is not proof the chart used those Input values.

Keep fixed Inputs once per configuration; preserve an unambiguous link from each
bar/candidate/trade to that configuration. Changing a chart Input generally
requires recalculation and a new export. Do not imply in-run setting-event support
already exists. Declare diagnostic units, availability timing and missing-value
rules. Optional diagnostics must not silently become training features; causal
feature eligibility requires a separate supported feature contract/review.

## Toy strategy recipes

### A. MA plus filters

Inputs: FastLength, SlowLength, RSILength, RSILimit, UseVWAPFilter,
StartTime, EndTime and supported exit/quantity/cost inputs.

Entry: MA crossover plus RSI limit, optional VWAP filter and session-time filter.
Export the actual Input values. If diagnostics are requested and supported,
export computed fast/slow MA, RSI, VWAP and condition flags at bar availability.
Declare the VWAP calculation and reset policy; do not substitute a differently
defined function merely because its name resembles VWAP.

### B. Different rule family

Inputs: ConsecutiveDownBars=3 and HoldBars=5, plus execution settings.

Entry: three completed falling bars; exit after the declared holding period.
Record the signal bar separately from the execution bar and retain actual fills.
Use a descriptive family name. Generic ledger validation and observed-trade
training should not demand MA-specific signal reproduction.

### C. Multiple lots

Buy one lot, add one lot, partially exit and finally close. Export separate fill
identities and quantities under the correct position identity. Reversals must
close one position and open another. Do not flatten several lots into an invented
single entry/exit pair. Stop at the unsupported capability if the installed
ledger/label unit cannot represent the transitions accurately.

## Required top-of-source instructions

Use a readable comment with one '-' item per idea. Include:

- This is a research Strategy and the intended strategy name/revision.
- Exact entry, exit, session-reset and order-timing behavior.
- Editable sections and export plumbing that must be preserved.
- ExportEnabled=true is required for this scaffold's research export/order flow.
- ExportInbox must match the installed fixed inbox; ExportFolder remains empty
  where required by the installed scaffold.
- Keep intended strategy/exit/quantity/cost settings after source replacement.
- For automatic metadata, set AutoMetadata=true and VolumeMode, PriceBasis,
  ChartTimeZone to unknown; check retained chart Inputs explicitly.
- Scaffold-specific MaxBarsBack, calculation and intrabar requirements.
- Diagnostic series, units, missing-value rules and availability semantics.
- Known unsupported execution/export capabilities; no live-use claim.

## Verification and handoff

1. Verify/compile in TradeStation; use supported EL APIs rather than guessed
   namespace members. Compilation is a human/platform gate when tools cannot
   access the editor.
2. Inspect actual chart Inputs and newest Events Log. Resolve missing export
   settings before blaming the timeframe for zero trades.
3. Recalculate the chart, create a fresh export child and wait for closure/sealing.
4. Use installed MCP/typed operations for automatic source/ledger checks. Do not
   directly read private market exports or models without explicit authorization.
5. Compare expected and reported configuration, trade population, candidate/bar
   joins, cost units and execution shape. Do not claim an untested strategy is
   trainable merely because it compiled or created files.
6. Guide the human through ordinary source approval; retain exact source and
   settings fingerprints. If a current producer allowlist blocks an edited
   exporter, report that actual restriction. Do not silently bypass it.
7. Explain any missing reusable capability precisely. More filters or parameters
   alone are not a reason to redesign the broker.

Never collect Windows passwords in chat or tool arguments. Preserve live
services, terminal shortcuts and other strategies. Report recorded-ledger ML
filtering accurately: it does not recreate the hypothetical strategy path after
rejected entries change occupancy or later decisions.

## Agent completion report

- Technique type: Strategy; full name, identity and revision.
- Changed logic/Inputs and preserved scaffold sections.
- Actual configuration versus per-bar diagnostic declarations.
- Position model, fill semantics, costs and label unit if supported.
- Compile evidence, export closure and automatic validation results.
- Supported import/display/labels/training/replay capabilities and exact gaps.
- Source approval action, without promising deployment or live promotion.
