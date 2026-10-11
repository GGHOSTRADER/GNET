"""Compare original entry-bar and prior-completed-bar models on identical trades."""

from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, roc_auc_score

from training_mlp.validation import EventIntervals, purged_chronological_holdout


ROOT = Path(__file__).resolve().parent / "strategies/MA2CrossLE"
ORIGINAL_DATA = ROOT / "processed/df_features_labeled_master_libb_ts_vwap.csv"
SHIFTED_DATA = ROOT / "processed/ma2cross_old_libb_prior_bar_13.csv"
ORIGINAL_MODEL = ROOT / "model/mlp_ts_vwap_libb"
SHIFTED_MODEL = ROOT / "model/mlp_old_libb_prior_bar_13_ablation"
OUTPUT = ROOT / "reports/old_libb_prior_bar_ablation"


def _predict(model_dir: Path, feature_rows: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    script = Path(__file__).with_name("30_training_mlp.py")
    spec = importlib.util.spec_from_file_location("gnet_ablation_training", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with (model_dir / "scaler_best.pkl").open("rb") as stream:
        scaler = pickle.load(stream)
    model = module.MLP(input_dim=len(feature_cols))
    model.load_state_dict(torch.load(model_dir / "model_best.pt", map_location="cpu"))
    model.eval()
    values = feature_rows[feature_cols].to_numpy(dtype=np.float32)
    saved_values = np.load(model_dir / "X_test.npy").astype(np.float32)
    if not np.allclose(values, saved_values):
        raise ValueError(f"holdout features do not match saved model: {model_dir}")
    with torch.no_grad():
        return torch.sigmoid(model(torch.from_numpy(scaler.transform(values).astype(np.float32)))).numpy()


def _holdout(frame: pd.DataFrame, test_size: float) -> np.ndarray:
    events = EventIntervals.from_arrays(
        pd.to_datetime(frame["Date/Time"]), pd.to_datetime(frame["t1"])
    )
    return purged_chronological_holdout(events, test_size=test_size).test_indices


def _summary(frame: pd.DataFrame, threshold: float, name: str) -> dict:
    approved = frame.loc[frame[f"prob_{name}"] >= threshold]
    zero = approved.loc[approved["entry_time"] == approved["exit_time"]]
    pnl = approved["net_pnl_at_3_24_per_side"]
    return {
        "model": name, "threshold": threshold,
        "approved": len(approved), "winners": int((pnl > 0).sum()),
        "win_rate": float((pnl > 0).mean()),
        "net_pnl": float(pnl.sum()), "mean_net_pnl": float(pnl.mean()),
        "same_timestamp_trades": len(zero),
        "same_timestamp_net_pnl": float(zero["net_pnl_at_3_24_per_side"].sum()),
    }


def evaluate(original_data: Path = ORIGINAL_DATA, shifted_data: Path = SHIFTED_DATA,
             original_model: Path = ORIGINAL_MODEL, shifted_model: Path = SHIFTED_MODEL,
             output: Path = OUTPUT) -> dict:
    original = pd.read_csv(original_data).dropna().reset_index(drop=True)
    shifted = pd.read_csv(shifted_data).dropna().reset_index(drop=True)
    if len(original) != len(shifted):
        raise ValueError("ablation changed the number of trades")
    if not np.array_equal(original["Label"], shifted["Label"]):
        raise ValueError("ablation changed trade labels or their order")
    if not np.array_equal(pd.to_datetime(original["Date/Time"]), pd.to_datetime(shifted["entry_time"])):
        raise ValueError("original events do not align with shifted entries")
    if not np.array_equal(pd.to_datetime(original["t1"]), pd.to_datetime(shifted["t1"])):
        raise ValueError("ablation changed trade exits")
    old_config = json.loads((original_model / "config.json").read_text(encoding="utf-8"))
    new_config = json.loads((shifted_model / "config.json").read_text(encoding="utf-8"))
    if old_config["feature_cols"] != new_config["feature_cols"]:
        raise ValueError("feature set changed")
    old_indices = _holdout(original, old_config["test_size"])
    new_indices = _holdout(shifted, new_config["test_size"])
    if not np.array_equal(old_indices, new_indices):
        raise ValueError("ablation changed the holdout population")
    original_holdout = original.iloc[old_indices]
    comparison = shifted.iloc[new_indices].copy()
    comparison["prob_original"] = _predict(original_model, original_holdout, old_config["feature_cols"])
    comparison["prob_prior_bar"] = _predict(shifted_model, comparison, new_config["feature_cols"])
    y = comparison["Label"].to_numpy()
    old_auc = float(roc_auc_score(y, comparison["prob_original"]))
    new_auc = float(roc_auc_score(y, comparison["prob_prior_bar"]))
    reported_old_auc = json.loads((original_model / "results_test.json").read_text(encoding="utf-8"))["test_auc"]
    if abs(old_auc - reported_old_auc) > 1e-6:
        raise ValueError("original holdout AUC cannot be reproduced")
    summaries = [
        _summary(comparison, threshold, name)
        for threshold in (0.50, 0.52)
        for name in ("original", "prior_bar")
    ]
    original_at_052 = next(row for row in summaries if row["model"] == "original" and row["threshold"] == 0.52)
    reported_old_net = json.loads(
        (original_model.parent.parent / "reports/real_cost_threshold_selection/holdout_results.json").read_text(encoding="utf-8")
    )["net_profit"]
    if abs(original_at_052["net_pnl"] - reported_old_net) > 0.01:
        raise ValueError("original holdout net P/L cannot be reproduced")
    output.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(output / "identical_holdout_trade_predictions.csv", index=False)
    pd.DataFrame(summaries).to_csv(output / "threshold_comparison.csv", index=False)
    old_cv = pd.read_csv(original_model / "results_cv.csv")
    new_cv = pd.read_csv(shifted_model / "results_cv.csv")
    result = {
        "original_model": str(original_model.resolve()),
        "prior_bar_model": str(shifted_model.resolve()),
        "holdout_trades": len(comparison),
        "holdout_first_entry": str(comparison["entry_time"].min()),
        "holdout_last_entry": str(comparison["entry_time"].max()),
        "original_cv_mean_auc": float(old_cv.loc[old_cv["fold"] == "mean", "auc"].iloc[0]),
        "prior_bar_cv_mean_auc": float(new_cv.loc[new_cv["fold"] == "mean", "auc"].iloc[0]),
        "original_holdout_auc": old_auc,
        "prior_bar_holdout_auc": new_auc,
        "original_holdout_accuracy_at_050": float(accuracy_score(y, comparison["prob_original"] >= 0.5)),
        "prior_bar_holdout_accuracy_at_050": float(accuracy_score(y, comparison["prob_prior_bar"] >= 0.5)),
        "unfiltered_holdout_net_pnl": float(comparison["net_pnl_at_3_24_per_side"].sum()),
        "thresholds": summaries,
    }
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-data", type=Path, default=ORIGINAL_DATA)
    parser.add_argument("--shifted-data", type=Path, default=SHIFTED_DATA)
    parser.add_argument("--original-model", type=Path, default=ORIGINAL_MODEL)
    parser.add_argument("--shifted-model", type=Path, default=SHIFTED_MODEL)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.original_data, args.shifted_data, args.original_model,
                              args.shifted_model, args.output), indent=2))


if __name__ == "__main__":
    main()
