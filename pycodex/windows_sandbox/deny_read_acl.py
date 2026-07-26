"""Deny-read ACL planning and application.

Rust owner: ``codex-windows-sandbox::deny_read_acl``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .acl import add_deny_read_ace, revoke_ace
from .path_normalization import canonicalize_path
from .token import LocalSid


def lexical_path_key(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/").rstrip("/").lower()


def plan_deny_read_acl_paths(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    planned: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw)
        _push_planned_path(planned, seen, path)
        if path.exists():
            _push_planned_path(planned, seen, canonicalize_path(path))
    return tuple(planned)


def apply_deny_read_acls(
    paths: Iterable[str | Path],
    sid: LocalSid | int,
) -> tuple[Path, ...]:
    applied: list[Path] = []
    added: list[Path] = []
    try:
        for path in plan_deny_read_acl_paths(paths):
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            if add_deny_read_ace(path, sid):
                added.append(path)
            applied.append(path)
    except BaseException:
        for path in added:
            revoke_ace(path, sid)
        raise
    return tuple(applied)


def _push_planned_path(
    output: list[Path],
    seen: set[str],
    path: Path,
) -> None:
    key = lexical_path_key(path)
    if key not in seen:
        seen.add(key)
        output.append(path)


__all__ = [
    "apply_deny_read_acls",
    "lexical_path_key",
    "plan_deny_read_acl_paths",
]
