"""
zona_lstm.py
============

LSTM meta-labeling for the Zona strategy.

Instead of engineered features, feeds the raw 60-bar sequence (2 hours)
before each trade entry directly into an LSTM. Input per bar:
  Open, High, Low, Close, Up, Down, Volume (7 channels)

Each bar is normalized relative to the entry bar's Close so the model
sees returns/ratios rather than absolute prices.

Same purged-embargo walk-forward CV as zona_training.py.

Outputs saved to strategies/zona_strat/model/lstm/:
  model_lstm_best.pt
  scaler_lstm_best.pkl   (per-channel StandardScaler fitted on train set)
  config_lstm.json
  results_cv_lstm.csv
  cv_summary_lstm.png
  loss_fold_N.png

Run
---
    cd training_mlp
    python zona_lstm.py
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from dotenv import load_dotenv
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

load_dotenv(Path(__file__).parent / ".env")
from zona_pipeline import load_bars, load_paired_trades, BARS_FILE, TRADES_FILE

# ── Config ────────────────────────────────────────────────────────────────────

RANDOM_SEED  = int(os.getenv("RANDOM_SEED",   "42"))
N_SPLITS     = int(os.getenv("N_SPLITS",      "25"))
FOLD_SIZE    = int(os.getenv("FOLD_SIZE",     "0")) or None
PURGE_BARS   = int(os.getenv("PURGE_BARS",    "20"))
EMBARGO_BARS = int(os.getenv("EMBARGO_BARS",  "60"))
TEST_SIZE    = float(os.getenv("TEST_SIZE",   "0.10"))
EPOCHS       = int(os.getenv("EPOCHS",        "100"))
BATCH_SIZE   = int(os.getenv("BATCH_SIZE",    "16"))
LR           = float(os.getenv("LR",          "1e-3"))
LR_MIN       = float(os.getenv("LR_MIN",      "1e-6"))
WARMUP_EPOCHS= int(os.getenv("WARMUP_EPOCHS", "10"))
PATIENCE     = int(os.getenv("PATIENCE",      "5"))
WEIGHT_DECAY = float(os.getenv("WEIGHT_DECAY","1e-2"))

LOOKBACK     = 60   # bars to look back before entry (2 hours on 2-min bars)
BAR_FEATURES = ["Open", "High", "Low", "Close", "Up", "Down", "Volume"]
N_BAR_FEAT   = len(BAR_FEATURES)

OUT_DIR = Path("strategies/zona_strat/model/lstm")

torch.manual_seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


# ── Dataset ───────────────────────────────────────────────────────────────────

class SequenceDataset(Dataset):
    def __init__(self, sequences: np.ndarray, labels: np.ndarray):
        self.X = torch.tensor(sequences, dtype=torch.float32)
        self.y = torch.tensor(labels,    dtype=torch.float32)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


def build_sequences(bars_df: pd.DataFrame, trades_df: pd.DataFrame, lookback: int):
    """
    For each trade, extract the lookback bars ending at (but not including)
    the entry bar. Returns sequences array (N, lookback, N_BAR_FEAT) and
    per-channel normalization relative to the entry bar close.
    """
    bars_df = bars_df.sort_values("Date/Time").reset_index(drop=True)
    dt_index = bars_df["Date/Time"].values
    bar_vals = bars_df[BAR_FEATURES].values.astype(np.float32)

    sequences, labels, timestamps = [], [], []

    for _, trade in trades_df.iterrows():
        entry_dt = trade["entry_ts"]
        label    = int(trade["pnl"] > 0)

        # Find index of the bar at or just before entry
        idx = np.searchsorted(dt_index, np.datetime64(entry_dt), side="right") - 1
        if idx < lookback:
            continue

        seq = bar_vals[idx - lookback: idx].copy()   # (lookback, 7)

        # Normalize each channel by entry bar close — model sees % changes
        entry_close = bar_vals[idx, BAR_FEATURES.index("Close")]
        if entry_close == 0:
            continue
        seq = seq / entry_close

        sequences.append(seq)
        labels.append(label)
        timestamps.append(entry_dt)

    return (
        np.array(sequences, dtype=np.float32),
        np.array(labels,    dtype=np.float32),
        np.array(timestamps),
    )


# ── Splits ────────────────────────────────────────────────────────────────────

def split_test(n_total, test_size, purge, embargo):
    n_test = int(n_total * test_size)
    gap    = purge + embargo
    n_cv   = n_total - n_test - gap
    return n_cv, gap


def purged_embargo_splits(n_samples, n_splits, purge, embargo, fold_size=None):
    indices = np.arange(n_samples)
    if fold_size is None:
        fold_size = n_samples // (n_splits + 1)
    for i in range(1, n_splits + 1):
        val_start = i * fold_size
        val_end   = val_start + fold_size
        if val_end > n_samples:
            break
        train_end = val_start - purge
        train_idx = indices[:max(train_end, 0)]
        val_idx   = indices[val_start:val_end]
        if len(train_idx) == 0 or len(val_idx) == 0:
            continue
        yield train_idx, val_idx


# ── Model ─────────────────────────────────────────────────────────────────────

class LSTMClassifier(nn.Module):
    def __init__(self, input_dim=N_BAR_FEAT, hidden=64, n_layers=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim, hidden_size=hidden,
            num_layers=n_layers, batch_first=True,
            dropout=dropout if n_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        # x: (batch, seq_len, input_dim)
        out, _ = self.lstm(x)
        last    = out[:, -1, :]   # take last timestep
        return self.head(last).squeeze(1)


# ── Scheduler ─────────────────────────────────────────────────────────────────

def build_scheduler(optimizer, warmup_epochs, total_epochs, lr, lr_min):
    def lr_lambda(epoch):
        if epoch < warmup_epochs:
            return (epoch + 1) / warmup_epochs
        progress = (epoch - warmup_epochs) / max(total_epochs - warmup_epochs, 1)
        cosine   = 0.5 * (1 + np.cos(np.pi * progress))
        return lr_min / lr + (1 - lr_min / lr) * cosine
    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


# ── Train / Eval ──────────────────────────────────────────────────────────────

def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total = 0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        loss = criterion(model(X_batch), y_batch)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total += loss.item()
    return total / len(loader)


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    all_probs, all_labels = [], []
    total = 0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        logits = model(X_batch)
        total += criterion(logits, y_batch).item()
        probs  = torch.sigmoid(logits).cpu().numpy()
        all_probs.extend(probs)
        all_labels.extend(y_batch.cpu().numpy())
    return total / len(loader), np.array(all_labels), np.array(all_probs)


# ── Plots ─────────────────────────────────────────────────────────────────────

def plot_fold_loss(train_losses, val_losses, fold, auc, out_dir):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(train_losses, label="Train loss", color="steelblue")
    ax.plot(val_losses,   label="Val loss",   color="tomato")
    ax.set_title(f"Fold {fold} — Val AUC {auc:.4f}")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / f"loss_fold_{fold}.png", dpi=100)
    plt.close(fig)


def plot_cv_summary(results, naive_acc, out_dir):
    res_df   = pd.DataFrame(results)
    folds    = res_df["fold"].tolist()
    aucs     = res_df["auc"].tolist()
    mean_auc = res_df["auc"].mean()

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    ax = axes[0]
    bars = ax.bar(folds, aucs, color="steelblue", alpha=0.8)
    ax.axhline(mean_auc, color="tomato",  linestyle="--", label=f"Mean AUC {mean_auc:.4f}")
    ax.axhline(0.5,      color="dimgray", linestyle=":",  label="Random (0.50)")
    ax.set_title("LSTM Val AUC per Fold")
    ax.set_xlabel("Fold")
    ax.set_ylabel("AUC")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    for bar, v in zip(bars, aucs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.001,
                f"{v:.3f}", ha="center", va="bottom", fontsize=7)

    ax2 = axes[1]
    metrics = ["acc", "f1", "auc"]
    means   = [res_df[m].mean() for m in metrics]
    stds    = [res_df[m].std()  for m in metrics]
    ax2.bar(metrics, means, yerr=stds, capsize=5,
            color=["steelblue", "seagreen", "darkorange"], alpha=0.8)
    ax2.axhline(naive_acc, color="dimgray", linestyle="--", label=f"Naive acc {naive_acc:.4f}")
    ax2.set_ylim(0, 1)
    ax2.set_title("CV Mean +/- Std")
    ax2.legend()
    ax2.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    path = out_dir / "cv_summary_lstm.png"
    fig.savefig(path, dpi=100)
    plt.close(fig)
    print(f"Saved -> {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    print("=" * 52)
    print("  ZONA LSTM -- CONFIG")
    print("=" * 52)
    print(f"  Device        : {device}")
    print(f"  Lookback      : {LOOKBACK} bars ({LOOKBACK * 2} min)")
    print(f"  Input channels: {N_BAR_FEAT} (OHLCV + Up + Down)")
    print(f"  Architecture  : LSTM(64, layers=2) -> Linear(32) -> 1")
    print(f"  Epochs        : {EPOCHS}  Patience: {PATIENCE}")
    print(f"  Batch size    : {BATCH_SIZE}  LR: {LR}")
    print(f"  N splits      : {N_SPLITS}  Fold size: {FOLD_SIZE or 'auto'}")
    print(f"  Output dir    : {OUT_DIR.resolve()}")
    print("=" * 52)

    print("\nLoading bars...")
    bars_df = load_bars(BARS_FILE)
    print(f"  {len(bars_df):,} bars")

    print("Loading trades...")
    trades_df = load_paired_trades(TRADES_FILE)
    print(f"  {len(trades_df):,} trades")

    print("Building sequences...")
    X, y, timestamps = build_sequences(bars_df, trades_df, LOOKBACK)
    print(f"  {len(X):,} sequences  shape={X.shape}")

    n_cv, gap = split_test(len(X), TEST_SIZE, PURGE_BARS, EMBARGO_BARS)
    X_cv, y_cv   = X[:n_cv],       y[:n_cv]
    X_test, y_test = X[n_cv + gap:], y[n_cv + gap:]
    print(f"  CV: {len(X_cv):,}  Test: {len(X_test):,}  Gap: {gap}")

    np.save(OUT_DIR / "X_test.npy", X_test)
    np.save(OUT_DIR / "y_test.npy", y_test)

    majority  = int(np.round(y_cv.mean()))
    naive_acc = (y_cv == majority).mean()
    scale_pos = float((y_cv == 0).sum() / (y_cv == 1).sum())
    print(f"  Naive acc: {naive_acc:.4f}")

    results          = []
    best_fold_auc    = -np.inf
    best_fold_idx    = None
    best_model_state = None

    for fold, (train_idx, val_idx) in enumerate(
        purged_embargo_splits(len(X_cv), N_SPLITS, PURGE_BARS, EMBARGO_BARS, FOLD_SIZE)
    ):
        X_train, X_val = X_cv[train_idx], X_cv[val_idx]
        y_train, y_val = y_cv[train_idx], y_cv[val_idx]

        # Fit scaler on flattened train sequences, apply per channel
        flat_train = X_train.reshape(-1, N_BAR_FEAT)
        scaler = StandardScaler().fit(flat_train)
        X_train_s = scaler.transform(X_train.reshape(-1, N_BAR_FEAT)).reshape(X_train.shape)
        X_val_s   = scaler.transform(X_val.reshape(-1,   N_BAR_FEAT)).reshape(X_val.shape)

        train_dl = DataLoader(SequenceDataset(X_train_s, y_train), batch_size=BATCH_SIZE, shuffle=False)
        val_dl   = DataLoader(SequenceDataset(X_val_s,   y_val),   batch_size=BATCH_SIZE)

        pos_weight = torch.tensor([scale_pos]).to(device)
        criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        model      = LSTMClassifier().to(device)
        optimizer  = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
        scheduler  = build_scheduler(optimizer, WARMUP_EPOCHS, EPOCHS, LR, LR_MIN)

        best_val_loss, best_state, patience_count = np.inf, None, 0
        train_losses, val_losses = [], []

        epoch_bar = tqdm(range(EPOCHS), desc=f"  Fold {fold+1:>2}", leave=False, unit="ep")
        for epoch in epoch_bar:
            train_loss = train_epoch(model, train_dl, optimizer, criterion, device)
            val_loss, _, _ = evaluate(model, val_dl, criterion, device)
            scheduler.step()

            train_losses.append(train_loss)
            val_losses.append(val_loss)

            epoch_bar.set_postfix(
                train=f"{train_loss:.4f}", val=f"{val_loss:.4f}",
                patience=f"{patience_count}/{PATIENCE}"
            )

            if val_loss < best_val_loss:
                best_val_loss  = val_loss
                best_state     = {k: v.clone() for k, v in model.state_dict().items()}
                best_scaler    = pickle.loads(pickle.dumps(scaler))
                patience_count = 0
            else:
                patience_count += 1
            if patience_count >= PATIENCE:
                break

        model.load_state_dict(best_state)
        _, y_true, y_prob = evaluate(model, val_dl, criterion, device)
        y_pred = (y_prob >= 0.5).astype(int)

        acc = accuracy_score(y_true, y_pred)
        f1  = f1_score(y_true, y_pred)
        auc = roc_auc_score(y_true, y_prob)

        results.append({"fold": fold+1, "acc": acc, "f1": f1, "auc": auc,
                        "train_n": len(train_idx), "val_n": len(val_idx)})

        print(f"  Fold {fold+1:>2}  train={len(train_idx):>6,}  val={len(val_idx):>5,}  "
              f"acc={acc:.4f}  f1={f1:.4f}  auc={auc:.4f}")

        plot_fold_loss(train_losses, val_losses, fold+1, auc, OUT_DIR)

        if auc > best_fold_auc:
            best_fold_auc    = auc
            best_fold_idx    = fold + 1
            best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
            best_scaler_save = best_scaler

    # ── Save ──────────────────────────────────────────────────────────────────
    torch.save(best_model_state, OUT_DIR / "model_lstm_best.pt")
    with open(OUT_DIR / "scaler_lstm_best.pkl", "wb") as f:
        pickle.dump(best_scaler_save, f)

    res_df = pd.DataFrame(results)
    res_df.to_csv(OUT_DIR / "results_cv_lstm.csv", index=False)

    config = {
        "lookback": LOOKBACK, "n_bar_features": N_BAR_FEAT,
        "bar_features": BAR_FEATURES, "architecture": "LSTM(64,2)->Linear(32)->1",
        "epochs": EPOCHS, "batch_size": BATCH_SIZE, "lr": LR, "patience": PATIENCE,
        "n_splits": N_SPLITS, "fold_size": FOLD_SIZE,
        "purge_bars": PURGE_BARS, "embargo_bars": EMBARGO_BARS,
        "test_size": TEST_SIZE, "naive_acc": naive_acc,
        "best_fold": best_fold_idx, "best_fold_val_auc": best_fold_auc,
        "output_dir": str(OUT_DIR.resolve()),
    }
    with open(OUT_DIR / "config_lstm.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n-- CV Summary -------------------------------------------")
    print(res_df.to_string(index=False))
    print(f"\nBest fold : {best_fold_idx}  (val AUC {best_fold_auc:.4f})")
    print(f"Naive acc : {naive_acc:.4f}")

    plot_cv_summary(results, naive_acc, OUT_DIR)
    print(f"All artifacts saved to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    run()
