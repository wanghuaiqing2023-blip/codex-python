"""Git tooling errors owned by ``errors.rs``."""

from __future__ import annotations

from pathlib import Path


class GitToolingError(Exception):
    """Error raised while managing git worktree snapshots."""


class GitCommandError(GitToolingError):
    """Raised when a git command exits unsuccessfully."""

    def __init__(self, command: str, status: int | str, stderr: str) -> None:
        _ensure_str(command, "command")
        _ensure_str(stderr, "stderr")
        self.command = command
        self.status = status
        self.stderr = stderr
        super().__init__(f"git command `{command}` failed with status {status}: {stderr}")


class GitOutputUtf8Error(GitToolingError):
    """Raised when a git command produces non-UTF-8 output."""

    def __init__(self, command: str, source: UnicodeDecodeError | None = None) -> None:
        _ensure_str(command, "command")
        self.command = command
        self.source = source
        super().__init__(f"git command `{command}` produced non-UTF-8 output")


class NotAGitRepositoryError(GitToolingError):
    """Raised when an expected repository path is not a git repository."""

    def __init__(self, path: Path | str) -> None:
        _ensure_pathlike(path, "path")
        self.path = Path(path)
        super().__init__(f"{self.path!r} is not a git repository")


class NonRelativePathError(GitToolingError):
    """Raised when a path must be relative to the repository root."""

    def __init__(self, path: Path | str) -> None:
        _ensure_pathlike(path, "path")
        self.path = Path(path)
        super().__init__(f"path {self.path!r} must be relative to the repository root")


class PathEscapesRepositoryError(GitToolingError):
    """Raised when a path escapes the repository root."""

    def __init__(self, path: Path | str) -> None:
        _ensure_pathlike(path, "path")
        self.path = Path(path)
        super().__init__(f"path {self.path!r} escapes the repository root")


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


__all__ = ['GitToolingError', 'GitCommandError', 'GitOutputUtf8Error', 'NotAGitRepositoryError', 'NonRelativePathError', 'PathEscapesRepositoryError']
