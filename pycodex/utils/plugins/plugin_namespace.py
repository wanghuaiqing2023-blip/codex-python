"""Plugin namespace helpers ported from ``codex-rs/utils/plugins``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DISCOVERABLE_PLUGIN_MANIFEST_PATHS = (
    ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json",
)


@dataclass(frozen=True)
class PluginSkillRoot:
    path: Path
    plugin_id: str
    plugin_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _ensure_path(self.path, "path"))
        if not isinstance(self.plugin_id, str):
            raise TypeError("plugin_id must be a string")
        object.__setattr__(self, "plugin_root", _ensure_path(self.plugin_root, "plugin_root"))


def find_plugin_manifest_path(plugin_root: str | Path) -> Path | None:
    root = _ensure_path(plugin_root, "plugin_root")
    for relative_path in DISCOVERABLE_PLUGIN_MANIFEST_PATHS:
        manifest_path = root / Path(relative_path)
        if manifest_path.is_file():
            return manifest_path
    return None


def plugin_namespace_for_skill_path(path: str | Path) -> str | None:
    skill_path = _ensure_path(path, "path")
    for ancestor in (skill_path, *skill_path.parents):
        name = _plugin_manifest_name(ancestor)
        if name is not None:
            return name
    return None


def _plugin_manifest_name(plugin_root: Path) -> str | None:
    manifest_path = find_plugin_manifest_path(plugin_root)
    if manifest_path is None:
        return None
    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw_manifest, dict):
        return None
    raw_name = raw_manifest.get("name", "")
    if not isinstance(raw_name, str):
        return None
    if raw_name.strip():
        return raw_name
    return plugin_root.name or None


def _ensure_path(value: Any, label: str) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise TypeError(f"{label} must be a string or Path")


__all__ = [
    "DISCOVERABLE_PLUGIN_MANIFEST_PATHS",
    "PluginSkillRoot",
    "find_plugin_manifest_path",
    "plugin_namespace_for_skill_path",
]
