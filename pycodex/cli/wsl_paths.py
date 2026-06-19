"""WSL path helpers for CLI compatibility.

Ported from ``codex/codex-rs/cli/src/wsl_paths.rs``.
"""

from __future__ import annotations

from os import PathLike

from pycodex.utils.path import is_wsl


def win_path_to_wsl(path: str) -> str | None:
    """Convert a Windows drive path into a WSL ``/mnt/<drive>`` path."""

    if not isinstance(path, str):
        raise TypeError("path must be a string")
    if len(path) < 3:
        return None
    drive, colon, separator = path[0], path[1], path[2]
    if colon != ":" or separator not in {"\\", "/"} or not drive.isascii() or not drive.isalpha():
        return None
    drive = drive.lower()
    tail = path[3:].replace("\\", "/")
    if not tail:
        return f"/mnt/{drive}"
    return f"/mnt/{drive}/{tail}"


def normalize_for_wsl(path: str | PathLike[str], *, wsl: bool | None = None) -> str:
    """Map Windows drive paths to WSL mount paths when running under WSL."""

    value = str(path)
    if wsl is None:
        wsl = is_wsl()
    if not wsl:
        return value
    return win_path_to_wsl(value) or value
