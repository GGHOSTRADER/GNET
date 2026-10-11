# Fast inventory client — October 11, 2026

Installed client: `gnet-client-v75-fast-inventory-r1`.
Broker: `guarded-v43-native-browse-fix`.
Manifest SHA256: `c4e1485b709d9a72951dc275f14dfe2d28de93d764e8afcd8802a21bc38819ea`.

The catalog reuses bounded JSON summaries in browser local storage, keyed by
broker release and the exact catalog query. At most 40 summaries are retained.
Only metadata-only broker catalog responses are cached. No raw market data is
opened or cached by this change.

Summaries younger than 60 seconds render without scheduling a catalog job.
Older summaries render first, while a fresh metadata job runs. A failed refresh
retains the old summary and displays its refresh failure. Explicit Refresh
inventories clears the catalog cache and requests fresh metadata. Trash changes
invalidate it. A different broker release cannot reuse old summaries. Disabled
or unavailable browser storage falls back to fresh requests.

Received-source rows render immediately after public receipt metadata arrives;
they no longer wait for scheduled availability checks. Availability is refreshed
in the background and the rows are reconciled afterward. Protected broker action
checks remain authoritative, including permission and retirement checks.

This is a client optimization. A first uncached catalog query still needs a
broker job. Availability checks still run in the background. It does not yet
replace these jobs with a broker-published consolidated snapshot endpoint.

All 130 browser tests passed without snapshot updates, including five new cache
and latency-path regressions. Existing inventory screenshots passed unchanged.
The client was installed and restarted on port 9040 after the full gate passed.

Receipt and browser evidence:
`.test_artifacts/release-gates/gnet-client-v75-fast-inventory-r1-20261011T063131806Z/installation-receipt.json`.
