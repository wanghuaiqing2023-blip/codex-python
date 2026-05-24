"""Git metadata helpers ported from ``codex/codex-rs/git-utils``."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pycodex.protocol import GitInfo, GitSha

GIT_COMMAND_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class CommitLogEntry:
    sha: str
    timestamp: int
    subject: str


@dataclass(frozen=True)
class GitDiffToRemote:
    sha: GitSha
    diff: str


def get_git_repo_root(base_dir: Path | str) -> Path | None:
    base_path = Path(base_dir)
    base = base_path if base_path.is_dir() else base_path.parent
    current = base
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def collect_git_info(cwd: Path | str) -> GitInfo | None:
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
    cwd = Path(cwd)
    repo_check = run_git_command_with_timeout(("rev-parse", "--git-dir"), cwd)
    if repo_check is None or repo_check.returncode != 0:
        return None
    return get_git_remote_urls_assume_git_repo(cwd)


def get_git_remote_urls_assume_git_repo(cwd: Path | str) -> dict[str, str] | None:
    output = run_git_command_with_timeout(("remote", "-v"), Path(cwd))
    if output is None or output.returncode != 0:
        return None
    return parse_git_remote_urls(output.stdout.decode("utf-8", errors="replace"))


def get_head_commit_hash(cwd: Path | str) -> GitSha | None:
    output = run_git_command_with_timeout(("rev-parse", "HEAD"), Path(cwd))
    if output is None or output.returncode != 0:
        return None
    text = _stdout_text(output)
    return GitSha.new(text) if text else None


def canonicalize_git_remote_url(url: str) -> str | None:
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
    output = run_git_command_with_timeout(("status", "--porcelain"), Path(cwd))
    if output is None or output.returncode != 0:
        return None
    return bool(output.stdout)


def recent_commits(cwd: Path | str, limit: int) -> list[CommitLogEntry]:
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
    output = run_git_command_with_timeout(("branch", "--show-current"), Path(cwd))
    if output is None or output.returncode != 0:
        return None
    text = _stdout_text(output)
    return text or None


def resolve_root_git_project_for_trust(cwd: Path | str) -> Path | None:
    repo_root = get_git_repo_root(cwd)
    if repo_root is None:
        return None
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return repo_root
    try:
        gitdir_text = dot_git.read_text(encoding="utf-8").strip()
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


def run_git_command_with_timeout(args: Iterable[str], cwd: Path) -> subprocess.CompletedProcess[bytes] | None:
    command = [
        "git",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        *list(args),
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


def parse_git_remote_urls(stdout: str) -> dict[str, str] | None:
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
    default_port = {"git": "9418", "http": "80", "https": "443", "ssh": "22"}.get(scheme)
    if default_port is None:
        return None
    rest = rest.split("?", 1)[0].split("#", 1)[0]
    if "/" not in rest:
        return None
    host_part, path = rest.split("/", 1)
    return _canonicalize_git_remote_host_path(host_part, path, default_port)


def _parse_scp_like_remote(remote: str) -> tuple[str, str] | None:
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
    host = host.lower()
    if default_port is not None and ":" in host:
        host_without_port, port = host.rsplit(":", 1)
        if port == default_port:
            return host_without_port
    return host


def _trim_git_suffix(value: str) -> str:
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
    parts = line.split("\x1f", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


__all__ = [
    "CommitLogEntry",
    "GIT_COMMAND_TIMEOUT_SECONDS",
    "GitDiffToRemote",
    "canonicalize_git_remote_url",
    "collect_git_info",
    "current_branch_name",
    "default_branch_name",
    "get_git_remote_urls",
    "get_git_remote_urls_assume_git_repo",
    "get_git_repo_root",
    "get_has_changes",
    "get_head_commit_hash",
    "git_diff_to_remote",
    "local_git_branches",
    "parse_git_remote_urls",
    "recent_commits",
    "resolve_root_git_project_for_trust",
    "run_git_command_with_timeout",
]
