# Real TradeStation development workflow acceptance

Run on October 9, 2026, America/New_York (job IDs use October 10 UTC).

Installed broker: `guarded-v36-public-evidence`; client: `gnet-client-v40-public-evidence-r1`.
Source: `ts-20261009132443-414197210-926725058`, @ES five-minute bars.
All computation used the installed typed client and protected scheduled broker.
The agent received bounded public metadata and metrics; no private rows or models.

## Passed stages

- Automatic review: timestamps, coverage and calendar passed; 5,520 bars across
  20 complete sessions through October 8. The unfinished October 9 session was
  excluded (229 bars); original export retained unchanged.
- Exact local Administrator source review activated. Initial registration used
  the pre-template policy ID and failed closed with intake_policy_pending.
  Registration using the activated deterministic review/policy ID passed.
- Primary source: 170 recorded closed positions; seven outside retained scope
  excluded. Exact MA-cross signals and bar parent independently validated.
- Primary labels: 163 eligible targets, 70 positive and 93 negative.
- Feature join: 162 samples, 70 positive and 92 negative; one warm-up exclusion.
- Correlation/variance diagnostics used first training prefix only (41 samples).
- Feature review retained 11 canonical features, omitting Amihud (very small
  original-unit variance) and 30-bar volatility (0.948 correlation with 15-bar).
- XGBoost: 50 rounds, depth 2, learning rate 0.05, seed 42, RFE disabled;
  three chronological folds, 1% embargo, fixed 0.5 score threshold.
- 121 out-of-sample scores; 41 initial samples unscored. Purge was enabled and
  removed zero overlapping samples. Embargo counts were 1, 1 and 0. No CPCV.
- Recorded native ledger comparison passed with exact model/prediction parents.

## Results

Accuracy 0.4463; ROC AUC 0.4186; precision 0.3704; recall 0.3774.
These weak development results do not establish predictive value.

| Arm | Trades | Reported net P&L | Maximum drawdown |
|---|---:|---:|---:|
| Full eligible primary | 163 | -1150 | 1200 |
| Score-matched primary | 121 | -750 | 850 |
| ML-approved subset | 54 | -700 | 850 |

Exported round-trip cost is zero. Recorded fills, adjusted continuous-series
simulation and declared costs are the research basis. Engine commissions,
slippage configuration, Bar Magnifier and platform fill-clock semantics remain
unverified. This filters recorded executions; it does not rerun the TS engine
with different position occupancy or recover unobserved candidates.

## Public evidence

- Training: `job-20261010T002749Z-e86af5447e5a4fa4aad16a5199dd4a16`, model_training.html.
- Features: `job-20261010T002704Z-b1196c95e4874c0e8fab0b828ca2e78f`, feature_analysis.html.
- Scoring: `job-20261010T002805Z-07066ef1df8b4a8b8602eb1524bafa4b`, model_scoring.html.
- Replay: `job-20261010T002816Z-09304e8e72394ef9a5bc100ca51b99c9`, ml_replay.html.
- Bounded receipts/reports saved under `.artifacts/real-ts-*-report.json`.

## Remaining gates and follow-up

- Separate untouched, nonoverlapping final source, reservation, exact model
  freeze and one-use final evaluation. This development export cannot be reused
  as a newly untouched final archive. No final evaluation occurred.
- Full acceptance under both Windows identities remains separate.
- Browser chart interaction and complete manual GUI workflow were not verified
  by this typed-client run.
- Feature diagnostics currently call variance <=1e-12 constant in original
  units. Amihud's variance is about 6.46e-22; this alone does not prove it is
  constant. Review unit-aware near-constant detection before generalized feature
  selection. Current omission is a declared baseline choice, not a proven
  absence of information.
- Per-import local Administrator review remains a usability boundary to revisit;
  automatic deterministic checks passed without manual row inspection.
- Guarded client/source diagnostic scripts are orchestration helpers, not a
  replacement for protected production code or proof of UI acceptance.
