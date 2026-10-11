# Guarded research system — implementation phases

Status: implementation roadmap, October 2, 2026. All phases below are planned;
existing engine capabilities are reused but do not count as completed broker
integration. This roadmap governs implementation order where earlier design
documents contain shorter rollout sketches.

## Contract map

| Contract | Governs |
|---|---|
| [Guarded runtime architecture](guarded_research_runtime_architecture.md) | Accounts, protected runtime/data, job execution and shared results |
| [Backtester architecture](backtester_architecture.md) | Bar/strategy/execution/exit-analysis/statistics responsibilities |
| [Interface and viewer specification](research_interfaces_and_trade_viewer.md) | Job names, inputs/outputs, artifact handoffs, chart/filter behavior |
| [Validation and provenance requirements](research_validation_and_provenance_requirements.md) | Audit jobs, source filenames, revisions, contracts, rollover and report gates |
| [File/schema contract](backtester_file_contract.md) | Current accepted source/prepared formats and merge compatibility |
| [Source-bar aggregation](source_bar_aggregation.md) | Grouping imported source bars versus traded-volume thresholds |
| [Integration audit](reports/guarded_backtester_integration_audit_2026-10-02.md) | Twelve gaps that the phases must close |

The file/schema contract documents current formats; new broker IDs and
manifests adapt those formats. Any changed format must be versioned and its
consumer updated. Keep historical datasets and run references reproducible.

## Phase 1 — Executable interface contracts

Depends on: none.

Contracts: [interfaces, sections 1–3](research_interfaces_and_trade_viewer.md),
[provenance, sections 2–4](research_validation_and_provenance_requirements.md),
[audit findings 1 and 9](reports/guarded_backtester_integration_audit_2026-10-02.md).

Deliverables:

- Versioned request/result, dataset, artifact and validation schemas with
  Python types; canonical operation names and structured errors.
- Protected resolver interface for dataset/artifact/release IDs.
- Adapter mapping job parameters to current engine `Config`; allocate internal
  paths in the broker, never accept user-supplied execution paths.
- Separate execution identity, search identity and job-attempt identity.
- Correct the architecture diagram so exit analysis calls execution and
  consumes per-policy statistics.

Completion: synthetic requests map exactly to intended configuration;
unsupported operations, types, paths and incompatible artifacts are rejected.
Schemas include required identity fields; all examples validate.

## Phase 2 — Job client, queue and safe publication

Depends on: phase 1. Uses synthetic fixtures and a local test broker.

Contracts: [runtime, sections 3–4 and 6](guarded_research_runtime_architecture.md),
[interfaces, section 2](research_interfaces_and_trade_viewer.md),
[audit findings 2, 6 and 12](reports/guarded_backtester_integration_audit_2026-10-02.md).

Deliverables:

- `submit`, `status`, `report` and cancellation client operations.
- Atomic queue submission/claim, duplicate detection, leases/heartbeat,
  bounded draining and retriggering; recovery after worker failure.
- Protected workspace abstraction and a distinct shared publication writer.
- Bounded logs/results and safe HTML links; capability discovery reports
  implemented/planned/unavailable operations.
- Requested versus enforced CPU/RAM/time/disk/output limits; documented hard
  stop and resumable checkpoint behavior.

Completion: concurrent/repeated submissions and a simulated crash reach
defined states without duplicate execution or stranded requests; published
results expose no protected artifact links or full trade/tick tables.

## Phase 3 — Data catalog, provenance and ingestion adapters

Depends on: phases 1–2. Build with synthetic exports first.

Contracts: [provenance, sections 2–4](research_validation_and_provenance_requirements.md),
[current file formats](backtester_file_contract.md),
[data inventory](backtester_data_inventory.md),
[audit finding 4](reports/guarded_backtester_integration_audit_2026-10-02.md).

Deliverables:

- Dataset and artifact manifests with exact original filenames, hashes,
  contract/month/series identity, timezone, coverage and parent references.
- `data_inventory` and `provenance_summary` broker jobs with compact outputs.
- Immutable ingestion/preparation/merge adapter; explicit overlap ownership,
  adjustment policy and contract cutover map.
- Revised naming containing `revised_revNN`, separate validation/lifecycle
  status, and mapping from legacy paths to immutable IDs.
