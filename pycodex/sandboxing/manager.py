"""Sandbox manager surface for the Rust ``codex-sandboxing`` crate.

Rust counterpart: ``codex/codex-rs/sandboxing/src/manager.rs``.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.core.sandbox_tags import (
    SandboxType,
    get_platform_sandbox,
    should_require_platform_sandbox,
)
from pycodex.core.sandboxing import (
    SandboxExecRequest,
    compatibility_sandbox_policy_for_permission_profile,
)
from pycodex.linux_sandbox import (
    allow_network_for_proxy,
    create_linux_sandbox_command_args_for_permission_profile,
    linux_sandbox_arg0,
)
from pycodex.sandboxing.bwrap import WSL1_BWRAP_WARNING, is_wsl1
from pycodex.protocol import (
    AdditionalPermissionProfile,
    FileSystemAccessMode,
    FileSystemSandboxEntry,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
    PermissionProfile,
    WindowsSandboxLevel,
)
from pycodex.sandboxing.seatbelt import (
    CreateSeatbeltCommandArgsParams,
    MACOS_PATH_TO_SEATBELT_EXECUTABLE,
    create_seatbelt_command_args,
)


class SandboxablePreference(str, Enum):
    AUTO = "auto"
    REQUIRE = "require"
    FORBID = "forbid"


class SandboxTransformError(RuntimeError):
    """Base error for sandbox command transformation failures."""


class MissingLinuxSandboxExecutable(SandboxTransformError):
    def __init__(self) -> None:
        super().__init__("missing codex-linux-sandbox executable path")


class SeatbeltUnavailable(SandboxTransformError):
    def __init__(self) -> None:
        super().__init__("seatbelt sandbox is only available on macOS")


class SeatbeltCommandBuilderUnavailable(SandboxTransformError):
    def __init__(self) -> None:
        super().__init__("seatbelt sandbox argv construction is not implemented in Python")


class Wsl1UnsupportedForBubblewrap(SandboxTransformError):
    def __init__(self) -> None:
        super().__init__(WSL1_BWRAP_WARNING)


@dataclass(frozen=True)
class SandboxCommand:
    program: str
    args: tuple[str, ...] = ()
    cwd: Path = Path(".")
    env: Mapping[str, str] | None = None
    additional_permissions: AdditionalPermissionProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.program, str):
            raise TypeError("program must be a string")
        if isinstance(self.args, str) or not isinstance(self.args, Sequence):
            raise TypeError("args must be a sequence of strings")
        if not all(isinstance(arg, str) for arg in self.args):
            raise TypeError("args must contain strings")
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "cwd", Path(self.cwd))
        if self.env is None:
            object.__setattr__(self, "env", {})
        elif not all(isinstance(k, str) and isinstance(v, str) for k, v in self.env.items()):
            raise TypeError("env must contain string keys and values")
        else:
            object.__setattr__(self, "env", dict(self.env))
        if self.additional_permissions is not None and not isinstance(
            self.additional_permissions,
            AdditionalPermissionProfile,
        ):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SandboxCommand":
        return cls(
            program=str(value["program"]),
            args=tuple(str(arg) for arg in value.get("args", ())),
            cwd=Path(value.get("cwd", ".")),
            env=dict(value.get("env", {})),
            additional_permissions=value.get("additional_permissions"),
        )


@dataclass(frozen=True)
class SandboxTransformRequest:
    command: SandboxCommand
    permissions: PermissionProfile
    sandbox: SandboxType
    enforce_managed_network: bool
    network: Any = None
    sandbox_policy_cwd: Path = Path(".")
    codex_linux_sandbox_exe: Path | None = None
    use_legacy_landlock: bool = False
    windows_sandbox_level: WindowsSandboxLevel = WindowsSandboxLevel.DISABLED
    windows_sandbox_private_desktop: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.command, SandboxCommand):
            raise TypeError("command must be SandboxCommand")
        if not isinstance(self.permissions, PermissionProfile):
            raise TypeError("permissions must be PermissionProfile")
        if not isinstance(self.sandbox, SandboxType):
            object.__setattr__(self, "sandbox", SandboxType(str(self.sandbox)))
        if not isinstance(self.enforce_managed_network, bool):
            raise TypeError("enforce_managed_network must be a bool")
        object.__setattr__(self, "sandbox_policy_cwd", Path(self.sandbox_policy_cwd))
        if self.codex_linux_sandbox_exe is not None:
            object.__setattr__(self, "codex_linux_sandbox_exe", Path(self.codex_linux_sandbox_exe))
        if not isinstance(self.use_legacy_landlock, bool):
            raise TypeError("use_legacy_landlock must be a bool")
        if not isinstance(self.windows_sandbox_level, WindowsSandboxLevel):
            object.__setattr__(
                self,
                "windows_sandbox_level",
                WindowsSandboxLevel.parse(str(self.windows_sandbox_level)),
            )
        if not isinstance(self.windows_sandbox_private_desktop, bool):
            raise TypeError("windows_sandbox_private_desktop must be a bool")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SandboxTransformRequest":
        command = value["command"]
        if not isinstance(command, SandboxCommand):
            command = SandboxCommand.from_mapping(command)
        permissions = value.get("permission_profile", value.get("permissions"))
        if isinstance(permissions, tuple):
            permissions = PermissionProfile.from_runtime_permissions(*permissions)
        return cls(
            command=command,
            permissions=permissions,
            sandbox=value.get("sandbox", SandboxType.NONE),
            enforce_managed_network=bool(value.get("enforce_managed_network", False)),
            network=value.get("network"),
            sandbox_policy_cwd=Path(value.get("sandbox_policy_cwd", command.cwd)),
            codex_linux_sandbox_exe=value.get("codex_linux_sandbox_exe"),
            use_legacy_landlock=bool(value.get("use_legacy_landlock", False)),
            windows_sandbox_level=value.get("windows_sandbox_level", WindowsSandboxLevel.DISABLED),
            windows_sandbox_private_desktop=bool(value.get("windows_sandbox_private_desktop", False)),
        )


class SandboxManager:
    @classmethod
    def new(cls) -> "SandboxManager":
        return cls()

    def select_initial(
        self,
        file_system_policy: FileSystemSandboxPolicy,
        network_policy: NetworkSandboxPolicy,
        pref: SandboxablePreference | str,
        windows_sandbox_level: WindowsSandboxLevel | str,
        has_managed_network_requirements: bool,
    ) -> SandboxType:
        if not isinstance(file_system_policy, FileSystemSandboxPolicy):
            raise TypeError("file_system_policy must be FileSystemSandboxPolicy")
        if not isinstance(network_policy, NetworkSandboxPolicy):
            network_policy = NetworkSandboxPolicy.parse(str(network_policy))
        pref = SandboxablePreference(pref)
        if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
            windows_sandbox_level = WindowsSandboxLevel.parse(str(windows_sandbox_level))

        if pref is SandboxablePreference.FORBID:
            return SandboxType.NONE
        if pref is SandboxablePreference.REQUIRE:
            return get_platform_sandbox(windows_sandbox_level is not WindowsSandboxLevel.DISABLED) or SandboxType.NONE
        if should_require_platform_sandbox(
            file_system_policy,
            network_policy,
            has_managed_network_requirements,
        ):
            return get_platform_sandbox(windows_sandbox_level is not WindowsSandboxLevel.DISABLED) or SandboxType.NONE
        return SandboxType.NONE

    def transform(
        self,
        request: SandboxTransformRequest | Mapping[str, Any],
    ) -> SandboxExecRequest:
        if isinstance(request, Mapping):
            request = SandboxTransformRequest.from_mapping(request)
        if not isinstance(request, SandboxTransformRequest):
            raise TypeError("request must be SandboxTransformRequest or mapping")

        effective_permissions = effective_permission_profile(
            request.permissions,
            request.command.additional_permissions,
        )
        file_system_policy, network_policy = effective_permissions.to_runtime_permissions()
        command = [request.command.program, *request.command.args]
        arg0: str | None = None

        if request.sandbox is SandboxType.NONE:
            argv = command
        elif request.sandbox is SandboxType.MACOS_SEATBELT:
            if sys.platform != "darwin":
                raise SeatbeltUnavailable()
            args = create_seatbelt_command_args(
                CreateSeatbeltCommandArgsParams(
                    command=tuple(command),
                    file_system_sandbox_policy=file_system_policy,
                    network_sandbox_policy=network_policy,
                    sandbox_policy_cwd=request.sandbox_policy_cwd,
                    enforce_managed_network=request.enforce_managed_network,
                    network=request.network,
                    extra_allow_unix_sockets=(),
                )
            )
            argv = [MACOS_PATH_TO_SEATBELT_EXECUTABLE, *args]
        elif request.sandbox is SandboxType.LINUX_SECCOMP:
            if request.codex_linux_sandbox_exe is None:
                raise MissingLinuxSandboxExecutable()
            allow_proxy_network = allow_network_for_proxy(request.enforce_managed_network)
            if sys.platform.startswith("linux"):
                ensure_linux_bubblewrap_is_supported(
                    file_system_policy,
                    request.use_legacy_landlock,
                    allow_proxy_network,
                    is_wsl1(),
                )
            args = create_linux_sandbox_command_args_for_permission_profile(
                command,
                request.command.cwd,
                effective_permissions,
                request.sandbox_policy_cwd,
                request.use_legacy_landlock,
                allow_proxy_network,
            )
            argv = [str(request.codex_linux_sandbox_exe), *args]
            arg0 = linux_sandbox_arg0(request.codex_linux_sandbox_exe)
        elif request.sandbox is SandboxType.WINDOWS_RESTRICTED_TOKEN:
            argv = command
        else:
            argv = command

        return SandboxExecRequest(
            command=tuple(argv),
            cwd=request.command.cwd,
            env=dict(request.command.env or {}),
            network=request.network,
            sandbox=request.sandbox,
            windows_sandbox_level=request.windows_sandbox_level,
            windows_sandbox_private_desktop=request.windows_sandbox_private_desktop,
            permission_profile=effective_permissions,
            file_system_sandbox_policy=file_system_policy,
            network_sandbox_policy=network_policy,
            arg0=arg0,
        )


def effective_permission_profile(
    permissions: PermissionProfile,
    additional_permissions: AdditionalPermissionProfile | None,
) -> PermissionProfile:
    if not isinstance(permissions, PermissionProfile):
        raise TypeError("permissions must be PermissionProfile")
    if additional_permissions is None:
        return permissions
    if not isinstance(additional_permissions, AdditionalPermissionProfile):
        raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
    file_system_policy = effective_file_system_sandbox_policy(
        permissions.file_system_sandbox_policy(),
        additional_permissions,
    )
    network_policy = effective_network_sandbox_policy(
        permissions.network_sandbox_policy(),
        additional_permissions,
    )
    return PermissionProfile.from_runtime_permissions(file_system_policy, network_policy)


def effective_file_system_sandbox_policy(
    file_system_policy: FileSystemSandboxPolicy,
    additional_permissions: AdditionalPermissionProfile | None,
) -> FileSystemSandboxPolicy:
    if not isinstance(file_system_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_policy must be FileSystemSandboxPolicy")
    if additional_permissions is None or additional_permissions.file_system is None:
        return file_system_policy
    if file_system_policy.kind is not FileSystemSandboxKind.RESTRICTED:
        return file_system_policy
    entries = list(file_system_policy.entries)
    for entry in additional_permissions.file_system.entries:
        if entry not in entries:
            entries.append(entry)
    return replace(
        file_system_policy,
        entries=tuple(entries),
        glob_scan_max_depth=_merge_glob_scan_max_depth(
            file_system_policy.entries,
            file_system_policy.glob_scan_max_depth,
            additional_permissions.file_system.entries,
            additional_permissions.file_system.glob_scan_max_depth,
        ),
    )


def effective_network_sandbox_policy(
    network_policy: NetworkSandboxPolicy,
    additional_permissions: AdditionalPermissionProfile | None,
) -> NetworkSandboxPolicy:
    if not isinstance(network_policy, NetworkSandboxPolicy):
        network_policy = NetworkSandboxPolicy.parse(str(network_policy))
    if additional_permissions is None or additional_permissions.network is None:
        return network_policy
    if additional_permissions.network.enabled is True:
        return NetworkSandboxPolicy.ENABLED
    if additional_permissions.network.enabled is False:
        return NetworkSandboxPolicy.RESTRICTED
    return network_policy


def ensure_linux_bubblewrap_is_supported(
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    use_legacy_landlock: bool,
    allow_network_for_proxy_: bool,
    is_wsl1_: bool,
) -> None:
    requires_bubblewrap = (
        not use_legacy_landlock
        and (
            not file_system_sandbox_policy.has_full_disk_write_access()
            or allow_network_for_proxy_
        )
    )
    if is_wsl1_ and requires_bubblewrap:
        raise Wsl1UnsupportedForBubblewrap()


def _merge_glob_scan_max_depth(
    left_entries: tuple[FileSystemSandboxEntry, ...],
    left_depth: int | None,
    right_entries: tuple[FileSystemSandboxEntry, ...],
    right_depth: int | None,
) -> int | None:
    left_effective = _effective_glob_scan_depth(left_entries, left_depth)
    right_effective = _effective_glob_scan_depth(right_entries, right_depth)
    if left_effective == "unbounded" or right_effective == "unbounded":
        return None
    depths = [depth for depth in (left_effective, right_effective) if isinstance(depth, int)]
    return max(depths) if depths else None


def _effective_glob_scan_depth(
    entries: tuple[FileSystemSandboxEntry, ...],
    depth: int | None,
) -> int | str | None:
    has_deny_glob = any(
        entry.access is FileSystemAccessMode.DENY and entry.path.type == "glob_pattern"
        for entry in entries
    )
    if not has_deny_glob:
        return None
    return depth if depth is not None else "unbounded"


__all__ = [
    "MissingLinuxSandboxExecutable",
    "SandboxCommand",
    "SandboxExecRequest",
    "SandboxManager",
    "SandboxTransformError",
    "SandboxTransformRequest",
    "SandboxType",
    "SandboxablePreference",
    "SeatbeltCommandBuilderUnavailable",
    "SeatbeltUnavailable",
    "Wsl1UnsupportedForBubblewrap",
    "compatibility_sandbox_policy_for_permission_profile",
    "effective_file_system_sandbox_policy",
    "effective_network_sandbox_policy",
    "effective_permission_profile",
    "ensure_linux_bubblewrap_is_supported",
    "get_platform_sandbox",
]
