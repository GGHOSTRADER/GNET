# train.py
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
import wandb

from dotenv import load_dotenv
import os
load_dotenv(Path(__file__).parent / ".env")

from pipeline_paths import FEATURES_FILE as DATA_FILE, MODEL_DIR as OUTPUT_DIR
RANDOM_SEED    = int(os.getenv("RANDOM_SEED",    "42"))
BATCH_SIZE     = int(os.getenv("BATCH_SIZE",     "64"))
EPOCHS         = int(os.getenv("EPOCHS",         "100"))
LR             = float(os.getenv("LR",           "1e-3"))
LR_MIN         = float(os.getenv("LR_MIN",       "1e-6"))
WARMUP_EPOCHS  = int(os.getenv("WARMUP_EPOCHS",  "10"))
N_SPLITS       = int(os.getenv("N_SPLITS",       "5"))
EMBARGO_BARS   = int(os.getenv("EMBARGO_BARS",   "60"))
PURGE_BARS     = int(os.getenv("PURGE_BARS",     "20"))
PATIENCE       = int(os.getenv("PATIENCE",       "15"))
WEIGHT_DECAY   = float(os.getenv("WEIGHT_DECAY", "1e-2"))
TEST_SIZE      = float(os.getenv("TEST_SIZE",    "0.10"))
WANDB_PROJECT  = os.getenv("WANDB_PROJECT",  "mlp-metalabel")
WANDB_RUN_NAME = os.getenv("WANDB_RUN_NAME", "mlp-baseline")

torch.manual_seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

FEATURE_COLS = [
    "parkinson_vol_5", "parkinson_vol_15", "parkinson_vol_30",
    "ofi_5", "ofi_15", "ofi_30",
    "volume_percentile", "volume_momentum",
    "amihud_illiquidity", "vwap_distance",
    "minutes_since_open", "is_first_last_30min", "day_of_week",
]

# ── 1. SPLITS ─────────────────────────────────────────────────────────────────

def split_test(X, y, test_size, purge, embargo):
    n_total = len(X)
    n_test  = int(n_total * test_size)
    gap     = purge + embargo
    n_cv    = n_total - n_test - gap
    if n_cv <= 0:
        raise ValueError(f"Dataset too small for test split + gap of {gap} bars.")
    return X[:n_cv], y[:n_cv], X[n_cv + gap:], y[n_cv + gap:]


def purged_embargo_splits(n_samples, n_splits, purge, embargo):
    indices   = np.arange(n_samples)
    fold_size = n_samples // (n_splits + 1)
    for i in range(1, n_splits + 1):
        val_start = i * fold_size
        val_end   = val_start + fold_size
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


# ── 5. NAIVE BASELINE ─────────────────────────────────────────────────────────

def naive_baseline(y_true):
    from sklearn.metrics import classification_report
    majority = int(np.round(y_true.mean()))
    preds    = np.full_like(y_true, majority)
    print("\n── Naive baseline (majority class) ──────────────────")
    print(classification_report(y_true, preds, digits=4))
    return accuracy_score(y_true, preds)


# ── 6. SAVE HELPERS ───────────────────────────────────────────────────────────

def save_config(out_dir, config):
    path = out_dir / "config.json"
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Saved → {path}")


def save_cv_results(out_dir, results, naive_acc):
    res_df  = pd.DataFrame(results)
    summary = {"fold": "mean", "acc": res_df.acc.mean(), "f1": res_df.f1.mean(),
               "auc": res_df.auc.mean(), "train_n": "", "val_n": ""}
    std_row = {"fold": "std",  "acc": res_df.acc.std(),  "f1": res_df.f1.std(),
               "auc": res_df.auc.std(),  "train_n": "", "val_n": ""}
    base    = {"fold": "baseline", "acc": naive_acc, "f1": "", "auc": "",
               "train_n": "", "val_n": ""}
    full_df = pd.concat([res_df, pd.DataFrame([summary, std_row, base])], ignore_index=True)
    path    = out_dir / "results_cv.csv"
    full_df.to_csv(path, index=False)
    print(f"Saved → {path}")
    return res_df


# ── 7. MAIN ───────────────────────────────────────────────────────────────────

