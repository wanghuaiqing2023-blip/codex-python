"""Permission policy transforms for ``codex-sandboxing``.

Rust counterpart: ``codex/codex-rs/sandboxing/src/policy_transforms.rs``.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pycodex.core.sandbox_tags import should_require_platform_sandbox
from pycodex.core.tools.handlers.utils import (
    intersect_permission_profiles,
    merge_permission_profiles,
)
from pycodex.protocol import (
    AdditionalPermissionProfile,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    NetworkPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
    SandboxEnforcement,
)


def normalize_additional_permissions(
    additional_permissions: AdditionalPermissionProfile,
) -> AdditionalPermissionProfile:
    if not isinstance(additional_permissions, AdditionalPermissionProfile):
        raise TypeError("additional_permissions must be AdditionalPermissionProfile")
    network = additional_permissions.network
    if network is not None and network.is_empty():
        network = None

    file_system = additional_permissions.file_system
    if file_system is not None:
        entries: list[FileSystemSandboxEntry] = []
        for entry in file_system.entries:
            if entry.path.type == "glob_pattern" and entry.access is not FileSystemAccessMode.DENY:
                raise ValueError("glob file system permissions only support deny-read entries")
            normalized = FileSystemSandboxEntry(
                _normalize_file_system_path(entry.path),
                entry.access,
            )
            if normalized not in entries:
                entries.append(normalized)
        file_system = FileSystemPermissions(
            tuple(entries),
            glob_scan_max_depth=file_system.glob_scan_max_depth,
        )
        if file_system.is_empty():
            file_system = None

    return AdditionalPermissionProfile(network=network, file_system=file_system)


def merge_file_system_policy_with_additional_permissions(
    file_system_policy: FileSystemSandboxPolicy,
    additional_permissions: FileSystemPermissions,
) -> FileSystemSandboxPolicy:
    if not isinstance(file_system_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_policy must be FileSystemSandboxPolicy")
    if not isinstance(additional_permissions, FileSystemPermissions):
        raise TypeError("additional_permissions must be FileSystemPermissions")
    if file_system_policy.kind is not FileSystemSandboxKind.RESTRICTED:
        return file_system_policy
    entries = list(file_system_policy.entries)
    for entry in additional_permissions.entries:
        if entry not in entries:
            entries.append(entry)
    return replace(
        file_system_policy,
        entries=tuple(entries),
        glob_scan_max_depth=merge_glob_scan_max_depth(
            file_system_policy.entries,
            file_system_policy.glob_scan_max_depth,
            additional_permissions.entries,
            additional_permissions.glob_scan_max_depth,
        ),
    )


def effective_file_system_sandbox_policy(
    file_system_policy: FileSystemSandboxPolicy,
    additional_permissions: AdditionalPermissionProfile | None,
) -> FileSystemSandboxPolicy:
    if not isinstance(file_system_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_policy must be FileSystemSandboxPolicy")
    if additional_permissions is None:
        return file_system_policy
    if not isinstance(additional_permissions, AdditionalPermissionProfile):
        raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
    if additional_permissions.file_system is None or additional_permissions.file_system.is_empty():
        return file_system_policy
    return merge_file_system_policy_with_additional_permissions(
        file_system_policy,
        additional_permissions.file_system,
    )


def effective_network_sandbox_policy(
    network_policy: NetworkSandboxPolicy,
    additional_permissions: AdditionalPermissionProfile | None,
) -> NetworkSandboxPolicy:
    if not isinstance(network_policy, NetworkSandboxPolicy):
        network_policy = NetworkSandboxPolicy.parse(str(network_policy))
    if additional_permissions is None:
        return network_policy
    if not isinstance(additional_permissions, AdditionalPermissionProfile):
        raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
    if _merge_network_access(network_policy.is_enabled(), additional_permissions):
        return NetworkSandboxPolicy.ENABLED
    return NetworkSandboxPolicy.RESTRICTED


def effective_permission_profile(
    permission_profile: PermissionProfile,
    additional_permissions: AdditionalPermissionProfile | None,
) -> PermissionProfile:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be PermissionProfile")
    file_system_policy, network_policy = permission_profile.to_runtime_permissions()
    effective_file_system_policy = effective_file_system_sandbox_policy(
        file_system_policy,
        additional_permissions,
    )
    effective_network_policy = effective_network_sandbox_policy(
        network_policy,
        additional_permissions,
    )
    enforcement = permission_profile.enforcement()
    if not isinstance(enforcement, SandboxEnforcement):
        enforcement = SandboxEnforcement(enforcement)
    return PermissionProfile.from_runtime_permissions_with_enforcement(
        enforcement,
        effective_file_system_policy,
        effective_network_policy,
    )


def merge_glob_scan_max_depth(
    left_entries: tuple[FileSystemSandboxEntry, ...],
    left_depth: int | None,
    right_entries: tuple[FileSystemSandboxEntry, ...],
    right_depth: int | None,
) -> int | None:
    left_effective = effective_glob_scan_depth(left_entries, left_depth)
    right_effective = effective_glob_scan_depth(right_entries, right_depth)
    if left_effective == "unbounded" or right_effective == "unbounded":
        return None
    depths = [depth for depth in (left_effective, right_effective) if isinstance(depth, int)]
    return max(depths) if depths else None


def effective_glob_scan_depth(
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


def _merge_network_access(
    base_network_access: bool,
    additional_permissions: AdditionalPermissionProfile,
) -> bool:
    return bool(
        base_network_access
        or (
            additional_permissions.network is not None
            and additional_permissions.network.enabled is True
        )
    )


def _normalize_file_system_path(path: FileSystemPath) -> FileSystemPath:
    if path.type != "path" or path.path is None:
        return path
    resolved = _canonicalize_preserving_symlink_spelling(path.path)
    return FileSystemPath.explicit_path(resolved)


def _canonicalize_preserving_symlink_spelling(path: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return Path.cwd() / path


__all__ = [
    "effective_file_system_sandbox_policy",
    "effective_glob_scan_depth",
    "effective_network_sandbox_policy",
    "effective_permission_profile",
    "intersect_permission_profiles",
    "merge_file_system_policy_with_additional_permissions",
    "merge_glob_scan_max_depth",
    "merge_permission_profiles",
    "normalize_additional_permissions",
    "should_require_platform_sandbox",
]
