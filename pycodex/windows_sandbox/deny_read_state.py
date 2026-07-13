"""Persistent deny-read ACL reconciliation for elevated sandbox identities.

Rust owner: ``codex-windows-sandbox::deny_read_state`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .acl import add_deny_read_ace, revoke_ace
from .path_normalization import canonicalize_path
from .setup import sandbox_dir
from .token import LocalSid


DENY_READ_ACL_STATE_FILE = "deny_read_acl_state.json"


def lexical_path_key(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/").rstrip("/").lower()


def plan_deny_read_acl_paths(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    planned: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw)
        _append_unique(planned, seen, path)
        if path.exists():
            _append_unique(planned, seen, canonicalize_path(path))
    return tuple(planned)


def apply_deny_read_acls(paths: Iterable[str | Path], sid: LocalSid | int) -> tuple[Path, ...]:
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


def sync_persistent_deny_read_acls(
    codex_home: str | Path,
    principal_sid: str,
    desired_paths: Iterable[str | Path],
    sid: LocalSid | int,
) -> tuple[Path, ...]:
    state_path = sandbox_dir(codex_home) / DENY_READ_ACL_STATE_FILE
    state = _load_state(state_path)
    previous = tuple(Path(path) for path in state.get(principal_sid, ()))
    applied = apply_deny_read_acls(desired_paths, sid)
    desired_keys = {lexical_path_key(path) for path in applied}
    for path in previous:
        if lexical_path_key(path) not in desired_keys:
            revoke_ace(path, sid)
    if applied:
        state[principal_sid] = [str(path) for path in applied]
    else:
        state.pop(principal_sid, None)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"principals": state}, indent=2), encoding="utf-8")
    return applied


def _load_state(path: Path) -> dict[str, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict) or not isinstance(value.get("principals", {}), dict):
        raise ValueError(f"invalid deny-read ACL state: {path}")
    result: dict[str, list[str]] = {}
    for principal, paths in value.get("principals", {}).items():
        if not isinstance(principal, str) or not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            raise ValueError(f"invalid deny-read ACL state entry: {path}")
        result[principal] = list(paths)
    return result


def _append_unique(output: list[Path], seen: set[str], path: Path) -> None:
    key = lexical_path_key(path)
    if key not in seen:
        seen.add(key)
        output.append(path)


__all__ = [
    "DENY_READ_ACL_STATE_FILE",
    "apply_deny_read_acls",
    "lexical_path_key",
    "plan_deny_read_acl_paths",
    "sync_persistent_deny_read_acls",
]
