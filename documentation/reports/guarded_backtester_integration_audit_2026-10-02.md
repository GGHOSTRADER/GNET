# Integration audit: guarded runtime, backtester, validation/provenance

Date: October 2, 2026. Scope: static review of three design documents and
relevant source modules. No raw market datasets were opened and no backtest or
Windows configuration was run. Findings describe current implementation and
design gaps; they are not a runtime security certification.

Documents reviewed:

1. [Guarded runtime](../guarded_research_runtime_architecture.md).
2. [Backtester architecture](../backtester_architecture.md).
3. [Validation and provenance requirements](../research_validation_and_provenance_requirements.md).

## Overall finding

The responsibilities are compatible: the runtime controls access and jobs;
the backtester performs research computation; validation checks the inputs,
execution and resulting evidence. The integration is still a proposal.
It needs a broker adapter, typed artifact interfaces, validation gates and
a separate safe publication path before it can operate as described.

Existing useful foundations include strategy registration, completed-bar
signal availability, event-index entry references, chronological independent
policy execution, separate exit/statistics reports, code/config identities,
and immutable-output checks. These reduce implementation work but do not
already provide the broker boundary.

## Integration ownership

| Boundary | Current implementation | Missing contract |
|---|---|---|
| Agent -> broker | Proposed `gnet_jobs` client/tasks | Request envelope, submission rules, stable operation names |
| Broker -> data | Catalog/inventory helper exists | Protected catalog lookup, versioned dataset/contract/lineage schema |
| Broker -> backtester | `backtester.run` accepts local `Config` | Validated request -> internal config adapter and artifact resolver |
| Bars -> candidates | Integrated in `data.prepare` | Standalone bar/candidate job APIs, source-bar execution mapping |
| Candidates -> execution | Event references and per-policy occupancy exist | Versioned artifact handles, alignment audit output |
| Exit search -> execution | `ExitAnalyzer` invokes evaluator | Correct diagram, validation-aware evaluation callback |
| Execution -> validation/results | Basic validity flag and statistics exist | Full preflight/postflight gates and bar-offset distributions |
| Results -> agent | Existing local HTML/JSON artifacts | Bounded publication writer, permitted fields, safe links |

## Priority 1: resolve before using the protected runtime on real data

### 1. Define the broker-to-backtester adapter

The runtime request uses `dataset_id`, `sessions`, `exit_search` and `costs`.
The engine requires `tick_root`, `start_session`, `end_session`, `profits`,
`stops`, `holds`, `round_trip_cost`, and `execution_mode`. There is no explicit
mapping or protected output-root allocation. Runtime examples also omit fields
the prose says every request requires (release ID, schema/job identity).

Evidence: [Config](../../backtester/config.py:71),
[load_config](../../backtester/config.py:171),
[run entry point](../../backtester/run.py:14).

Required decision: one canonical request envelope plus operation-specific
payloads. The broker resolves dataset/artifact IDs and release IDs from trusted
registries, supplies internal paths, constructs `Config`, and rejects unknown
fields/unsupported operations. Choose one preset operation name consistently;
the drafts use both `backtest_run` and `backtest_preset`.

Acceptance: a synthetic request produces the exact intended config; forbidden
paths, releases, keys and invalid budgets are rejected before data access.

### 2. Separate protected execution artifacts from shared publication

Existing result HTML includes the full engine config and direct links to
`equity.parquet` and `trades.parquet`. The inventory helper returns full paths
and one entry per partition. Copying a run folder to shared results would
expose protected artifacts and create excessive agent output.

Evidence: [report settings/links](../../backtester/results_report.py:75),
[full config attachment](../../backtester/results_report.py:95),
[partition inventory](../../scripts/backtester_inventory.py:75).

Required decision: allocate a protected job workspace for caches, bars,
candidates, trades and equity. A dedicated publisher emits only allowlisted
metrics, original filenames/hashes, bounded aggregates, safe HTML and plots.
Regenerate shared HTML links; do not publish engine folders wholesale. Logs
and exception output need the same bounded publication rule. Bound aggregate
table cardinality, report bytes, policy rows and plot density as well as raw
diagnostic rows.

Acceptance: shared reports have no protected-file links, raw tables, arbitrary
configuration paths or unbounded traces; every permitted linked artifact exists.

### 3. Validation gates need an actual lifecycle and enforcement point

