# ML Pipeline — Techniques Summary

## Data
- **Meta-labeling** — binary label from trade P&L (1 = profit, 0 = loss)
- **Feature engineering** from 30s OHLCV bars: Parkinson volatility, OFI, Amihud illiquidity, VWAP distance, volume percentile/momentum, session time encoding

## Validation strategy
- **Temporal train/val/test split** — no random shuffling, always chronological
- **Purge** (20 bars = 10 min) — removes train samples whose rolling features overlap with the val boundary
- **Embargo** (60 bars = 30 min) — gap between val end and next fold's train start to prevent serial correlation leakage
- **Walk-forward CV** (5 folds) — expanding train window, fixed val window
- **Held-out test set** — last 10% of data, frozen until final evaluation, also gapped from CV pool

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



