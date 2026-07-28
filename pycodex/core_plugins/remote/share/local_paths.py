"""Local checkout-path cache for shared remote plugins.

Rust owner: ``codex-core-plugins::remote::share::local_paths``.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


PLUGIN_SHARE_LOCAL_PATHS_FILE = ".tmp/plugin-share-local-paths-v1.json"
_LOCK = threading.Lock()


def load_plugin_share_local_paths(codex_home: Path) -> dict[str, Path]:
    with _LOCK:
        return _read_plugin_share_local_paths(Path(codex_home))


def record_plugin_share_local_path(
    codex_home: Path,
    remote_plugin_id: str,
    plugin_path: Path,
) -> None:
    with _LOCK:
        mapping = _read_plugin_share_local_paths_for_update(Path(codex_home))
        mapping[str(remote_plugin_id)] = Path(plugin_path)
        _write_plugin_share_local_paths(Path(codex_home), mapping)


def remove_plugin_share_local_path(
    codex_home: Path,
    remote_plugin_id: str,
) -> None:
    with _LOCK:
        mapping = _read_plugin_share_local_paths_for_update(Path(codex_home))
        mapping.pop(str(remote_plugin_id), None)
        _write_plugin_share_local_paths(Path(codex_home), mapping)


def _read_plugin_share_local_paths(codex_home: Path) -> dict[str, Path]:
    path = _plugin_share_local_paths_path(codex_home)
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    try:
        payload = json.loads(contents)
        raw_mapping = payload.get("localPluginPathsByRemotePluginId", {})
        if not isinstance(raw_mapping, dict):
            raise TypeError("localPluginPathsByRemotePluginId must be an object")
        return {
            str(remote_id): Path(plugin_path)
            for remote_id, plugin_path in raw_mapping.items()
            if isinstance(plugin_path, str)
        }
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        raise ValueError(
            f"failed to parse plugin share local path mapping {path}: {exc}"
        ) from exc


def _read_plugin_share_local_paths_for_update(
    codex_home: Path,
) -> dict[str, Path]:
    try:
        return _read_plugin_share_local_paths(codex_home)
    except ValueError:
        return {}


def _write_plugin_share_local_paths(
    codex_home: Path,
    mapping: dict[str, Path],
) -> None:
    path = _plugin_share_local_paths_path(codex_home)
    if not mapping:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return

    payload = {
        "localPluginPathsByRemotePluginId": {
            remote_id: str(plugin_path)
            for remote_id, plugin_path in sorted(mapping.items())
        }
    }
    contents = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _plugin_share_local_paths_path(codex_home: Path) -> Path:
    return codex_home / PLUGIN_SHARE_LOCAL_PATHS_FILE


__all__ = [
    "PLUGIN_SHARE_LOCAL_PATHS_FILE",
    "load_plugin_share_local_paths",
    "record_plugin_share_local_path",
    "remove_plugin_share_local_path",
]
