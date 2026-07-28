"""Merge-base resolution owned by ``branch.rs``."""

from __future__ import annotations

from pathlib import Path

from .errors import NotAGitRepositoryError
from .info import _run_git_stdout, _run_git_stdout_or_none, get_git_repo_root


def merge_base_with_head(repo_path: Path | str, branch: str) -> str | None:
    """Return the merge-base between ``HEAD`` and a local/remote branch."""

    _ensure_pathlike(repo_path, "repo_path")
    _ensure_str(branch, "branch")
    repo_root = get_git_repo_root(repo_path)
    if repo_root is None:
        raise NotAGitRepositoryError(repo_path)
    head = _run_git_stdout_or_none(repo_root, ("rev-parse", "--verify", "HEAD"))
    if head is None:
        return None
    branch_ref = _resolve_branch_ref(repo_root, branch)
    if branch_ref is None:
        return None
    upstream = _resolve_upstream_if_remote_ahead(repo_root, branch)
    preferred_ref = _resolve_branch_ref(repo_root, upstream) if upstream is not None else None
    return _run_git_stdout(repo_root, ("merge-base", head, preferred_ref or branch_ref))


def _resolve_branch_ref(repo_root: Path, branch: str) -> str | None:
    return _run_git_stdout_or_none(repo_root, ("rev-parse", "--verify", branch))


def _resolve_upstream_if_remote_ahead(repo_root: Path, branch: str) -> str | None:
    upstream = _run_git_stdout_or_none(
        repo_root,
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}"),
    )
    if not upstream:
        return None
    counts = _run_git_stdout_or_none(
        repo_root,
        ("rev-list", "--left-right", "--count", f"{branch}...{upstream}"),
    )
    if not counts:
        return None
    parts = counts.split()
    right = int(parts[1]) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else 0
    return upstream if right > 0 else None


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


__all__ = ['merge_base_with_head']
