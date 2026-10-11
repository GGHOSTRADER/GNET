# Research validation and provenance requirements

Status: requirements agreed during architecture planning, October 2, 2026.
These requirements describe work to implement; they do not certify existing
datasets or imply that the validation tools already exist.

Related documents:

- [Guarded runtime architecture](guarded_research_runtime_architecture.md)
- [Backtester module boundaries](backtester_architecture.md)
- [Human backtester guide](guides/BACKTESTER_GUIDE.md)
- [Agent backtester guide](guides/BACKTESTER_AGENT_GUIDE.md)
- [Data inventory](backtester_data_inventory.md)
- [Existing file/schema contract](backtester_file_contract.md)
- [Strategy inventory](backtester_strategy_inventory.md)
- [Report locations and outputs](backtester_reports.md)
- [Imported source-bar aggregation](source_bar_aggregation.md)
- [Independent-entry exit collector](exit_module.md)

## 1. Purpose and execution boundary

Provide reusable Python jobs that inspect data and research outputs, perform
the expensive calculations, and return concise evidence to the agent. The
agent receives metadata, aggregates, charts, and HTML reports through the
guarded runtime. Raw ticks, bars, candidates, trades, and large derived tables
remain in protected storage. Any explicitly requested diagnostic sample must
respect the gateway's field and row limits.

The suite covers bar construction, primary-strategy candidates, entry/fill
evaluation, preset execution, optional exit-policy search, and results
analysis. Candidate events and executed trades must remain distinguishable.
The independent-entry exit collector and the position-aware backtester must
identify their different execution assumptions in their reports.

## 2. Dataset identity, revision, and naming

Every dataset must have an immutable dataset ID and manifest. Each revised
dataset must contain the literal `revised` in its new folder/file name plus a
revision number. Keep the original version; never overwrite it in place.

Illustrative naming patterns (dates and contract ownership must be verified
from actual sources before use):

```text
ES__ESU26__tick1__<first>_to_<last>__rev01
ES__ESU26__tick1__<first>_to_<last>__revised_rev02
ES__continuous_ESU26_ESZ26__tick1__<first>_to_<last>__unadjusted-splice__revised_rev02
```

Dates use `YYYY-MM-DD`. Distinguish session-date coverage from calendar
timestamps. The `revised` marker identifies a revision; validation status
establishes which checks passed for that version. Do not equate renaming with
correctness or trading edge.

Record these independent fields:

| Field | Required meaning |
|---|---|
| `dataset_id`, `revision` | Immutable identity and version |
| `asset` | ES, independently of symbol/contract |
| `provider_symbol` | Exact export symbol, such as ESU26 or @ES |
| `series_type` | Outright, provider-continuous, unadjusted splice, or adjusted series |
| `contract_segments` | Actual delivery month/year/symbol and ownership interval for every segment |
| `price_basis` | Unadjusted or explicit adjustment policy/version |
| `coverage` | First/last event timestamps, session range, timezone, partial-session flags |
| `source_kind`, `source_size` | Individual ticks or source volume/tick bars, including actual size |
| `bar_timestamp_convention` | Start, end, or actual last-event time; boundary-inclusion rule |
| `session_policy` | Session boundaries, calendar/version, holidays and shortened sessions |
| `instrument_specification` | Tick size, contract multiplier, volume interpretation and units |
| `revision_reason`, `supersedes_dataset_id` | Why the new version exists and its predecessor |
| `lifecycle_status` | Draft, active, deprecated, or rejected |
| `validation_status` | Pending, pass, warn, or fail; linked validation evidence |

Unknown actual contract ownership must remain explicitly unknown. A provider's
continuous symbol alone does not prove which historical delivery contract it
contains. Such data cannot pass a check requiring known ownership.

The catalog records which version supersedes another. Historical manifests
remain immutable so prior studies can be reproduced.

## 3. Exact filenames and traceability

Every generated bar dataset must record the **actual original source filenames**,
including their extensions. A generic `tick1` label is insufficient.

The protected manifest must list, for every contributing file:

- Original filename and original logical location.
- Current vault-relative path or registered artifact ID.
- SHA-256 content hash, size, provider/export timestamp, and schema version.
- Asset, exact symbol, actual contract when known, timezone and price vintage.
- Observed timestamp/session coverage, source row count and source sequence ID.
- Preparation/merge job ID, module release, effective configuration, and hash.
- Ownership decision for overlaps and any price adjustments applied.

