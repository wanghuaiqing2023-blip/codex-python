"""Shell type detection for the ``codex-shell-command`` crate coordinate.

Rust source: ``codex/codex-rs/shell-command/src/shell_detect.rs``.
"""

from __future__ import annotations

from pathlib import PurePath
from typing import Any


def detect_shell_type(shell_path: str | PurePath) -> Any | None:
    """Return the known shell type for a binary name or path.

    The Rust helper first checks exact known names, then recursively checks the
    file stem. That means ``/usr/bin/bash`` and ``powershell.exe`` both resolve
    through their stem, while unknown names return ``None``.
    """

    if not isinstance(shell_path, (str, PurePath)):
        raise TypeError("shell_path must be a string or path-like value")
    return _detect(str(shell_path))


def _detect(value: str) -> Any | None:
    ShellType = _shell_type()
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

    stem = _file_stem(value)
    if stem and stem != value:
        return _detect(stem)
    return None


def _shell_type() -> Any:
    from pycodex.core.shell import ShellType

    return ShellType


def _file_stem(value: str) -> str:
    normalized = value.replace("\\", "/").rstrip("/")
    base = normalized.rsplit("/", 1)[-1]
    if "." not in base:
        return base
    return base.rsplit(".", 1)[0]


__all__ = ["detect_shell_type"]
