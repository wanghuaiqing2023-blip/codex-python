"""Platform-specific symlink behavior owned by ``platform.rs``."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import GitToolingError


def create_symlink(source: Path | str, link_target: Path | str, destination: Path | str) -> None:
    """Create a symlink for git snapshot materialization.

    Mirrors Rust ``codex_git_utils::create_symlink``.  Unix uses the provided
    link target directly; Windows asks Python to create a directory symlink
    when the source path resolves as a directory, otherwise a file symlink.
    """

    _ensure_pathlike(source, "source")
    _ensure_pathlike(link_target, "link_target")
    _ensure_pathlike(destination, "destination")
    source_path = Path(source)
    target_path = Path(link_target)
    destination_path = Path(destination)
    try:
        if os.name == "nt":
            os.symlink(target_path, destination_path, target_is_directory=source_path.is_dir())
        else:
            os.symlink(target_path, destination_path)
    except OSError as exc:
        raise GitToolingError(str(exc)) from exc


def _ensure_pathlike(value: object, name: str) -> None:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a path-like value")


def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")


def _ensure_str_list(value: object, name: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{name} must be a list of strings")


def _ensure_i64(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


def _ensure_usize(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


__all__ = ['create_symlink']
