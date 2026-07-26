"""Shared setup/root helpers for the native Windows sandbox.

Rust owner: ``codex-windows-sandbox::setup`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from .path_normalization import canonical_path_key, canonicalize_path
from .resolved_permissions import ResolvedWindowsSandboxPermissions
from .ssh_config_dependencies import ssh_config_dependency_paths
from .setup_error import (
    SetupErrorCode,
    SetupFailure,
    clear_setup_error_report,
    read_setup_error_report,
)


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
            "mode": "full",
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
    return _filter_ssh_config_dependency_roots(_canonical_existing(roots))


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
    return _filter_ssh_config_dependency_roots(_canonical_existing(roots))


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
    read_roots = list(
        _filter_ssh_config_dependency_roots(_canonical_existing(read_roots))
    )
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
        roots = _filter_ssh_config_dependency_roots(roots)

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


def _filter_ssh_config_dependency_roots(
    roots: Iterable[str | Path],
) -> tuple[Path, ...]:
    profile_value = os.environ.get("USERPROFILE")
    roots_tuple = tuple(Path(root) for root in roots)
    if not profile_value:
        return roots_tuple
    profile = Path(profile_value)
    dependency_paths = ssh_config_dependency_paths(profile)
    dependency_children = {
        child
        for path in dependency_paths
        if (child := _user_profile_child_name(path, profile)) is not None
    }
    return tuple(
        root
        for root in roots_tuple
        if _user_profile_child_name(root, profile) not in dependency_children
    )


def _user_profile_child_name(path: Path, profile: Path) -> str | None:
    path_key = canonical_path_key(path)
    profile_key = canonical_path_key(profile).rstrip("/")
    prefix = profile_key + "/"
    if not path_key.startswith(prefix):
        return None
    relative = path_key[len(prefix) :]
    child = relative.split("/", 1)[0]
    return child.lower() if child else None


if os.name == "nt":
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_HIDE = 0
    INFINITE = 0xFFFFFFFF
    ERROR_CANCELLED = 1223

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    _shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    _shell32.ShellExecuteExW.restype = wintypes.BOOL
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _advapi32.CheckTokenMembership.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
    ]
    _advapi32.CheckTokenMembership.restype = wintypes.BOOL
    _advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def is_elevated() -> bool:
    """Return whether the current token is a member of Administrators."""

    _require_windows()
    sid = ctypes.c_void_p()
    if not _advapi32.ConvertStringSidToSidW(
        "S-1-5-32-544",
        ctypes.byref(sid),
    ):
        error = ctypes.get_last_error()
        raise SetupFailure(
            SetupErrorCode.ORCHESTRATOR_ELEVATION_CHECK_FAILED,
            f"resolve Administrators SID failed: {error}",
        )
    try:
        member = wintypes.BOOL()
        if not _advapi32.CheckTokenMembership(
            None,
            sid,
            ctypes.byref(member),
        ):
            error = ctypes.get_last_error()
            raise SetupFailure(
                SetupErrorCode.ORCHESTRATOR_ELEVATION_CHECK_FAILED,
                f"CheckTokenMembership failed: {error}",
            )
        return bool(member.value)
    finally:
        _kernel32.LocalFree(sid)


def run_setup_exe(
    payload: ElevationPayload,
    needs_elevation: bool,
    codex_home: str | Path,
) -> None:
    """Serialize a setup request and wait for the Cargo setup binary owner."""

    _require_windows()
    home = Path(codex_home)
    try:
        sandbox_dir(home).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SetupFailure(
            SetupErrorCode.ORCHESTRATOR_SANDBOX_DIR_CREATE_FAILED,
            f"failed to create sandbox dir {sandbox_dir(home)}: {exc}",
        ) from exc
    try:
        encoded = base64.b64encode(
            json.dumps(
                payload.to_mapping(),
                separators=(",", ":"),
            ).encode("utf-8")
        ).decode("ascii")
    except (TypeError, ValueError) as exc:
        raise SetupFailure(
            SetupErrorCode.ORCHESTRATOR_PAYLOAD_SERIALIZE_FAILED,
            str(exc),
        ) from exc

    cleared_report = True
    try:
        clear_setup_error_report(home)
    except OSError:
        cleared_report = False
    exit_code = _run_helper_process(
        encoded,
        needs_elevation=needs_elevation,
        codex_home=home,
    )
    if exit_code != 0:
        _raise_helper_failure(home, cleared_report, exit_code)
    try:
        clear_setup_error_report(home)
    except OSError:
        pass


def _run_helper_process(
    encoded: str,
    *,
    needs_elevation: bool,
    codex_home: Path,
) -> int:
    from .helper_materialization import resolve_current_exe_for_launch

    executable = resolve_current_exe_for_launch(
        codex_home,
        sys.executable,
    )
    arguments = [
        "-m",
        "pycodex.windows_sandbox.bin.setup_main",
        encoded,
    ]
    if not needs_elevation:
        completed = subprocess.run(
            [str(executable), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        return completed.returncode

    parameters = subprocess.list2cmdline(arguments)
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = str(executable)
    info.lpParameters = parameters
    info.lpDirectory = str(Path.cwd())
    info.nShow = SW_HIDE
    ctypes.set_last_error(0)
    if not _shell32.ShellExecuteExW(ctypes.byref(info)) or not info.hProcess:
        error = ctypes.get_last_error()
        code = (
            SetupErrorCode.ORCHESTRATOR_HELPER_LAUNCH_CANCELED
            if error == ERROR_CANCELLED
            else SetupErrorCode.ORCHESTRATOR_HELPER_LAUNCH_FAILED
        )
        raise SetupFailure(
            code,
            f"ShellExecuteExW failed to launch setup helper: {error}",
        )
    try:
        _kernel32.WaitForSingleObject(info.hProcess, INFINITE)
        exit_code = wintypes.DWORD(1)
        if not _kernel32.GetExitCodeProcess(
            info.hProcess,
            ctypes.byref(exit_code),
        ):
            error = ctypes.get_last_error()
            raise SetupFailure(
                SetupErrorCode.ORCHESTRATOR_HELPER_LAUNCH_FAILED,
                f"GetExitCodeProcess failed: {error}",
            )
        return int(exit_code.value)
    finally:
        _kernel32.CloseHandle(info.hProcess)


def _raise_helper_failure(
    codex_home: Path,
    cleared_report: bool,
    exit_code: int,
) -> None:
    detail = f"setup helper exited with status {exit_code}"
    if cleared_report:
        try:
            report = read_setup_error_report(codex_home)
        except (OSError, ValueError) as exc:
            raise SetupFailure(
                SetupErrorCode.ORCHESTRATOR_HELPER_REPORT_READ_FAILED,
                f"{detail}; failed to read setup_error.json: {exc}",
            ) from exc
        if report is not None:
            raise SetupFailure(report.code, report.message)
    raise SetupFailure(
        SetupErrorCode.ORCHESTRATOR_HELPER_EXIT_NONZERO,
        detail,
    )


def _require_windows() -> None:
    if os.name != "nt":
        raise SetupFailure(
            SetupErrorCode.ORCHESTRATOR_HELPER_LAUNCH_FAILED,
            "setup helper requires Windows",
        )


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
    "is_elevated",
    "loopback_proxy_port_from_url",
    "offline_proxy_settings_from_env",
    "proxy_ports_from_env",
    "run_setup_exe",
    "sandbox_bin_dir",
    "sandbox_dir",
    "sandbox_secrets_dir",
    "sandbox_users_path",
    "setup_marker_path",
]
