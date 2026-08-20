# ML Pipeline — Techniques Summary

## Data
- **Meta-labeling** — binary label from trade P&L (1 = profit, 0 = loss)
- **Feature engineering** from 30s OHLCV bars: Parkinson volatility, OFI, Amihud illiquidity, VWAP distance, volume percentile/momentum, session time encoding

## Validation strategy
- **Temporal train/val/test split** — no random shuffling, always chronological
- **Event-aware purge** — removes training labels whose `[entry_time, t1]` information intervals overlap validation
- **Embargo** — López de Prado observation-count percentage, configured by `EMBARGO_PCT`
- **Walk-forward CV** — expanding past-only train window and subsequent fixed validation window
- **Held-out test set** — last 10% of data, frozen until final evaluation; overlapping training labels are purged by `t1`

## Model
- **MLP** — 2 hidden layers (64 → 32), BatchNorm + ReLU + Dropout (0.3)
- **BCEWithLogitsLoss** with `pos_weight` — handles class imbalance per fold

## Optimization
- **AdamW** — decoupled weight decay (1e-2) as primary regularizer
- **Linear warmup** (10 epochs) → **cosine decay** to LR_MIN — avoids large early updates on small dataset
- **Early stopping** (patience 15) — restores best val loss checkpoint

## Evaluation
- Metrics: accuracy, F1, AUC-ROC per fold + test
- **Baseline**: majority-class classifier (naive fixed-rule trading analog)
- Best fold selected by val AUC → single evaluation on test set



