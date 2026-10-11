# V38 corrected-feature development comparison

Installed broker V38/client V42. Approved real @ES five-minute source; retained
September 11–October 8 development sessions. No final holdout or live promotion.

## Fixed settings and identities

Restored varying Amihud after correcting the units-dependent constant test.
Excluded only parkinson_vol_30 based on its 0.94818 correlation with
parkinson_vol_15 in the first purged training prefix. Twelve features selected.
Same XGBoost settings as the previous eleven-feature experiment: seed 42,
50 rounds, depth 2, learning rate 0.05, three purged walk-forward folds,
1% embargo, threshold 0.5 and RFE disabled. Dataset population remained 162
eligible samples, 121 scored out of sample and 41 initial unscored samples.

- Review: `job-20261010T011513Z-c2c63500587b44b28c29b1d8ca1f9788`.
- Training: `job-20261010T011518Z-d6cdd47ce8eb44cdafeb70b9eb1971f6`.
- Scoring: `job-20261010T011524Z-8309fb63aabb4595961edb59ed080d82`.
- Replay: `job-20261010T011531Z-84bcb3c4868b434a8052efecb27bc330`.
- All four jobs published usable results. Old artifacts were preserved.

## Results

| Metric | Previous 11 features | Corrected 12 features |
|---|---:|---:|
| OOS accuracy | 44.63% | 41.32% |
| OOS ROC AUC | 0.4186 | 0.4462 |
| Approved recorded trades | 54 | 64 |
| ML-approved net P&L | -$700 | -$900 |
| ML-approved maximum drawdown | $850 | $950 |

The score-matched primary baseline remains 121 trades, -$750 net and $850
maximum drawdown. Full eligible primary remains 163 trades, -$1,150 net and
$1,200 maximum drawdown. The corrected run underperformed both the previous ML
run and the matched primary in net P&L/drawdown. Correctly admitting a varying
feature does not establish predictive value or improve the model automatically.

The training report includes fit gain importance and per-fold held-out permutation
diagnostics. Amihud has nonzero gain and positive reported permutation values;
these diagnostics do not overturn the aggregate trading result or justify further
selection using the same validation outcomes without recording another experiment.

## Scope and remaining gates

These are development comparisons of recorded native TS positions. They do not
rerun the TS engine with rejected entries removed or recover unobserved candidates.
Provider-adjusted continuous prices remain historical simulation. Declared
round-trip costs in this export are zero; P&L does not include independently
verified commission/slippage. No new real final session, final evaluation, CPCV,
researcher-password acceptance or isolation certification was completed.

Public receipts: `.artifacts/v38-real-ts-model-comparison.json` and the four
`v38-real-ts-*-report.json` files. Reports are available through the installed
Command Center under their exact job IDs.