The requirements call for mandatory preflight/postflight and block usable
publication on critical failures. `run()` currently inventories sources,
prepares data and evaluates policies without those hooks. A `valid` trade
flag is narrower than the new suite.

Evidence: [run orchestration](../../backtester/run.py:16),
[trade validity](../../backtester/replay.py:83).

Required decision: job lifecycle must distinguish execution completion from
validation and publication. Suggested states: queued, claimed, preparing,
preflight, running, postflight, published, failed, cancelled. A completed
diagnostic run can publish a failure summary without being marked usable.
Define required checks and tolerances per operation, warning treatment, and
how `unavailable` blocks a required check. Bind validation to data/config/release
hashes, and invalidate evidence when any of those change.

Acceptance: a synthetic timing or lineage failure blocks usable publication;
the compact failure report remains accessible.

### 4. Contract identity and source-content provenance are incomplete

The engine derives vintage labels from `old_sessions`/`new_sessions` or the
archive folder name. These are not actual delivery contracts. A missing
manifest is currently substituted with `{}`; source identity includes prepared
file path/size/mtime/row count and manifest hash rather than prepared-content
hashes. The new requirements require exact original filenames, contracts,
parent chains and hashes.

Evidence: [source inventory](../../backtester/data.py:36),
[missing-manifest fallback](../../backtester/data.py:41),
[source identity](../../backtester/data.py:58),
[identity method](../../backtester/data.py:170).

Required decision: versioned trusted manifests with explicit contract segments,
original filenames/hashes, prepared-partition hashes and parent relationships.
Hash at ingestion/preparation, retain immutable artifacts, and define verification
on reuse without repeatedly hashing the whole archive. Keep unknown ownership
explicit and prevent it passing a contract-alignment gate.

Acceptance: a run ID resolves through bars/partitions to original filenames;
inconsistent or missing manifests cannot pass provenance validation.

### 5. Rollover flat-position requirement conflicts with current replay

Requirements say positions must be flat at the handoff. Current replay marks
a position unresolved at a vintage boundary rather than executing a declared
close. Its unresolved-position branch then blocks later signals for the rest
of that policy replay. This is conservative data handling, but differs from
the proposed policy of closing before the handoff and restarting on the new
contract.

Evidence: [vintage-boundary outcome](../../backtester/replay.py:78),
[unresolved occupancy](../../backtester/replay.py:112).

Required decision: an explicit executable flatten deadline before each cutover,
close-price/slippage convention and failure behavior when no eligible tick
exists. Decide whether a coverage failure invalidates the full run or an
explicit segment. Do not silently reset an unresolved real position to flat.
Record the boundary and next-contract warm-up separately.

Acceptance: a synthetic open trade closes according to the declared old-contract
rule; a missing executable close produces an explicit failure, and the behavior
for subsequent segments is deterministic.

### 6. On-demand queue and task permissions are underspecified

The draft mentions locks and a bounded queue drain. It does not define atomic
claiming, task-run permission for the caller, recovery after a crash, or how
pending jobs are awakened if submissions arrive while a task is already busy.
A successfully invoked task is not evidence that a particular job completed.

Required decision: protected fixed task action/runtime/interpreter/working
directory and dependencies; permission to run the named task without editing
its action or runtime; atomic submission/claim; idempotent job IDs; heartbeat,
lease and recovery; cancellation; and a queue drain/retrigger protocol that
cannot leave requests stranded. Define result/status write permissions separately
from the agent's request-write permissions. Do not import plugins or settings
from agent-writable locations into the broker process.

Acceptance: simultaneous submissions, repeated invocations, a crashing worker
and a late submission all reach a defined terminal state without duplicate
execution or abandoned queued jobs.

## Priority 2: resolve while building the adapters and audit jobs

### 7. Imported bar sources have no end-to-end execution adapter

The protected runtime describes bars made from ticks, while requirements allow
imported source volume/tick bars. The existing source-bar builder groups those
rows, but its row references are not execution-tick indices. Its outputs do
not yet feed `backtester.run`.

Evidence: [source-bar integration limitation](../source_bar_aggregation.md).

Required decision: distinguish `tick_tape` from `source_bars` and volume
threshold aggregation from grouping N source rows. Require a compatible tick
tape ID for exit replay of imported OHLC bars. Define timestamp/sequence mapping
and fail ambiguous joins. An independent build-only job can work before that
execution adapter is complete.

### 8. Standalone module jobs need typed artifact handles

