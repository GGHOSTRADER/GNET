# Research findings

Short, source-linked observations for later experiments. These are descriptive results, not changes to live strategy rules.

## 2026-09-30 — Larger old-dataset logistic and feature-stability replication

- The regularized-logistic and four-test feature-stability procedure was repeated on two point-in-time-correct older datasets: all 11,196 canonical-13 events (9,516 development and 1,680 chronological confirmation) and the 6,444 events with matched canonical-13 + VP32 coverage (5,477 development and 967 confirmation). CPCV(6,2), purging, 1% embargo, chronological separation, and $6.48 round-trip cost were retained.
- The initial unconstrained regularization ranking selected degenerate configurations whose median fold model had zero nonzero coefficients. These were rejected explicitly. Final regularization selection required the median fold model to retain at least 10% of candidate features.
- **Canonical 13:** the nondegenerate full model had development median complete-path AUC 0.4927 and chronological AUC 0.5040. At 0.50, 991 of 1,680 confirmation trades were approved and lost $2,171.68. The quantitative stability rule retained only `ofi_15` and `vwap_distance`; this two-feature subset had development AUC 0.5063, confirmation AUC 0.4965, and lost $2,711.68 on 866 approvals.
- **Canonical 13 + VP32:** the nondegenerate full model had development median complete-path AUC 0.5006 and chronological AUC 0.4878. At 0.50, 604 of 967 confirmation trades lost $2,226.42. The stability rule retained 20 features; that subset improved development AUC to 0.5176 but confirmed at only 0.4997. It lost $1,892.18 at 0.50 and $658.08 on 171 approvals at the development-selected 0.525 cutoff.
- **Decision:** increasing observations did not reveal stable linear predictive information. Feature selection again raised development AUC without producing chronological discrimination, which is consistent with weak/time-varying relationships and selection optimism. Do not promote the full or reduced models. Artifacts: `reports/old_dataset_logistic_stability_2026-09-30/`.

## 2026-09-29 — Quantitative VP feature stability and ablation

- Feature analysis was restricted to the same 1,867-event purged CPCV development sample; the later 330 chronological events were excluded from selection. Each feature was evaluated by validation-fold permutation importance, complete-path leave-one-feature-out AUC contribution, coefficient-sign stability, and univariate validation AUC. The retention rule was fixed before inspection: pass at least three of the four diagnostics.
- In VP32 alone, 13 features passed. The selected subset's development median complete-path AUC increased from 0.5100 to 0.5392, but its chronological confirmation AUC was 0.4863. At the fixed 0.50 cutoff, 179 approvals lost $709.92. The development-selected 0.55 cutoff approved only 30 and earned $105.60; that small profit is not persuasive because ranking AUC was below random and the sample is very small.
- In canonical 13 + VP32, only `day_of_week` and `volume_above_vah_ratio` passed. The two-feature subset's development median complete-path AUC was 0.5410, but chronological confirmation AUC was 0.4810. Its 128 approvals lost $229.44 at the fixed and development-selected 0.50 cutoff.
- `volume_above_vah_ratio` was the only feature selected in both contexts. `day_of_week` dominated the combined model's development diagnostics, which may reflect period/regime structure rather than a durable causal relationship.
- **Decision:** quantitative reduction improved in-sample development ranking but failed chronological confirmation. Do not promote either selected subset or interpret the 30-trade positive VP13 result as an edge. The next diagnostic should test coefficient/importance behavior by time regime rather than perform another unrestricted model sweep. Artifacts: `reports/vp_feature_stability_2026-09-29/`.

## 2026-09-29 — Regularized logistic VP32 and canonical-13 + VP32 benchmark

