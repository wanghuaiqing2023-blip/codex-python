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