`prepare()` currently constructs tick caches, bars and strategy signals together.
The planned separate `build_bars` and `generate_candidates` jobs need explicit
inputs/outputs and reuse identities. `run()` calls `prepare()` even in report-only
mode, which can recreate preparation if the cache is absent.

Evidence: [preparation](../../backtester/data.py:78),
[report-only orchestration](../../backtester/run.py:29).

Required decision: broker-generated artifact IDs with type, parents, contract,
coverage, schema and release/config hash. Define bars-only, candidates-only,
execution and reports-only adapters. A reports-only job should not launch
preparation or replay when an artifact is missing; return the missing-artifact
diagnostic instead.

### 9. Correct the architecture's exit-analyzer arrow

The guarded-runtime diagram places execution before the optional analyzer.
The backtester architecture and code correctly have the analyzer propose
policies and call execution. Statistics return to the analyzer for comparison.

Required flow: broker -> optional analyzer -> execution -> per-policy statistics
-> analyzer; preset goes directly to execution. Shared publication occurs after
validation. Add separate preflight/postflight nodes in the next diagram revision.

Evidence: [run's evaluator callback](../../backtester/run.py:73).

### 10. Distinguish current statistics from planned capability

The guarded-runtime prose includes benchmark comparison within the existing
statistics contract; the backtester architecture explicitly says benchmark
inputs are unimplemented. AUC is listed as a safe aggregate but the execution
backtester currently has no ML-prediction input. Holding-time buckets are in
seconds rather than entry/exit bar offsets; required extrema and complete P&L
histograms also need additional report jobs.

Evidence: [statistics output](../../backtester/results.py:187),
[benchmark/ML limitations](../../backtester/results.py:231),
[trade schema](../../backtester/replay.py:13).

Required decision: a capability inventory (`implemented`, `planned`,
`unavailable`) returned by the broker. Add global stable bar IDs or a reliable
session/bar-key mapping to compute entry-bar offset and first-bar distributions.
Implement benchmark and ML diagnostics only with their required inputs.

### 11. Invalid but measurable exits need separate reporting populations

An exit can have a price/P&L yet be invalid because of time delay or tick gaps.
Current replay includes all measurable closes in diagnostic P&L and win rate,
while marking the policy ineligible and disabling return inference. New
requirements need reconciled accepted/excluded/censored populations.

Evidence: [validity and measurable P&L](../../backtester/replay.py:83),
[closed population](../../backtester/replay.py:121).

Required decision: return diagnostic-all, valid-measured and unresolved/invalid
counts/totals explicitly. Keep the current eligibility information. Define which
population every chart and ranking uses; no silent removal of losing outliers.

### 12. Job budget/recovery and experiment identity need separate rules

Search time is checked between batches; preparation/report generation and
in-flight workers can exceed it. The gateway promises bounded jobs but has no
job-wide watchdog, disk quota or RAM limit. Engine identity excludes workers,
batch size and evaluation/time budgets, which is useful for some cache reuse
but insufficient as the whole experiment/search identity. Search rebuilds its
state and can reuse cached policy results; a formal broker resume protocol is
still needed.

Evidence: [identity exclusions](../../backtester/config.py:160),
[search budgets](../../backtester/search.py:19),
[worker shutdown](../../backtester/workers.py:30).

Required decision: separate immutable execution identity, search-procedure
identity and attempt/job identity. Preserve all budgets and attempted trials.
Define soft batch limits versus job-wide hard limits and cleanup/resume after
termination. Publishing results must record whether the search exhausted its
domain, stopped by heuristic or hit a resource budget.

## Recommended implementation order

1. Canonical request, dataset, artifact, validation and publication schemas;
   exact operation names and a broker adapter using synthetic inputs.
2. Protected job workspace and safe publication writer, with queue/recovery
   protocol and capability discovery.
3. Provenance and contract map, inventory/lineage jobs and preflight enforcement.
4. Preset execution with postflight, entry-price/bar-offset audits and corrected
   declared rollover behavior.
5. Optional exit search through the same validated execution path, retaining
   trial/attempt identities and bounded surface reports.
6. Imported source-bar -> tick-tape adapter, benchmark inputs and other planned
   capabilities as individually tested additions.

This audit does not require replacing the existing execution engine. Most work
belongs in adapters, provenance, validation and publication. The rollover and
artifact/timing extensions need targeted engine changes with synthetic
regression tests.