- A simpler regularized logistic classifier was tested on the same 2,197-event ESU26/VP common universe used by the controlled MLP comparison. The first contract used all 32 VP features; the second used the 13 canonical features plus all 32 VP features. Both used the same CPCV(6,2) paths, 1% embargo, purging, 1,867-event development sample, later 330-event chronological confirmation segment, and $6.48 round-trip cost.
- L1, L2, and elastic-net regularization were searched across `C = 0.001, 0.01, 0.1, 1, 10, 100`. Regularization was selected exclusively by median complete-path development CPCV ROC AUC, with log loss as the tie-breaker. Trading thresholds were selected separately using development CPCV paths; the chronological confirmation segment was not consulted.
- **VP32:** L2 with `C=0.01` won development selection with median CPCV AUC 0.5100. On the chronological confirmation segment, AUC was 0.4746. The fixed 0.50 threshold approved 182 trades and lost $679.36; the development-selected 0.55 threshold approved 41 and lost $415.68.
- **Canonical 13 + VP32:** elastic net with `C=0.01` and L1 ratio 0.25 won development selection with median CPCV AUC 0.5264. The final fit retained seven nonzero coefficients, but chronological confirmation AUC was only 0.4893. At 0.50 it approved 136 trades and lost $281.28. At the development-selected 0.525 threshold it approved 52 and lost $36.96.
- **Decision:** the simpler classifier does not establish stable predictive or economic value. The seven retained coefficients are evidence of shrinkage in this fitted sample, not a validated compact feature set; coefficient stability must be measured across folds before using them for feature selection. No deployable model was written and the live registry was not modified. Artifacts: `reports/logistic_vp32_vp45_cpcv_2026-09-29/`.

## 2026-09-29 — Hypothesis-driven compact VP8 feature contract

- A compact VP-only contract was declared before evaluating it: `poc_distance`, `va_position`, `poc_migration`, `classified_delta_ratio`, `price_classified_delta_divergence`, `va_expansion_rate`, `nearest_hvn_distance_ticks`, and `nearest_lvn_distance_ticks`. The architecture and the latest 2,197-event ESU26/VP common universe were held constant against VP32, VP42, and VP45.
- Compact VP8 improved median CPCV ROC AUC to 0.5175 versus 0.5004 for VP32, and improved median profit factor to 0.86 versus 0.83. Nevertheless, every one of its five complete CPCV paths lost money: -$3,185.60, -$582.08, -$1,165.28, -$1,903.20, and -$941.28. Median net was -$1,165.28 after $6.48 round-trip cost.
- The later 330-event chronological segment approved only 35 trades at the development-selected 0.575 threshold and earned +$23.20, with 0.4882 AUC and 1.03 profit factor. The sample is too small, its ranking AUC is below random, and it contradicts five negative development paths; it is not evidence of an edge.
- **Decision:** feature reduction slightly reduced overfitting but did not solve generalization or economic performance. VP8 was chosen conceptually rather than by a quantitative selection procedure, so retire it as a candidate feature contract. Preserve it only as a historical diagnostic result. Artifacts: `reports/cpcv_esu26_compact8_vp32_vp45_vp42_real_cost_2026-09-29/`.

## 2026-09-29 — Latest ESU26 canonical universe with VP32, VP42, and VP45

- This is the controlled VP comparison against the latest matched ESU26 canonical-13 source. It starts from `ma2cross_esu26_closed_bar_canonical_2026-09-18.csv` (5,725 trades) and retains the 2,197 events from June 14 through August 14 that also have historical VP coverage. Every model sees exactly the same candidates and labels. Canonical features come from the completed signal bar before the next-bar-open entry, and every VP snapshot is exactly one second before that signal-bar timestamp.
- The fixed comparison uses CPCV(6,2), 1% observation-count embargo, 15 splits/five complete paths, the same `(64, 32)` MLP configuration, development-only threshold selection, and a later 15% chronological confirmation segment. P&L is taken directly from `net_pnl_at_3_24_per_side`, so every completed trade includes **$6.48 round-trip cost**. Slippage is not included. The unfiltered 2,197-trade common universe loses $12,786.56.
- **VP32 only:** median CPCV AUC 0.5004, profit factor 0.83, -$1,518.88 median net, and -$4.76 average approved trade at threshold 0.65. All five paths lost between $1,307.84 and $2,940.16. The 330-event chronological segment approved only 27 trades and earned +$75.04 (AUC 0.5345, profit factor 1.12); this sample is too small and contradicts uniformly negative development paths, so it is not confirmation of an edge.
- **VP45 (13 canonical plus all VP):** median CPCV AUC 0.5055, profit factor 0.80, and -$5,355.04 median net at threshold 0.475. Every path lost between $4,390.24 and $8,204.16.
- **VP42 (13 canonical plus reduced VP):** median CPCV AUC 0.4965, profit factor 0.78, and -$4,102.72 median net at threshold 0.60. Every path lost between $3,359.36 and $5,104.64.
- **Decision:** none of the three feature contracts demonstrates stable predictive or economic value on the latest common ESU26 population. Do not promote or tune against the 330-event confirmation segment. Artifacts: `processed/ma2cross_esu26_closed_bar_canonical_vp45_common_through_2026-08-14.parquet` and `reports/cpcv_esu26_common_vp32_vp45_vp42_real_cost_2026-09-29/`. No deployable weights were written and the live registry was not modified by this experiment.

