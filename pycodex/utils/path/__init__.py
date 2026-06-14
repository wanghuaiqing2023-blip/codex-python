"""Python API boundary for Rust crate ``codex-utils-path``."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def is_wsl() -> bool:
    """Best-effort Python boundary for Rust ``env::is_wsl``."""

    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def normalize_for_path_comparison(path: str | os.PathLike[str]) -> Path:
    return Path(path).resolve(strict=True)


def paths_match_after_normalization(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
    try:
        return normalize_for_path_comparison(left) == normalize_for_path_comparison(right)
    except OSError:
        return Path(left) == Path(right)


def normalize_for_native_workdir(path: str | os.PathLike[str]) -> Path:
    return Path(path)


@dataclass(frozen=True)
class SymlinkWritePaths:
    read_path: Path | None
    write_path: Path


def resolve_symlink_write_paths(path: str | os.PathLike[str]) -> SymlinkWritePaths:
    root = Path(path)
    try:
        current = root.resolve(strict=False)
    except OSError:
        return SymlinkWritePaths(read_path=None, write_path=root)
    return SymlinkWritePaths(read_path=current, write_path=current)


def write_atomically(write_path: str | os.PathLike[str], contents: str) -> None:
    path = Path(write_path)
    parent = path.parent
    if not str(parent):
        raise OSError(f"path {path} has no parent directory")
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(parent), prefix=f".{path.name}.", text=True)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(contents)
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "SymlinkWritePaths",
    "is_wsl",
    "normalize_for_native_workdir",
    "normalize_for_path_comparison",
    "paths_match_after_normalization",
    "resolve_symlink_write_paths",
    "write_atomically",
]
