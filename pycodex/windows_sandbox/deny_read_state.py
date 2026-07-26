"""Persistent deny-read ACL reconciliation for elevated sandbox identities.

Rust owner: ``codex-windows-sandbox::deny_read_state`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .acl import revoke_ace
from .deny_read_acl import (
    apply_deny_read_acls,
    lexical_path_key,
)
from .setup import sandbox_dir
from .token import LocalSid


DENY_READ_ACL_STATE_FILE = "deny_read_acl_state.json"


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


__all__ = [
    "DENY_READ_ACL_STATE_FILE",
    "sync_persistent_deny_read_acls",
]