- Hash verification policy that avoids hashing the whole archive for every
  metadata request; preserve current preparation/splice semantics.

Completion: a synthetic source -> prepared data -> bars -> run chain resolves
back to original filenames/hashes. Missing/incompatible provenance fails;
revision creation preserves its predecessor. Unknown contracts stay unknown.

## Phase 4 — Validation gates and bar/candidate jobs

Depends on: phases 1–3.

Contracts: [validation jobs and gates](research_validation_and_provenance_requirements.md),
[backtester boundaries](backtester_architecture.md),
[interfaces, sections 1 and 3](research_interfaces_and_trade_viewer.md),
[audit findings 3 and 8](reports/guarded_backtester_integration_audit_2026-10-02.md).

Deliverables:

- Standalone `build_bars` and `generate_candidates` over prepared tick tapes;
  reuse current time/tick-count/volume-threshold builders and strategy registry.
- Stable bar/candidate IDs with event availability and source references.
- Continuity, session/DST, completeness, warm-up and signal/entry alignment
  checks; explicit operation-specific required checks and tolerances.
- `validation_preflight`/`validation_postflight` records bound to identities;
  fail/warn/unavailable handling and diagnostic publication.

Completion: synthetic first/last bars, gaps, tied ticks, session transitions and
partial bars give known results. Signals cannot use incomplete/future bars.
Failed required checks prevent a result from being marked usable.

## Phase 5 — Preset backtesting and rollover execution

Depends on: phase 4. Establish the full preset path before adding sweep jobs.

Contracts: [execution routes](backtester_architecture.md),
[rollover and timing requirements](research_validation_and_provenance_requirements.md),
[audit findings 5 and 11](reports/guarded_backtester_integration_audit_2026-10-02.md).

Deliverables:

- `backtest_preset` adapter over current chronological execution with three
  barriers, costs, slippage, occupancy and explicitly recorded conventions.
- First eligible tick versus entry-bar open audit and fill-gap classification.
- Executable flatten-before-cutover rule, source-state reset/warm-up and
  explicit behavior when the old-contract close cannot be executed.
- Separate valid-measured, diagnostic-all and unresolved/invalid populations.
- Per-policy event references, stable trade IDs and entry/exit bar mapping.

Completion: known synthetic stop/target/time/gap/occupancy/rollover paths match
exact expected outcomes; all accepted/skipped/invalid counts reconcile.
Policy execution on one versus multiple workers agrees. Any comparison with
external platform results is reported as an audit, not forced into equality.

## Phase 6 — Statistics and compact research reports

Depends on: phase 5.

Contracts: [statistics specification](backtester_architecture.md),
[holding-time, distributions and extremes](research_validation_and_provenance_requirements.md),
[report inventory](backtester_reports.md),
[audit finding 10](reports/guarded_backtester_integration_audit_2026-10-02.md).

Deliverables:

- Reuse existing equity/drawdown/concentration/Sharpe statistics; retain
  unavailable metrics when capital/trial-history inputs are absent.
- Holding seconds and entry-bar-offset distributions; gross/net P&L by
  holding bucket, outcome/month/exit reason; quantiles and extreme-trade IDs.
- Cost and aggregate reconciliation; bounded diagnostic and excursion jobs.
- Separate safe statistics report and manifest with actual filenames,
  contracts, dates, assumptions, validation status and code/data identity.
- Explicit benchmark interface and same-period ES comparison where supported;
  declare sizing/capital/roll/cost conventions. Report unavailable otherwise.
- Reports-only operation over saved artifacts without starting replay or
  reconstructing missing caches.

Completion: counts and totals reconcile to declared populations, entry-bar
offset zero is consistent, hand-calculated statistics fixtures pass, and
shared reports contain only permitted outputs. Classifier AUC remains
unavailable unless prediction/label inputs are supplied.

## Phase 7 — Trade viewer

Depends on: phases 4–6. UI development can start with synthetic fixtures after
phase 2; connection to real runs requires phase 6 outputs.

Contract: [viewer and filters, section 4](research_interfaces_and_trade_viewer.md),
[protected publication](guarded_research_runtime_architecture.md).

Deliverables:

