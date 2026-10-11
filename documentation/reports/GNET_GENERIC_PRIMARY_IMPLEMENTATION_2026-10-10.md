# Generic EasyLanguage primary: first implementation

## Completed source changes

Source checkout: `C:\Users\g_med\.codex\worktrees\guarded-research\GNET`.
Installed V38 and existing immutable packages were not modified.

- Added native primary contract 3 alongside legacy contract 2. The generic
  contract has a descriptive family/revision and bounded typed Input manifest.
  Duplicate case-insensitive names, reserved execution names, wrong types and
  unsupported position semantics are rejected.
- Legacy MA exports retain independent crossover verification. Generic exports
  validate observed signal/execution anchors, side, quantity, fill grid/range,
  chronology, occupancy, declared costs and fill-derived P&L without claiming
  independent entry-rule reproduction.
- Sealing, custody-compatible schemas, reviewed source preparation and causal
  training accept the generic nested contract. Fixed inputs participate in
  settings fingerprints and remain attached to training provenance.
- Imported trade reports show declared Input names/types/values and distinguish
  independently checked MA rules from observed generic signal rows. Values are
  rendered as text; report JSON escapes markup.
- Added `EL_files/GNET_Primary_Generic_Scaffold.els` as an editable research
  Strategy template with explicit Input manifest and marked entry-logic section.
  `LogicImplemented=false` prevents accidental execution of unfinished logic.
  The MA example remains a reference block to replace, not inferred custom logic.

## Verification

- Native primary and source-review/model/replay regressions: 49 passed after
  correcting an existing stale assertion that expected eligibility during source
  preparation. Preparation reports observed/closed counts; feature eligibility
  belongs to the separate dataset-building stage.
- Latest generic contract/workflow and affected native-view suites: 37 passed.
  This includes a generic-family synthetic source through custody/review,
  causal feature/label construction, XGBoost training, scoring and recorded-position
  comparison. No real market data was used.
- All five edited Python modules imported. Exact-edit helper preserved pre-edit
  top-level definitions; tracked HEAD inventory is checked separately.
- TradeStation Verify and actual generic EL export were not run. Python tests
  are not evidence that the EL template compiles on the installed platform.

## Still required for the wider design

The matching immutable installation candidate is now built:
`.artifacts/GNET-Command-Center-v39-GenericPrimary-r1`, broker
`guarded-v39-generic-primary`, client `gnet-client-v43-generic-primary-r1`.
Both deployment plans passed and 11 generic synthetic tests passed against the
frozen candidate implementation, including XGBoost/scoring/comparison.
Broker manifest SHA-256:
`586bb75caeb5840fa4a1becb63a94665e3fbafdc3d5e883458d73f4983a893ae`.
Client manifest SHA-256:
`8a502f70a7c02ac9e57cc1810c1dae10f630c644704a95cad2eddc53ad19e0d1`.
Activation/audit and matching ordinary-user client installation remain pending.

- Build/review/deploy a matching broker/client release; this source is not live.
- Separate producer transport trust from per-strategy fingerprints. The existing
  exact producer allowlist remains enforced; arbitrary edited exporters are not
  automatically authorized by this change.
- Versioned per-bar calculated diagnostics and dynamic-setting event transport.
  Fixed Input values are linked once per export; arbitrary calculated series are
  not yet recorded on every bar.
- Generic fill/lot ledger for reversals, pyramiding, partial fills/exits and
  concurrent positions, with explicit label units and supported replay semantics.
- General internal rule composition for GNET-generated primaries on internal or
  imported bars. Internal primary generation remains MA-specific.

Current generic source path is still single-full-exit/next-bar-market, and the
training adapter still requires one ES contract. Recorded-position filtering is
not counterfactual TradeStation resimulation. These limits are explicit, rather
than silently accepting unsupported shapes.
