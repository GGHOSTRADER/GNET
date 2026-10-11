# Builder handoff prompt — guarded research runtime

Copy the prompt below into the builder's chat. It directs implementation of
the documented roadmap; this file does not create a worktree or deploy anything.

---

Implement GNET's guarded research runtime and backtester interfaces using the
existing engine and the linked specifications. Python performs data processing;
the agent submits typed jobs and reads compact results. Work through the phases
in order, deliver working code and evidence, and update the roadmap's status.

## Checkout and worktree

Authoritative starting checkout:
`C:\Users\g_med\python_new\GNET`.

The dedicated guarded-research worktree has not been created. The existing
`C:\Users\g_med\.codex\worktrees\crossover-context\GNET` is from earlier
feature research and does not contain the current backtester modules.

Create/reuse a suitable isolated worktree on `codex/guarded-research`, using
the Codex managed-worktree tools when available. Before creation, verify that
the current engine, strategies, tests and required documents are included in
the base commit: they were untracked at handoff. Prepare a narrowly scoped
source/documentation snapshot if necessary; preserve unrelated user changes
and verify dependencies. Do not use `git add .`, stage raw data/results, copy
the whole repository, or assume uncommitted files will appear in a new worktree.
Use an explicit ref containing that snapshot rather than the remote default
branch. Report the actual returned workspace path and use it for all edits/tests.

## Read these documents first

All paths below are relative to the authoritative checkout or the verified
builder worktree. Read `AGENTS.md` and applicable nested instructions first.

1. `documentation/guarded_research_implementation_phases.md` — phase order,
   dependencies, deliverables and completion checks.
2. `documentation/guarded_research_runtime_architecture.md` — account/job/data
   boundaries and protected runtime deployment.
3. `documentation/research_interfaces_and_trade_viewer.md` — canonical jobs,
   request/result/artifact interfaces, candle/line viewer and filters.
4. `documentation/research_validation_and_provenance_requirements.md` —
   timing/continuity/execution audits, exact source filenames, contract identity,
   revision naming, rollover and publication gates.
5. `documentation/backtester_architecture.md` — existing engine boundaries.
6. `documentation/reports/guarded_backtester_integration_audit_2026-10-02.md`
   — unresolved integration gaps and code references.
7. `documentation/guides/BACKTESTER_AGENT_GUIDE.md` — current operating rules;
   required before running an offline job.
8. `documentation/backtester_file_contract.md`,
   `documentation/source_bar_aggregation.md`,
   `documentation/backtester_strategy_inventory.md`,
   `documentation/backtester_data_inventory.md`, and
   `documentation/backtester_reports.md` — relevant formats and inventories.

The phase roadmap controls delivery order. Preserve versioned schemas and
document any genuine conflict before making a material change to the contracts.

## Strict market-data access rule

Do not directly open, print, scan, parse or load real trading/trades, bars,
ticks, feature matrices or large generated tables into agent context. They
consume excessive tokens and can overwhelm the machine. This includes CSV,
TXT, Parquet and embedded tables in generated reports.

Do not use broad `rg`, recursive file dumps, `Get-Content`, `head`, dataframe
prints or Git diffs over market-data/output directories. Scope searches to
source code, tests, configuration and documentation. Locate sources only by
names, sizes, timestamps and approved catalog metadata.

Development uses small synthetic fixtures. Before executing any existing test,
inspect its code/config to establish whether it reads real archives; do not
blindly run the entire suite. An inventory/summary script may read permitted
metadata but must return bounded output, not full partition inventories.

Any later real-data run requires explicit user authorization for the dataset
and bounded scope. Processing happens through the protected broker or an
explicitly authorized summary job. Return only counts, coverage, metrics,
validation evidence and allowed chart/report references. Creating the broker
does not itself authorize a historical sweep or a raw-data migration.

## Implementation expectations

