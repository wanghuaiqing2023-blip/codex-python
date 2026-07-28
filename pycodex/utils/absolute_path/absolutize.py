"""Lexical path absolutization from ``codex-utils-absolute-path``."""

from __future__ import annotations

import os
from pathlib import Path


def absolutize(path: str | Path) -> Path:
    value = Path(path)
    if value.is_absolute():
        return normalize_path(value)
    return absolutize_from(value, Path.cwd())


def absolutize_from(path: str | Path, base_path: str | Path) -> Path:
    return normalize_path(path_with_base(Path(path), Path(base_path)))


def normalize_path(path: Path) -> Path:
    normalized: list[str] = []
    for component in path.parts:
        if component == ".":
            continue
        if component == "..":
            if normalized:
                candidate = Path(*normalized)
                if not (len(normalized) == 1 and candidate.anchor):
                    normalized.pop()
            continue
        normalized.append(component)
    return Path(*normalized) if normalized else Path(".")


def path_with_base(path: Path, base_path: Path) -> Path:
    if os.name != "nt":
        return path if path.is_absolute() else base_path / path

    text = str(path)
    drive, tail = os.path.splitdrive(text)
    base_drive, base_tail = os.path.splitdrive(str(base_path))
    if path.is_absolute():
        return path
    if tail.startswith(("\\", "/")):
        return Path(f"{base_drive}{tail}")
    if drive:
        return Path(f"{drive}{base_tail}\\{tail}")
    return base_path / path


__all__ = ["absolutize", "absolutize_from"]
