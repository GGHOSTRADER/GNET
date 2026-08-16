"""Validated directory-backed strategy model registry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from threading import Lock


REGISTRY_ROOT = Path("model_registry")
_REPO_ROOT = Path(__file__).resolve().parents[1]
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_EDITABLE_FIELDS = {"enabled", "threshold", "device"}
_UPDATE_LOCK = Lock()


class RegistryError(ValueError):
    """A registry entry is malformed or references unavailable artifacts."""


@dataclass(frozen=True)
class RegistryEntry:
    strategy_id: str
    display_name: str
    enabled: bool
    model_type: str
    artifact_dir: Path
    threshold: float
    device: str
    feature_stream: str
    registry_file: Path

    def model_settings(self) -> dict:
        return {
            "model": self.artifact_dir / "model_best.pt",
            "scaler": self.artifact_dir / "scaler_best.pkl",
            "config": self.artifact_dir / "config.json",
            "threshold": self.threshold,
            "device": self.device,
        }


def _registry_root(root: Path = REGISTRY_ROOT) -> Path:
    return root if root.is_absolute() else _REPO_ROOT / root


def _parse_entry(registry_file: Path) -> RegistryEntry:
    try:
        data = json.loads(registry_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot read {registry_file}: {exc}") from exc
    if data.get("schema_version") != 1:
        raise RegistryError(f"{registry_file}: unsupported schema_version")
    strategy_id = data.get("strategy_id", "")
    if not _IDENTIFIER.fullmatch(strategy_id):
        raise RegistryError(f"{registry_file}: invalid strategy_id")
    if registry_file.parent.name != strategy_id:
        raise RegistryError(
            f"{registry_file}: directory must be named {strategy_id}"
        )
    threshold = float(data.get("threshold", 0.5))
    if not 0.0 <= threshold <= 1.0:
        raise RegistryError(f"{registry_file}: threshold must be between 0 and 1")
    device = data.get("device", "cpu")
    if device not in ("cpu", "cuda"):
        raise RegistryError(f"{registry_file}: device must be cpu or cuda")
    model_type = data.get("model_type", "")
    if model_type != "pytorch_mlp":
        raise RegistryError(f"{registry_file}: unsupported model_type {model_type!r}")
    artifact_dir = (_REPO_ROOT / data.get("artifact_dir", "")).resolve()
    missing = [
        name
        for name in ("model_best.pt", "scaler_best.pkl", "config.json")
        if not (artifact_dir / name).is_file()
    ]
    if missing:
        raise RegistryError(f"{registry_file}: missing artifacts {missing}")
    feature_stream = str(data.get("feature_stream", ""))
    if feature_stream != "features_transformer":
        raise RegistryError(
            f"{registry_file}: current router supports features_transformer only"
        )
    return RegistryEntry(
        strategy_id=strategy_id,
        display_name=str(data.get("display_name", strategy_id)),
        enabled=data.get("enabled") is True,
        model_type=model_type,
        artifact_dir=artifact_dir,
        threshold=threshold,
        device=device,
        feature_stream=feature_stream,
        registry_file=registry_file,
    )


def discover_registry(root: Path = REGISTRY_ROOT) -> tuple[list[RegistryEntry], list[str]]:
    entries: list[RegistryEntry] = []
    errors: list[str] = []
    resolved_root = _registry_root(root)
    if not resolved_root.exists():
        return entries, [f"registry directory not found: {resolved_root}"]
    for registry_file in sorted(resolved_root.glob("*/registry.json")):
        try:
            entries.append(_parse_entry(registry_file))
        except RegistryError as exc:
            errors.append(str(exc))
    return entries, errors


def enabled_model_settings(root: Path = REGISTRY_ROOT) -> dict[str, dict]:
    entries, errors = discover_registry(root)
    if errors:
        raise RegistryError("; ".join(errors))
    enabled = {entry.strategy_id: entry.model_settings() for entry in entries if entry.enabled}
    if not enabled:
        raise RegistryError("no enabled strategy models")
    return enabled


def update_registry_entry(
    strategy_id: str, changes: dict, root: Path = REGISTRY_ROOT
) -> RegistryEntry:
    if not _IDENTIFIER.fullmatch(strategy_id):
        raise RegistryError("invalid strategy_id")
    unknown = set(changes) - _EDITABLE_FIELDS
    if unknown:
        raise RegistryError(f"fields are not editable: {sorted(unknown)}")
    registry_file = _registry_root(root) / strategy_id / "registry.json"
    entry = _parse_entry(registry_file)
    with _UPDATE_LOCK:
        data = json.loads(registry_file.read_text(encoding="utf-8"))
        if "enabled" in changes:
            if not isinstance(changes["enabled"], bool):
                raise RegistryError("enabled must be boolean")
            data["enabled"] = changes["enabled"]
        if "threshold" in changes:
            threshold = float(changes["threshold"])
            if not 0.0 <= threshold <= 1.0:
                raise RegistryError("threshold must be between 0 and 1")
            data["threshold"] = threshold
        if "device" in changes:
            if changes["device"] not in ("cpu", "cuda"):
                raise RegistryError("device must be cpu or cuda")
            data["device"] = changes["device"]
        temporary = registry_file.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(registry_file)
    return _parse_entry(registry_file)
