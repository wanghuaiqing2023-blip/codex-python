"""Low-level Git command operations owned by ``operations.rs``."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable

from .errors import (
    GitCommandError,
    GitOutputUtf8Error,
    GitToolingError,
    NotAGitRepositoryError,
)


def ensure_git_repository(path: Path | str) -> None:
    _ensure_pathlike(path, "path")
    path = Path(path)
    try:
        output = run_git_for_stdout(path, ("rev-parse", "--is-inside-work-tree"))
    except GitCommandError as exc:
        if exc.status == 128:
            raise NotAGitRepositoryError(path) from exc
        raise
    if output.strip() != "true":
        raise NotAGitRepositoryError(path)


def resolve_head(path: Path | str) -> str | None:
    _ensure_pathlike(path, "path")
    try:
        return run_git_for_stdout(Path(path), ("rev-parse", "--verify", "HEAD"))
    except GitCommandError as exc:
        if exc.status == 128:
            return None
        raise


def resolve_repository_root(path: Path | str) -> Path:
    _ensure_pathlike(path, "path")
    return Path(run_git_for_stdout(Path(path), ("rev-parse", "--show-toplevel")))


def run_git_for_status(
    directory: Path | str,
    args: Iterable[str],
    env: Iterable[tuple[str, str]] | None = None,
) -> None:
    run_git(directory, args, env)


def run_git_for_stdout(
    directory: Path | str,
    args: Iterable[str],
    env: Iterable[tuple[str, str]] | None = None,
) -> str:
    command, output = run_git(directory, args, env)
    try:
        return output.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise GitOutputUtf8Error(command, exc) from exc


def run_git(
    directory: Path | str,
    args: Iterable[str],
    env: Iterable[tuple[str, str]] | None = None,
) -> tuple[str, subprocess.CompletedProcess[bytes]]:
    _ensure_pathlike(directory, "directory")
    if isinstance(args, (str, bytes)):
        raise TypeError("args must be an iterable of strings")
    args_list = list(args)
    if not all(isinstance(arg, str) for arg in args_list):
        raise TypeError("args must contain only strings")
    disabled_hooks_path = "NUL" if os.name == "nt" else "/dev/null"
    git_args = ["-c", f"core.hooksPath={disabled_hooks_path}", *args_list]
    command = _build_git_command_string(git_args)
    child_env = os.environ.copy()
    if env is not None:
        for key, value in env:
            child_env[str(key)] = str(value)
    try:
        output = subprocess.run(
            ["git", *git_args],
            cwd=Path(directory),
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise GitToolingError(str(exc)) from exc
    if output.returncode != 0:
        stderr = output.stderr.decode("utf-8", errors="replace").strip()
        raise GitCommandError(command, output.returncode, stderr)
    return command, output


def _build_git_command_string(args: Iterable[str]) -> str:
    args_list = list(args)
    if not args_list:
        return "git"
    return "git " + " ".join(args_list)


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


__all__ = ['ensure_git_repository', 'resolve_head', 'resolve_repository_root', 'run_git', 'run_git_for_status', 'run_git_for_stdout']
