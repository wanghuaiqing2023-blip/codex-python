"""Git baseline snapshots owned by ``baseline.rs``."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from difflib import unified_diff
from enum import Enum
from pathlib import Path
from typing import Iterable

from pycodex.protocol import GitSha

from .errors import GitCommandError, GitToolingError
from .info import run_git_command_with_timeout
from .operations import resolve_head, run_git_for_status, run_git_for_stdout

BASELINE_COMMIT_MESSAGE = "Initialize Codex git baseline\n\nCo-authored-by: Codex <noreply@openai.com>"


class GitBaselineChangeStatus(Enum):
    ADDED = "Added"
    MODIFIED = "Modified"
    DELETED = "Deleted"

    def label(self) -> str:
        if self is GitBaselineChangeStatus.ADDED:
            return "A"
        if self is GitBaselineChangeStatus.MODIFIED:
            return "M"
        return "D"


@dataclass(frozen=True)
class GitBaselineChange:
    status: GitBaselineChangeStatus
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, GitBaselineChangeStatus):
            raise TypeError("status must be a GitBaselineChangeStatus")
        _ensure_str(self.path, "path")


@dataclass(frozen=True)
class GitBaselineDiff:
    changes: list[GitBaselineChange]
    unified_diff: str

    def __post_init__(self) -> None:
        if not isinstance(self.changes, list) or not all(isinstance(change, GitBaselineChange) for change in self.changes):
            raise TypeError("changes must be a list of GitBaselineChange")
        _ensure_str(self.unified_diff, "unified_diff")

    def has_changes(self) -> bool:
        return bool(self.changes)


def reset_git_repository(root: Path | str) -> None:
    """Replace ``root/.git`` with a fresh one-commit baseline repository."""

    _ensure_pathlike(root, "root")
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    _remove_git_metadata(root_path)
    run_git_for_status(root_path, ("init",))
    _commit_current_tree(root_path, BASELINE_COMMIT_MESSAGE)
    _write_index_from_head(root_path)


def ensure_git_baseline_repository(root: Path | str) -> None:
    """Ensure ``root`` has a usable git baseline repository."""

    _ensure_pathlike(root, "root")
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    if (root_path / ".git").is_dir():
        try:
            if resolve_head(root_path) is not None:
                _write_index_from_head(root_path)
                return
        except GitToolingError:
            pass
    reset_git_repository(root_path)


def diff_since_latest_init(root: Path | str) -> GitBaselineDiff:
    """Return the diff between the baseline commit and current directory."""

    _ensure_pathlike(root, "root")
    root_path = Path(root)
    head_entries = _baseline_head_entries(root_path)
    current_entries = _baseline_current_entries(root_path)
    changes = _diff_baseline_entries(head_entries, current_entries)
    rendered = "".join(
        _render_baseline_change_diff(root_path, head_entries, current_entries, change)
        for change in changes
    )
    return GitBaselineDiff(changes=changes, unified_diff=rendered)


def _remove_git_metadata(root: Path) -> None:
    git_path = root / ".git"
    try:
        metadata = git_path.lstat()
    except FileNotFoundError:
        return
    if git_path.is_dir() and not git_path.is_symlink():
        shutil.rmtree(git_path)
    else:
        git_path.unlink()


def _commit_current_tree(root: Path, message: str) -> None:
    run_git_for_status(root, ("config", "core.autocrlf", "false"))
    run_git_for_status(root, ("add", "-A"))
    run_git_for_status(
        root,
        (
            "-c",
            "user.name=Codex",
            "-c",
            "user.email=noreply@openai.com",
            "commit",
            "--allow-empty",
            "-m",
            message,
        ),
        env=(
            ("GIT_AUTHOR_NAME", "Codex"),
            ("GIT_AUTHOR_EMAIL", "noreply@openai.com"),
            ("GIT_COMMITTER_NAME", "Codex"),
            ("GIT_COMMITTER_EMAIL", "noreply@openai.com"),
        ),
    )


def _write_index_from_head(root: Path) -> None:
    run_git_for_status(root, ("read-tree", "--reset", "HEAD"))


def _baseline_head_entries(root: Path) -> dict[str, tuple[str, str]]:
    output = run_git_for_stdout(root, ("ls-tree", "-r", "--full-tree", "HEAD"))
    entries: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        metadata, _, path = line.partition("\t")
        parts = metadata.split()
        if len(parts) >= 3 and path:
            mode, oid = parts[0], parts[2]
            entries[path] = (oid, mode)
    return entries


def _baseline_current_entries(root: Path) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        try:
            relative = _path_to_slash(path.relative_to(root))
            if path.is_symlink():
                content = os.readlink(path).encode()
                mode = "120000"
            elif path.is_file():
                content = path.read_bytes()
                mode = _baseline_file_mode(path)
            else:
                continue
        except OSError:
            continue
        oid = git_blob_sha1_hex_bytes(content)
        entries[relative] = (oid, mode)
    return entries


def _diff_baseline_entries(
    head: dict[str, tuple[str, str]],
    current: dict[str, tuple[str, str]],
) -> list[GitBaselineChange]:
    changes: list[GitBaselineChange] = []
    for path, entry in current.items():
        head_entry = head.get(path)
        if head_entry is None:
            changes.append(GitBaselineChange(GitBaselineChangeStatus.ADDED, path))
        elif head_entry != entry:
            changes.append(GitBaselineChange(GitBaselineChangeStatus.MODIFIED, path))
    for path in head:
        if path not in current:
            changes.append(GitBaselineChange(GitBaselineChangeStatus.DELETED, path))
    return sorted(changes, key=lambda change: change.path)


def _render_baseline_change_diff(
    root: Path,
    head_entries: dict[str, tuple[str, str]],
    current_entries: dict[str, tuple[str, str]],
    change: GitBaselineChange,
) -> str:
    old_entry = head_entries.get(change.path)
    new_entry = current_entries.get(change.path)
    old_text = _baseline_head_text(root, change.path) if old_entry is not None else ""
    new_text = _baseline_current_text(root, change.path) if new_entry is not None else ""
    old_header = f"a/{change.path}" if old_entry is not None else "/dev/null"
    new_header = f"b/{change.path}" if new_entry is not None else "/dev/null"
    section = f"diff --git a/{change.path} b/{change.path}\n"
    if old_entry is None and new_entry is not None:
        section += f"new file mode {new_entry[1]}\n"
    elif old_entry is not None and new_entry is None:
        section += f"deleted file mode {old_entry[1]}\n"
    elif old_entry is not None and new_entry is not None and old_entry[1] != new_entry[1]:
        section += f"old mode {old_entry[1]}\nnew mode {new_entry[1]}\n"
    section += "".join(
        unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=old_header,
            tofile=new_header,
            lineterm="\n",
            n=3,
        )
    )
    if not section.endswith("\n"):
        section += "\n"
    return section


def _baseline_head_text(root: Path, relative_path: str) -> str:
    output = _run_git_raw_stdout(root, ("show", f"HEAD:{relative_path}"))
    return output.decode("utf-8", errors="replace")


def _baseline_current_text(root: Path, relative_path: str) -> str:
    path = root / relative_path
    try:
        if path.is_symlink():
            return os.readlink(path)
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _baseline_file_mode(path: Path) -> str:
    if os.name != "nt" and os.access(path, os.X_OK):
        return "100755"
    return "100644"


def _path_to_slash(path: Path) -> str:
    return "/".join(path.parts)


def git_blob_sha1_hex_bytes(content: bytes) -> str:
    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


def git_blob_oid(content: bytes) -> GitSha:
    return GitSha.new(git_blob_sha1_hex_bytes(content))


def _run_git_raw_stdout(cwd: Path, args: Iterable[str]) -> bytes:
    output = run_git_command_with_timeout(args, cwd)
    command = "git " + " ".join(args)
    if output is None:
        raise GitCommandError(command, "timeout", "")
    if output.returncode != 0:
        stderr = output.stderr.decode("utf-8", errors="replace").strip()
        raise GitCommandError(command, output.returncode, stderr)
    return output.stdout


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


__all__ = ['BASELINE_COMMIT_MESSAGE', 'GitBaselineChange', 'GitBaselineChangeStatus', 'GitBaselineDiff', 'diff_since_latest_init', 'ensure_git_baseline_repository', 'git_blob_oid', 'git_blob_sha1_hex_bytes', 'reset_git_repository']
