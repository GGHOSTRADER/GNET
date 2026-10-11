"""Verify the pinned MA-13 Python, registry, scaler, and model runtime."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys


EXPECTED_PYTHON = (3, 12, 7)
EXPECTED_PACKAGES = {
    "redis": "7.4.0",
    "numpy": "1.26.4",
    "scipy": "1.13.1",
    "scikit-learn": "1.8.0",
    "joblib": "1.4.2",
    "threadpoolctl": "3.5.0",
    "torch": "2.12.0",
}
EXPECTED_TRAINING_PACKAGES = {
    "pytest": "7.4.4",
    "pandas": "2.3.2",
    "pyarrow": "16.1.0",
    "matplotlib": "3.9.4",
    "python-dotenv": "0.21.0",
    "tqdm": "4.66.5",
    "xgboost": "3.3.0",
    "wandb": "0.29.0",
}


def verify(
    root: Path, *, include_training: bool = False, pre_training: bool = False
) -> list[str]:
    """Return all runtime contract failures; an empty list means success."""
    failures: list[str] = []
    if sys.version_info[:3] != EXPECTED_PYTHON:
        failures.append(
            f"Python is {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; "
            f"expected {'.'.join(map(str, EXPECTED_PYTHON))}"
        )
    expected_packages = dict(EXPECTED_PACKAGES)
    if include_training:
        expected_packages.update(EXPECTED_TRAINING_PACKAGES)
    for package, expected in expected_packages.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            failures.append(f"missing Python package: {package}=={expected}")
            continue
        if actual != expected:
            failures.append(f"{package} is {actual}; expected {expected}")

    if failures:
        return failures

    sys.path.insert(0, str(root))
    try:
        from feat_files.canonical_features import FEATURE_NAMES
        if pre_training:
            templates = list((root / "model_registry").glob("*/registry.template.json"))
            if len(templates) != 1:
                failures.append(
                    f"expected exactly one local-training registry template; found {len(templates)}"
                )
                return failures
            template = json.loads(templates[0].read_text(encoding="utf-8"))
            if template.get("enabled") is not False:
                failures.append("local-training registry template must remain disabled")
            prohibited = []
            for pattern in ("model_best.pt", "scaler_best.pkl", "X_test.npy", "y_test.npy"):
                prohibited.extend(root.glob(f"training_mlp/strategies/**/{pattern}"))
            if prohibited:
                failures.append(
                    "pre-training package contains excluded model artifacts: "
                    + ", ".join(str(path.relative_to(root)) for path in prohibited)
                )
            if len(FEATURE_NAMES) != 13:
                failures.append("canonical MA feature contract does not contain 13 features")
            return failures
        from inference.model_registry import discover_registry
        from inference.strategy_router import StrategyModel

        entries, registry_errors = discover_registry(root / "model_registry")
        failures.extend(registry_errors)
        enabled = [entry for entry in entries if entry.enabled]
        if len(enabled) != 1:
            failures.append(
                f"expected exactly one enabled registry entry; found {len(enabled)}"
            )
            return failures
        entry = enabled[0]
        if entry.strategy_id != "MA2CrossLE":
            failures.append(f"enabled strategy is {entry.strategy_id}; expected MA2CrossLE")
        if entry.threshold != 0.5:
            failures.append(f"MA2CrossLE threshold is {entry.threshold}; expected 0.5")
        config_path = entry.artifact_dir / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config.get("n_features") != 13:
            failures.append("MA2CrossLE model does not declare 13 features")
        if config.get("feature_cols") != list(FEATURE_NAMES):
            failures.append("MA2CrossLE feature order differs from the canonical contract")
        if not failures:
            runtime = StrategyModel(entry.model_settings())
            fields = {name: "0" for name in FEATURE_NAMES}
            approved, probability = runtime.infer(fields)
            if not isinstance(approved, bool) or not 0.0 <= probability <= 1.0:
                failures.append("synthetic model inference returned an invalid result")
    except Exception as exc:
        failures.append(f"runtime load/inference failed: {exc}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--include-training", action="store_true")
    parser.add_argument("--pre-training", action="store_true")
    args = parser.parse_args()
    failures = verify(
        args.root.resolve(),
        include_training=args.include_training,
        pre_training=args.pre_training,
    )
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        raise SystemExit(1)
    print("[PASS] Python and pinned package versions")
    if args.include_training:
        print("[PASS] Pinned training and analysis package versions")
    if args.pre_training:
        print("[PASS] Disabled local-training registry template")
        print("[PASS] Reference data and trained-model artifacts are absent")
        print("[PASS] Canonical 13-feature training contract")
    else:
        print("[PASS] Enabled MA2CrossLE registry entry and threshold 0.50")
        print("[PASS] Canonical 13-feature model/scaler load and synthetic inference")


if __name__ == "__main__":
    main()
