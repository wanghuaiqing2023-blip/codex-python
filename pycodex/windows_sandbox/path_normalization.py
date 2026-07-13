"""Windows sandbox path normalization.

Rust owner: ``codex-windows-sandbox::path_normalization`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

from pathlib import Path


def canonicalize_path(path: str | Path) -> Path:
    candidate = Path(path)
    try:
        return candidate.resolve(strict=True)
    except OSError:
        return candidate


def canonical_path_key(path: str | Path) -> str:
    return str(canonicalize_path(path)).replace("\\", "/").lower()


__all__ = ["canonical_path_key", "canonicalize_path"]
