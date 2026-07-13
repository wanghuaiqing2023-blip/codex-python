"""Shared setup/root helpers for the native Windows sandbox.

Rust owner: ``codex-windows-sandbox::setup`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from .path_normalization import canonical_path_key, canonicalize_path
from .resolved_permissions import ResolvedWindowsSandboxPermissions


SETUP_VERSION = 5
OFFLINE_USERNAME = "CodexSandboxOffline"
ONLINE_USERNAME = "CodexSandboxOnline"
WINDOWS_PLATFORM_DEFAULT_READ_ROOTS = (
    Path(r"C:\Windows"),
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
    Path(r"C:\ProgramData"),
)
PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "WS_PROXY", "WSS_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "ws_proxy", "wss_proxy",
)


class SandboxNetworkIdentity(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"

    @classmethod
    def from_permissions(
        cls,
        permissions: ResolvedWindowsSandboxPermissions,
        proxy_enforced: bool,
    ) -> "SandboxNetworkIdentity":
        return cls.OFFLINE if proxy_enforced or not permissions.network_policy().is_enabled() else cls.ONLINE


@dataclass(frozen=True)
class OfflineProxySettings:
    proxy_ports: tuple[int, ...] = ()
    allow_local_binding: bool = False


@dataclass(frozen=True)
class SetupMarker:
    version: int
    offline_username: str
    online_username: str
    created_at: str | None = None
    proxy_ports: tuple[int, ...] = ()
    allow_local_binding: bool = False

    def version_matches(self) -> bool:
        return self.version == SETUP_VERSION

    def request_mismatch_reason(
        self,
        network_identity: SandboxNetworkIdentity,
        desired: OfflineProxySettings,
    ) -> str | None:
        if network_identity is SandboxNetworkIdentity.ONLINE:
            return None
        if self.proxy_ports == desired.proxy_ports and self.allow_local_binding == desired.allow_local_binding:
            return None
        return (
            "offline firewall settings changed "
            f"(stored_ports={list(self.proxy_ports)}, desired_ports={list(desired.proxy_ports)}, "
            f"stored_allow_local_binding={str(self.allow_local_binding).lower()}, "
            f"desired_allow_local_binding={str(desired.allow_local_binding).lower()})"
        )


@dataclass(frozen=True)
class ElevationPayload:
    version: int
    offline_username: str
    online_username: str
    codex_home: Path
    command_cwd: Path
    read_roots: tuple[Path, ...]
    write_roots: tuple[Path, ...]
    deny_read_paths: tuple[Path, ...]
    deny_write_paths: tuple[Path, ...]
    proxy_ports: tuple[int, ...]
    allow_local_binding: bool
    real_user: str
    refresh_only: bool

    def to_mapping(self) -> dict[str, object]:
        return {
            "version": self.version,
            "offline_username": self.offline_username,
            "online_username": self.online_username,
            "codex_home": str(self.codex_home),
            "command_cwd": str(self.command_cwd),
            "read_roots": [str(path) for path in self.read_roots],
            "write_roots": [str(path) for path in self.write_roots],
            "deny_read_paths": [str(path) for path in self.deny_read_paths],
            "deny_write_paths": [str(path) for path in self.deny_write_paths],
            "proxy_ports": list(self.proxy_ports),
            "allow_local_binding": self.allow_local_binding,
            "otel": None,
            "real_user": self.real_user,
            "refresh_only": self.refresh_only,
        }


@dataclass(frozen=True)
class SandboxSetupRequest:
    permissions: ResolvedWindowsSandboxPermissions
    command_cwd: Path
    env_map: Mapping[str, str]
    codex_home: Path
    proxy_enforced: bool = False


@dataclass(frozen=True)
class SetupRootOverrides:
    read_roots: tuple[Path, ...] | None = None
    read_roots_include_platform_defaults: bool = False
    write_roots: tuple[Path, ...] | None = None
    deny_read_paths: tuple[Path, ...] | None = None
    deny_write_paths: tuple[Path, ...] | None = None


def sandbox_dir(codex_home: str | Path) -> Path:
    return Path(codex_home) / ".sandbox"


def sandbox_bin_dir(codex_home: str | Path) -> Path:
    return Path(codex_home) / ".sandbox-bin"


def sandbox_secrets_dir(codex_home: str | Path) -> Path:
    return Path(codex_home) / ".sandbox-secrets"


def setup_marker_path(codex_home: str | Path) -> Path:
    return sandbox_dir(codex_home) / "setup_marker.json"


def sandbox_users_path(codex_home: str | Path) -> Path:
    return sandbox_secrets_dir(codex_home) / "sandbox_users.json"


def gather_write_roots_for_permissions(
    permissions: ResolvedWindowsSandboxPermissions,
    command_cwd: str | Path,
    env_map: Mapping[str, str],
) -> tuple[Path, ...]:
    roots = (root.root for root in permissions.writable_roots_for_cwd(command_cwd, env_map))
    return _canonical_existing(roots)


def gather_read_roots(
    command_cwd: str | Path,
    permissions: ResolvedWindowsSandboxPermissions,
    env_map: Mapping[str, str],
    codex_home: str | Path,
) -> tuple[Path, ...]:
    helper_root = sandbox_bin_dir(codex_home)
    helper_root.mkdir(parents=True, exist_ok=True)
    roots: list[Path] = [helper_root]
    if permissions.has_full_disk_read_access() or permissions.include_platform_defaults():
        roots.extend(WINDOWS_PLATFORM_DEFAULT_READ_ROOTS)
    if permissions.has_full_disk_read_access():
        profile = os.environ.get("USERPROFILE")
        if profile:
            roots.extend(_profile_read_roots(Path(profile)))
        roots.append(Path(command_cwd))
        roots.extend(root.root for root in permissions.writable_roots_for_cwd(command_cwd, env_map))
    else:
        roots.extend(permissions.readable_roots_for_cwd(command_cwd))
    return _canonical_existing(roots)


def proxy_ports_from_env(env_map: Mapping[str, str]) -> tuple[int, ...]:
    ports: set[int] = set()
    for key in PROXY_ENV_KEYS:
        value = env_map.get(key)
        if value is None:
            continue
        port = loopback_proxy_port_from_url(value)
        if port is not None:
            ports.add(port)
    return tuple(sorted(ports))


def loopback_proxy_port_from_url(value: str) -> int | None:
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme == "" or host is None or port is None or port == 0:
        return None
    if host.lower() not in {"localhost", "127.0.0.1", "::1"}:
        return None
    return port


def offline_proxy_settings_from_env(
    env_map: Mapping[str, str],
    network_identity: SandboxNetworkIdentity,
) -> OfflineProxySettings:
    if network_identity is SandboxNetworkIdentity.ONLINE:
        return OfflineProxySettings()
    return OfflineProxySettings(
        proxy_ports_from_env(env_map),
        env_map.get("CODEX_NETWORK_ALLOW_LOCAL_BINDING") == "1",
    )


def build_elevation_payload(
    permissions: ResolvedWindowsSandboxPermissions,
    command_cwd: str | Path,
    env_map: Mapping[str, str],
    codex_home: str | Path,
    *,
    proxy_enforced: bool = False,
    read_roots_override: Iterable[str | Path] | None = None,
    read_roots_include_platform_defaults: bool = False,
    write_roots_override: Iterable[str | Path] | None = None,
    deny_read_paths: Iterable[str | Path] = (),
    deny_write_paths: Iterable[str | Path] = (),
    refresh_only: bool = False,
) -> ElevationPayload:
    read_roots = list(
        _canonical_existing(read_roots_override)
        if read_roots_override is not None
        else gather_read_roots(command_cwd, permissions, env_map, codex_home)
    )
    helper_root = sandbox_bin_dir(codex_home)
    helper_root.mkdir(parents=True, exist_ok=True)
    if canonical_path_key(helper_root) not in {canonical_path_key(path) for path in read_roots}:
        read_roots.insert(0, canonicalize_path(helper_root))
    if read_roots_override is not None and read_roots_include_platform_defaults:
        read_roots.extend(_canonical_existing(WINDOWS_PLATFORM_DEFAULT_READ_ROOTS))
    read_roots = list(_canonical_existing(read_roots))
    write_roots = effective_write_roots_for_permissions(
        permissions, command_cwd, env_map, codex_home, write_roots_override
    )
    identity = SandboxNetworkIdentity.from_permissions(permissions, proxy_enforced)
    proxy = offline_proxy_settings_from_env(env_map, identity)
    return ElevationPayload(
        SETUP_VERSION,
        OFFLINE_USERNAME,
        ONLINE_USERNAME,
        Path(codex_home),
        Path(command_cwd),
        tuple(read_roots),
        tuple(write_roots),
        _policy_paths(deny_read_paths),
        _policy_paths(deny_write_paths),
        proxy.proxy_ports,
        proxy.allow_local_binding,
        os.environ.get("USERNAME") or "Administrators",
        refresh_only,
    )


def effective_write_roots_for_permissions(
    permissions: ResolvedWindowsSandboxPermissions,
    command_cwd: str | Path,
    env_map: Mapping[str, str],
    codex_home: str | Path,
    write_roots_override: Iterable[str | Path] | None = None,
) -> tuple[Path, ...]:
    roots = (
        _canonical_existing(write_roots_override)
        if write_roots_override is not None
        else gather_write_roots_for_permissions(permissions, command_cwd, env_map)
    )
    profile = os.environ.get("USERPROFILE")
    if profile:
        profile_key = canonical_path_key(profile)
        roots = tuple(root for root in roots if canonical_path_key(root) != profile_key)
        exclusions = {".ssh", ".tsh", ".brev", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".config", ".npm", ".pki", ".terraform.d"}
        prefix = profile_key.rstrip("/") + "/"
        roots = tuple(
            root
            for root in roots
            if not (
                (key := canonical_path_key(root)).startswith(prefix)
                and key[len(prefix) :].split("/", 1)[0].lower() in exclusions
            )
        )

    sensitive = tuple(
        canonical_path_key(path)
        for path in (
            Path(codex_home),
            sandbox_dir(codex_home),
            sandbox_bin_dir(codex_home),
            sandbox_secrets_dir(codex_home),
        )
    )
    filtered: list[Path] = []
    for root in roots:
        key = canonical_path_key(root)
        if key == sensitive[0]:
            continue
        if any(key == item or key.startswith(item.rstrip("/") + "/") for item in sensitive[1:]):
            continue
        filtered.append(root)
    return tuple(filtered)


def _canonical_existing(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    output: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            continue
        canonical = canonicalize_path(path)
        key = canonical_path_key(canonical)
        if key not in seen:
            seen.add(key)
            output.append(canonical)
    return tuple(output)


def _policy_paths(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    """Preserve absent policy paths so setup can materialize their deny ACEs."""

    output: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw)
        normalized = canonicalize_path(path) if path.exists() else path.absolute()
        key = canonical_path_key(normalized)
        if key not in seen:
            seen.add(key)
            output.append(normalized)
    return tuple(output)


def _profile_read_roots(profile: Path) -> tuple[Path, ...]:
    exclusions = {".ssh", ".tsh", ".brev", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".config", ".npm", ".pki", ".terraform.d"}
    try:
        return tuple(path for path in profile.iterdir() if path.name.lower() not in exclusions)
    except OSError:
        return (profile,)


__all__ = [
    "SETUP_VERSION",
    "ElevationPayload",
    "OFFLINE_USERNAME",
    "ONLINE_USERNAME",
    "OfflineProxySettings",
    "SandboxNetworkIdentity",
    "SandboxSetupRequest",
    "SetupRootOverrides",
    "SetupMarker",
    "build_elevation_payload",
    "effective_write_roots_for_permissions",
    "gather_read_roots",
    "gather_write_roots_for_permissions",
    "loopback_proxy_port_from_url",
    "offline_proxy_settings_from_env",
    "proxy_ports_from_env",
    "sandbox_bin_dir",
    "sandbox_dir",
    "sandbox_secrets_dir",
    "sandbox_users_path",
    "setup_marker_path",
]
