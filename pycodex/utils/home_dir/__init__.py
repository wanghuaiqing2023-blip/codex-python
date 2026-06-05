"""Codex home directory helpers.

Ported from ``codex/codex-rs/utils/home-dir/src/lib.rs``.
"""

from __future__ import annotations

import os
from pathlib import Path

CODEX_HOME_ENV = "CODEX_HOME"


def find_codex_home(env: dict[str, str] | None = None, home: Path | str | None = None) -> Path:
    """Return ``CODEX_HOME`` or ``~/.codex`` using upstream validation rules."""

    if env is not None and not isinstance(env, dict):
        raise TypeError("env must be a mapping or None")
    environ = os.environ if env is None else env
    raw = environ.get(CODEX_HOME_ENV)
    if raw is not None and not isinstance(raw, str):
        raise TypeError("CODEX_HOME must be a string")
    if raw:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(f"CODEX_HOME points to {raw!r}, but that path does not exist")
        if not path.is_dir():
            raise NotADirectoryError(f"CODEX_HOME points to {raw!r}, but that path is not a directory")
        return path.resolve()

    if home is not None and not isinstance(home, (str, Path)):
        raise TypeError("home must be a string or Path")
    base_home = Path.home() if home is None else Path(home)
    return base_home / ".codex"


__all__ = [
    "CODEX_HOME_ENV",
    "find_codex_home",
]