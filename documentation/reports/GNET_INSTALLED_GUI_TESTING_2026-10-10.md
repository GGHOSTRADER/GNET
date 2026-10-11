# Installed GUI continuation

Scope: existing explicitly fabricated source
`ts-esu26-30-seconds-primary-2026-07-20_to_2026-07-20-edc7b809cc47`.
Browser controls submitted actual scheduled V42 broker jobs; API responses were
not mocked for this part of the check. No real market data was used.

## Findings and fixes

- Feature diagnostics could show “Published result unavailable” during a gap
  between published status and readable result. The actual analysis subsequently
  proved usable. The client now retries that exact published/404 condition up to
  eight times without resubmitting the calculation, then reports the original job
  ID if the result remains missing.
- Feature sections appeared in order 3.1, 3.3, 3.2. They now follow 3.1, 3.2, 3.3.
- The native export viewer checked only the first transfer-receipt page. It now
  searches bounded advancing pages for the exact export and requests the shared
  500-observation window. Missing receipts remain blocked.

The older synthetic registered fixture has no ordinary-client transfer receipt.
Its export launcher could not be accepted on this fixture. The pagination fix is
covered by fabricated browser tests; fresh native custody-to-launcher acceptance
remains a separate test. Its registered-dataset chart was tested through the GUI.

## Installed observations

- GUI native labeling completed; reloading the browser recovered its saved target
  and usable report: `job-20261011T015209Z-7a457f7d4d64445c873d64c0f290ffdd`.
- GUI feature/target join completed with 57 eligible records:
  `job-20261011T015254Z-239c77a26c3f41c2b03944e2fce3e941`.
- Diagnostics completed after the fix with 19 training-prefix rows, two selected
  variable features and zero constant features:
  `job-20261011T020125Z-b6f094f4c7d7458d83f50b19d759ea47`.
- Feature review was saved by the GUI:
  `job-20261011T020145Z-fd8c6ff3dadc47d78b6532c97e4416f6`.
- GUI XGBoost training completed: 57 samples, two folds, 38 unseen scores, 19
  initial unscored rows, two selected features. Eight rounds, depth two, rate 0.1:
  `job-20261011T020228Z-42812ed85ae2402688554b7494164379`.
- Training report opened with ROC, fold log-loss, native gain and unseen-fold
  permutation analysis. GUI scoring completed with 38 scored, 19 unscored and
  zero approved at threshold 0.5:
  `job-20261011T020309Z-0d628c20e8034633b5edeb3447946370`.
- GUI native recorded-position replay completed with 70 primary positions, 38
  scored/rejected, 19 eligible unscored and 13 feature/label exclusions:
  `job-20261011T020353Z-25f84c9eed724af4b3e3cace75dbcf1a`.
- Dataset chart completed with 300 observations:
  `job-20261011T020048Z-d5d5447264764dc38d6540404d3a9e75`. Local zoom reduced the
  visible window to 150 bars; the slider moved its timestamp range; line mode and
  reset worked. Evidence: `.artifacts/installed-gui-chart-check.png`.

The separate fabricated-response browser suite passed 99/99 in 1.9 minutes,
including publication delay, bounded permanent failure, ordering and older export
lookup. Installed client: `gnet-client-v68-publication-retry-r2`; manifest SHA-256:
`e20b5d070ff0c0094b1801c63d7d99ff3e3d2abaadace703df4de95bccfdfb47`.

Synthetic execution is engineering evidence, not model-quality evidence. Fresh
source approval, native Windows authentication, full isolation and real-platform
acceptance were not certified by this run.
