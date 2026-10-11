# Immediate metadata polling — October 11, 2026

Installed client: `gnet-client-v76-immediate-metadata-poll-r1`.
Broker: `guarded-v43-native-browse-fix`.
Manifest SHA256: `5729931f6126e72ba15376cedbc6a462b94e064bf371407fd4e8b44bb1a8c17f`.

Pipeline, source inventory, review, dataset chart, native primary viewer and
receipt admission now check job status immediately after submission. The
existing 500/750 ms wait applies only to subsequent checks. Pending-job backoff,
bounded publication retries, exact identities and broker enforcement remain.

Feature inventory responses are reused in a bounded in-page cache for 60 seconds,
keyed by broker release and the complete parent payload. Concurrent identical
queries share one promise; failures are removed so retry remains possible.
Fresh progress and computation results are not cached by this change.

The full suite passed 170 tests without snapshot updates. The training screen's
three fabricated-response readiness samples were 323, 296 and 294 ms, compared
with the previous 2,052 ms slow sample. All repeated readiness scenarios were
below 348 ms in this run. Warm inventory reloads measured 166–189 ms.
Regression ceilings are now 1,500 ms for screen readiness and 750 ms for warm
inventory readiness. The 2,000 ms individual fabricated API ceiling is unchanged.

The installed read-only HTTP probe also passed. These timings distinguish local
client responsiveness from protected worker scheduling and real computation.
They do not certify full installed research execution latency.

Receipt and complete browser/performance evidence:
`.test_artifacts/release-gates/gnet-client-v76-immediate-metadata-poll-r1-20261011T065124038Z/installation-receipt.json`.
