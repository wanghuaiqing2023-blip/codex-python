"""Port of Rust ``codex-utils-absolute-path`` public API.

Rust source:
- ``codex/codex-rs/utils/absolute-path/src/lib.rs``
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


_ABSOLUTE_PATH_BASE: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "absolute_path_base",
    default=None,
)


@dataclass(frozen=True, order=True)
class AbsolutePathBuf:
    _path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "_path", _normalize(self._path))

    @classmethod
    def resolve_path_against_base(cls, path: str | Path, base_path: str | Path) -> "AbsolutePathBuf":
        candidate = _expand_home(Path(path))
        base = _normalize(Path(base_path))
        if not candidate.is_absolute():
            candidate = base / candidate
        return cls(_absolutize(candidate))

    @classmethod
    def from_absolute_path(cls, path: str | Path) -> "AbsolutePathBuf":
        candidate = _expand_home(Path(path))
        return cls(_absolutize(candidate))

    @classmethod
    def from_absolute_path_checked(cls, path: str | Path) -> "AbsolutePathBuf":
        candidate = _expand_home(Path(path))
        candidate = _normalize(candidate)
        if not candidate.is_absolute():
            raise ValueError(f"path is not absolute: {path}")
        return cls(_absolutize(candidate))

    @classmethod
    def current_dir(cls) -> "AbsolutePathBuf":
        return cls.from_absolute_path(Path.cwd())

    @classmethod
    def relative_to_current_dir(cls, path: str | Path) -> "AbsolutePathBuf":
        return cls.resolve_path_against_base(path, Path.cwd())

    @classmethod
    def deserialize(cls, path: str | Path) -> "AbsolutePathBuf":
        candidate = Path(path)
        base = _ABSOLUTE_PATH_BASE.get()
        if base is not None:
            return cls.resolve_path_against_base(candidate, base)
        if candidate.is_absolute():
            return cls.from_absolute_path(candidate)
        raise ValueError("AbsolutePathBuf deserialized without a base path")

    def join(self, path: str | Path) -> "AbsolutePathBuf":
        return self.resolve_path_against_base(path, self._path)

    def canonicalize(self) -> "AbsolutePathBuf":
        return AbsolutePathBuf.from_absolute_path_checked(self._path.resolve(strict=True))

    def parent(self) -> "AbsolutePathBuf | None":
        parent = self._path.parent
        return AbsolutePathBuf(parent) if parent != self._path else None

    def ancestors(self) -> Iterator["AbsolutePathBuf"]:
        for ancestor in self._path.parents:
            yield AbsolutePathBuf(ancestor)

    def as_path(self) -> Path:
        return self._path

    def into_path_buf(self) -> Path:
        return self._path

    def to_path_buf(self) -> Path:
        return self._path

    def to_string_lossy(self) -> str:
        return str(self._path)

    def display(self) -> str:
        return str(self._path)

    def __fspath__(self) -> str:
        return str(self._path)

    def __str__(self) -> str:
        return str(self._path)


class AbsolutePathBufGuard:
    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path)
        self._token: contextvars.Token[Path | None] | None = None

    def __enter__(self) -> "AbsolutePathBufGuard":
        self._token = _ABSOLUTE_PATH_BASE.set(self._base_path)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._token is not None:
            _ABSOLUTE_PATH_BASE.reset(self._token)
            self._token = None


def canonicalize_preserving_symlinks(path: str | Path) -> Path:
    logical = AbsolutePathBuf.from_absolute_path(path).into_path_buf()
    try:
        canonical = Path(path).resolve(strict=True)
    except OSError:
        return logical
    return logical if _should_preserve_logical_path(logical) and canonical != logical else canonical


def canonicalize_existing_preserving_symlinks(path: str | Path) -> Path:
    logical = AbsolutePathBuf.from_absolute_path(path).into_path_buf()
    canonical = Path(path).resolve(strict=True)
    return logical if _should_preserve_logical_path(logical) and canonical != logical else canonical


def _expand_home(path: Path) -> Path:
    text = str(path)
    if text == "~" or text.startswith("~/") or text.startswith("~\\"):
        return Path.home() / text[2:] if len(text) > 1 else Path.home()
    return path


def _normalize(path: Path) -> Path:
    return Path(_normalize_windows_device_path(str(path)) or path)


def _normalize_windows_device_path(path: str) -> str | None:
    for prefix in ("\\\\?\\UNC\\", "\\\\.\\UNC\\"):
        if path.startswith(prefix):
            return "\\\\" + path[len(prefix):]
    for prefix in ("\\\\?\\", "\\\\.\\"):
        if path.startswith(prefix):
            rest = path[len(prefix):]
            if len(rest) >= 3 and rest[0].isalpha() and rest[1] == ":" and rest[2] in "\\/":
                return rest
    return None


def _absolutize(path: Path) -> Path:
    if path.is_absolute():
        return Path(*_normalized_parts(path))
    return Path.cwd() / Path(*_normalized_parts(path))


def _normalized_parts(path: Path) -> tuple[str, ...]:
    output: list[str] = []
    for part in path.parts:
        if part == ".":
            continue
        if part == ".." and output and output[-1] != "..":
            if len(output) > 1 or not Path(output[0]).anchor:
                output.pop()
            continue
        output.append(part)
    return tuple(output)


def _should_preserve_logical_path(logical: Path) -> bool:
    ancestors = list(logical.parents)
    for ancestor in ancestors:
        try:
            if ancestor.is_symlink() and ancestor.parent.parent != ancestor.parent:
                return True
        except OSError:
            continue
    return False


__all__ = [
    "AbsolutePathBuf",
    "AbsolutePathBufGuard",
    "canonicalize_existing_preserving_symlinks",
    "canonicalize_preserving_symlinks",
]
