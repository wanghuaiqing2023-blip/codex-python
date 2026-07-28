"""Path helpers from Rust ``local/path.rs``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..backend import MemoriesBackendError


def read_sorted_dir_paths(dir_path: str | Path) -> list[Path]:
    path = Path(dir_path)
    if not path.exists():
        return []
    return sorted(path.iterdir())


def reject_symlink(path: str, metadata: Any) -> None:
    is_symlink = (
        metadata.is_symlink()
        if hasattr(metadata, "is_symlink")
        else bool(getattr(metadata, "is_symlink", False))
    )
    if is_symlink:
        raise MemoriesBackendError.invalid_path(path, "must not be a symlink")


def is_hidden_component(component: str | Path) -> bool:
    return str(component).startswith(".")


def is_hidden_path(path: str | Path) -> bool:
    return Path(path).name.startswith(".")


def display_relative_path(root: str | Path, path: str | Path) -> str:
    root_path = Path(root)
    path_value = Path(path)
    try:
        relative = path_value.relative_to(root_path)
    except ValueError:
        relative = path_value
    return "/".join(part for part in relative.parts if part)


__all__ = [
    "display_relative_path",
    "is_hidden_component",
    "is_hidden_path",
    "read_sorted_dir_paths",
    "reject_symlink",
]