## 2026-09-29 — Point-in-time-correct VP32, VP42, and VP45 CPCV comparison

- The common dataset contains 6,444 MA candidates from March 15 through August 14, 2026. Canonical features use the completed signal bar immediately before the next-bar-open entry. Each VP snapshot is from the same ES session and exactly one second before that signal-bar timestamp. The comparison uses CPCV(6,2), a 1% observation-count embargo, 15 splits/five complete paths, one fixed `(64, 32)` MLP configuration, and a separate 15% chronological confirmation segment. The TradeStation source P&L embeds $4.50 round trip; the runner subtracts another $1.98 so every result uses the documented **$6.48 round-trip cost**. Slippage is not included.
- **VP32 only:** median path ROC AUC 0.4967, profit factor 0.89, -$3,214.08 median net, and -$2.87 average approved trade at its development-selected 0.625 threshold. The later 967-event confirmation segment produced 0.4982 AUC; 193 approvals lost $513.14 with a 0.90 profit factor.
- **VP42 (13 canonical plus reduced VP):** median path ROC AUC 0.4902, profit factor 0.88, and -$10,788.18 median net at threshold 0.475.
- **VP45 (13 canonical plus all VP):** median path ROC AUC 0.4851, profit factor 0.88, and -$12,756.22 median net at threshold 0.425.
- Every complete CPCV path lost money for every feature contract. The experiment does not support promoting VP32, VP42, or VP45. The earlier same-entry-stamp run produced apparent AUC near 0.65, but it used VP/canonical values accumulated inside the entry bar after its opening fill and is retained only as a discarded timing-control result.
- Artifacts: `processed/ma2cross_old_libb_prior_bar_vp45.parquet`, its manifest, and `reports/cpcv_prior_bar_vp32_vp45_vp42_real_cost_2026-09-29/`. No deployable weights were written and the live registry was not modified.

## 2026-09-29 — Forced exit at the close of the entry 30-second bar

- The point-in-time-correct prior-bar MLP holdout was evaluated at its fixed 0.50 threshold. All 612 approved trades were retained. The 243 trades already closed by TradeStation within their entry-stamped bar preserved their one-tick-LIBB stop/target result; the other 369 were repriced at that entry bar's historical close. Every trade includes the $6.48 round-turn cost.
- The forced-exit approximation produced **-$1,128.26** net, 39.71% winning trades, 0.87 profit factor, -$1.84 average trade, and **-$1,234.14** maximum drawdown. The original stop/target outcomes for the same 612 approvals produced -$1,565.76 net and -$2,284.48 maximum drawdown. The forced exit therefore improved net P&L by **$437.50** and materially reduced drawdown, but did not create positive expectancy.
- The 243 realized same-bar exits contributed +$775.36; the 369 forced bar-close exits contributed -$1,903.62. This confirms that merely forcing all positions out at the first bar close is not equivalent to selecting the profitable same-bar cohort retrospectively.
- Artifacts: `training_mlp/evaluate_first_bar_forced_exit.py` and `training_mlp/strategies/MA2CrossLE/reports/corrected_holdout_forced_first_bar_exit/`. This is a 30-second bar-close approximation. Before any live rule change, reproduce it with tick-level timestamps and explicit order timing, then confirm it on future unseen trades.

## 2026-09-29 — Tick-level breakeven and trailing-stop sweep

