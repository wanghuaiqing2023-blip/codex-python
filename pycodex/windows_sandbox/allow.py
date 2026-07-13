"""Allow/deny path projection for legacy Windows sandbox ACLs.

Rust owner: ``codex-windows-sandbox::allow`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .path_normalization import canonicalize_path
from .resolved_permissions import ResolvedWindowsSandboxPermissions


@dataclass(frozen=True)
class AllowDenyPaths:
    allow: frozenset[Path] = frozenset()
    deny: frozenset[Path] = frozenset()


def compute_allow_paths_for_permissions(
    permissions: ResolvedWindowsSandboxPermissions,
    command_cwd: str | Path,
    env_map: Mapping[str, str],
) -> AllowDenyPaths:
    if not isinstance(permissions, ResolvedWindowsSandboxPermissions):
        raise TypeError("permissions must be ResolvedWindowsSandboxPermissions")
    cwd = Path(command_cwd)
    allow: set[Path] = set()
    deny: set[Path] = set()
    for writable_root in permissions.writable_roots_for_cwd(cwd, env_map):
        root = canonicalize_path(writable_root.root)
        if root.exists():
            allow.add(root)
        for read_only_subpath in writable_root.read_only_subpaths:
            path = canonicalize_path(read_only_subpath)
            if path.exists():
                deny.add(path)
    return AllowDenyPaths(frozenset(allow), frozenset(deny))


__all__ = ["AllowDenyPaths", "compute_allow_paths_for_permissions"]