Traceability must work through the complete chain:

```text
backtest run -> executed trade -> candidate -> engineered bar
            -> prepared source partition -> original export filename/hash
```

Broker-side artifacts preserve stable bar/candidate/trade IDs, constituent
source references, and execution-tick references. Preserve sequence order for
equal timestamps. Where aggregation combines several files, record all
contributing sources; use compact ranges or a protected lineage table instead
of duplicating millions of row IDs into a shared manifest.

The agent-readable provenance summary lists original filenames, hashes,
coverage, dataset/parent IDs and revision reason. It returns no source rows,
credentials, or raw data. A `provenance_summary` job resolves a dataset or run
ID to this chain for quick backtracking.

## 4. Naming and metadata for research outputs

Every primary backtest, candidate dataset, generated bar dataset, and exit
search output identifies the asset, contract/series, and covered dates. Use a
unique UTC run stamp plus a collision-resistant job ID. Example patterns:

```text
bars__ES__ESU26__time30s__<first>_to_<last>__<job-id>
candidates__ES__ESU26__ma_cross__<first>_to_<last>__<job-id>
backtest__ES__ESU26__<first>_to_<last>__run_<UTC-stamp>_<job-id>
exit-search__ES__continuous_ESU26_ESZ26__<first>_to_<last>__<job-id>
```

These are proposed naming rules. Existing data/results are not renamed by
this requirements document. Future migration must retain a mapping from old
names to new IDs and all historical references.

Each output manifest must contain the exact dataset/revision/hash, original
source filenames, contract segments, adjustment policy, bar specification,
strategy implementation and parameters, entry convention, exit rules or search
axes, position sizing/occupancy, fee/slippage assumptions, runtime release and
dependency identities, job/config hash, search budget, workers, phase/date
splits, execution status, warnings and report references.

Use $6.48 round-trip cost per one-contract ES trade as the currently agreed
research assumption; record it explicitly rather than treating it as a
universal or permanently current brokerage rate. Do not invent initial
capital to obtain percentage-return statistics.

## 5. Required validation jobs

| Job | Required evidence |
|---|---|
| `data_continuity` | First/last tick and bar, coverage, chronology, unexpected gaps, partial sessions, duplicates, schema and units |
| `signal_alignment` | Signal bar ID, completed-bar availability, decision time/order, entry-bar association and absence of future feature inputs |
| `entry_price_alignment` | Recorded entry versus reconstructed entry-bar open and first eligible tick; exact discrepancy in ticks and time |
| `execution_path` | First profit/stop/time hit, eligible event order, fill convention, gaps and unavailable/censored exits |
| `position_occupancy` | Policy-specific accepted/skipped candidates; no unintended overlapping positions |
| `rollover_integrity` | Matching contract/vintage for ticks, bars and trades; cutover, adjustment, reset and position policy |
| `trade_distribution` | Gross/net P&L buckets, quantiles, win/loss/breakeven counts, exit reasons and aggregate reconciliation |
| `holding_time_analysis` | Elapsed seconds and exit-bar offset distributions, separated by winners/losers and exit reason |
| `holding_profit_analysis` | Count, gross/net sum, mean/median P&L and win rate for every declared holding-bar bucket |
| `trade_extremes` | Longest duration, biggest gross/net profit and biggest loss with stable IDs and bounded diagnostic evidence |
| `state_and_warmup` | Correct indicator/feature/session/roll state, required history and partial-bar handling |
| `reproducibility` | Stable results for identical data/config/release and serial versus parallel execution |
| `research_guardrails` | Declared development/confirmation periods, overlap of label intervals, split/purge/embargo evidence where applicable, and trial history |
| `provenance_summary` | Original filenames and hashes resolved from dataset/run IDs through every derivation |

Not all these checks currently exist. The implementation must expose available,
unavailable and failed checks explicitly.

### Timing and price checks

Store signal-bar start/end, decision availability, candidate order, actual
entry timestamp and entry sequence index. Timestamp equality alone does not
prove correct or incorrect timing; equal-second ticks require event order.
Features must use data available at the actual decision event.

For an entry at the next bar open, test the entry against that bar's first
eligible tick. The signal-bar close may differ legitimately from the next-bar
open. A recorded fill may differ due to slippage, gaps, order type or source
conventions; report and classify it instead of changing the source silently.
Report mismatch count/rate, gap quantiles and maximum, with referenced source
filenames and affected candidate/trade IDs.

