# Named-source read-only clock review evidence

Follow-up: dedicated-worktree implementation has resumed with hash-bound clock
resolution and bounded continuity diagnostics. The final synthetic guarded
regression passed 438 tests. V5 is prepared but uninstalled; real continuity
and registration remain pending. The original observation below is preserved.

## Delivery and provenance

User supplied the bounded JSON from the administrative isolated-v4 source review.
The agent did not read raw records. Source and all reviewed parents stayed
unchanged during that run. No migration, calendar/dataset registration or
backtest occurred.

- Original source: `C:\Users\g_med\python_new\GNET\historical_vp\raw\ES\tick\test_data.txt`.
- Size: 28,511,886 bytes.
- Source SHA-256: `545ae113f151100127d0ed862ff774ca7968dd79a783abaeeb8230ba2c63973a`.
- Original companion SHA-256: `ca5ab0459e6ac11e8551f4af15f2e0f3a31fdfbdfefc14f014d5b77ca66820dc`.
- Calendar review ID: `ESU26__2026-09-16_to_2026-09-18__review_v1`.
- Calendar SHA-256: `523ac91fea557f2b8213e16b0cc0624e1d522cc4dbf12a45e5ba33cb827f7fe8`.

## Actual result

The installed v4 default policy selected America/New_York. That profile failed
at physical source row 2, before any accepted events. Its generic redacted
error does not independently identify every cause, but America/Chicago passed
the same full-source contract and session-scope checks against the same calendar.
The unique passing calendar-alignment profile is America/Chicago.

| Scope | Accepted events under the Chicago profile |
|---|---:|
| 2026-09-16 | 126,771 |
| 2026-09-17 | 83,950 |
| 2026-09-18 | 5,271 |
| Total | 215,992 |

Aggregate UTC coverage is `2026-09-15T22:00:00+00:00` through
`2026-09-18T13:29:58+00:00`. There are 168,741 equal-timestamp events and 880
same-session gaps longer than 30 seconds. These are summary diagnostics, not
raw records. Equal timestamps retain source sequence. Gap counts alone do not
establish missing ticks or complete sessions; liquidity, halts and coverage
require a separate audit.

The receipt's `source_contract_review_passed` is false because its preferred
New York policy failed. `complete_sessions_verified`,
`source_timestamps_verified`, `ready_for_real_data_acceptance`,
`calendar_registered`, `dataset_registered`, `data_migrated` and `backtest_run`
remain false. `raw_records_returned` is zero.

## Correction and remaining work

The earlier inference that this futures export's Exchange mode implied New
York was incorrect for the reviewed delivery. Withdraw that interpretation
for this source. The original chart mode remains Exchange; do not ask the user
to change the chart or re-export. Do not rewrite the original companion or
silently infer a universal mapping for every product from this receipt.

The next code correction must bind the reviewed source-clock resolution to
this exact source/companion/calendar evidence and verify parent hashes before
use, rather than silently accepting another file or overwriting provenance.
Retain the failed New York profile as evidence. Calendar alignment is not
independent certification of historical platform timestamps or full coverage.
Then complete a bounded continuity/partial-session audit. Calendar/dataset
registration and ingestion remain separate, explicitly authorized operations.

Implementation remains in
`C:\Users\g_med\.codex\worktrees\guarded-research\GNET`, branch
`codex/guarded-research`, latest saved commit `f802498`. Protected v4 remains
immutable and installed synthetic acceptance passed. Automatic approval review
was unavailable due to its usage limit, so the clock consumer correction has
not been applied or tested. This durable evidence is saved in the writable
original checkout; it does not change deployed code, raw data or either Git
index. Resume the dedicated-worktree implementation when approval review is
available. Do not mark the real-data phase complete from this diagnostic pass.
