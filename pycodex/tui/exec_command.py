"""Command display/splitting helpers for the TUI port.

Rust counterpart: ``codex-rs/tui/src/exec_command.rs``.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Iterable

from pycodex.shell_command.parse_command import extract_shell_command


def escape_command(command: Iterable[str]) -> str:
    parts = [str(part) for part in command]
    try:
        return shlex.join(parts)
    except Exception:
        return " ".join(parts)


def strip_bash_lc_and_escape(command: Iterable[str]) -> str:
    parts = [str(part) for part in command]
    extracted = extract_shell_command(parts)
    if extracted is not None:
        return extracted[1]
    return escape_command(parts)


def split_command_string(command: str) -> list[str]:
    if ":\\" in command:
        windows_parts = _split_shlex_joined_windows_command(command)
        if windows_parts is not None:
            return windows_parts
    try:
        parts = shlex.split(command)
    except ValueError:
        return [command]
    try:
        round_trip = shlex.join(parts)
    except Exception:
        return [command]
    if round_trip == command:
        return parts
    if ":\\" not in command:
        try:
            if shlex.split(round_trip) == parts:
                return parts
        except ValueError:
            pass
    return [command]


def _split_shlex_joined_windows_command(command: str) -> list[str] | None:
    """Reverse Rust/Python shlex joining without consuming path backslashes."""

    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""
    try:
        parts = list(lexer)
    except ValueError:
        return None
    if not parts:
        return None
    try:
        return parts if shlex.join(parts) == command else None
    except Exception:
        return None


def relativize_to_home(path: str | os.PathLike[str]) -> Path | None:
    candidate = Path(path)
    if not candidate.is_absolute():
        return None
    home = Path.home()
    try:
        return candidate.relative_to(home)
    except ValueError:
        return None


__all__ = [
    "escape_command",
    "relativize_to_home",
    "split_command_string",
    "strip_bash_lc_and_escape",
]
