# V38 publication recovery component acceptance

Four injected process-stop cases passed against the exact V38 packaged gateway,
queue, publication and JSON I/O code in 1.08 seconds. Inputs and outputs were
fabricated. No installed task, protected configuration, ACL or real data changed.

| Stop after | Complete public result before recovery | Computation rerun |
|---|---|---|
| Private checkpoint report | No | Yes, incomplete checkpoint |
| Private checkpoint result | No | No |
| Public report | No | No |
| Public result commit, before queue finish | Yes | No |

Each case released the claim handle through a simulated process-stop exception,
expired its lease and recovered the same job on attempt 2. The recovered queue
state was published, the result usable, the fabricated count correct and the
report intact. Complete private checkpoints avoided rerunning the handler; a
committed public result completed queue bookkeeping without recomputation.

Test file: `.artifacts/test_v38_publication_crash_windows.py`.
Three existing synthetic tests also passed against packaged V38 in 0.29 seconds:
live-worker fencing and stale-owner commit rejection, queued/running cancellation,
and bounded immutable publication with unsafe-link/output rejection. Nine unrelated
cases were deselected; no full-suite claim is made.
The first sandbox attempt failed before injection because Windows hard-link
creation was denied. The native run outside the sandbox passed all four tests.
This is fault injection at component boundaries, not an installed broker process
termination, machine reboot, power failure or disk-failure acceptance.

## Remaining work

- Installed interruption and active cancellation now passed under V38; see the
  installed acceptance section below. Broader power/disk/reboot recovery remains
  outside this test's scope.
- Complete broader file/ancestor and account-policy isolation checks, native
  researcher-password acceptance and the combined certification record.
- Prepare a separate approved real source strictly after the October 8 development
  cutoff for final evaluation. Current development outcomes cannot be reused as
  an untouched final holdout.
- Full counterfactual TS engine replay and live model promotion remain separate
  implementation gaps. `isolation_certified` remains false.

## Installed V38 acceptance

The current matching client prepared the existing fabricated 16-event archive:
eight two-tick bars and two MA-cross candidates. All three preparation jobs
published successfully. No real source was used.

Recovery job `job-20261010T033357Z-91b2cd1363854877b7ec3bcaa5fa45b1`
ran through the installed ResearchRun task. The ordinary researcher controller
verified the isolated workload and exact task instance before stopping that
instance. Attempt 1 exposed no public result and no usable partial output.
After the 32-second lease wait, the same job recovered on attempt 2 and published
a usable, validated result: 16 tested policies, zero failed policies.

Active cancellation job `job-20261010T033446Z-cc67e78a625643d7ab41780cb70b9488`
was observed running before cancellation. It ended cancelled, with no usable
artifact, and the expected cancellation error. The helper's acceptance checks
passed.

Receipts: `.artifacts/v38-recovery-fixture.json`,
`.artifacts/v38-installed-recovery.json`, `.artifacts/v38-interrupted-output.json`
and `.artifacts/v38-active-cancellation.json`. V38 controller copies preserve
the V36 top-level definition inventory; Python compilation and PowerShell parsing
passed. The sandbox blocked exchange publication; the ordinary-user execution
outside the sandbox succeeded. No accounts, ACLs, task definitions, installed
runtime or real data changed. This closes installed interruption and cancellation
acceptance, not full isolation certification or real final evaluation.
