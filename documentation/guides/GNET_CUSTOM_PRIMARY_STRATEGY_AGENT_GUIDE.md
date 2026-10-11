# Custom primary strategies: agent guide

For EasyLanguage authoring, read
[the EL strategy authoring guide](GNET_EL_PRIMARY_STRATEGY_AGENT_GUIDE.md).
The [revised extension policy](GNET_PRIMARY_STRATEGY_EXTENSION_REVISION.md)
separates desired generic behavior from current installed limitations. A new
strategy family or additional input is not inherently a broker deployment.

## Mission

Help a client adapt a primary TradeStation strategy without pretending that a
custom rule is the built-in MA crossover. Preserve the generic trade contract,
capture the strategy's actual inputs, and stop at the correct review boundary.

## Discover before editing

1. Identify whether the user wants a bar indicator or a primary strategy.
2. Read the installed scaffold and its editable logic markers.
3. Discover the actual installed client and broker release/tool schemas.
4. Record the strategy's full name, optional nickname, family, input names/types,
   values, position model and execution assumptions.
5. Classify the change:
   - parameter-only;
   - new rule family;
   - reverse, pyramid, partial-fill or multi-position execution;
   - new export fields or validation rules.

Do not infer strategy inputs from a filename or from a ready badge.

## Parameter manifest

For a parameter-only strategy, write an extensible descriptor rather than fixed MA
fields:

```json
{
  "logic_family": "custom",
  "logic_revision": "rev01",
  "parameters": {
    "name": {"type": "string", "value": "rsi-vwap-primary"},
    "rsi_length": {"type": "integer", "value": 14},
    "vwap_filter": {"type": "boolean", "value": true}
  }
}
```

The exact installed schema takes precedence. Never add arbitrary top-level fields
to a submitted bundle. If the installed schema does not accept an extensible
parameter manifest, report `contract_extension_required`; do not relabel the
strategy as `ma_cross`.

## Edit rules

- Edit only the scaffold's marked strategy-logic and input sections.
- Preserve exporter, custody, session, metadata, closure and identity code.
- Keep `ExportInbox` at the fixed installed root and keep `ExportFolder` empty.
- Keep automatic metadata inputs as `unknown` unless the user has verified them.
- Keep MaxBarsBack and intrabar settings as documented by the scaffold.
- Do not add arbitrary paths, DLLs, network calls or broker writes.
- Do not read raw rows, ticks, matrices, private models or credentials.

## Validation classification

Generic validation may check source/bundle identity, timestamp order, bar linkage,
position chronology, fill bounds, quantity, costs and recomputed P&L.

Determine support from installed capabilities rather than strategy complexity:

- New rule families and extra inputs should use generic descriptors and observed
  trade validation. Independent signal reproduction is a separate capability.
- Reversals, pyramiding, partial exits/fills and multiple positions should reuse
  the generic position ledger when its transition and label-unit capabilities
  are implemented; otherwise report the precise unsupported capability.
- A genuinely new executable primitive, breaking schema or calculation meaning
  may need a reusable adapter and reviewed protected update.

The inspected current receiver remains MA-specific; generic parameter handling
and complex ledger support must not be claimed installed. Required system
extensions need tests and reviewed activation. The agent must not silently
change the protected broker or allowlist for an individual strategy.

## Command Center handoff

Use the installed typed operations and exact parent IDs. The intended sequence is:

1. prepare the primary exporter;
2. verify and recalculate in TradeStation;
3. wait for the closed transfer receipt;
4. run automatic source validation;
5. submit a draft review with the generated IDs and strategy descriptor;
6. report the adapter status and unresolved evidence;
7. stop before registration, training or promotion unless the reviewed policy
   explicitly authorizes those operations.

The Command Center should render the strategy descriptor's input manifest as a
table of name, type, value and provenance. If it only shows a strategy ID and
settings fingerprint, report that the current UI lacks generic parameter rendering
and keep the source pending rather than claiming the inputs were displayed.

## Required agent report

Return a bounded report containing:

- strategy ID, family and revision;
- input names/types/values from the descriptor;
- source, settings and bundle fingerprints;
- position/execution shape;
- generic checks passed/failed;
- adapter required or not required;
- exact next human or administrator action.

Never claim a custom source is approved, trainable or safe for live use merely
because TradeStation compiled it or a file arrived in the inbox.