### Bar continuity and holding-time conventions

Time-bar gaps are checked against the declared session/calendar and empty-bar
policy. Tick/volume bars have variable durations; do not demand fixed spacing.
Validate OHLC consistency, final-bar completeness, counts/volume totals, and
whether bars crossing a session boundary are allowed.

Define `exit_bar_offset=0` as exit in the entry bar, `1` as exit in the next
bar, and so on. Display offset 0 as "entry bar" or "first bar". Separately
report bars touched (`exit_bar_offset + 1`, where measurable), elapsed seconds,
and completed bars; do not mix these definitions. Use each tested bar series'
own IDs. An unresolved exit has no invented holding-bar count or P&L.

### Distribution and extreme reports

Declare bucket edges and inclusivity in the result. All bucket counts and
P&L sums must reconcile with the eligible trade population. Report excluded,
unresolved and censored rows separately. Include winners/losers, session/month,
exit reason and direction where supported. Net-zero trades use a distinct
breakeven category. Ties for extremes must have a documented ordering or
return all tied IDs within the output bound.

Useful extensions include favorable/adverse excursion and time to first hit,
measured over declared horizons; these help analyze future exit hypotheses.
Inspection of outcomes does not make an exit rule available in advance.

## 6. Rollover requirements

Maintain a versioned contract map with delivery month/year, exact symbols,
cutover sessions, source vintage, roll-rule inputs, and adjustment policy.
Separate actual expiry/contract rollover from a provider revising its historical
continuous-series price basis.

Initial intraday policy: matching source ownership for ticks and bars, flat
positions at the handoff, declared state reset/warm-up, and no tradable P&L
attributed to the splice jump. Any future position-carry policy must model
closing/reopening contracts and the associated costs explicitly.

Choose the cutover by a declared rule, such as a fixed calendar rule or a
liquidity rule using information available before the switch. Record the
choice and any overlap comparison. Preserve executable unadjusted contract
prices; an adjusted analysis series must retain its mapping to those prices.
Reject unexplained contract/price-basis mismatches and double adjustment.

López de Prado's book index identifies the single futures roll method and
gaps series on pages 36–37: [publisher index](https://catalogimages.wiley.com/images/db/pdf/9781119482086.index.pdf).
The numerical roll policy still needs to be selected for GNET; this document
does not claim a specific book implementation has been reproduced.

## 7. Tests, report gates, and resource limits

Build synthetic fixtures with exact known results for target first, stop
first, both touched in one bar, equal timestamps, boundary ticks, price gaps,
delayed time exits, missing coverage, partial bars, session transitions, DST,
rollover and position occupancy. Test each supported bar family and source
adapter. Verify row-order preservation and cost/tick/multiplier units.

`validation_preflight` records data/provenance/timing checks before a run;
`validation_postflight` verifies execution, distributions and reconciliation.
Every check returns `pass`, `warn`, `fail` or `unavailable`, plus counts,
configured tolerances and compact evidence. Critical failed checks block
publication as usable research. Warnings and unavailable required checks
remain visible. Passing engineering validation does not establish profitability.

Run independent policies over their complete chronology. Verify that one and
multiple workers produce the same candidates, trades and aggregates, allowing
only declared numerical tolerances. Limit CPU/workers, RAM, runtime, policy
evaluations, output rows and artifact size; return resumable status on a
documented termination path. Save failed and unsuccessful trials too.

Keep full forensic artifacts protected. Shared output includes a small JSON
validation manifest, summary tables/charts and HTML links. Longest/worst/best
trade inspection uses a separate explicitly requested bounded job.

## 8. Implementation order

1. Versioned identity/provenance schemas, naming helpers, and synthetic tests.
2. Metadata-only inventory and provenance summaries through the broker.
3. Data continuity, signal/entry alignment and rollover checks.
4. Execution audit, occupancy, state/warm-up and cost reconciliation.
5. Holding-time/P&L distributions, extremes and optional excursion summaries.
6. Mandatory preflight/postflight manifests in preset and sweep workflows.
7. Serial/parallel regression checks and protected deployment/ACL tests.

These requirements extend the existing guarded-runtime and backtester designs;
their architecture, guides, inventory and report documents remain authoritative
for currently implemented behavior until the new jobs are built.
