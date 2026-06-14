"""Approval payload conversion helpers for the TUI app-server bridge.

Upstream source: ``codex/codex-rs/tui/src/app_server_approval_conversions.rs``.
The Rust module performs narrow conversions between app-server permission/file
update payloads and TUI display models.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from ._porting import RustTuiModule
from .diff_model import FileChange

RUST_MODULE = RustTuiModule(crate="codex-tui", module="app_server_approval_conversions", source="codex/codex-rs/tui/src/app_server_approval_conversions.rs")


@dataclass(frozen=True)
class AdditionalNetworkPermissions:
    enabled: Optional[bool] = None


@dataclass(frozen=True)
class GrantedPermissionProfile:
    network: Optional[AdditionalNetworkPermissions] = None
    file_system: Optional[Any] = None


class PatchChangeKind(str, Enum):
    ADD = "add"
    DELETE = "delete"
    UPDATE = "update"


@dataclass(frozen=True)
class FileUpdateChange:
    path: Union[str, Path]
    kind: Any
    diff: str


def granted_permission_profile_from_request(value: Any) -> GrantedPermissionProfile:
    """Convert a core request-permission profile into an app-server granted profile."""

    network = _get_attr_or_key(value, "network")
    file_system = _get_attr_or_key(value, "file_system", _get_attr_or_key(value, "fileSystem"))

    granted_network = None
    if network is not None:
        granted_network = AdditionalNetworkPermissions(enabled=_get_attr_or_key(network, "enabled"))

    return GrantedPermissionProfile(network=granted_network, file_system=file_system)


def file_update_changes_to_display(changes: Union[List[Any], Tuple[Any, ...]]) -> Dict[Path, FileChange]:
    """Convert app-server file update changes to TUI display ``FileChange`` values."""

    result: Dict[Path, FileChange] = {}
    for change in changes:
        path = Path(_get_attr_or_key(change, "path"))
        diff = _get_attr_or_key(change, "diff")
        kind = _get_attr_or_key(change, "kind")
        result[path] = _file_change_for_kind(kind, diff)
    return result


def absolute_path(path: Union[str, Path]) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        raise ValueError("path must be absolute")
    return resolved


def _file_change_for_kind(kind: Any, diff: str) -> FileChange:
    if not isinstance(diff, str):
        raise TypeError("diff must be a string")

    kind_value, move_path = _patch_kind_and_move_path(kind)
    if kind_value == PatchChangeKind.ADD.value:
        return FileChange.add(diff)
    if kind_value == PatchChangeKind.DELETE.value:
        return FileChange.delete(diff)
    if kind_value == PatchChangeKind.UPDATE.value:
        return FileChange.update(diff, move_path)
    raise ValueError(f"unknown patch change kind: {kind_value!r}")


def _patch_kind_and_move_path(kind: Any) -> Tuple[str, Optional[Union[str, Path]]]:
    if isinstance(kind, PatchChangeKind):
        return kind.value, None
    if isinstance(kind, str):
        return kind, None
    if isinstance(kind, Mapping):
        kind_type = kind.get("type") or kind.get("kind")
        return str(kind_type), kind.get("move_path") or kind.get("movePath")
    root = getattr(kind, "root", None)
    if root is not None:
        return _patch_kind_and_move_path(root)
    kind_type = getattr(kind, "type", None) or getattr(kind, "kind", None)
    if kind_type is not None:
        return str(kind_type), getattr(kind, "move_path", None)
    value = getattr(kind, "value", None)
    if isinstance(value, str):
        return value, None
    raise TypeError("kind must be a patch change kind")


def _get_attr_or_key(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


__all__ = [
    "AdditionalNetworkPermissions",
    "FileUpdateChange",
    "GrantedPermissionProfile",
    "PatchChangeKind",
    "RUST_MODULE",
    "absolute_path",
    "file_update_changes_to_display",
    "granted_permission_profile_from_request",
]