- The corrected prior-bar MLP holdout approvals at threshold 0.50 were replayed against the continuous tick archive. The unchanged one-point stop/target control reproduced 572 of 612 TradeStation outcomes exactly; 40 trades with conflicting tick-versus-LIBB event priority were excluded from every configuration rather than resolved using an arbitrary assumption. The replay applies the documented 67.75-point continuous-contract scale adjustment, which does not change tick distances or P&L.
- Breakeven activation was swept at 1, 2, and 3 favorable ticks. Trailing stops used the full 3×3 combination of activation at 1/2/3 ticks and distance behind the best price of 1/2/3 ticks. The original one-point stop, one-point target and $6.48 round-turn cost were retained.
- No dynamic-stop configuration improved the unchanged control. On the 572 validated trades, the control lost **$1,706.56** with 53.50% winners and -$2,176.96 maximum drawdown. The least-bad dynamic rule—breakeven after three favorable ticks, equivalent here to a three-tick trail activated at three ticks—lost **$2,406.56**, with 44.23% winners and -$2,899.20 maximum drawdown. Every tighter rule performed worse.
- A high win rate did not imply profitability: activation at two ticks with a one-tick trailing distance won 66.78% of trades but lost **$4,581.56**, because the rule produced many small gains while retaining full-sized losses and paying transaction costs. The tested dynamic stops should not be added to the live strategy. Artifacts: `training_mlp/sweep_dynamic_stops.py` and `training_mlp/strategies/MA2CrossLE/reports/corrected_holdout_dynamic_stop_sweep/`.

## 2026-09-22 — Old LIBB first-bar result fails point-in-time feature test

- Controlled source files: `training_mlp/strategies/MA2CrossLE/inputs/data_30_master.txt` and `training_mlp/strategies/MA2CrossLE/inputs/trades_30_libb_2026-04-07.csv`. Their hashes match the earlier study's `reports/real_cost_threshold_selection/provenance.json`. The old feature builder was reproduced to maximum absolute difference `2.84e-14` before changing timing.
- Ablation: preserve all 11,196 trades, labels, costs ($3.24/side), old calendar-day OHLC4/volume VWAP, 13 feature definitions, five purged walk-forward folds, 10% chronological holdout, seed, architecture, and training settings. Shift only feature availability from the full entry bar to the immediately preceding completed bar. Dataset: `processed/ma2cross_old_libb_prior_bar_13.csv`; model: `model/mlp_old_libb_prior_bar_13_ablation`; results: `reports/old_libb_prior_bar_ablation/results.json`.
- The 1,119 holdout trade IDs/labels/exits are identical. Mean validation ROC AUC fell from **0.5798 to 0.4993**; holdout ROC AUC fell from **0.5696 to 0.5071**. At the original preselected 0.52 threshold, 498 old-model approvals earned **+$1,472.96** net, while 403 prior-bar-model approvals lost **$2,161.44** net. At 0.50, the corresponding totals were +$1,174.08 and -$1,565.76. The original holdout result was independently reproduced before comparison.
- Interpretation: the original dataset joined each trade label to features calculated from the *completed entry-stamped bar*. For a `next bar at market` fill at that bar's open, the completed entry bar's high, low, close, and total volume are not yet available; the immediately preceding signal bar is the point-in-time candidate. This is a bar-alignment mismatch consistent with look-ahead leakage. The ablation shows the apparent model edge does not survive the one-bar shift, but it does not identify which feature contributed most or independently reconstruct every intrabar signal time. Do not promote the old model or infer a profitable live strategy from its earlier holdout P/L. The holdout had already been inspected in prior research, so it is not a fresh untouched confirmation set.

## 2026-09-23 — Regularized XGBoost does not recover the corrected MA-13 edge

- An isolated XGBoost benchmark used the same leakage-corrected 11,196-event dataset, 13 features, five purged expanding walk-forward folds, and identical 1,119-trade chronological holdout as the corrected MLP. The model used shallow depth, minimum child weight, row and feature subsampling, L1/L2 penalties, and fold-level early stopping. The live registry was not changed.
- Mean validation ROC AUC was **0.5124** and holdout ROC AUC was **0.5020**. The final seven-tree model's training AUC was only **0.5395**, so the result does not show a large train-versus-test overfit gap. It instead indicates that this regularized tree found little stable predictive information in the corrected 13-feature dataset.
- Holdout probabilities occupied only **0.5302–0.5419**, so thresholds 0.50 and 0.52 approved all 1,119 trades. The result therefore equaled the naive baseline: **52.90%** wins and **-$3,763.62** net after the $6.48 round-turn cost. Artifacts: `training_mlp/strategies/MA2CrossLE/reports/xgboost_old_libb_prior_bar_13/`.

## Future feature idea — Positioning analysis

Investigate who is participating in the ES market, how those participants are
positioned, and how much deployable capital or risk capacity they may still
have. Possible inputs require separate data-source and licensing review; the
current bar/tick exports do not directly identify participants or their
remaining capital. Treat any positioning proxy as a research hypothesis, and
check publication lag, timestamp availability, and look-ahead risk before
adding it to training or live inference.

## Rollover data-integrity rule

