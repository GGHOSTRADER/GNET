# Revised primary-strategy extension policy

## Status

Design proposal for reducing strategy-authoring friction. Its first source
implementation now supports generic fixed Inputs and observed single-position
trade validation alongside legacy MA contracts; synthetic XGBoost/scoring tests
passed. It is not installed. Per-bar diagnostics, generic complex positions and
internal rule composition remain pending. Native training still assumes quantity
1 and ES point value 50. See
[implementation evidence](../reports/GNET_GENERIC_PRIMARY_IMPLEMENTATION_2026-10-10.md).

## Principle

New strategy complexity must not itself require a broker deployment. Separate
strategy entry logic and descriptive inputs from ledger validation, label policy
and execution/replay capabilities. A new family name or additional conditions
must not automatically change the data contract.

## TradeStation imported strategies

TradeStation owns strategy execution. GNET accepts bars, candidate anchors,
executed fills/positions, declared costs and a versioned strategy descriptor.
Inputs are a bounded typed parameter map, not fixed fast/slow columns. The UI
renders names, types and values generically. Unknown descriptive fields may be
preserved/displayed, but must not silently influence calculations.

GNET automatically validates the ledger: timestamp and bar joins, causal signal
anchors, fill/position quantities, side, prices, costs, P&L reconciliation and
coverage. It need not reproduce the original entry rule to train a secondary
model on correctly anchored observed trades. Independent entry-rule reproduction
is a separate optional check with its own status.

Recorded-ledger filtering must not be presented as a counterfactual rerun: rejecting
one trade can affect later entries/occupancy in the original strategy. Candidate
coverage must be reported explicitly: executed trades alone are not all signals.

## Generic position model

Implement reusable support once for position IDs, order/fill IDs, entry/exit lots,
quantities, reversals, partial fills/exits and pyramiding. A reversal closes one
position and opens another; simultaneous positions retain separate identities.
Strategies using supported transitions then require no new per-family adapter.

Define label units explicitly: candidate, entry lot or completed position. Costs,
aggregated outcomes, observation times and information intervals must match that
unit. Complex trades are not eligible for training merely because storage can
accept them. Expose capabilities separately for import, display, labels, training,
recorded-ledger comparison and independent execution. Unsupported capabilities
must explain the missing evidence or semantics without blocking supported ones.

## Internally generated primaries

The same primary engine can consume GNET-constructed bars or imported TS bars.
A composable, versioned rule specification should allow supported conditions and
operators to be combined into new strategies without broker edits. Strategies are
saved configurations. Truly new executable primitives still require reviewed code
installation; arbitrary strategy code must not become unchecked broker execution.

## Changes and required action

| Change | Intended workflow |
|---|---|
| More inputs, filters or TS entry triggers; new family name | Export, automatic ledger validation, ordinary source approval |
| Combine existing GNET rule primitives | Save configuration, validate and backtest |
| Reversal/pyramiding/partial exits represented by supported generic ledger | Validate transition/label capabilities; no per-strategy deployment |
| New optional descriptive metadata | Preserve/display within bounded schema; no executable meaning |
| New execution semantics or new GNET executable primitive | Implement reusable capability and review protected code once |
| Breaking export schema | Versioned adapter/migration; keep compatible strategies working |

## Integrity and producer identity

Retain integrity checks for the installed broker runtime. Remove the assumption
that every strategy source edit must renew a whole-producer allowlist. Separate
the stable export transport/schema identity from the strategy source/settings
fingerprint. Strategy fingerprints provide provenance and bind approvals to exact
exports; they must not imply a broker reinstall. Transport identity alone does not
prove arbitrary producer code trustworthy: validate exports as untrusted data and
retain local source approval. Do not weaken existing gates until the replacement
contract and installed tests are complete.

## First implementation acceptance

1. Import an MA strategy and a multi-trigger non-MA strategy through the same
   installed receiver, with different parameter maps and no per-family deployment.
2. Render all declared inputs and validate bar/candidate/trade joins automatically.
3. Build causal features/labels and train from observed trades for both strategies
   without requiring entry-rule reproduction; report its separate status.
4. Reject malformed position transitions, incorrect P&L/costs and missing causal
   anchors with precise errors; never guess signal anchors.
5. Add generic position transitions with explicit label units and independent
   capability tests before declaring those shapes trainable.
6. Verify new strategy edits require source review only; altered protected broker
   code still fails the integrity check.
