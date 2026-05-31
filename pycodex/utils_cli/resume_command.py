"""Formatting for user-facing ``codex resume`` command hints.

Ported from ``codex/codex-rs/utils/cli/src/resume_command.rs``.
"""

from __future__ import annotations

import re
from typing import Any

_SAFE_UNQUOTED = re.compile(r"^[A-Za-z0-9_@%+=:,./-]+$")


def resume_command(thread_name: str | None, thread_id: Any | None) -> str | None:
    resume_target = thread_name if thread_name else None
    if resume_target is None and thread_id is not None:
        resume_target = str(thread_id)
    if resume_target is None:
        return None

    needs_double_dash = resume_target.startswith("-")
    escaped = _shlex_join_one(resume_target)
    if needs_double_dash:
        return f"codex resume -- {escaped}"
    return f"codex resume {escaped}"


def resume_hint(thread_name: str | None, thread_id: Any | None) -> str | None:
    if thread_id is None:
        return None
    thread_id_text = str(thread_id)
    if thread_name:
        return f"codex resume, then select {thread_name} ({thread_id_text})"
    return resume_command(None, thread_id_text)


def _shlex_join_one(token: str) -> str:
    if "\x00" in token:
        return "<command included NUL byte>"
    if token and _SAFE_UNQUOTED.fullmatch(token):
        return token
    if "'" in token and '"' not in token and not any(ch in token for ch in "\\$`\n\r"):
        return f'"{token}"'
    return "'" + token.replace("'", "'\"'\"'") + "'"