Continuous `@ES` exports can be back-adjusted after a contract rollover.
Before each new export is used, identify the last ES session shared by the old
and new bar and tick files. Verify that the old tick stream agrees with the
old 30-second bars and the new tick stream agrees with the new 30-second bars
(OHLC plus `Up`/`Down`), then switch both streams at the same session boundary.
If the first new bar/tick prices are separated from the old scale by a large
constant, record it as a rollover-vintage break and do not train across it
without an explicit state reset and documented validation.

## 2026-09-21 — Reconstructed VWAP underperforms the prior VWAP in VP45

- Sources: `training_mlp/strategies/MA2CrossLE/reports/pwf_feature_comparison_libb/validation_predictions.parquet` (prior VWAP), `training_mlp/strategies/MA2CrossLE/reports/pwf_feature_comparison_libb_ts_vwap/validation_predictions.parquet` (reconstructed TradeStation-style VWAP), and `training_mlp/strategies/MA2CrossLE/reports/trade_execution_anomalies_libb_all_trades.csv` (realized TradeStation trades).
- Controlled comparison: the same 5,365 walk-forward candidate events, labels, exit timestamps, and other 44 VP45 features. Only `vwap_distance` changed in the input datasets; each model was retrained. Both were evaluated at the same exploratory probability threshold of 0.52. The threshold was not selected specifically for VP45.
- Cost-adjusted result: the prior-VWAP model approved 2,671 trades for **+$23,766.92** net; the reconstructed-VWAP model approved 2,648 trades for **+$21,765.96** net. The decrease is **$2,000.96, or 8.42%** of prior net profit. TradeStation's export already includes $2.25 per side; another $0.99 per side was subtracted to model $3.24 per side. Slippage is not included.
- Decision sensitivity: 2,565 candidates were approved by both models, 106 only by the prior-VWAP model, and 83 only by the reconstructed-VWAP model. Mean walk-forward ROC AUC changed much less, from 0.65682 to 0.65589; similar AUC did **not** imply similar trading P&L.
- Holding-time warning: reconstructed-VWAP approvals exiting at the entry timestamp earned +$25,646.56 net; all longer-held approvals lost $3,880.60 net. A shared 30-second timestamp does not reveal the actual intrabar holding time. Validate the execution-label and fill assumptions before treating either profit total as live expectancy.

| VP45 model, approved trades exiting at entry timestamp | Trades | Winners | Win rate | Net P&L | Mean net/trade | Profit factor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Prior calculated VWAP | 1,456 | 1,090 | 74.86% | +$26,765.12 | +$18.38 | 2.29 |
| Reconstructed TradeStation-style VWAP | 1,428 | 1,063 | 74.44% | +$25,646.56 | +$17.96 | 2.24 |

For the prior-VWAP model, the 1,215 approved trades with later exit timestamps lost $2,998.20 net (54.16% winners, profit factor 0.91). For the reconstructed-VWAP model, the 1,220 later-exiting trades lost $3,880.60 net (53.44% winners, profit factor 0.88). Thus the observed short-hold cohort is much more profitable, but filtering trades *after* observing their eventual holding time is look-ahead bias. A rule that forces every trade out in its first 30-second bar could reprice both cohorts, change which stops or targets fill, and yield a different result; test such a rule directly with intrabar data and costs.

**Decision for this research branch:** do not promote the reconstructed-VWAP VP45 model. It is materially worse than the prior-VWAP version in this controlled, cost-adjusted walk-forward test. This does not establish that a directly exported TradeStation VWAP series will have the same result.

**Next experiment and source limitation:** the historical bar master currently has only `Date, Time, Open, High, Low, Close, Up, Down`; it contains no per-bar VWAP values. TradeStation documents the EasyLanguage `VWAP` reserved word as a current quote field without historical values. It cannot be exported over past Chart Analysis bars simply by waiting for RTH. Obtain or derive a historical trade-level VWAP series with the same symbol, session, and reset rules, then verify timestamp uniqueness, coverage, and spot-checks against live values. The isolated native-VWAP builder is ready to consume a verified historical series but cannot manufacture one. Join the verified series one-to-one to the same bar history; recompute only `vwap_distance`; rerun the same purged folds, 0.52-threshold cost-adjusted trade analysis, and untouched holdout. If this still materially reduces trading performance, evaluate retaining the prior calculated VWAP, but first resolve how that prior feature will be computed consistently in live inference. Keep all variants separate from the live registry until validated.