Reuse `backtester/`, `strategies/` and relevant `scripts/` adapters. Keep the
independent-entry `exit_module/` distinct from position-aware `backtester.run`.
The current registered primary strategy is `ma_cross`; do not claim the planned
five-strategy inventory or ML training adapters already exist.

Implement schema validation and ID resolution before execution, then queue/
recovery, protected-workspace abstraction, safe publication and provenance.
Connect standalone bars/candidates, mandatory validation gates, preset replay,
rollover behavior, statistics, viewer and optional exit sweep in roadmap order.
The engine takes internal paths; broker requests accept trusted IDs instead.

Retain exact original filenames/hashes, actual contract/month or continuous
series identity, price vintage, coverage and all parent artifact IDs. Revised
datasets have new immutable names containing `revised_revNN`; validation status
is separate from revision. Never silently overwrite prior datasets/results.

The trade UI must show candles or a price line, actual entry/exit markers,
signal markers and a duration lane; distinguish winners, losers, breakeven and
unresolved trades with color plus labels/styles. Include combined date/outcome/
gross-or-net P&L filters, stable sorting, pagination and selected-trade details.
Default outcome classification uses net P&L. Fetch bounded broker windows;
never embed the full trade history in browser HTML/JavaScript.

Preserve exact tick sequence order, completed-bar availability, per-policy
position occupancy, three exit barriers and declared fees/slippage. Current
research cost is $6.48 per one-contract ES round trip, recorded in each run.
Use synthetic regressions for timing, rollover, gaps, equal timestamps,
occupancy and serial/parallel determinism. Do not force platform-replay equality
or change outcome populations silently.

Develop Windows setup/deployment scripts and verify them without executing
account creation, ACL changes, task registration or real-data migration until
that OS operation is explicitly authorized. Deploy protected reviewed releases;
agent-editable development code must not become the broker's execution source.
Leave live trading services, model deployment and terminal hotkeys untouched.

## Working and delivery rules

### Unattended overnight execution

The user may be asleep and unavailable. Continue authorized code development,
documentation and synthetic testing without requesting routine design choices.
Use the contracts and reasonable documented defaults. Complete all independent
work that can be done within the available workspace permissions.

Implement and test Windows provisioning/deployment scripts as code, but defer
their actual account/ACL/task installation, credential entry and real-data
migration. Use a synthetic/local launcher to test broker logic; do not claim
that mock execution establishes Windows account isolation.

If sandbox/app approval is required, do not bypass it or wait indefinitely.
Record the exact blocked operation and continue independent authorized work.
Do not mark dependent phases complete. If no useful independent work remains,
save the current progress and report the blocker clearly. Lack of a user reply
is not approval.

Establish and verify the source snapshot and builder worktree before the
unattended run if possible. If that setup needs unavailable permission, record
it as a prerequisite blocker rather than dropping untracked code or using the
older research checkout. The user has not authorized weakening global app or
Windows permissions to eliminate prompts.

At the end, provide completed phases, tested commands, actual worktree path,
remaining blockers and a short list of operations requiring the user's return.
Keep a durable progress note in the builder worktree so another turn can resume.

Start by establishing the source snapshot/worktree, read the contracts, then
implement phase 1. Continue through executable phases and applicable checks;
do not stop at another architecture proposal. Keep phase status current and
report any dependent work blocked by missing authority or concrete evidence.

Use `.venv` from the appropriate checkout or a documented isolated environment,
not base Python. Use precise patch edits, preserve other work, and follow
AGENTS.md import/definition-inventory checks after structural changes.

For each completed phase deliver:

- Actual workspace/branch and changed source locations.
- Working commands using synthetic inputs and bounded outputs.
- Relevant test results and resolved audit findings.
- Updated contracts/runbooks/examples where interfaces changed.
- Remaining capability gaps and the next phase.

Report implementation, tests, Windows deployment and real-data validation
separately. Never mark a phase complete because its specification is written.

---
