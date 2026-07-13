"""Windows-local permission resolution for the native sandbox backend.

Rust owner: ``codex-windows-sandbox::resolved_permissions`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping

from pycodex.protocol import (
    FileSystemSandboxKind,
    NetworkSandboxPolicy,
    PermissionProfile,
)


class WindowsSandboxPermissionError(ValueError):
    """Raised when a permission profile cannot be enforced on Windows."""


class WindowsSandboxTokenMode(str, Enum):
    READ_ONLY_CAPABILITY = "read-only-capability"
    WRITABLE_ROOTS_CAPABILITY = "writable-roots-capability"


@dataclass(frozen=True)
class WindowsWritableRoot:
    root: Path
    read_only_subpaths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ResolvedWindowsSandboxPermissions:
    """Runtime permissions materialized against one permission-profile cwd."""

    file_system: object
    network: NetworkSandboxPolicy

    @classmethod
    def try_from_permission_profile(
        cls,
        permission_profile: PermissionProfile,
    ) -> "ResolvedWindowsSandboxPermissions":
        if not isinstance(permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be a PermissionProfile")
        if permission_profile.type != "managed":
            raise WindowsSandboxPermissionError(
                "only managed permission profiles can be enforced by the Windows sandbox"
            )
        file_system, network = permission_profile.to_runtime_permissions()
        if file_system.kind is not FileSystemSandboxKind.RESTRICTED:
            raise WindowsSandboxPermissionError(
                "only restricted managed filesystem permissions can be enforced by the Windows sandbox"
            )
        return cls(file_system=file_system, network=network)

    @classmethod
    def try_from_permission_profile_for_cwd(
        cls,
        permission_profile: PermissionProfile,
        cwd: str | Path,
    ) -> "ResolvedWindowsSandboxPermissions":
        resolved = cls.try_from_permission_profile(permission_profile)
        return cls(
            file_system=resolved.file_system.materialize_project_roots_with_cwd(Path(cwd)),
            network=resolved.network,
        )

    def should_apply_network_block(self) -> bool:
        return not self.network.is_enabled()

    def network_policy(self) -> NetworkSandboxPolicy:
        return self.network

    def is_enforceable_by_windows_sandbox(self) -> bool:
        return self.file_system.kind is FileSystemSandboxKind.RESTRICTED

    def has_full_disk_read_access(self) -> bool:
        return bool(self.file_system.has_full_disk_read_access())

    def include_platform_defaults(self) -> bool:
        return bool(self.file_system.include_platform_defaults())

    def readable_roots_for_cwd(self, cwd: str | Path) -> tuple[Path, ...]:
        return tuple(Path(path) for path in self.file_system.get_readable_roots_with_cwd(Path(cwd)))

    def uses_write_capabilities_for_cwd(
        self,
        cwd: str | Path,
        env_map: Mapping[str, str],
    ) -> bool:
        return bool(self.writable_roots_for_cwd(cwd, env_map))

    def writable_roots_for_cwd(
        self,
        cwd: str | Path,
        env_map: Mapping[str, str],
    ) -> tuple[WindowsWritableRoot, ...]:
        roots = [
            WindowsWritableRoot(
                root=Path(root.root),
                read_only_subpaths=tuple(Path(path) for path in root.read_only_subpaths),
            )
            for root in self.file_system.get_writable_roots_with_cwd(Path(cwd))
        ]
        if self._has_writable_tmpdir_entry():
            roots.extend(
                WindowsWritableRoot(root=root)
                for root in _windows_temp_env_roots(env_map)
            )
        return tuple(roots)

    def _has_writable_tmpdir_entry(self) -> bool:
        return any(
            entry.path.type == "special"
            and entry.path.value is not None
            and entry.path.value.kind == "tmpdir"
            and entry.access.can_write()
            for entry in self.file_system.entries
        )


def token_mode_for_permission_profile(
    permission_profile: PermissionProfile,
    cwd: str | Path,
    env_map: Mapping[str, str],
) -> WindowsSandboxTokenMode:
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        permission_profile,
        cwd,
    )
    if permissions.file_system.has_full_disk_write_access():
        raise WindowsSandboxPermissionError(
            "permission profile requests full-disk filesystem writes, which cannot be enforced by the Windows sandbox"
        )
    if permissions.writable_roots_for_cwd(cwd, env_map):
        return WindowsSandboxTokenMode.WRITABLE_ROOTS_CAPABILITY
    return WindowsSandboxTokenMode.READ_ONLY_CAPABILITY


def _windows_temp_env_roots(env_map: Mapping[str, str]) -> tuple[Path, ...]:
    roots: list[Path] = []
    for key in ("TEMP", "TMP"):
        value = env_map.get(key) or os.environ.get(key)
        if value:
            path = Path(value)
            if path.is_absolute():
                roots.append(path)
    return tuple(roots)


__all__ = [
    "ResolvedWindowsSandboxPermissions",
    "WindowsSandboxPermissionError",
    "WindowsSandboxTokenMode",
    "WindowsWritableRoot",
    "token_mode_for_permission_profile",
]
