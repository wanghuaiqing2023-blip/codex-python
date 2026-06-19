"""Git metadata helpers ported from ``codex/codex-rs/git-utils``."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import hashlib
from dataclasses import dataclass
from difflib import unified_diff
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pycodex.protocol import GitInfo, GitSha

GIT_COMMAND_TIMEOUT_SECONDS = 5
BASELINE_COMMIT_MESSAGE = "Initialize Codex git baseline\n\nCo-authored-by: Codex <noreply@openai.com>"


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


@dataclass(frozen=True)
class ApplyGitRequest:
    cwd: Path
    diff: str
    revert: bool = False
    preflight: bool = False

    def __post_init__(self) -> None:
        _ensure_pathlike(self.cwd, "cwd")
        _ensure_str(self.diff, "diff")
        if not isinstance(self.revert, bool):
            raise TypeError("revert must be a bool")
        if not isinstance(self.preflight, bool):
            raise TypeError("preflight must be a bool")


@dataclass(frozen=True)
class ApplyGitResult:
    exit_code: int
    applied_paths: list[str]
    skipped_paths: list[str]
    conflicted_paths: list[str]
    stdout: str
    stderr: str
    cmd_for_log: str

    def __post_init__(self) -> None:
        _ensure_i64(self.exit_code, "exit_code")
        _ensure_str_list(self.applied_paths, "applied_paths")
        _ensure_str_list(self.skipped_paths, "skipped_paths")
        _ensure_str_list(self.conflicted_paths, "conflicted_paths")
        _ensure_str(self.stdout, "stdout")
        _ensure_str(self.stderr, "stderr")
        _ensure_str(self.cmd_for_log, "cmd_for_log")


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


@dataclass(frozen=True)
class CommitLogEntry:
    sha: str
    timestamp: int
    subject: str

    def __post_init__(self) -> None:
        _ensure_str(self.sha, "sha")
        _ensure_i64(self.timestamp, "timestamp")
        _ensure_str(self.subject, "subject")


@dataclass(frozen=True)
class GitDiffToRemote:
    sha: GitSha
    diff: str

    def __post_init__(self) -> None:
        if not isinstance(self.sha, GitSha):
            raise TypeError("sha must be a GitSha")
        _ensure_str(self.diff, "diff")


def get_git_repo_root(base_dir: Path | str) -> Path | None:
    _ensure_pathlike(base_dir, "base_dir")
    base_path = Path(base_dir)
    base = base_path if base_path.is_dir() else base_path.parent
    return _find_ancestor_git_entry(base)


def create_symlink(source: Path | str, link_target: Path | str, destination: Path | str) -> None:
    """Create a symlink for git snapshot materialization.

    Mirrors Rust ``codex_git_utils::create_symlink``.  Unix uses the provided
    link target directly; Windows asks Python to create a directory symlink
    when the source path resolves as a directory, otherwise a file symlink.
    """

    _ensure_pathlike(source, "source")
    _ensure_pathlike(link_target, "link_target")
    _ensure_pathlike(destination, "destination")
    source_path = Path(source)
    target_path = Path(link_target)
    destination_path = Path(destination)
    try:
        if os.name == "nt":
            os.symlink(target_path, destination_path, target_is_directory=source_path.is_dir())
        else:
            os.symlink(target_path, destination_path)
    except OSError as exc:
        raise GitToolingError(str(exc)) from exc


def get_git_repo_root_with_fs(fs: Any, cwd: Path | str | None = None) -> Path | None:
    """Return the repository root using a filesystem facade when supplied.

    Mirrors Rust ``codex_git_utils::get_git_repo_root_with_fs``.  The Python
    port keeps this synchronous because the local core helpers are synchronous;
    callers may pass either ``(fs, cwd)`` with a facade exposing ``get_metadata``
    or just ``(cwd)`` for the local filesystem behavior.
    """

    if cwd is None:
        cwd = fs
        fs = None
    _ensure_pathlike(cwd, "cwd")
    cwd_path = Path(cwd)
    if fs is None:
        return get_git_repo_root(cwd_path)
    base = cwd_path if _fs_path_is_directory(fs, cwd_path) else cwd_path.parent
    return _find_ancestor_git_entry_with_fs(fs, base)



def collect_git_info(cwd: Path | str) -> GitInfo | None:
    _ensure_pathlike(cwd, "cwd")
    cwd = Path(cwd)
    repo_check = run_git_command_with_timeout(("rev-parse", "--git-dir"), cwd)
    if repo_check is None or repo_check.returncode != 0:
        return None

    commit = run_git_command_with_timeout(("rev-parse", "HEAD"), cwd)
    branch = run_git_command_with_timeout(("rev-parse", "--abbrev-ref", "HEAD"), cwd)
    url = run_git_command_with_timeout(("remote", "get-url", "origin"), cwd)

    return GitInfo(
        commit_hash=_stdout_text(commit) if commit is not None and commit.returncode == 0 else None,
        branch=_branch_name(_stdout_text(branch)) if branch is not None and branch.returncode == 0 else None,
        repository_url=_stdout_text(url) if url is not None and url.returncode == 0 else None,
    )


def get_git_remote_urls(cwd: Path | str) -> dict[str, str] | None:
    _ensure_pathlike(cwd, "cwd")
    cwd = Path(cwd)
    repo_check = run_git_command_with_timeout(("rev-parse", "--git-dir"), cwd)
    if repo_check is None or repo_check.returncode != 0:
        return None
    return get_git_remote_urls_assume_git_repo(cwd)


def get_git_remote_urls_assume_git_repo(cwd: Path | str) -> dict[str, str] | None:
    _ensure_pathlike(cwd, "cwd")
    output = run_git_command_with_timeout(("remote", "-v"), Path(cwd))
    if output is None or output.returncode != 0:
        return None
    return parse_git_remote_urls(output.stdout.decode("utf-8", errors="replace"))


def get_head_commit_hash(cwd: Path | str) -> GitSha | None:
    _ensure_pathlike(cwd, "cwd")
    output = run_git_command_with_timeout(("rev-parse", "HEAD"), Path(cwd))
    if output is None or output.returncode != 0:
        return None
    text = _stdout_text(output)
    return GitSha.new(text) if text else None


def canonicalize_git_remote_url(url: str) -> str | None:
    _ensure_str(url, "url")
    value = _trim_git_suffix(url.strip().rstrip("/"))
    if not value:
        return None
    if "://" in value:
        scheme, rest = value.split("://", 1)
        return _canonicalize_git_url_like_remote(scheme, rest)
    scp = _parse_scp_like_remote(value)
    if scp is not None:
        host_part, path = scp
        return _canonicalize_git_remote_host_path(host_part, path)
    if "/" not in value:
        return None
    host_part, path = value.split("/", 1)
    return _canonicalize_git_remote_host_path(host_part, path)


def get_has_changes(cwd: Path | str) -> bool | None:
    _ensure_pathlike(cwd, "cwd")
    output = run_git_command_with_timeout(("status", "--porcelain"), Path(cwd))
    if output is None or output.returncode != 0:
        return None
    return bool(output.stdout)


def recent_commits(cwd: Path | str, limit: int) -> list[CommitLogEntry]:
    _ensure_pathlike(cwd, "cwd")
    _ensure_usize(limit, "limit")
    cwd = Path(cwd)
    repo_check = run_git_command_with_timeout(("rev-parse", "--git-dir"), cwd)
    if repo_check is None or repo_check.returncode != 0:
        return []

    args = ["log"]
    if limit > 0:
        args.extend(["-n", str(limit)])
    args.append("--pretty=format:%H%x1f%ct%x1f%s")
    output = run_git_command_with_timeout(args, cwd)
    if output is None or output.returncode != 0:
        return []

    entries: list[CommitLogEntry] = []
    for line in output.stdout.decode("utf-8", errors="replace").splitlines():
        sha, timestamp, subject = _split_commit_line(line)
        if not sha or not timestamp:
            continue
        try:
            parsed_timestamp = int(timestamp)
        except ValueError:
            parsed_timestamp = 0
        entries.append(CommitLogEntry(sha=sha, timestamp=parsed_timestamp, subject=subject))
    return entries


def git_diff_to_remote(cwd: Path | str) -> GitDiffToRemote | None:
    _ensure_pathlike(cwd, "cwd")
    cwd = Path(cwd)
    if get_git_repo_root(cwd) is None:
        return None
    remotes = _get_git_remotes(cwd)
    if remotes is None:
        return None
    branches = _branch_ancestry(cwd)
    if branches is None:
        return None
    base_sha = _find_closest_sha(cwd, branches, remotes)
    if base_sha is None:
        return None
    diff = _diff_against_sha(cwd, base_sha)
    if diff is None:
        return None
    return GitDiffToRemote(sha=base_sha, diff=diff)


def default_branch_name(cwd: Path | str) -> str | None:
    _ensure_pathlike(cwd, "cwd")
    cwd = Path(cwd)
    for remote in _get_git_remotes(cwd) or []:
        symref = run_git_command_with_timeout(("symbolic-ref", "--quiet", f"refs/remotes/{remote}/HEAD"), cwd)
        if symref is not None and symref.returncode == 0:
            text = _stdout_text(symref)
            if "/" in text:
                return text.rsplit("/", 1)[1]
        show = run_git_command_with_timeout(("remote", "show", remote), cwd)
        if show is not None and show.returncode == 0:
            for line in show.stdout.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("HEAD branch:"):
                    name = line.removeprefix("HEAD branch:").strip()
                    if name:
                        return name
    return _default_branch_local(cwd)


def local_git_branches(cwd: Path | str) -> list[str]:
    _ensure_pathlike(cwd, "cwd")
    cwd = Path(cwd)
    output = run_git_command_with_timeout(("branch", "--format=%(refname:short)"), cwd)
    if output is None or output.returncode != 0:
        return []
    branches = sorted(
        line.strip()
        for line in output.stdout.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    )
    base = _default_branch_local(cwd)
    if base in branches:
        branches.remove(base)
        branches.insert(0, base)
    return branches


def current_branch_name(cwd: Path | str) -> str | None:
    _ensure_pathlike(cwd, "cwd")
    output = run_git_command_with_timeout(("branch", "--show-current"), Path(cwd))
    if output is None or output.returncode != 0:
        return None
    text = _stdout_text(output)
    return text or None


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


def resolve_root_git_project_for_trust(fs: Any, cwd: Path | str | None = None) -> Path | None:
    """Resolve the path used for repository trust checks.

    Supports the Rust-shaped ``(fs, cwd)`` call as well as the historical
    Python ``(cwd)`` call. Linked worktrees resolve to their main repository
    root by inspecting the ``.git`` gitdir pointer without invoking git.
    """

    if cwd is None:
        cwd = fs
        fs = None
    _ensure_pathlike(cwd, "cwd")
    repo_root = get_git_repo_root_with_fs(fs, cwd) if fs is not None else get_git_repo_root(cwd)
    if repo_root is None:
        return None
    dot_git = repo_root / ".git"
    if _fs_path_is_directory(fs, dot_git) if fs is not None else dot_git.is_dir():
        return repo_root
    try:
        gitdir_text = _fs_read_text(fs, dot_git).strip() if fs is not None else dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    gitdir = gitdir_text.removeprefix("gitdir:").strip() if gitdir_text.startswith("gitdir:") else ""
    if not gitdir:
        return None
    gitdir_path = Path(gitdir)
    if not gitdir_path.is_absolute():
        gitdir_path = repo_root / gitdir_path
    worktrees_dir = gitdir_path.parent
    if worktrees_dir.name != "worktrees":
        return None
    return worktrees_dir.parent.parent



def _find_ancestor_git_entry(base_dir: Path) -> Path | None:
    current = base_dir
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _find_ancestor_git_entry_with_fs(fs: Any, base_dir: Path) -> Path | None:
    current = base_dir
    while True:
        if _fs_path_exists(fs, current / ".git"):
            return current
        if current.parent == current:
            return None
        current = current.parent


def _fs_path_exists(fs: Any, path: Path) -> bool:
    try:
        _fs_get_metadata(fs, path)
        return True
    except OSError:
        return False


def _fs_path_is_directory(fs: Any, path: Path) -> bool:
    if fs is None:
        return path.is_dir()
    try:
        metadata = _fs_get_metadata(fs, path)
    except OSError:
        return False
    value = getattr(metadata, "is_directory", None)
    if value is not None:
        return bool(value)
    value = getattr(metadata, "is_dir", None)
    return bool(value() if callable(value) else value)


def _fs_get_metadata(fs: Any, path: Path) -> Any:
    getter = getattr(fs, "get_metadata", None)
    if getter is None:
        raise OSError("filesystem facade must expose get_metadata")
    try:
        return getter(path, None)
    except TypeError:
        return getter(path)


def _fs_read_text(fs: Any, path: Path) -> str:
    reader = getattr(fs, "read_file_text", None)
    if reader is None:
        raise OSError("filesystem facade must expose read_file_text")
    try:
        return reader(path, None)
    except TypeError:
        return reader(path)

def _run_git_stdout(cwd: Path, args: Iterable[str]) -> str:
    args_list = list(args)
    output = run_git_command_with_timeout(args_list, cwd)
    command = "git " + " ".join(args_list)
    if output is None:
        raise GitCommandError(command, "timeout", "")
    if output.returncode != 0:
        stderr = output.stderr.decode("utf-8", errors="replace").strip()
        raise GitCommandError(command, output.returncode, stderr)
    try:
        return output.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise GitOutputUtf8Error(command, exc) from exc


def _run_git_stdout_or_none(cwd: Path, args: Iterable[str]) -> str | None:
    try:
        value = _run_git_stdout(cwd, args)
    except GitCommandError:
        return None
    return value or None


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


def run_git_command_with_timeout(args: Iterable[str], cwd: Path) -> subprocess.CompletedProcess[bytes] | None:
    if isinstance(args, (str, bytes)):
        raise TypeError("args must be an iterable of strings")
    args_list = list(args)
    if not all(isinstance(arg, str) for arg in args_list):
        raise TypeError("args must contain only strings")
    if not isinstance(cwd, Path):
        raise TypeError("cwd must be a Path")
    command = [
        "git",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        *args_list,
    ]
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


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


def extract_paths_from_patch(diff_text: str) -> list[str]:
    """Collect paths referenced by ``diff --git`` headers."""

    _ensure_str(diff_text, "diff_text")
    paths: set[str] = set()
    for raw_line in diff_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("diff --git "):
            continue
        parsed = _parse_diff_git_paths(line.removeprefix("diff --git "))
        if parsed is None:
            continue
        left, right = parsed
        left_path = _normalize_diff_path(left, "a/")
        right_path = _normalize_diff_path(right, "b/")
        if left_path is not None:
            paths.add(left_path)
        if right_path is not None:
            paths.add(right_path)
    return sorted(paths)


def stage_paths(git_root: Path | str, diff: str) -> None:
    """Best-effort stage of existing paths referenced by a patch."""

    _ensure_pathlike(git_root, "git_root")
    _ensure_str(diff, "diff")
    root = Path(git_root)
    existing = [path for path in extract_paths_from_patch(diff) if (root / path).exists() or (root / path).is_symlink()]
    if not existing:
        return
    try:
        subprocess.run(
            ["git", "add", "--", *existing],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return


def parse_git_apply_output(stdout: str, stderr: str) -> tuple[list[str], list[str], list[str]]:
    """Parse ``git apply`` output into applied, skipped, and conflicted paths."""

    _ensure_str(stdout, "stdout")
    _ensure_str(stderr, "stderr")
    combined = "\n".join(part for part in (stdout, stderr) if part)
    applied: set[str] = set()
    skipped: set[str] = set()
    conflicted: set[str] = set()
    last_seen_path: str | None = None

    clean_patterns = [
        r"^Applied patch(?: to)?\s+(.+?)\s+cleanly\.?$",
    ]
    conflict_patterns = [
        r"^Applied patch(?: to)?\s+(.+?)\s+with conflicts\.?$",
        r"^Applying patch\s+(.+?)\s+with\s+\d+\s+rejects?\.{0,3}$",
        r"^U\s+(.+)$",
        r"^warning:\s*Cannot merge binary files:\s+(.+?)\s+\(ours\s+vs\.\s+theirs\)",
    ]
    early_skip_patterns = [
        r"^error:\s+patch failed:\s+(.+?)(?::\d+)?(?:\s|$)",
        r"^error:\s+(.+?):\s+patch does not apply$",
    ]
    skip_patterns = [
        r"^error:\s+(.+?):\s+does not match index\b",
        r"^error:\s+(.+?):\s+does not exist in index\b",
        r"^error:\s+(.+?)\s+already exists in (?:the )?working directory\b",
        r"^error:\s+patch failed:\s+(.+?)\s+File exists",
        r"^error:\s+path\s+(.+?)\s+has been renamed/deleted",
        r"^error:\s+cannot apply binary patch to\s+['\"]?(.+?)['\"]?\s+without full index line$",
        r"^error:\s+binary patch does not apply to\s+['\"]?(.+?)['\"]?$",
        r"^error:\s+binary patch to\s+['\"]?(.+?)['\"]?\s+creates incorrect result\b",
        r"^error:\s+cannot read the current contents of\s+['\"]?(.+?)['\"]?$",
        r"^Skipped patch\s+['\"]?(.+?)['\"]\.$",
    ]

    for raw_line in combined.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        checking = re.match(r"^Checking patch\s+(.+?)\.\.\.$", line, flags=re.IGNORECASE)
        if checking is not None:
            last_seen_path = checking.group(1)
            continue
        matched = _match_apply_path(clean_patterns, line)
        if matched is not None:
            path = _add_apply_path(applied, matched)
            if path is not None:
                conflicted.discard(path)
                skipped.discard(path)
                last_seen_path = path
            continue
        matched = _match_apply_path(conflict_patterns, line)
        if matched is not None:
            path = _add_apply_path(conflicted, matched)
            if path is not None:
                applied.discard(path)
                skipped.discard(path)
                last_seen_path = path
            continue
        matched = _match_apply_path(early_skip_patterns, line)
        if matched is not None:
            path = _add_apply_path(skipped, matched)
            if path is not None:
                last_seen_path = path
            continue
        if re.match(r"^(?:Performing three-way merge|Falling back to three-way merge)\.\.\.$", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^Falling back to direct application\.\.\.$", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^Failed to perform three-way merge\.\.\.$", line, flags=re.IGNORECASE) or re.match(
            r"^(?:error: )?repository lacks the necessary blob to (?:perform|fall back on) 3-?way merge\.?$",
            line,
            flags=re.IGNORECASE,
        ):
            if last_seen_path is not None:
                path = _add_apply_path(skipped, last_seen_path)
                if path is not None:
                    applied.discard(path)
                    conflicted.discard(path)
            continue
        matched = _match_apply_path(skip_patterns, line)
        if matched is not None:
            path = _add_apply_path(skipped, matched)
            if path is not None:
                applied.discard(path)
                conflicted.discard(path)
                last_seen_path = path

    for path in conflicted:
        applied.discard(path)
        skipped.discard(path)
    for path in applied:
        skipped.discard(path)
    return sorted(applied), sorted(skipped), sorted(conflicted)


def apply_git_patch(request: ApplyGitRequest) -> ApplyGitResult:
    """Apply a unified diff to a git repository using ``git apply``."""

    if not isinstance(request, ApplyGitRequest):
        raise TypeError("request must be an ApplyGitRequest")
    git_root = resolve_repository_root(request.cwd)
    with tempfile.TemporaryDirectory() as tmpdir:
        patch_path = Path(tmpdir) / "patch.diff"
        patch_path.write_text(request.diff, encoding="utf-8")
        if request.revert and not request.preflight:
            stage_paths(git_root, request.diff)

        git_cfg = _apply_git_cfg_parts()
        if request.preflight:
            args = ["apply", "--check"]
            if request.revert:
                args.append("-R")
            args.append(str(patch_path))
            cmd_for_log = _render_command_for_log(git_root, git_cfg, args)
            exit_code, stdout, stderr = _run_git_apply_command(git_root, git_cfg, args)
        else:
            args = ["apply", "--3way"]
            if request.revert:
                args.append("-R")
            args.append(str(patch_path))
            cmd_for_log = _render_command_for_log(git_root, git_cfg, args)
            exit_code, stdout, stderr = _run_git_apply_command(git_root, git_cfg, args)

    applied, skipped, conflicted = parse_git_apply_output(stdout, stderr)
    return ApplyGitResult(
        exit_code=exit_code,
        applied_paths=applied,
        skipped_paths=skipped,
        conflicted_paths=conflicted,
        stdout=stdout,
        stderr=stderr,
        cmd_for_log=cmd_for_log,
    )


def _apply_git_cfg_parts() -> list[str]:
    parts: list[str] = []
    for pair in os.environ.get("CODEX_APPLY_GIT_CFG", "").split(","):
        value = pair.strip()
        if not value or "=" not in value:
            continue
        parts.extend(["-c", value])
    return parts


def _run_git_apply_command(cwd: Path, git_cfg: list[str], args: list[str]) -> tuple[int, str, str]:
    try:
        output = subprocess.run(
            ["git", *git_cfg, *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise GitToolingError(str(exc)) from exc
    return (
        output.returncode if output.returncode is not None else -1,
        output.stdout.decode("utf-8", errors="replace"),
        output.stderr.decode("utf-8", errors="replace"),
    )


def _quote_shell(value: str) -> str:
    simple = all(char.isascii() and (char.isalnum() or char in "-_.:/@%+") for char in value)
    if simple:
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def _render_command_for_log(cwd: Path, git_cfg: list[str], args: list[str]) -> str:
    parts = ["git", *(_quote_shell(arg) for arg in git_cfg), *(_quote_shell(arg) for arg in args)]
    return f"(cd {_quote_shell(str(cwd))} && {' '.join(parts)})"


def _match_apply_path(patterns: Iterable[str], line: str) -> str | None:
    for pattern in patterns:
        match = re.match(pattern, line, flags=re.IGNORECASE)
        if match is not None:
            return match.group(1)
    return None


def _add_apply_path(paths: set[str], raw: str) -> str | None:
    trimmed = raw.strip()
    if not trimmed:
        return None
    first = trimmed[0]
    last = trimmed[-1]
    if first in {"'", '"'} and last == first and len(trimmed) >= 2:
        value = _unescape_c_string(trimmed[1:-1])
    else:
        value = trimmed
    if not value:
        return None
    paths.add(value)
    return value


def _parse_diff_git_paths(line: str) -> tuple[str, str] | None:
    tokens: list[str] = []
    index = 0
    while len(tokens) < 2:
        token, index = _read_diff_git_token(line, index)
        if token is None:
            return None
        tokens.append(token)
    return tokens[0], tokens[1]


def _read_diff_git_token(line: str, index: int) -> tuple[str | None, int]:
    length = len(line)
    while index < length and line[index].isspace():
        index += 1
    if index >= length:
        return None, index
    quote = line[index] if line[index] in {"'", '"'} else None
    if quote is not None:
        index += 1
    output: list[str] = []
    while index < length:
        char = line[index]
        index += 1
        if quote is not None:
            if char == quote:
                break
            if char == "\\" and index < length:
                output.append(char)
                output.append(line[index])
                index += 1
                continue
        elif char.isspace():
            break
        output.append(char)
    if not output and quote is None:
        return None, index
    token = "".join(output)
    return (_unescape_c_string(token) if quote is not None else token), index


def _normalize_diff_path(raw: str, prefix: str) -> str | None:
    trimmed = raw.strip()
    if not trimmed or trimmed == "/dev/null" or trimmed == f"{prefix}dev/null":
        return None
    if trimmed.startswith(prefix):
        trimmed = trimmed[len(prefix) :]
    return trimmed or None


def _unescape_c_string(input_text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(input_text):
        char = input_text[index]
        index += 1
        if char != "\\":
            output.append(char)
            continue
        if index >= len(input_text):
            output.append("\\")
            break
        escaped = input_text[index]
        index += 1
        mapping = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "a": "\a", "v": "\v", "\\": "\\", '"': '"', "'": "'"}
        if escaped in mapping:
            output.append(mapping[escaped])
        elif escaped in "01234567":
            digits = [escaped]
            for _ in range(2):
                if index < len(input_text) and input_text[index] in "01234567":
                    digits.append(input_text[index])
                    index += 1
                else:
                    break
            output.append(chr(int("".join(digits), 8)))
        else:
            output.append(escaped)
    return "".join(output)


def parse_git_remote_urls(stdout: str) -> dict[str, str] | None:
    _ensure_str(stdout, "stdout")
    remotes: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.endswith(" (fetch)"):
            continue
        fetch_line = line.removesuffix(" (fetch)")
        if "\t" in fetch_line:
            name, url = fetch_line.split("\t", 1)
        elif " " in fetch_line:
            name, url = fetch_line.split(" ", 1)
        else:
            continue
        url = url.strip()
        if url:
            remotes[name] = url
    return remotes or None


def _canonicalize_git_url_like_remote(scheme: str, rest: str) -> str | None:
    _ensure_str(scheme, "scheme")
    _ensure_str(rest, "rest")
    default_port = {"git": "9418", "http": "80", "https": "443", "ssh": "22"}.get(scheme)
    if default_port is None:
        return None
    rest = rest.split("?", 1)[0].split("#", 1)[0]
    if "/" not in rest:
        return None
    host_part, path = rest.split("/", 1)
    return _canonicalize_git_remote_host_path(host_part, path, default_port)


def _parse_scp_like_remote(remote: str) -> tuple[str, str] | None:
    _ensure_str(remote, "remote")
    slash = remote.find("/")
    colon = remote.find(":")
    if slash != -1 and (colon == -1 or slash < colon):
        return None
    if ":" not in remote:
        return None
    host_part, path = remote.split(":", 1)
    if not host_part or not path:
        return None
    return host_part, path


def _canonicalize_git_remote_host_path(host_part: str, path: str, default_port: str | None = None) -> str | None:
    _ensure_str(host_part, "host_part")
    _ensure_str(path, "path")
    if default_port is not None:
        _ensure_str(default_port, "default_port")
    host = _normalize_remote_host(host_part.rsplit("@", 1)[-1].strip().rstrip("/"), default_port)
    if not host:
        return None
    clean_path = _trim_git_suffix(path.strip().strip("/"))
    components = [part for part in clean_path.split("/") if part]
    if len(components) < 2:
        return None
    owner, repo = components[0], components[1]
    if owner in {".", ".."} or repo in {".", ".."}:
        return None
    joined = "/".join(components)
    if host == "github.com":
        joined = joined.lower()
    return f"{host}/{joined}"


def _normalize_remote_host(host: str, default_port: str | None) -> str:
    _ensure_str(host, "host")
    if default_port is not None:
        _ensure_str(default_port, "default_port")
    host = host.lower()
    if default_port is not None and ":" in host:
        host_without_port, port = host.rsplit(":", 1)
        if port == default_port:
            return host_without_port
    return host


def _trim_git_suffix(value: str) -> str:
    _ensure_str(value, "value")
    return value.removesuffix(".git")


def _get_git_remotes(cwd: Path) -> list[str] | None:
    output = run_git_command_with_timeout(("remote",), cwd)
    if output is None or output.returncode != 0:
        return None
    remotes = [line for line in output.stdout.decode("utf-8", errors="replace").splitlines() if line]
    if "origin" in remotes:
        remotes.remove("origin")
        remotes.insert(0, "origin")
    return remotes


def _default_branch_local(cwd: Path) -> str | None:
    for candidate in ("main", "master"):
        verify = run_git_command_with_timeout(
            ("rev-parse", "--verify", "--quiet", f"refs/heads/{candidate}"),
            cwd,
        )
        if verify is not None and verify.returncode == 0:
            return candidate
    return None


def _branch_ancestry(cwd: Path) -> list[str] | None:
    current = current_branch_name(cwd)
    default = default_branch_name(cwd)
    ancestry: list[str] = []
    seen: set[str] = set()
    for branch in (current, default):
        if branch and branch not in seen:
            seen.add(branch)
            ancestry.append(branch)
    for remote in _get_git_remotes(cwd) or []:
        output = run_git_command_with_timeout(
            ("for-each-ref", "--format=%(refname:short)", "--contains=HEAD", f"refs/remotes/{remote}"),
            cwd,
        )
        if output is None or output.returncode != 0:
            continue
        for line in output.stdout.decode("utf-8", errors="replace").splitlines():
            short = line.strip()
            prefix = f"{remote}/"
            if short.startswith(prefix):
                branch = short.removeprefix(prefix)
                if branch and branch != "HEAD" and branch not in seen:
                    seen.add(branch)
                    ancestry.append(branch)
    return ancestry


def _branch_remote_and_distance(cwd: Path, branch: str, remotes: list[str]) -> tuple[GitSha | None, int] | None:
    remote_sha: GitSha | None = None
    remote_ref: str | None = None
    for remote in remotes:
        candidate = f"refs/remotes/{remote}/{branch}"
        verify = run_git_command_with_timeout(("rev-parse", "--verify", "--quiet", candidate), cwd)
        if verify is None:
            return None
        if verify.returncode != 0:
            continue
        remote_sha = GitSha.new(_stdout_text(verify))
        remote_ref = candidate
        break

    count = run_git_command_with_timeout(("rev-list", "--count", f"{branch}..HEAD"), cwd)
    if count is None or count.returncode != 0:
        if remote_ref is None:
            return None
        count = run_git_command_with_timeout(("rev-list", "--count", f"{remote_ref}..HEAD"), cwd)
    if count is None or count.returncode != 0:
        return None
    try:
        distance = int(_stdout_text(count))
    except ValueError:
        return None
    return remote_sha, distance


def _find_closest_sha(cwd: Path, branches: list[str], remotes: list[str]) -> GitSha | None:
    closest: tuple[GitSha, int] | None = None
    for branch in branches:
        result = _branch_remote_and_distance(cwd, branch, remotes)
        if result is None:
            continue
        remote_sha, distance = result
        if remote_sha is None:
            continue
        if closest is None or distance < closest[1]:
            closest = (remote_sha, distance)
    return closest[0] if closest is not None else None


def _diff_against_sha(cwd: Path, sha: GitSha) -> str | None:
    output = run_git_command_with_timeout(("diff", "--no-textconv", "--no-ext-diff", sha.to_json()), cwd)
    if output is None or output.returncode not in {0, 1}:
        return None
    diff = output.stdout.decode("utf-8", errors="replace")
    untracked_output = run_git_command_with_timeout(("ls-files", "--others", "--exclude-standard"), cwd)
    if untracked_output is None or untracked_output.returncode != 0:
        return diff
    null_device = "NUL" if os.name == "nt" else "/dev/null"
    for line in untracked_output.stdout.decode("utf-8", errors="replace").splitlines():
        file_name = line.strip()
        if not file_name:
            continue
        extra = run_git_command_with_timeout(
            ("diff", "--no-textconv", "--no-ext-diff", "--binary", "--no-index", "--", null_device, file_name),
            cwd,
        )
        if extra is not None and extra.returncode in {0, 1}:
            diff += extra.stdout.decode("utf-8", errors="replace")
    return diff


def _stdout_text(output: subprocess.CompletedProcess[bytes]) -> str:
    return output.stdout.decode("utf-8", errors="replace").strip()


def _branch_name(value: str) -> str | None:
    return value if value and value != "HEAD" else None


def _split_commit_line(line: str) -> tuple[str, str, str]:
    _ensure_str(line, "line")
    parts = line.split("\x1f", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


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


__all__ = [
    "ApplyGitRequest",
    "ApplyGitResult",
    "BASELINE_COMMIT_MESSAGE",
    "CommitLogEntry",
    "GIT_COMMAND_TIMEOUT_SECONDS",
    "GitBaselineChange",
    "GitBaselineChangeStatus",
    "GitBaselineDiff",
    "GitDiffToRemote",
    "GitCommandError",
    "GitToolingError",
    "GitOutputUtf8Error",
    "NonRelativePathError",
    "NotAGitRepositoryError",
    "PathEscapesRepositoryError",
    "apply_git_patch",
    "canonicalize_git_remote_url",
    "collect_git_info",
    "create_symlink",
    "current_branch_name",
    "default_branch_name",
    "diff_since_latest_init",
    "ensure_git_repository",
    "ensure_git_baseline_repository",
    "extract_paths_from_patch",
    "get_git_remote_urls",
    "get_git_remote_urls_assume_git_repo",
    "get_git_repo_root",
    "get_git_repo_root_with_fs",
    "get_has_changes",
    "get_head_commit_hash",
    "git_blob_oid",
    "git_blob_sha1_hex_bytes",
    "git_diff_to_remote",
    "local_git_branches",
    "merge_base_with_head",
    "parse_git_apply_output",
    "parse_git_remote_urls",
    "recent_commits",
    "reset_git_repository",
    "resolve_head",
    "resolve_repository_root",
    "resolve_root_git_project_for_trust",
    "run_git",
    "run_git_for_status",
    "run_git_for_stdout",
    "run_git_command_with_timeout",
    "stage_paths",
]


