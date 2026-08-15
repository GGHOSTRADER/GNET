# evaluate.py
import numpy as np
import json
import pickle
from pathlib import Path
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, classification_report
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import wandb

from dotenv import load_dotenv
import os
load_dotenv(Path(__file__).parent / ".env")

from pipeline_paths import MODEL_DIR
EXPERIMENT_DIR = str(MODEL_DIR)
WANDB_PROJECT  = os.getenv("WANDB_PROJECT", "mlp-metalabel")

# ── MODEL (must match train.py) ───────────────────────────────────────────────

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


# ── EVAL ──────────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    all_preds, all_probs, all_labels = [], [], []
    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        probs   = torch.sigmoid(model(X_batch)).cpu().numpy()
        all_probs.extend(probs)
        all_preds.extend((probs >= 0.5).astype(int))
        all_labels.extend(y_batch.numpy())
    return np.array(all_labels), np.array(all_preds), np.array(all_probs)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run():
    device  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(EXPERIMENT_DIR)

    # Load config
    with open(out_dir / "config.json") as f:
        config = json.load(f)

    best_fold    = config["best_fold"]
    naive_acc    = config["naive_acc"]
    n_features   = config["n_features"]
    batch_size   = config["batch_size"]

    print(f"Experiment : {out_dir.resolve()}")
    print(f"Best fold  : {best_fold}  (val AUC {config['best_fold_val_auc']:.4f})")
    print(f"Test size  : {config['n_test']} samples")

    # Load test set
    X_test = np.load(out_dir / "X_test.npy").astype(np.float32)
    y_test = np.load(out_dir / "y_test.npy").astype(np.float32)

    # Load best scaler + model
    with open(out_dir / "scaler_best.pkl", "rb") as f:
        scaler = pickle.load(f)

    X_test_scaled = scaler.transform(X_test)

    model = MLP(input_dim=n_features).to(device)
    model.load_state_dict(torch.load(out_dir / "model_best.pt", map_location=device))

    test_dl = DataLoader(
        TensorDataset(torch.tensor(X_test_scaled), torch.tensor(y_test)),
        batch_size=batch_size
    )

    y_true, y_pred, y_prob = evaluate(model, test_dl, device)

    test_acc = accuracy_score(y_true, y_pred)
    test_f1  = f1_score(y_true, y_pred)
    test_auc = roc_auc_score(y_true, y_prob)

    print("\n── Test results ─────────────────────────────────────")
    print(classification_report(y_true, y_pred, digits=4))
    print(f"acc: {test_acc:.4f}  f1: {test_f1:.4f}  auc: {test_auc:.4f}")
    print(f"\nBaseline acc : {naive_acc:.4f}")
    print(f"Test acc     : {test_acc:.4f}  ({'↑ beats' if test_acc > naive_acc else '↓ loses to'} baseline)")

    # Save results
    results = {
        "best_fold": best_fold,
        "best_fold_val_auc": config["best_fold_val_auc"],
        "test_acc": test_acc, "test_f1": test_f1, "test_auc": test_auc,
        "naive_acc": naive_acc,
        "beats_baseline": int(test_acc > naive_acc),
    }
    results_path = out_dir / "results_test.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved → {results_path}")

    # Log to same W&B project
    wandb.init(project=WANDB_PROJECT, name=f"{out_dir.name}-test", config=config)
    wandb.log({
        "test/acc": test_acc, "test/f1": test_f1, "test/auc": test_auc,
        "test/beats_baseline": int(test_acc > naive_acc),
        "test/naive_acc": naive_acc,
    })
    wandb.finish()


if __name__ == "__main__":
    run()