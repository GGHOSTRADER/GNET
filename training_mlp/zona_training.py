# zona_training.py — MLP meta-labeling, trained separately per direction (long/short)

import pandas as pd
import numpy as np
import json
import pickle
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dotenv import load_dotenv
import os
load_dotenv(Path(__file__).parent / ".env")

from pipeline_paths import FEATURES_FILE as DATA_FILE
from zona_features import FEATURE_COLS

RANDOM_SEED    = int(os.getenv("RANDOM_SEED",    "42"))
BATCH_SIZE     = int(os.getenv("BATCH_SIZE",     "16"))
EPOCHS         = int(os.getenv("EPOCHS",         "100"))
LR             = float(os.getenv("LR",           "1e-3"))
LR_MIN         = float(os.getenv("LR_MIN",       "1e-6"))
WARMUP_EPOCHS  = int(os.getenv("WARMUP_EPOCHS",  "10"))
N_SPLITS       = int(os.getenv("N_SPLITS",       "25"))
FOLD_SIZE      = int(os.getenv("FOLD_SIZE",      "0")) or None
EMBARGO_BARS   = int(os.getenv("EMBARGO_BARS",   "60"))
PURGE_BARS     = int(os.getenv("PURGE_BARS",     "20"))
PATIENCE       = int(os.getenv("PATIENCE",       "5"))
WEIGHT_DECAY   = float(os.getenv("WEIGHT_DECAY", "1e-2"))
TEST_SIZE      = float(os.getenv("TEST_SIZE",    "0.10"))

BASE_DIR = Path("strategies/zona_strat/model")

torch.manual_seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


# ── 1. SPLITS ─────────────────────────────────────────────────────────────────

def split_test(X, y, test_size, purge, embargo):
    n_total = len(X)
    n_test  = int(n_total * test_size)
    gap     = purge + embargo
    n_cv    = n_total - n_test - gap
    return X[:n_cv], y[:n_cv], X[n_cv + gap:], y[n_cv + gap:]


def purged_embargo_splits(n_samples, n_splits, purge, embargo, fold_size=None):
    indices   = np.arange(n_samples)
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
        yield train_idx, val_idx, val_end + embargo


# ── 2. MODEL ──────────────────────────────────────────────────────────────────

class MLP(nn.Module):
    def __init__(self, input_dim, hidden_dims=(64, 32), dropout=0.3):
        super().__init__()
        layers = []
        prev = input_dim
        for h in hidden_dims:
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h), nn.ReLU(), nn.Dropout(dropout)]
            prev = h
        layers += [nn.Linear(prev, 1)]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x).squeeze(1)


# ── 3. SCHEDULER ──────────────────────────────────────────────────────────────

def build_scheduler(optimizer, warmup_epochs, total_epochs, lr, lr_min):
    def lr_lambda(epoch):
        if epoch < warmup_epochs:
            return (epoch + 1) / warmup_epochs
        progress = (epoch - warmup_epochs) / max(total_epochs - warmup_epochs, 1)
        cosine   = 0.5 * (1 + np.cos(np.pi * progress))
        return lr_min / lr + (1 - lr_min / lr) * cosine
    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


# ── 4. TRAIN / EVAL ───────────────────────────────────────────────────────────

def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        loss = criterion(model(X_batch), y_batch)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(loader)


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    all_preds, all_probs, all_labels = [], [], []
    total_loss = 0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        logits = model(X_batch)
        total_loss += criterion(logits, y_batch).item()
        probs  = torch.sigmoid(logits).cpu().numpy()
        all_probs.extend(probs)
        all_preds.extend((probs >= 0.5).astype(int))
        all_labels.extend(y_batch.cpu().numpy())
    return (
        total_loss / len(loader),
        np.array(all_labels),
        np.array(all_preds),
        np.array(all_probs),
    )


# ── 5. PLOTS ──────────────────────────────────────────────────────────────────

def plot_fold_loss(train_losses, val_losses, fold, auc, out_dir):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(train_losses, label="Train loss", color="steelblue")
    ax.plot(val_losses,   label="Val loss",   color="tomato")
    ax.set_title(f"Fold {fold} -- Val AUC {auc:.4f}")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / f"loss_fold_{fold}.png", dpi=100)
    plt.close(fig)


