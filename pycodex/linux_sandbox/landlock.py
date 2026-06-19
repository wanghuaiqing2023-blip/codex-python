"""In-process Linux sandbox policy decisions.

Port of ``codex/codex-rs/linux-sandbox/src/landlock.rs``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pycodex.protocol import FileSystemSandboxPolicy, NetworkSandboxPolicy, PermissionProfile


class NetworkSeccompMode(str, Enum):
    RESTRICTED = "restricted"
    PROXY_ROUTED = "proxy_routed"


@dataclass(frozen=True)
class LandlockApplicationPlan:
    set_no_new_privs: bool
    network_seccomp_mode: NetworkSeccompMode | None
    apply_filesystem_landlock: bool
    writable_roots: tuple[Path, ...] = ()


NoNewPrivsHook = Callable[[], None]
NetworkSeccompHook = Callable[[NetworkSeccompMode], None]
FilesystemLandlockHook = Callable[[tuple[Path, ...]], None]


def apply_permission_profile_to_current_thread(
    permission_profile: PermissionProfile,
    cwd: Path | str,
    apply_landlock_fs: bool,
    allow_network_for_proxy: bool,
    proxy_routed_network: bool,
    *,
    set_no_new_privs_hook: NoNewPrivsHook | None = None,
    install_network_seccomp_hook: NetworkSeccompHook | None = None,
    install_filesystem_landlock_hook: FilesystemLandlockHook | None = None,
) -> LandlockApplicationPlan:
    """Compute and optionally apply the current-thread Linux sandbox policy."""

    plan = plan_permission_profile_application(
        permission_profile,
        cwd,
        apply_landlock_fs,
        allow_network_for_proxy,
        proxy_routed_network,
    )
    if plan.set_no_new_privs and set_no_new_privs_hook is not None:
        set_no_new_privs_hook()
    if plan.network_seccomp_mode is not None and install_network_seccomp_hook is not None:
        install_network_seccomp_hook(plan.network_seccomp_mode)
    if plan.apply_filesystem_landlock and install_filesystem_landlock_hook is not None:
        install_filesystem_landlock_hook(plan.writable_roots)
    return plan


def plan_permission_profile_application(
    permission_profile: PermissionProfile,
    cwd: Path | str,
    apply_landlock_fs: bool,
    allow_network_for_proxy: bool,
    proxy_routed_network: bool,
) -> LandlockApplicationPlan:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be PermissionProfile")
    file_system_sandbox_policy, network_sandbox_policy = permission_profile.to_runtime_permissions()
    mode = network_seccomp_mode(
        network_sandbox_policy,
        allow_network_for_proxy,
        proxy_routed_network,
    )
    apply_fs = apply_landlock_fs and not file_system_sandbox_policy.has_full_disk_write_access()
    if apply_fs and not file_system_sandbox_policy.has_full_disk_read_access():
        raise NotImplementedError(
            "Restricted read-only access is not supported by the legacy Linux Landlock filesystem backend."
        )

    writable_roots = ()
    if apply_fs:
        writable_roots = tuple(Path(root.root) for root in file_system_sandbox_policy.get_writable_roots_with_cwd(cwd))

    return LandlockApplicationPlan(
        set_no_new_privs=mode is not None or apply_fs,
        network_seccomp_mode=mode,
        apply_filesystem_landlock=apply_fs,
        writable_roots=writable_roots,
    )


def should_install_network_seccomp(
    network_sandbox_policy: NetworkSandboxPolicy,
    allow_network_for_proxy: bool,
) -> bool:
    if not isinstance(network_sandbox_policy, NetworkSandboxPolicy):
        network_sandbox_policy = NetworkSandboxPolicy.parse(str(network_sandbox_policy))
    return (not network_sandbox_policy.is_enabled()) or allow_network_for_proxy


def network_seccomp_mode(
    network_sandbox_policy: NetworkSandboxPolicy,
    allow_network_for_proxy: bool,
    proxy_routed_network: bool,
) -> NetworkSeccompMode | None:
    if not should_install_network_seccomp(network_sandbox_policy, allow_network_for_proxy):
        return None
    if proxy_routed_network:
        return NetworkSeccompMode.PROXY_ROUTED
    return NetworkSeccompMode.RESTRICTED


def set_no_new_privs() -> None:
    raise NotImplementedError("PR_SET_NO_NEW_PRIVS is an OS syscall boundary in the Python port")


def install_network_seccomp_filter_on_current_thread(mode: NetworkSeccompMode) -> None:
    raise NotImplementedError("seccomp filter installation is an OS syscall boundary in the Python port")


def install_filesystem_landlock_rules_on_current_thread(writable_roots: tuple[Path, ...]) -> None:
    raise NotImplementedError("Landlock filesystem rule installation is an OS syscall boundary in the Python port")


__all__ = [
    "LandlockApplicationPlan",
    "NetworkSeccompMode",
    "apply_permission_profile_to_current_thread",
    "install_filesystem_landlock_rules_on_current_thread",
    "install_network_seccomp_filter_on_current_thread",
    "network_seccomp_mode",
    "plan_permission_profile_application",
    "set_no_new_privs",
    "should_install_network_seccomp",
]
