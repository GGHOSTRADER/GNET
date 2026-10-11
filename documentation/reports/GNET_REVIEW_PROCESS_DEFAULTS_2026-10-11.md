# Source review process defaults — October 11, 2026

Installed client: `gnet-client-v74-review-process-defaults-r1`.
Broker: `guarded-v43-native-browse-fix`.
Client manifest SHA256: `7ba219a9b0a0caf5bd29e220af92991d3a0cc75d57b63f38ae5d5122660ede31`.

The review page selects compatible requested processes from source metadata.
Individual 1-tick inputs default to VP features and bar building. Recognized
bar inputs default to primary research, bar features and training. The existing
captured-export policy restriction takes precedence: only bar features and
training are selectable. Unknown types select nothing. Removing a process is
preserved when automatic validation refreshes the same source and review basis.
An empty process selection cannot submit a draft.

Chart confirmation now names the intended symbol, interval and session.
Research authorization explicitly grants use for the selected processes.
Neither confirmation is automatically checked. Captured evidence continues to
hide the unsupported platform/fill attestations and submit those flags as false.
Defaults do not activate policies, grant permission or start training.

Seven additional fabricated-response behavior tests cover source types, outgoing
process lists and preserved user choices. All 125 browser tests passed without
snapshot updates in the final installation gate. Review screenshots were
inspected at 1440, 768 and 390 pixels. The installed client restarted on port 9040.

Installation receipt and full browser evidence:
`.test_artifacts/release-gates/gnet-client-v74-review-process-defaults-r1-20261011T062350189Z/installation-receipt.json`.

This is browser/client acceptance. Protected source admission and installed
end-to-end research acceptance retain their separate gates.
