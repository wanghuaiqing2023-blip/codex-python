"""Resume hints from Rust ``resume_command.rs``."""

from __future__ import annotations

import shlex


def resume_command(
    thread_name: str | None,
    thread_id: object | None,
) -> str | None:
    target = thread_name if thread_name else (
        str(thread_id) if thread_id is not None else None
    )
    if not target:
        return None
    escaped = _shlex_join_one(target)
    if target.startswith("-"):
        return f"codex resume -- {escaped}"
    return f"codex resume {escaped}"


def resume_hint(
    thread_name: str | None,
    thread_id: object | None,
) -> str | None:
    if thread_id is None:
        return None
    if thread_name:
        return f"codex resume, then select {thread_name} ({thread_id})"
    return resume_command(None, thread_id)


def _shlex_join_one(value: str) -> str:
    if value and all(ch.isalnum() or ch in "@%_+=:,./-" for ch in value):
        return value
    if "'" in value and '"' not in value:
        return '"' + value.replace('"', '\\"') + '"'
    return shlex.quote(value)


__all__ = ["resume_command", "resume_hint"]
