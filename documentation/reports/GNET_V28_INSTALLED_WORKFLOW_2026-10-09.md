# Installed v28 workflow acceptance — October 9, 2026

Broker v28 and client v30 are installed. The deployment audit passed with a
complete metadata scan and zero findings. The synthetic research pipeline passed;
overall acceptance remains incomplete because the separate trade viewer correctly
rejected a producer missing from the reviewed custody policy.

## Synthetic pipeline

The fixture has 300 fabricated bars and 70 closed positions. No real market data
was read or trained. Its exact review had already been activated locally.

| Operation | Result | Job |
|---|---|---|
| Source review status | Published | `job-20261009T110228Z-3b754942b4c64e63a537da92eff656c7` |
| Source admission | 300 records | `job-20261009T110232Z-1f2ab87416354ea7bc0cc89279c23e4e` |
| Primary validation | 70 closed positions | `job-20261009T110234Z-efc2d0e30a874c50bcc772f4dee9b94e` |
| Primary targets | 35 positive, 35 negative | `job-20261009T110236Z-bee7313c1bb94c6d85cddc73ab8ff9a5` |
| Feature dataset | 57 eligible, 13 excluded | `job-20261009T110241Z-82a3f9ef3550452e8c2bd5b062ed58ca` |
| Feature diagnostics | 13 canonical inputs; 11 constant | `job-20261009T110243Z-2e8d4a4cc8a144e2a826dce5275aa606` |
| Feature review | 2 variable inputs selected | `job-20261009T110255Z-c5a76eae695d44f0830723df76a8a3a9` |
| XGBoost training | 2 walk-forward folds; 38 OOS scores | `job-20261009T110302Z-3137f0c597c7437ba8e7782e36c8cfdf` |
| Model scoring | 38 reject, 0 approve, 19 unscored | `job-20261009T110352Z-b1e717526a954b9c954ddee7fb69373c` |
| Recorded-position replay | Published; exact source/target parents accepted | `job-20261009T110357Z-53062042c08243f285f1b53e68969b4c` |
| Native trade viewer | Blocked: `custody_producer` | `job-20261009T110359Z-f424448c1e46417a9cbf5a2ff4f17a7d` |

Selected inputs were `vwap_distance` and `minutes_since_open`. Classification
accuracy was 0.5; ROC AUC was approximately 0.474. These synthetic results are
not evidence of market performance. Purge/embargo were enabled, with zero
removals for this nonoverlapping fixture. CPCV was not run.

Replay filters recorded primary positions. No counterfactual TradeStation engine
run or final holdout evaluation was performed.

[Training report](http://127.0.0.1:9040/reports/job-20261009T110302Z-3137f0c597c7437ba8e7782e36c8cfdf/model_training.html)
and [replay report](http://127.0.0.1:9040/reports/job-20261009T110357Z-53062042c08243f285f1b53e68969b4c/ml_replay.html)
are served by the installed command center.

## Remaining acceptance

- Review the exact synthetic fixture producer for custody before rerunning its
  native trade viewer. Do not remove the policy check or overwrite failed evidence.
- Exercise native recoverable Trash authentication under the Windows researcher
  identity and complete both-identity isolation acceptance.
- Reconnect Codex to use the newly configured MCP client; this chat's existing
  connection remains pinned to the previous release.
- Complete actual TradeStation platform and real-data acceptance separately.

Refresh the command center with Ctrl+F5. Stable launcher:
`C:\Users\g_med\python_new\GNET\.artifacts\client-delivery-installed\Open-GNETResearch.ps1`.