- `trade_view` job and candle/price-line display; bars, trade-focused, and both
  modes; signal/entry/exit markers and aligned duration lane.
- Clear winner/loser/breakeven/unresolved styles based on net P&L, using color
  plus labels/shapes; candidate events remain visibly distinct from fills.
- Combined date, outcome and gross/net P&L filters; stable sort/pagination;
  selecting a match centers its trade interval and displays approved details.
- Broker-generated bounded windows with explicit aggregation, exact fill
  markers, coverage/contract warnings and matching/shown counts.

Completion: synthetic fixtures verify both chart modes, filters/date boundaries,
equal timestamps, unresolved trades, selection and limits. Broader browsing
requests a new broker window rather than downloading the entire history.

## Phase 8 — Optional exit search and surfaces

Depends on: phases 5–6; viewer integration follows phase 7.

Contracts: [exit analyzer](backtester_architecture.md),
[resource/trial requirements](research_validation_and_provenance_requirements.md),
[audit findings 9 and 12](reports/guarded_backtester_integration_audit_2026-10-02.md).

Deliverables:

- `backtest_sweep` routes each proposed policy through the same validated
  chronological execution and statistics path as preset jobs.
- Declared profit/stop/time domain, start points, patience, jump probes and
  budgets; stop reason and unsuccessful trials retained.
- Separate bounded exit surface/rankings/region report, distinct from per-policy
  statistics; untested nodes remain unknown.
- Frozen selection/confirmation metadata and recovery/checkpoint rules.

Completion: serial/parallel and preset-versus-identical-sweep-policy results
agree; heuristics and budgets terminate as declared; selecting a surface node
opens the matching policy report/viewer. No automatic claim of trading edge.

## Phase 9 — Imported source-bar execution integration

Depends on: phases 3–5. Keep unsupported source combinations explicit until done.

Contracts: [source-bar aggregation](source_bar_aggregation.md),
[file/schema contract](backtester_file_contract.md),
[audit finding 7](reports/guarded_backtester_integration_audit_2026-10-02.md).

Deliverables:

- Broker build jobs for grouping N imported tick or volume bars, including
  one-volume sources; distinguish row grouping from traded-volume thresholds.
- Contract/vintage/clock alignment of those bars with a separate execution tape.
- Audited mapping from source close/availability to executable tick events;
  preserve OHLC and original filenames through aggregation.

Completion: a synthetic imported-bar strategy can drive exact known tick exits;
ambiguous mappings fail explicitly. Neither source OHLC nor source-row IDs
are presented as an inferred intrabar execution path.

## Phase 10 — Protected Windows deployment and end-to-end acceptance

Depends on: phases 1–8 for tick-tape V1; phase 9 for imported-bar capability.
The deployment script can be developed earlier against synthetic fixtures.

Contracts: [runtime identities, scheduling and release lifecycle](guarded_research_runtime_architecture.md),
[human runbook](guides/BACKTESTER_GUIDE.md),
[agent runbook](guides/BACKTESTER_AGENT_GUIDE.md).

Deliverables:

- Versioned release package/dependencies, broker account and folder/task setup
  scripts, fixed interpreter/action/working directory, and release verification.
- Task permissions allowing invocation while protecting task modification and
  deployed code; vault/workspace/request/status/results permission boundaries.
- Human and agent instructions for ingest, submit, inspect, cancel, resume,
  deploy/rollback and locate source provenance.
- Planned legacy-data registration/migration with preserved references;
  Windows setup and real-data migration are distinct recorded operations.
- End-to-end acceptance of normal-user request -> protected computation ->
  validation -> safe metrics/HTML -> candle/line viewer.

Completion: normal development identity cannot read vault data or modify broker
code/tasks; it can start allowed jobs and read their bounded reports. Crash/
restart/cancellation tests pass. Any real-data acceptance uses an explicitly
authorized bounded dataset and never prints raw rows to the agent.

## Tracking and scope

For each phase record: status, implementing release/commit, delivered interfaces,
test evidence, open findings and links to its reports. Mark complete only when
its completion checks pass. Current phase status: all planned.

The design remains an offline research system. Adding live deployment, ML
training adapters or more strategies requires explicit additional phases;
their capability must not be implied by building these broker interfaces.
