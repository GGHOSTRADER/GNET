# MVP — Meta-Labeling ML Pipeline

## Objective
Predict whether a trade entry signal (MA2CrossLE) will result in a profitable trade using market microstructure features at the moment of entry.

## Data
- **Trade log** — TradeStation export, 17,761 labeled trade entries
- **Bar data** — 30-second OHLCV bars with Up/Down volume split
- **Label** — binary, 1 = profitable trade, 0 = loss (meta-labeling)
- **Class balance** — 50.6% / 49.4% — nearly balanced

## Feature Engineering (13 features)
| Feature | Description |
|---|---|
| `parkinson_vol_{5,15,30}` | Volatility from High/Low range |
| `ofi_{5,15,30}` | Order flow imbalance (Up - Down volume) |
| `volume_percentile` | Volume rank vs last 60 bars |
| `volume_momentum` | Volume % change over 5 bars |
| `amihud_illiquidity` | Price impact per unit volume |
| `vwap_distance` | Distance from VWAP normalized by ATR |
| `minutes_since_open` | Session time encoding |
| `is_first_last_30min` | Session boundary flag |
| `day_of_week` | Day encoding |

## Validation Strategy
- **Temporal split** — no random shuffling, strictly chronological
- **Purge** — 20 bars (10 min) removed at each fold boundary
- **Embargo** — 60 bars (30 min) gap to prevent serial correlation leakage
- **Walk-forward CV** — 5 folds, expanding train window
- **Held-out test set** — last 10% of data, gapped and frozen

## Model
- **MLP** — 2 hidden layers (64 → 32), BatchNorm + ReLU + Dropout (0.3)
- **Loss** — BCEWithLogitsLoss with pos_weight for class imbalance
- **Optimizer** — AdamW, weight decay 1e-2
- **Schedule** — linear warmup (10 epochs) + cosine decay
- **Early stopping** — patience 15, restores best val loss checkpoint

## Results
| | Naive baseline | MLP |
|---|---|---|
| Accuracy | 0.5058 | 0.5822 |
| F1 | — | 0.6123 |
| AUC | — | 0.6203 |
| Beats baseline | — | ✅ |

## Conclusion
The model learns a statistically meaningful signal from market microstructure features at trade entry, generalizing to unseen data with +7.6% accuracy over the naive baseline and AUC 0.62. This confirms the signal exists and is learnable — a foundation for further feature expansion and model iteration.

## Next Steps
- Add more features (rolling returns, bid-ask spread proxies, regime indicators)
- Lookback window with GRU/LSTM to capture temporal patterns
- Hyperparameter search on architecture and regularization
- Expand to multiple signals beyond MA2CrossLE