## 2026-09-21 — Holding time and realized profit

### Canonical 13-feature model: frozen holdout

- Source: `training_mlp/strategies/MA2CrossLE/reports/real_cost_threshold_selection/holdout_approved_trades.csv` and its `provenance.json`.
- Population: 498 out-of-sample trades approved by the deployed 13-feature model at probability threshold 0.52. No VP features.
- Cost: `real_cost_pnl`, with $3.24 per contract per side ($6.48 round trip); slippage is not included.
- Result: $1,472.96 net overall. The 172 same-timestamp trades earned $2,685.44 net (124 winners, 48 losers; 72.09% win rate). The other 326 trades lost $1,212.48 net in aggregate.

| Entry-to-exit timestamp difference | Trades | Winners | Losers | Net P&L | Average P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 seconds | 172 | 124 | 48 | +$2,685.44 | +$15.61 |
| 30 seconds | 97 | 55 | 42 | +$21.44 | +$0.22 |
| 1–2 minutes | 107 | 55 | 52 | -$543.36 | -$5.08 |
| >2–5 minutes | 69 | 32 | 37 | -$697.12 | -$10.10 |
| >5–10 minutes | 37 | 20 | 17 | -$89.76 | -$2.43 |
| >10–30 minutes | 16 | 10 | 6 | +$96.32 | +$6.02 |

### Canonical plus volume profile: VP45 walk-forward validation

- Source: `training_mlp/strategies/MA2CrossLE/reports/pwf_feature_comparison_libb/validation_predictions.parquet`, joined one-to-one by entry timestamp to `training_mlp/strategies/MA2CrossLE/reports/trade_execution_anomalies_libb_all_trades.csv`. All 5,365 VP45 predictions matched a trade and an exit timestamp.
- Population: 2,671 approved trades across five out-of-sample walk-forward validation folds of the 45-feature model (`ma_vp_45`), using probability threshold 0.52 for an exploratory calculation. This threshold was selected for the 13-feature model, not optimized or frozen for VP45.
- Cost: original trade P&L includes $2.25 per side; subtracting another $0.99 per side gives an assumed effective $3.24 per side. Slippage is not included.
- Result: $23,766.92 net overall. The 1,456 same-timestamp trades earned $26,765.12 net (1,090 winners, 366 losers; 74.86% win rate). The other 1,215 trades lost $2,998.20 net in aggregate.

| Entry-to-exit timestamp difference | Trades | Winners | Losers | Net P&L | Average P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 seconds | 1,456 | 1,090 | 366 | +$26,765.12 | +$18.38 |
| 30 seconds | 630 | 347 | 283 | -$594.90 | -$0.94 |
| 1–2 minutes | 407 | 229 | 178 | -$99.86 | -$0.25 |
| >2–5 minutes | 137 | 69 | 68 | -$837.76 | -$6.12 |
| >5–10 minutes | 29 | 12 | 17 | -$437.92 | -$15.10 |
| >10–30 minutes | 10 | 0 | 10 | -$564.80 | -$56.48 |
| >30–60 minutes | 0 | 0 | 0 | $0.00 | — |
| >60 minutes | 2 | 1 | 1 | -$462.96 | -$231.48 |

### Interpretation and follow-up

Both studies concentrate realized profit in trades whose entry and exit share a 30-second-bar timestamp. A zero-second difference does **not** mean instantaneous execution; the export does not preserve the intrabar elapsed time. The VP45 walk-forward study and the 13-feature frozen holdout use different populations and model versions, so their dollar totals and win rates are not a controlled VP-versus-non-VP comparison. The VP45 study also uses the earlier merged MA/VP feature file, not the later TradeStation-VWAP-retrained canonical dataset.

Holding time is only known after entry and cannot be an entry feature. Before adding a time-based exit, reprice each still-open trade from historical bars at candidate time stops (for example 30, 60, 90, 120, and 300 seconds), preserving intrabar stop/target priority, fill assumptions, costs, and a separate untouched test period. Do not estimate a time stop by deleting long-duration trades from these tables.

## 2026-09-22 — Corrected closed-bar MA entry, June–September research run

