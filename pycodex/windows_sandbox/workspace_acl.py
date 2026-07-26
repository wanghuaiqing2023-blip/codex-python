"""Workspace-specific ACL decisions."""

from __future__ import annotations

from pathlib import Path

from .acl import add_deny_write_ace
from .path_normalization import canonicalize_path


def is_command_cwd_root(
    root: str | Path,
    canonical_command_cwd: str | Path,
) -> bool:
    return canonicalize_path(root) == Path(canonical_command_cwd)


def protect_workspace_codex_dir(cwd: str | Path, sid: object) -> bool:
    return _protect_workspace_subdir(cwd, sid, ".codex")


def protect_workspace_agents_dir(cwd: str | Path, sid: object) -> bool:
    return _protect_workspace_subdir(cwd, sid, ".agents")


def _protect_workspace_subdir(
    cwd: str | Path,
    sid: object,
    subdir: str,
) -> bool:
    path = Path(cwd) / subdir
    if not path.is_dir():
        return False
    return add_deny_write_ace(path, sid)


__all__ = [
    "is_command_cwd_root",
    "protect_workspace_agents_dir",
    "protect_workspace_codex_dir",
]
