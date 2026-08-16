import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from inference.model_registry import (
    RegistryError,
    discover_registry,
    enabled_model_settings,
    update_registry_entry,
)


@pytest.fixture
def registry_workspace():
    tests_root = Path(__file__).resolve().parent
    workspace = tests_root / ".tmp_model_registry" / uuid4().hex
    workspace.mkdir(parents=True)
    try:
        yield workspace
    finally:
        if workspace.is_relative_to(tests_root):
            shutil.rmtree(workspace, ignore_errors=True)


def _registry(tmp_path, *, enabled=True, threshold=0.5):
    root = tmp_path / "registry"
    strategy = root / "TestStrategy"
    artifacts = tmp_path / "artifacts"
    strategy.mkdir(parents=True)
    artifacts.mkdir()
    for name in ("model_best.pt", "scaler_best.pkl", "config.json"):
        (artifacts / name).write_text("test", encoding="utf-8")
    (strategy / "registry.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "strategy_id": "TestStrategy",
                "display_name": "Test Strategy",
                "enabled": enabled,
                "model_type": "pytorch_mlp",
                "artifact_dir": str(artifacts),
                "threshold": threshold,
                "device": "cpu",
                "feature_stream": "features_transformer",
            }
        ),
        encoding="utf-8",
    )
    return root


def test_discovers_valid_directory_entry(registry_workspace):
    entries, errors = discover_registry(_registry(registry_workspace))
    assert errors == []
    assert entries[0].strategy_id == "TestStrategy"
    assert entries[0].enabled is True


def test_enabled_settings_are_router_compatible(registry_workspace):
    settings = enabled_model_settings(_registry(registry_workspace))
    assert settings["TestStrategy"]["model"].name == "model_best.pt"
    assert settings["TestStrategy"]["threshold"] == 0.5


def test_browser_edit_updates_only_allowed_settings(registry_workspace):
    root = _registry(registry_workspace)
    entry = update_registry_entry(
        "TestStrategy", {"enabled": False, "threshold": 0.72, "device": "cpu"}, root
    )
    assert entry.enabled is False
    assert entry.threshold == 0.72


def test_rejects_unknown_edit_field(registry_workspace):
    root = _registry(registry_workspace)
    with pytest.raises(RegistryError, match="not editable"):
        update_registry_entry("TestStrategy", {"artifact_dir": "elsewhere"}, root)


def test_rejects_out_of_range_threshold(registry_workspace):
    with pytest.raises(RegistryError, match="between 0 and 1"):
        update_registry_entry(
            "TestStrategy", {"threshold": 1.5}, _registry(registry_workspace)
        )
