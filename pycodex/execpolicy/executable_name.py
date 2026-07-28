"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

import os
from pathlib import Path

def executable_lookup_key(raw: str) -> str:
    """Return the exec-policy lookup key for an executable token."""
    import os

    value = str(raw)
    if os.name == "nt":
        lowered = value.lower()
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            if lowered.endswith(suffix):
                return lowered[: -len(suffix)]
        return lowered
    return value


def executable_path_lookup_key(path: object) -> str | None:
    """Return the exec-policy lookup key for the final component of a path."""
    from pathlib import Path

    name = Path(path).name
    if not name:
        return None
    return executable_lookup_key(name)

__all__ = ['executable_lookup_key', 'executable_path_lookup_key']
