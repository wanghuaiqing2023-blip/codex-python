"""Branch and pull-request metadata for TUI status-line items.

Rust source: ``codex/codex-rs/tui/src/branch_summary.rs``.
The module talks only to an injected workspace-command runner; it does not run
real ``git`` or ``gh`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import asyncio
import json
from typing import Any, Dict, Iterable, List, Optional, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="branch_summary",
    source="codex/codex-rs/tui/src/branch_summary.rs",
    status="complete",
)


@dataclass(eq=True)
class GitBranchDiffStats:
    additions: int
    deletions: int


@dataclass(eq=True)
class StatusLineGitSummary:
    pull_request: Optional["StatusLinePullRequest"] = None
    branch_change_stats: Optional[GitBranchDiffStats] = None


@dataclass(eq=True)
class StatusLinePullRequest:
    number: int
    url: str


@dataclass(eq=True)
class DefaultBranch:
    merge_ref: str


@dataclass(eq=True)
class WorkspaceCommandOutput:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    def success(self) -> bool:
        return self.exit_code == 0


@dataclass(eq=True)
class WorkspaceCommand:
    argv: List[str]
    cwd_path: Optional[Path] = None
    env_vars: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def new(cls, argv: Iterable[str]) -> "WorkspaceCommand":
        return cls(list(argv))

    def cwd(self, cwd: Union[str, Path]) -> "WorkspaceCommand":
        self.cwd_path = Path(cwd)
        return self

    def env(self, key: str, value: str) -> "WorkspaceCommand":
        self.env_vars[key] = value
        return self


@dataclass(eq=True)
class GhPullRequestView:
    number: int
    url: str
    state: str


@dataclass(eq=True)
class GhPullRequestApiItem:
    number: int
    url: str
    state: str


@dataclass(eq=True)
class GhRepoParent:
    name_with_owner: str


@dataclass(eq=True)
class GhRepoView:
    name_with_owner: Optional[str]
    parent: Optional[GhRepoParent]


async def current_branch_name(runner: Any, cwd: Union[str, Path]) -> Optional[str]:
    output = await _try_run_git_command(runner, cwd, ["branch", "--show-current"])
    if output is None or not output.success():
        return None
    name = output.stdout.strip()
    return name or None


async def status_line_git_summary(runner: Any, cwd: Union[str, Path]) -> StatusLineGitSummary:
    pull_request, branch_change_stats = await asyncio.gather(
        open_pull_request(runner, cwd),
        branch_diff_stats_to_default_branch(runner, cwd),
    )
    return StatusLineGitSummary(pull_request=pull_request, branch_change_stats=branch_change_stats)


async def branch_diff_stats_to_default_branch(
    runner: Any, cwd: Union[str, Path]
) -> Optional[GitBranchDiffStats]:
    git_dir = await _try_run_git_command(runner, cwd, ["rev-parse", "--git-dir"])
    if git_dir is None or not git_dir.success():
        return None

    default_branch = await get_default_branch(runner, cwd)
    if default_branch is None:
        return None

    merge_base = await _try_run_git_command(
        runner, cwd, ["merge-base", "HEAD", default_branch.merge_ref]
    )
    if merge_base is None or not merge_base.success():
        return None
    base = merge_base.stdout.strip()
    if not base:
        return None

    numstat = await _try_run_git_command(runner, cwd, ["diff", "--numstat", f"{base}..HEAD"])
    if numstat is None or not numstat.success():
        return None

    additions = 0
    deletions = 0
    for line in numstat.stdout.splitlines():
        columns = line.split("\t")
        if columns:
            additions += _parse_int_or_zero(columns[0])
        if len(columns) > 1:
            deletions += _parse_int_or_zero(columns[1])
    return GitBranchDiffStats(additions=additions, deletions=deletions)


async def get_git_remotes(runner: Any, cwd: Union[str, Path]) -> Optional[List[str]]:
    output = await _try_run_git_command(runner, cwd, ["remote"])
    if output is None or not output.success():
        return None
    remotes = [line for line in output.stdout.splitlines()]
    if "origin" in remotes:
        remotes.remove("origin")
        remotes.insert(0, "origin")
    return remotes


async def get_default_branch(runner: Any, cwd: Union[str, Path]) -> Optional[DefaultBranch]:
    remotes = await get_git_remotes(runner, cwd) or []
    for remote in remotes:
        branch = await get_remote_default_branch_from_symbolic_ref(runner, cwd, remote)
        if branch is not None:
            return branch
        branch = await get_remote_default_branch_from_remote_show(runner, cwd, remote)
        if branch is not None:
            return branch
    return await get_default_branch_local(runner, cwd)


async def get_remote_default_branch_from_symbolic_ref(
    runner: Any, cwd: Union[str, Path], remote: str
) -> Optional[DefaultBranch]:
    remote_head = f"refs/remotes/{remote}/HEAD"
    output = await _try_run_git_command(runner, cwd, ["symbolic-ref", "--quiet", remote_head])
    if output is None or not output.success():
        return None
    trimmed = output.stdout.strip()
    prefix = f"refs/remotes/{remote}/"
    if not trimmed.startswith(prefix):
        return None
    if not await git_ref_exists(runner, cwd, trimmed):
        return None
    return DefaultBranch(merge_ref=trimmed)


async def get_remote_default_branch_from_remote_show(
    runner: Any, cwd: Union[str, Path], remote: str
) -> Optional[DefaultBranch]:
    output = await _try_run_git_command(runner, cwd, ["remote", "show", remote])
    if output is None or not output.success():
        return None
    for line in output.stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("HEAD branch:"):
            continue
        name = stripped[len("HEAD branch:") :].strip()
        remote_ref = f"refs/remotes/{remote}/{name}"
        if name and await git_ref_exists(runner, cwd, remote_ref):
            return DefaultBranch(merge_ref=remote_ref)
    return None


async def get_default_branch_local(runner: Any, cwd: Union[str, Path]) -> Optional[DefaultBranch]:
    for candidate in ("main", "master"):
        local_ref = f"refs/heads/{candidate}"
        if await git_ref_exists(runner, cwd, local_ref):
            return DefaultBranch(merge_ref=local_ref)
    return None


async def git_ref_exists(runner: Any, cwd: Union[str, Path], reference: str) -> bool:
    output = await _try_run_git_command(
        runner, cwd, ["rev-parse", "--verify", "--quiet", reference]
    )
    return output is not None and output.success()


async def open_pull_request(runner: Any, cwd: Union[str, Path]) -> Optional[StatusLinePullRequest]:
    pull_request = await open_pull_request_for_current_branch(runner, cwd)
    if pull_request is not None:
        return pull_request
    return await open_pull_request_for_head_commit(runner, cwd)


async def open_pull_request_for_current_branch(
    runner: Any, cwd: Union[str, Path]
) -> Optional[StatusLinePullRequest]:
    output = await _try_run_gh_command(runner, cwd, ["pr", "view", "--json", "number,url,state"])
    if output is None or not output.success():
        return None
    return pull_request_from_view_output(output.stdout)


async def open_pull_request_for_head_commit(
    runner: Any, cwd: Union[str, Path]
) -> Optional[StatusLinePullRequest]:
    head_sha = await current_head_sha(runner, cwd)
    if head_sha is None:
        return None
    repos = await gh_repo_search_order(runner, cwd)
    if repos is None:
        return None
    for repo in repos:
        endpoint = f"repos/{repo}/commits/{head_sha}/pulls"
        output = await _try_run_gh_command(
            runner,
            cwd,
            ["api", "-H", "Accept: application/vnd.github+json", endpoint],
        )
        if output is not None and output.success():
            pull_request = pull_request_from_api_output(output.stdout)
            if pull_request is not None:
                return pull_request
    return None


async def current_head_sha(runner: Any, cwd: Union[str, Path]) -> Optional[str]:
    output = await _try_run_git_command(runner, cwd, ["rev-parse", "HEAD"])
    if output is None or not output.success():
        return None
    sha = output.stdout.strip()
    return sha or None


async def gh_repo_search_order(runner: Any, cwd: Union[str, Path]) -> Optional[List[str]]:
    output = await _try_run_gh_command(runner, cwd, ["repo", "view", "--json", "nameWithOwner,parent"])
    if output is None or not output.success():
        return None
    return repo_search_order_from_output(output.stdout)


def pull_request_from_view_output(stdout: str) -> Optional[StatusLinePullRequest]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if str(data.get("state", "")).lower() != "open":
        return None
    try:
        return StatusLinePullRequest(number=int(data["number"]), url=str(data["url"]))
    except (KeyError, TypeError, ValueError):
        return None


def pull_request_from_api_output(stdout: str) -> Optional[StatusLinePullRequest]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    for item in data:
        if isinstance(item, dict) and str(item.get("state", "")).lower() == "open":
            try:
                return StatusLinePullRequest(number=int(item["number"]), url=str(item["html_url"]))
            except (KeyError, TypeError, ValueError):
                return None
    return None


def repo_search_order_from_output(stdout: str) -> Optional[List[str]]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    repos: List[str] = []
    parent = data.get("parent") if isinstance(data, dict) else None
    if isinstance(parent, dict) and parent.get("nameWithOwner"):
        repos.append(str(parent["nameWithOwner"]))
    name = data.get("nameWithOwner") if isinstance(data, dict) else None
    if name and str(name) not in repos:
        repos.append(str(name))
    return repos or None


async def run_git_command(
    runner: Any, cwd: Union[str, Path], args: Iterable[str]
) -> WorkspaceCommandOutput:
    command = WorkspaceCommand.new(["git"] + list(args)).cwd(cwd).env("GIT_OPTIONAL_LOCKS", "0")
    return await runner.run(command)


async def run_gh_command(
    runner: Any, cwd: Union[str, Path], args: Iterable[str]
) -> WorkspaceCommandOutput:
    command = (
        WorkspaceCommand.new(["gh"] + list(args))
        .cwd(cwd)
        .env("GH_PROMPT_DISABLED", "1")
        .env("GIT_TERMINAL_PROMPT", "0")
    )
    return await runner.run(command)


async def _try_run_git_command(
    runner: Any, cwd: Union[str, Path], args: Iterable[str]
) -> Optional[WorkspaceCommandOutput]:
    try:
        return await run_git_command(runner, cwd, args)
    except Exception:
        return None


async def _try_run_gh_command(
    runner: Any, cwd: Union[str, Path], args: Iterable[str]
) -> Optional[WorkspaceCommandOutput]:
    try:
        return await run_gh_command(runner, cwd, args)
    except Exception:
        return None


def _parse_int_or_zero(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


@dataclass
class FakeResponse:
    argv: List[str]
    output: WorkspaceCommandOutput


class FakeRunner:
    def __init__(self, responses: Iterable[FakeResponse]) -> None:
        self.responses = list(responses)
        self.seen: List[List[str]] = []

    @classmethod
    def new(cls, responses: Iterable[FakeResponse]) -> "FakeRunner":
        return cls(responses)

    def saw(self, argv: Iterable[str]) -> bool:
        target = list(argv)
        return any(seen == target for seen in self.seen)

    async def run(self, command: WorkspaceCommand) -> WorkspaceCommandOutput:
        self.seen.append(list(command.argv))
        for index, response in enumerate(self.responses):
            if response.argv == command.argv:
                return self.responses.pop(index).output
        raise RuntimeError(f"missing fake response for {command.argv!r}")


def response(argv: Iterable[str], exit_code: int, stdout: str) -> FakeResponse:
    return FakeResponse(list(argv), WorkspaceCommandOutput(exit_code=exit_code, stdout=stdout, stderr=""))


__all__ = [
    "DefaultBranch",
    "FakeResponse",
    "FakeRunner",
    "GhPullRequestApiItem",
    "GhPullRequestView",
    "GhRepoParent",
    "GhRepoView",
    "GitBranchDiffStats",
    "RUST_MODULE",
    "StatusLineGitSummary",
    "StatusLinePullRequest",
    "WorkspaceCommand",
    "WorkspaceCommandOutput",
    "branch_diff_stats_to_default_branch",
    "current_branch_name",
    "current_head_sha",
    "get_default_branch",
    "get_default_branch_local",
    "get_git_remotes",
    "get_remote_default_branch_from_remote_show",
    "get_remote_default_branch_from_symbolic_ref",
    "gh_repo_search_order",
    "git_ref_exists",
    "open_pull_request",
    "open_pull_request_for_current_branch",
    "open_pull_request_for_head_commit",
    "pull_request_from_api_output",
    "pull_request_from_view_output",
    "repo_search_order_from_output",
    "response",
    "run_gh_command",
    "run_git_command",
    "status_line_git_summary",
]
