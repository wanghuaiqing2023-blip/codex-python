"""Sandbox metric/policy tags ported from Codex core."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

from pycodex.protocol import (
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
    PermissionProfile,
    WindowsSandboxLevel,
)


class SandboxType(str, Enum):
    NONE = "none"
    MACOS_SEATBELT = "seatbelt"
    LINUX_SECCOMP = "seccomp"
    WINDOWS_RESTRICTED_TOKEN = "windows_sandbox"

    def as_metric_tag(self) -> str:
        return self.value


def get_platform_sandbox(
    windows_sandbox_enabled: bool,
) -> SandboxType | None:
    if not isinstance(windows_sandbox_enabled, bool):
        raise TypeError("windows_sandbox_enabled must be a bool")
    if sys.platform == "darwin":
        return SandboxType.MACOS_SEATBELT
    if sys.platform.startswith("linux"):
        return SandboxType.LINUX_SECCOMP
    if sys.platform == "win32" and windows_sandbox_enabled:
        return SandboxType.WINDOWS_RESTRICTED_TOKEN
    return None


def should_require_platform_sandbox(
    file_system_policy: FileSystemSandboxPolicy,
    network_policy: NetworkSandboxPolicy,
    has_managed_network_requirements: bool,
) -> bool:
    if not isinstance(file_system_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_policy must be a FileSystemSandboxPolicy")
    if not isinstance(network_policy, NetworkSandboxPolicy):
        raise TypeError("network_policy must be a NetworkSandboxPolicy")
    if not isinstance(has_managed_network_requirements, bool):
        raise TypeError("has_managed_network_requirements must be a bool")
    if has_managed_network_requirements:
        return True

    if not network_policy.is_enabled():
        return file_system_policy.kind is not FileSystemSandboxKind.EXTERNAL_SANDBOX

    if file_system_policy.kind is FileSystemSandboxKind.RESTRICTED:
        return not file_system_policy.has_full_disk_write_access()
    return False


def permission_profile_sandbox_tag(
    profile: PermissionProfile,
    windows_sandbox_level: WindowsSandboxLevel,
    enforce_managed_network: bool,
) -> str:
    if not isinstance(profile, PermissionProfile):
        raise TypeError("profile must be a PermissionProfile")
    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        raise TypeError("windows_sandbox_level must be a WindowsSandboxLevel")
    if not isinstance(enforce_managed_network, bool):
        raise TypeError("enforce_managed_network must be a bool")
    if profile.type == "disabled":
        return "none"
    if profile.type == "external":
        return "external"

    file_system_policy = profile.file_system_sandbox_policy()
    if not should_require_platform_sandbox(
        file_system_policy,
        profile.network_sandbox_policy(),
        enforce_managed_network,
    ):
        return "none"

    if sys.platform == "win32" and windows_sandbox_level is WindowsSandboxLevel.ELEVATED:
        return "windows_elevated"

    sandbox = get_platform_sandbox(
        windows_sandbox_level is not WindowsSandboxLevel.DISABLED
    )
    if sandbox is None:
        return "none"
    return sandbox.as_metric_tag()


def permission_profile_policy_tag(
    profile: PermissionProfile,
    cwd: Path | str,
) -> str:
    if not isinstance(profile, PermissionProfile):
        raise TypeError("profile must be a PermissionProfile")
    if not isinstance(cwd, Path | str):
        raise TypeError("cwd must be a path")
    if profile.type == "disabled":
        return "danger-full-access"
    if profile.type == "external":
        return "external-sandbox"

    file_system_policy = profile.file_system_sandbox_policy()
    if file_system_policy.has_full_disk_write_access():
        return "danger-full-access"
    if not file_system_policy.get_writable_roots_with_cwd(cwd):
        return "read-only"
    return "workspace-write"


__all__ = [
    "SandboxType",
    "get_platform_sandbox",
    "permission_profile_policy_tag",
    "permission_profile_sandbox_tag",
    "should_require_platform_sandbox",
]
