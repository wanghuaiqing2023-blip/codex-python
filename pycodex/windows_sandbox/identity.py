"""Elevated-sandbox identity selection and credential loading.

Rust owner: ``codex-windows-sandbox::identity`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import dpapi
from .setup import (
    SETUP_VERSION,
    OfflineProxySettings,
    SandboxNetworkIdentity,
    SetupMarker,
    offline_proxy_settings_from_env,
    sandbox_users_path,
    setup_marker_path,
)


class WindowsSandboxIdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxUserRecord:
    username: str
    password: str


@dataclass(frozen=True)
class SandboxUsersFile:
    version: int
    offline: SandboxUserRecord
    online: SandboxUserRecord

    def version_matches(self) -> bool:
        return self.version == SETUP_VERSION


@dataclass(frozen=True)
class SandboxCreds:
    username: str
    password: str


def load_marker(codex_home: str | Path) -> SetupMarker | None:
    try:
        value = json.loads(setup_marker_path(codex_home).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    try:
        return SetupMarker(
            version=_required_int(value, "version"),
            offline_username=_required_str(value, "offline_username"),
            online_username=_required_str(value, "online_username"),
            created_at=value.get("created_at") if isinstance(value.get("created_at"), str) else None,
            proxy_ports=tuple(_int_list(value.get("proxy_ports", []))),
            allow_local_binding=bool(value.get("allow_local_binding", False)),
        )
    except (TypeError, ValueError):
        return None


def load_users(codex_home: str | Path) -> SandboxUsersFile | None:
    try:
        value = json.loads(sandbox_users_path(codex_home).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    try:
        return SandboxUsersFile(
            _required_int(value, "version"),
            _user_record(value.get("offline")),
            _user_record(value.get("online")),
        )
    except (TypeError, ValueError):
        return None


def sandbox_setup_is_complete(codex_home: str | Path) -> bool:
    marker = load_marker(codex_home)
    users = load_users(codex_home)
    return bool(marker and marker.version_matches() and users and users.version_matches())


def select_identity(
    network_identity: SandboxNetworkIdentity,
    codex_home: str | Path,
) -> SandboxCreds | None:
    marker = load_marker(codex_home)
    users = load_users(codex_home)
    if not marker or not marker.version_matches() or not users or not users.version_matches():
        return None
    record = users.offline if network_identity is SandboxNetworkIdentity.OFFLINE else users.online
    try:
        encrypted = base64.b64decode(record.password, validate=True)
        password = dpapi.unprotect(encrypted).decode("utf-8")
    except (ValueError, UnicodeDecodeError, OSError) as exc:
        raise WindowsSandboxIdentityError(f"failed to decode sandbox password: {exc}") from exc
    return SandboxCreds(record.username, password)


def setup_mismatch_reason(
    codex_home: str | Path,
    network_identity: SandboxNetworkIdentity,
    env_map: Mapping[str, str],
) -> str | None:
    marker = load_marker(codex_home)
    if marker is None or not marker.version_matches():
        return "sandbox setup marker missing or incompatible"
    desired: OfflineProxySettings = offline_proxy_settings_from_env(env_map, network_identity)
    mismatch = marker.request_mismatch_reason(network_identity, desired)
    if mismatch is not None:
        return mismatch
    users = load_users(codex_home)
    if users is None or not users.version_matches():
        return "sandbox users missing or incompatible with marker version"
    return None


def _user_record(value: object) -> SandboxUserRecord:
    if not isinstance(value, dict):
        raise ValueError("sandbox user record must be an object")
    return SandboxUserRecord(_required_str(value, "username"), _required_str(value, "password"))


def _required_str(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ValueError(f"{key} must be a string")
    return item


def _required_int(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise ValueError(f"{key} must be an integer")
    return item


def _int_list(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError("proxy_ports must be a list")
    output: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 65535:
            raise ValueError("proxy port must be an unsigned 16-bit integer")
        output.append(item)
    return tuple(output)


__all__ = [
    "SandboxCreds",
    "SandboxUserRecord",
    "SandboxUsersFile",
    "WindowsSandboxIdentityError",
    "load_marker",
    "load_users",
    "sandbox_setup_is_complete",
    "select_identity",
    "setup_mismatch_reason",
]
