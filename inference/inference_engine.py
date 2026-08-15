"""
inference_engine.py
===================

Reads from the features_transformer Redis stream, runs the pretrained MLP,
and writes trade signals to the trade_signal Redis stream.

Flow
----
  features_transformer (Redis) -> scale -> MLP -> trade_signal (Redis)

Signal schema written to trade_signal
--------------------------------------
  symbol   : str
  signal   : "1" (buy) or "0" (no trade)
  prob     : float str  -- sigmoid probability
  date     : int str    -- YYYYMMDD
  time_s   : int str    -- seconds since midnight
  bar_num  : int str

Run
---
  python -m inference.inference_engine
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from config.setting import (
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_FEATURES_TRANSFORMER_STREAM,
    REDIS1_SIGNAL_STREAM,
)
from netwo_files.redis_tool import get_redis_connection
from feat_files.canonical_features import FEATURE_NAMES

# ── INJECTIBLE ────────────────────────────────────────────────────────────────
EXPERIMENT_DIR = Path("training_mlp/strategies/MA2CrossLE/model/mlp_baseline")
MODEL_FILE     = EXPERIMENT_DIR / "model_best.pt"
SCALER_FILE    = EXPERIMENT_DIR / "scaler_best.pkl"
CONFIG_FILE    = EXPERIMENT_DIR / "config.json"
THRESHOLD      = 0.5   # sigmoid probability threshold for buy signal
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_COLS = list(FEATURE_NAMES)


# ── Model definition (must match training) ────────────────────────────────────

class MLP(nn.Module):
    def __init__(self, input_dim: int, hidden_dims=(64, 32), dropout=0.3):
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_fields(fields: dict) -> np.ndarray:
    """Build the 13-feature vector from a features_transformer Redis entry."""
    row = [float(fields[col]) for col in FEATURE_COLS]
    return np.array(row, dtype=np.float32).reshape(1, -1)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    with open(SCALER_FILE, "rb") as f:
        scaler = pickle.load(f)

    with open(CONFIG_FILE) as f:
        cfg = json.load(f)

    model = MLP(input_dim=cfg["n_features"]).to(device)
    model.load_state_dict(torch.load(MODEL_FILE, map_location=device))
    model.eval()

    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_FEATURES_TRANSFORMER_STREAM)
    r_out = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_SIGNAL_STREAM)

    print(
        f"[inference] Ready\n"
        f"  model   : {MODEL_FILE}\n"
        f"  device  : {device}\n"
        f"  threshold: {THRESHOLD}\n"
        f"  reading : {REDIS1_FEATURES_TRANSFORMER_STREAM}\n"
        f"  writing : {REDIS1_SIGNAL_STREAM}\n"
    )

    last_id = "$"

    while True:
        result = r.xread({REDIS1_FEATURES_TRANSFORMER_STREAM: last_id}, count=1, block=5000)
        if not result:
            continue

        _, entries = result[0]
        entry_id, fields = entries[0]
        last_id = entry_id

        try:
            X = _parse_fields(fields)
        except (KeyError, ValueError) as e:
            print(f"[inference] parse error: {e} | fields={fields}")
            continue

        X_scaled = scaler.transform(X).astype(np.float32)
        tensor = torch.tensor(X_scaled).to(device)

        with torch.no_grad():
            logit = model(tensor)
            prob  = torch.sigmoid(logit).item()

        signal = 1 if prob >= THRESHOLD else 0

        r_out.xadd(
            REDIS1_SIGNAL_STREAM,
            {
                "symbol":  fields.get("symbol", ""),
                "signal":  str(signal),
                "prob":    repr(prob),
                "date":    fields.get("date", ""),
                "time_s":  fields.get("time_s", ""),
                "bar_num": fields.get("bar_num", ""),
            },
            maxlen=500,
            approximate=True,
        )

        print(
            f"[inference] bar={fields.get('bar_num')} "
            f"prob={prob:.4f} signal={signal} "
            f"({'BUY' if signal else 'no trade'})"
        )


if __name__ == "__main__":
    run()
