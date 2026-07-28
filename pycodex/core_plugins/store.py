"""Installed plugin cache for ``codex-core-plugins::store``."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pycodex.plugin import PluginId, PluginIdError, validate_plugin_segment
from pycodex.utils.plugins import find_plugin_manifest_path

from .manifest import load_plugin_manifest

DEFAULT_PLUGIN_VERSION = "local"
PLUGINS_CACHE_DIR = "plugins/cache"
PLUGINS_DATA_DIR = "plugins/data"


@dataclass(frozen=True)
class PluginInstallResult:
    plugin_id: PluginId
    plugin_version: str
    installed_path: Path


class PluginStoreError(Exception):
    pass


class PluginStore:
    def __init__(self, codex_home: str | Path) -> None:
        home = Path(codex_home)
        if not home.is_absolute():
            raise PluginStoreError("plugin cache root should be absolute")
        self._root = home / PLUGINS_CACHE_DIR
        self._data_root = home / PLUGINS_DATA_DIR

    @classmethod
    def new(cls, codex_home: str | Path) -> "PluginStore":
        return cls(codex_home)

    @classmethod
    def try_new(cls, codex_home: str | Path) -> "PluginStore":
        return cls(codex_home)

    def root(self) -> Path:
        return self._root

    def plugin_base_root(self, plugin_id: PluginId) -> Path:
        return self._root / plugin_id.marketplace_name / plugin_id.plugin_name

    def plugin_root(self, plugin_id: PluginId, plugin_version: str) -> Path:
        validate_plugin_version_segment(plugin_version)
        return self.plugin_base_root(plugin_id) / plugin_version

    def plugin_data_root(self, plugin_id: PluginId) -> Path:
        return self._data_root / f"{plugin_id.plugin_name}-{plugin_id.marketplace_name}"

    def active_plugin_version(self, plugin_id: PluginId) -> str | None:
        base = self.plugin_base_root(plugin_id)
        try:
            versions = [
                path.name
                for path in base.iterdir()
                if path.is_dir() and _valid_plugin_version(path.name)
            ]
        except OSError:
            return None
        if DEFAULT_PLUGIN_VERSION in versions:
            return DEFAULT_PLUGIN_VERSION
        return max(versions, key=_version_key) if versions else None

    def active_plugin_root(self, plugin_id: PluginId) -> Path | None:
        version = self.active_plugin_version(plugin_id)
        return self.plugin_root(plugin_id, version) if version is not None else None

    def is_installed(self, plugin_id: PluginId) -> bool:
        return self.active_plugin_version(plugin_id) is not None

    def install(self, source_path: str | Path, plugin_id: PluginId) -> PluginInstallResult:
        source = Path(source_path)
        return self.install_with_version(
            source,
            plugin_id,
            plugin_version_for_source(source),
        )

    def install_with_version(
        self,
        source_path: str | Path,
        plugin_id: PluginId,
        plugin_version: str,
    ) -> PluginInstallResult:
        source = Path(source_path)
        if not source.is_dir():
            raise PluginStoreError(f"plugin source path is not a directory: {source}")
        manifest = load_plugin_manifest(source)
        if manifest is None:
            raise PluginStoreError("missing or invalid plugin.json")
        try:
            validate_plugin_segment(manifest.name, "plugin name")
        except PluginIdError as exc:
            raise PluginStoreError(str(exc)) from exc
        if manifest.name != plugin_id.plugin_name:
            raise PluginStoreError(
                f"plugin.json name `{manifest.name}` does not match marketplace plugin "
                f"name `{plugin_id.plugin_name}`"
            )
        validate_plugin_version_segment(plugin_version)

        target = self.plugin_root(plugin_id, plugin_version)
        _replace_plugin_root_atomically(
            source,
            self.plugin_base_root(plugin_id),
            plugin_version,
        )
        return PluginInstallResult(plugin_id, plugin_version, target)

    def uninstall(self, plugin_id: PluginId) -> None:
        _remove_existing_target(self.plugin_base_root(plugin_id))


def _remove_existing_target(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _replace_plugin_root_atomically(
    source: Path,
    target_root: Path,
    plugin_version: str,
) -> None:
    parent = target_root.parent
    parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix="plugin-install-", dir=parent))
    staged_root = staging / target_root.name
    staged_version_root = staged_root / plugin_version
    backup: Path | None = None
    try:
        shutil.copytree(source, staged_version_root)
        target_version_root = target_root / plugin_version

        if target_root.exists() and not target_version_root.exists():
            try:
                staged_version_root.rename(target_version_root)
            except OSError as exc:
                raise PluginStoreError(
                    "failed to activate updated plugin cache version"
                ) from exc
            _remove_old_plugin_versions(target_root, plugin_version)
            return

        if target_root.exists():
            backup = Path(tempfile.mkdtemp(prefix="plugin-backup-", dir=parent))
            backup_root = backup / target_root.name
            try:
                target_root.rename(backup_root)
            except OSError as exc:
                raise PluginStoreError(
                    "failed to back up plugin cache entry"
                ) from exc
            try:
                staged_root.rename(target_root)
            except OSError as exc:
                try:
                    backup_root.rename(target_root)
                except OSError as rollback_exc:
                    raise PluginStoreError(
                        "failed to activate updated plugin cache entry; "
                        f"failed to restore previous cache entry at {backup_root}"
                    ) from rollback_exc
                raise PluginStoreError(
                    "failed to activate updated plugin cache entry"
                ) from exc
        else:
            try:
                staged_root.rename(target_root)
            except OSError as exc:
                raise PluginStoreError(
                    "failed to activate plugin cache entry"
                ) from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)


def _remove_old_plugin_versions(target_root: Path, plugin_version: str) -> None:
    try:
        children = tuple(target_root.iterdir())
    except OSError:
        return
    for child in children:
        if child.is_dir() and child.name != plugin_version and _valid_plugin_version(child.name):
            shutil.rmtree(child)


def plugin_version_for_source(source_path: str | Path) -> str:
    manifest_path = find_plugin_manifest_path(source_path)
    if manifest_path is None:
        raise PluginStoreError("missing plugin.json")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginStoreError(f"failed to parse plugin.json: {exc}") from exc
    version = raw.get("version") if isinstance(raw, dict) else None
    if version is None:
        return DEFAULT_PLUGIN_VERSION
    if not isinstance(version, str):
        raise PluginStoreError("invalid plugin version in plugin.json: expected string")
    version = version.strip()
    if not version:
        raise PluginStoreError("invalid plugin version in plugin.json: must not be blank")
    validate_plugin_version_segment(version)
    return version


def validate_plugin_version_segment(plugin_version: str) -> None:
    if not plugin_version:
        raise PluginStoreError("invalid plugin version: must not be empty")
    if plugin_version in {".", ".."}:
        raise PluginStoreError("invalid plugin version: path traversal is not allowed")
    if re.fullmatch(r"[A-Za-z0-9._+-]+", plugin_version) is None:
        raise PluginStoreError(
            "invalid plugin version: only ASCII letters, digits, `.`, `+`, `_`, "
            "and `-` are allowed"
        )


def _valid_plugin_version(value: str) -> bool:
    try:
        validate_plugin_version_segment(value)
    except PluginStoreError:
        return False
    return True


def _version_key(value: str) -> tuple[object, ...]:
    if re.fullmatch(r"\d+(?:\.\d+)*(?:[-+].*)?", value):
        core, _, suffix = value.partition("-")
        numbers = tuple(int(part) for part in core.split("."))
        return (1, numbers, suffix)
    return (0, value)


__all__ = [
    "DEFAULT_PLUGIN_VERSION",
    "PLUGINS_CACHE_DIR",
    "PLUGINS_DATA_DIR",
    "PluginInstallResult",
    "PluginStore",
    "PluginStoreError",
    "plugin_version_for_source",
    "validate_plugin_version_segment",
]
