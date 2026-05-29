"""Shell type detection helpers.

Ported from ``codex/codex-rs/core/src/shell_detect.rs``. The Rust helper
canonicalizes a path by recursively looking at its file stem until it reaches a
known shell name.
"""

from __future__ import annotations

from pathlib import PurePath

from pycodex.core.shell import ShellType


def detect_shell_type(shell_path: str | PurePath) -> ShellType | None:
    if not isinstance(shell_path, (str, PurePath)):
        raise TypeError("shell_path must be a string or path-like value")
    return _detect(str(shell_path))


def _detect(value: str) -> ShellType | None:
    if value == "zsh":
        return ShellType.ZSH
    if value == "sh":
        return ShellType.SH
    if value == "cmd":
        return ShellType.CMD
    if value == "bash":
        return ShellType.BASH
    if value in {"pwsh", "powershell"}:
        return ShellType.POWERSHELL

    stem = PurePath(value).stem
    if stem and stem != value:
        return _detect(stem)
    return None


__all__ = ["detect_shell_type"]
