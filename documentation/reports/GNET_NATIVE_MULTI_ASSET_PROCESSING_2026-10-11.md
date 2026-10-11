# Imported-primary multi-asset processing — V47 / V80

Prepared and verified, not installed:
`.artifacts/GNET-NativeMultiAsset-v47-r1`.
Broker `guarded-v47-native-multiasset`, manifest SHA256:
`823788ff5a3b5733ae680ea4486d6560648d8cd7049081b469d3073a67721fd8`.
Client `gnet-client-v80-native-multiasset`, manifest SHA256:
`8e6b1f16bb5dcd43ca005b2a55514702c105bac8ce3a0f3b4d4f5d1c2ea25329`.
This continuation includes the staged V46 symbol-attribute export work; its three
EL sources are unchanged. Actual installed broker/client remain V44/V77.

## Processing changes

The recorded native-primary route now uses the accepted instrument's price grid,
point multiplier, declared whole-position quantity and total position round-trip
cost. Native quantities and fills must still match the exact reviewed ledger;
conflicts do not silently change labels. The paired legacy report adapter also
uses reviewed economics when supplied with a processing context, retaining its
old one-contract ES default for legacy context-free use.

Each imported bar binds to an explicit dated calendar window. Session membership
uses the bar-close instant minus one nanosecond, so a close exactly at the end
belongs to that session. Out-of-session timestamps and changed calendar hashes
fail. Partial opening bars stay incomplete. VWAP resets by the dated session;
minutes-since-open and the first/last-30-minute flag use actual UTC elapsed time
and scheduled close, including early closes, overnight sessions and DST.
Rolling windows continue across sessions and reset on vintage changes as before.
Amihud notional volume includes the instrument multiplier.

These semantics have separate `ma13-ts-calendar30-v2` and
`ma13-ts-calendar300-v2` feature contracts. Old contracts remain recognized.
Training artifacts retain the instrument/calendar processing context; the model
input loader checks it against the registered source and immutable calendar.
Feature artifact execution identity includes that context. Public artifact IDs
use the actual asset and encode symbols that cannot safely form registry IDs.

Non-ES capability gates now permit supported recorded-source bar features and
training after acceptance and policy checks. Internal primary generation,
tick construction and VP paths retain their asset restrictions. A stock has no
invented delivery month/year: native-recorded preflight accepts its exact reviewed
symbol ownership without pretending it is a futures contract.

The canonical engine change exists only in the staged package. Its optional
explicit session identity leaves the default legacy 18:00 reset behavior intact;
the independent live checkout and services were not modified.

## Validation

47 focused backend checks passed in 2.55 seconds. Thirteen cover this continuation:

- Fabricated stock: 0.01 increment, multiplier 1, three-share positions.
- Fabricated non-ES future: 0.25 increment, multiplier 20, two-contract positions.
- Actual worker construction of primary targets and training artifacts, exact
  target reconciliation, capability checks and model-input loading for both.
- Finite 13-column feature matrices and fill/quantity/cost-derived labels.
- Early close, next-session VWAP reset, overnight session date, DST and out-of-hours
  rejection. Bad quantities, multiplier and calendar scopes fail.
- Explicit exclusions for nonpositive prices where logarithmic features are
  undefined, with fresh warm-up afterward.
- Versioned feature hashes, actual asset naming and legacy engine defaults.

The wider existing canonical-feature study test could not collect because the
repository environment lacks `python-dotenv`. No dependency was installed to
alter that environment; the direct packaged default-clock/reset regression passes.

All 180 fabricated browser checks passed in 54.1 seconds without updating existing
screenshots. Those tests prove client behavior, not installed protected execution.
Modified Python modules import and existing definitions/class methods match the
immutable V46 baseline. Closed broker/client package verification, deployment-plan
hashes and PowerShell parser checks pass.

## Scope and remaining acceptance

Supported new path: accepted outright assets, unadjusted 30-second or five-minute
source bars, reviewed instrument profile and dated calendar, recorded next-bar
whole-position executions with matching full exits. Explicit exclusions are not
synthetic feature zeros. No real market data was opened and no model was fitted
during this change; tests use fabricated exports and temporary synthetic catalogs.

Non-ES continuous ownership/adjustment mappings, other bar periods, fractional
position quantities, pyramiding/reversal/partial-fill execution contracts and
internal/live trading remain separate work. Native research still describes
recorded positions, not a counterfactual TS engine rerun after ML rejection.

The candidate needs approved protected activation, deployment audit, matching
ordinary client install/restart and current installed-account acceptance before
using a selected real source. The three integrated EL sources still need the
user's TradeStation Verify results. Installing this continuation does not grant
source approval, isolation certification, live deployment or research permission.