- The isolated dataset `processed/ma2cross_corrected_jun_sep_2026.parquet` contains 5,905 completed trades: 3,727 from the September-contract export through August 14 and 2,178 from the newer December-vintage export through the available September 21 bar history. All entries match a crossover on the **preceding completed bar**. The 13 canonical features are taken at that crossover bar's close, before the next-bar-open entry. The two bar-price vintages remain separated by a feature reset. The manifest records source hashes and cutoffs.
- A separate MLP research run used 25 purged expanding walk-forward folds (the configured environment), 100 maximum epochs with patience 5, and a chronological 10% final holdout. Its output is `model/mlp_corrected_jun_sep_2026_research/`; the live registry was not changed. Mean validation accuracy was **52.43%** and mean ROC AUC was **0.5289**. The best fold's validation AUC was 0.5933; selecting that fold did not generalize to the final holdout.
- The untouched 590-trade holdout spans September 10 23:38:30 through September 21 23:00:30 (all new price vintage). Accuracy was **47.29%**, ROC AUC **0.4786**, and positive-class F1 **0.2717**. The holdout majority-class baseline was **51.69%** (305 positive trades out of 590); the trainer's printed 50.05% baseline is calculated on the CV pool, not on this holdout. The held-out unfiltered strategy lost **$2,835.70** net after $3.24 per side, before slippage. At the research model's default 0.50 cutoff, 122 approved trades lost **$1,090.56** net; at 0.52, 52 approved trades lost **$336.96** net. The 0.52 calculation is exploratory and is not a tuned threshold for this model.
- **Decision:** do not promote this model. These results cannot be compared as a controlled head-to-head with the currently registered `mlp_ts_vwap_libb` model: that model used different training events, a different VWAP feature definition, and an earlier holdout. A fair comparison requires a common, genuinely unseen period and compatible feature definitions; scoring the existing model on a period it may already have seen would not establish out-of-sample performance.

## 2026-09-22 — Matched ESU26 bar/trade export, canonical MA-13

- The later single-vintage TradeStation bar file `inputs/data_30_update_2026-06-14_to_2026-09-17.txt` has 189,537 bars from June 14 18:00:30 through September 18 09:30:00. Its paired corrected LIBB export `inputs/trades_30_libb_2026-06-15_to_2026-09-17.csv` has 5,725 completed trades through September 18 09:19:00. Despite the filenames, both exports include September 18 morning. Every entry timestamp matched a bar, every entry price equaled that bar's open, and every entry followed a completed-bar MA crossover. The source hashes and checks are recorded in `processed/ma2cross_esu26_closed_bar_canonical_2026-09-18.manifest.json`.
- The 13 canonical features use session VWAP based on `Close * (Up + Down)` with the ES 18:00 ET reset. Each candidate feature row comes from the completed crossover bar before its next-bar-open trade. This study uses **only these two matching ESU26 exports**, with no bar-vintage splice or December trade export. Its dataset contains 5,725 events, 2,861 net-positive after $3.24 commission per side. Slippage is not modeled.
- A separate research MLP used the earlier model's core training settings: five purged expanding walk-forward folds, batch size 64, patience 15, 100 maximum epochs, and a frozen chronological 10% holdout. Mean walk-forward AUC was approximately 0.5171 (fold AUCs 0.5021, 0.5275, 0.5393, 0.4879, 0.5288). The live model registry was not changed.
- The 572-trade final holdout ran from September 9 03:22:00 to September 18 09:18:30. ROC AUC was **0.5625**; accuracy at 0.50 was **52.80%**, compared with a **52.62% holdout majority-class baseline**. The training script's printed 50.26% baseline is from its CV pool, not the holdout.
- Without NN filtering, holdout trades won **271/572 (47.38%)** and lost **$5,356.56** net, or -$9.36 per trade. At a fixed 0.50 probability cutoff, the NN approved **411** trades, won **206 (50.12%)**, and lost **$2,763.28** net, or -$6.72 per approved trade. The NN filtered out a worse-than-average cohort (161 rejected trades, 40.37% winners). At 0.52, an exploratory cutoff not selected for this model, 350 approvals won 51.71% and lost $1,818.00 net. Thus this model improves ranking and loss avoidance on the matched-file holdout but does **not** produce positive net expectancy at these cutoffs.
- This is **not** directly comparable with the older deployed model's August holdout or the previous spliced-data study: the trade export, test dates, VWAP definition, and/or training settings differ. Do not promote the model solely because AUC exceeds 0.5. First verify the GNET live decision-to-fill timing against these backtest entries and select any operating threshold using validation data, not the September holdout.