def run():
    device  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Device    : {device}")
    print(f"Output dir: {out_dir.resolve()}")

    df = pd.read_csv(DATA_FILE).dropna().reset_index(drop=True)
    X  = df[FEATURE_COLS].values.astype(np.float32)
    y  = df["Label"].values.astype(np.float32)

    X_cv, y_cv, X_test, y_test = split_test(X, y, TEST_SIZE, PURGE_BARS, EMBARGO_BARS)
    gap = PURGE_BARS + EMBARGO_BARS
    print(f"\nTotal   : {len(X)} samples")
    print(f"CV pool : {len(X_cv)} samples")
    print(f"Gap     : {gap} bars discarded ({gap * 30 // 60} min)")
    print(f"Test    : {len(X_test)} samples — frozen until evaluate.py")

    np.save(out_dir / "X_test.npy", X_test)
    np.save(out_dir / "y_test.npy", y_test)
    print(f"Saved → X_test.npy + y_test.npy")

    naive_acc = naive_baseline(y_cv)

    config = {
        "epochs": EPOCHS, "batch_size": BATCH_SIZE,
        "lr": LR, "lr_min": LR_MIN, "warmup_epochs": WARMUP_EPOCHS,
        "weight_decay": WEIGHT_DECAY, "patience": PATIENCE,
        "n_splits": N_SPLITS, "purge_bars": PURGE_BARS,
        "embargo_bars": EMBARGO_BARS, "test_size": TEST_SIZE,
        "cv_test_gap_bars": gap, "cv_test_gap_mins": gap * 30 // 60,
        "n_features": len(FEATURE_COLS), "n_samples": len(X),
        "n_cv": len(X_cv), "n_test": len(X_test),
        "naive_acc": naive_acc, "feature_cols": FEATURE_COLS,
        "output_dir": str(out_dir.resolve()),
    }
    save_config(out_dir, config)
    wandb.init(project=WANDB_PROJECT, name=WANDB_RUN_NAME, config=config)

    results          = []
    best_fold_auc    = -np.inf
    best_fold_idx    = None
    best_model_state = None
    best_scaler      = None

    fold_bar = tqdm(
        enumerate(purged_embargo_splits(len(X_cv), N_SPLITS, PURGE_BARS, EMBARGO_BARS)),
        total=N_SPLITS, desc="Folds", unit="fold"
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

        best_val_loss, best_state, patience_count = np.inf, None, 0

        epoch_bar = tqdm(range(EPOCHS), desc=f"  Fold {fold+1}", leave=False, unit="ep")
        for epoch in epoch_bar:
            train_loss = train_epoch(model, train_dl, optimizer, criterion, device)
            val_loss, _, _, _ = evaluate(model, val_dl, criterion, device)
            current_lr = scheduler.get_last_lr()[0]
            scheduler.step()

            wandb.log({
                f"fold_{fold+1}/train_loss": train_loss,
                f"fold_{fold+1}/val_loss":   val_loss,
                f"fold_{fold+1}/lr":         current_lr,
                "epoch": epoch,
            })

            epoch_bar.set_postfix(
                train=f"{train_loss:.4f}",
                val=f"{val_loss:.4f}",
                lr=f"{current_lr:.2e}",
                patience=f"{patience_count}/{PATIENCE}",
            )

            if val_loss < best_val_loss:
                best_val_loss  = val_loss
                best_state     = {k: v.clone() for k, v in model.state_dict().items()}
                patience_count = 0
            else:
                patience_count += 1
            if patience_count >= PATIENCE:
                epoch_bar.set_postfix(
                    train=f"{train_loss:.4f}",
                    val=f"{val_loss:.4f}",
                    stopped=f"ep{epoch+1}"
                )
                break

        model.load_state_dict(best_state)
        torch.save(best_state, out_dir / f"model_fold_{fold+1}.pt")
        with open(out_dir / f"scaler_fold_{fold+1}.pkl", "wb") as f:
            pickle.dump(scaler, f)

        _, y_true, y_pred, y_prob = evaluate(model, val_dl, criterion, device)

        acc = accuracy_score(y_true, y_pred)
        f1  = f1_score(y_true, y_pred)
        auc = roc_auc_score(y_true, y_prob)
        results.append({"fold": fold+1, "acc": acc, "f1": f1, "auc": auc,
                        "train_n": len(train_idx), "val_n": len(val_idx)})

        if auc > best_fold_auc:
            best_fold_auc    = auc
            best_fold_idx    = fold + 1
            best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
            best_scaler      = pickle.loads(pickle.dumps(scaler))

        wandb.log({
            f"fold_{fold+1}/acc": acc,
            f"fold_{fold+1}/f1":  f1,
            f"fold_{fold+1}/auc": auc,
        })

        fold_bar.set_postfix(acc=f"{acc:.4f}", f1=f"{f1:.4f}", auc=f"{auc:.4f}")

    res_df = save_cv_results(out_dir, results, naive_acc)

    torch.save(best_model_state, out_dir / "model_best.pt")
    with open(out_dir / "scaler_best.pkl", "wb") as f:
        pickle.dump(best_scaler, f)

    config["best_fold"]         = best_fold_idx
    config["best_fold_val_auc"] = best_fold_auc
    save_config(out_dir, config)

    wandb.log({
        "summary/mean_acc": res_df.acc.mean(), "summary/mean_f1": res_df.f1.mean(),
        "summary/mean_auc": res_df.auc.mean(), "summary/naive_acc": naive_acc,
        "cv/best_fold": best_fold_idx, "cv/best_fold_val_auc": best_fold_auc,
    })
    wandb.finish()

    print("\n── CV summary ───────────────────────────────────────")
    print(res_df.to_string(index=False))
    print(f"\nBest fold : {best_fold_idx}  (val AUC {best_fold_auc:.4f})")
    print(f"Naive acc : {naive_acc:.4f}")
    print(f"\nAll artifacts saved to: {out_dir.resolve()}")
    print("Run evaluate.py to test on the held-out set.")


if __name__ == "__main__":
    run()