def plot_cv_summary(results, naive_acc, out_dir, label):
    res_df   = pd.DataFrame(results)
    folds    = res_df["fold"].tolist()
    aucs     = res_df["auc"].tolist()
    mean_auc = res_df["auc"].mean()

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    ax = axes[0]
    bars = ax.bar(folds, aucs, color="steelblue", alpha=0.8)
    ax.axhline(mean_auc, color="tomato",  linestyle="--", label=f"Mean AUC {mean_auc:.4f}")
    ax.axhline(0.5,      color="dimgray", linestyle=":",  label="Random (0.50)")
    ax.set_title(f"MLP Val AUC -- {label}")
    ax.set_xlabel("Fold")
    ax.set_ylabel("AUC")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    for bar, v in zip(bars, aucs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.002,
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
    fig.savefig(out_dir / "cv_summary.png", dpi=100)
    plt.close(fig)
    print(f"  Saved -> {out_dir / 'cv_summary.png'}")


# ── 6. TRAIN ONE DIRECTION ────────────────────────────────────────────────────

def train_direction(df_dir: pd.DataFrame, direction_label: str, out_dir: Path, device):
    out_dir.mkdir(parents=True, exist_ok=True)

    X = df_dir[FEATURE_COLS].values.astype(np.float32)
    y = df_dir["Label"].values.astype(np.float32)

    fold_size = (FOLD_SIZE // 2) if FOLD_SIZE else None

    X_cv, y_cv, X_test, y_test = split_test(X, y, TEST_SIZE, PURGE_BARS, EMBARGO_BARS)
    gap = PURGE_BARS + EMBARGO_BARS

    majority  = int(np.round(y_cv.mean()))
    naive_acc = (y_cv == majority).mean()

    print(f"  Total={len(X):,}  CV={len(X_cv):,}  Test={len(X_test):,}")
    print(f"  Naive acc: {naive_acc:.4f}  |  Label balance: {y_cv.mean():.3f}")

    np.save(out_dir / "X_test.npy", X_test)
    np.save(out_dir / "y_test.npy", y_test)

    results       = []
    best_fold_auc = -np.inf
    best_fold_idx = None
    best_state    = None
    best_scaler   = None

    fold_bar = tqdm(
        enumerate(purged_embargo_splits(len(X_cv), N_SPLITS, PURGE_BARS, EMBARGO_BARS, fold_size)),
        total=N_SPLITS, desc=f"  {direction_label}", unit="fold"
    )

    for fold, (train_idx, val_idx, _) in fold_bar:
        X_train, X_val = X_cv[train_idx], X_cv[val_idx]
        y_train, y_val = y_cv[train_idx], y_cv[val_idx]

        scaler  = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_val   = scaler.transform(X_val)

        train_dl = DataLoader(
            TensorDataset(torch.tensor(X_train), torch.tensor(y_train)),
            batch_size=BATCH_SIZE, shuffle=False
        )
        val_dl = DataLoader(
            TensorDataset(torch.tensor(X_val), torch.tensor(y_val)),
            batch_size=BATCH_SIZE
        )

        pos_weight = torch.tensor([(y_train == 0).sum() / (y_train == 1).sum()]).to(device)
        criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        model      = MLP(input_dim=len(FEATURE_COLS)).to(device)
        optimizer  = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
        scheduler  = build_scheduler(optimizer, WARMUP_EPOCHS, EPOCHS, LR, LR_MIN)

        best_val_loss, fold_best_state, patience_count = np.inf, None, 0
        train_losses, val_losses = [], []

        for epoch in range(EPOCHS):
            train_loss = train_epoch(model, train_dl, optimizer, criterion, device)
            val_loss, _, _, _ = evaluate(model, val_dl, criterion, device)
            scheduler.step()
            train_losses.append(train_loss)
            val_losses.append(val_loss)

            if val_loss < best_val_loss:
                best_val_loss   = val_loss
                fold_best_state = {k: v.clone() for k, v in model.state_dict().items()}
                fold_best_scaler = pickle.loads(pickle.dumps(scaler))
                patience_count  = 0
            else:
                patience_count += 1
            if patience_count >= PATIENCE:
                break

        model.load_state_dict(fold_best_state)
        _, y_true, y_pred, y_prob = evaluate(model, val_dl, criterion, device)

        acc = accuracy_score(y_true, y_pred)
        f1  = f1_score(y_true, y_pred, zero_division=0)
        auc = roc_auc_score(y_true, y_prob)

        results.append({"fold": fold+1, "acc": acc, "f1": f1, "auc": auc,
                        "train_n": len(train_idx), "val_n": len(val_idx)})

        plot_fold_loss(train_losses, val_losses, fold+1, auc, out_dir)
        fold_bar.set_postfix(acc=f"{acc:.4f}", f1=f"{f1:.4f}", auc=f"{auc:.4f}")

        if auc > best_fold_auc:
            best_fold_auc = auc
            best_fold_idx = fold + 1
            best_state    = {k: v.clone() for k, v in model.state_dict().items()}
            best_scaler   = fold_best_scaler

    # Save
    torch.save(best_state, out_dir / "model_best.pt")
    with open(out_dir / "scaler_best.pkl", "wb") as f:
        pickle.dump(best_scaler, f)

    res_df = pd.DataFrame(results)
    res_df.to_csv(out_dir / "results_cv.csv", index=False)

    config = {
        "direction": direction_label,
        "epochs": EPOCHS, "batch_size": BATCH_SIZE,
        "lr": LR, "lr_min": LR_MIN, "warmup_epochs": WARMUP_EPOCHS,
        "weight_decay": WEIGHT_DECAY, "patience": PATIENCE,
        "n_splits": N_SPLITS, "purge_bars": PURGE_BARS,
        "embargo_bars": EMBARGO_BARS, "test_size": TEST_SIZE,
        "n_features": len(FEATURE_COLS), "n_samples": len(X),
        "n_cv": len(X_cv), "n_test": len(X_test),
        "naive_acc": naive_acc, "feature_cols": FEATURE_COLS,
        "best_fold": best_fold_idx, "best_fold_val_auc": best_fold_auc,
        "output_dir": str(out_dir.resolve()),
    }
    with open(out_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n  -- CV Summary ({direction_label}) --")
    print(res_df.to_string(index=False))
    print(f"  Best fold: {best_fold_idx}  (val AUC {best_fold_auc:.4f})")
    print(f"  Naive acc: {naive_acc:.4f}")
    plot_cv_summary(results, naive_acc, out_dir, direction_label)
    print(f"  Artifacts -> {out_dir.resolve()}")


# ── 7. MAIN ───────────────────────────────────────────────────────────────────

def run():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    print("=" * 52)
    print("  ZONA MLP -- DIRECTION SPLIT")
    print("=" * 52)
    print(f"  Device        : {device}")
    print(f"  Features      : {len(FEATURE_COLS)}")
    print(f"  Epochs        : {EPOCHS}  Patience: {PATIENCE}")
    print(f"  Batch size    : {BATCH_SIZE}  LR: {LR}")
    print(f"  Architecture  : {len(FEATURE_COLS)} -> 64 -> 32 -> 1  Dropout: 0.3")
    print(f"  N splits      : {N_SPLITS}  Fold size: {FOLD_SIZE or 'auto'} / 2 per direction")
    print(f"  Purge/Embargo : {PURGE_BARS} / {EMBARGO_BARS} bars")
    print(f"  Test size     : {TEST_SIZE*100:.0f}%")
    print("=" * 52)

    df = pd.read_csv(DATA_FILE).dropna().reset_index(drop=True)

    for direction_val, direction_label, subdir in [
        ( 1, "Long",  "long"),
        (-1, "Short", "short"),
    ]:
        print(f"\n{'='*52}")
        print(f"  Training: {direction_label} trades")
        print(f"{'='*52}")
        df_dir  = df[df["direction"] == direction_val].reset_index(drop=True)
        out_dir = BASE_DIR / subdir
        train_direction(df_dir, direction_label, out_dir, device)


if __name__ == "__main__":
    run()
