"""Dependency-light projection of Rust `codex-cloud-tasks` env detection.

The Rust crate contains a TUI application and cloud-task orchestration.  This
Python package currently ports the module-scoped behavior contract from
`codex/codex-rs/cloud-tasks/src/env_detect.rs`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import inspect
import json
import subprocess
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Protocol, Sequence
from urllib import request

from pycodex.cloud_tasks_client import DiffSummary
from pycodex.cloud_tasks_client import ApplyStatus
from pycodex.cloud_tasks_client import TaskId
from pycodex.cloud_tasks_client import TaskStatus
from pycodex.cloud_tasks.scrollable_diff import ScrollableDiff
from pycodex.cloud_tasks.scrollable_diff import ScrollViewState
from pycodex.cloud_tasks.cli import ApplyCommand
from pycodex.cloud_tasks.cli import Cli
from pycodex.cloud_tasks.cli import Command
from pycodex.cloud_tasks.cli import DiffCommand
from pycodex.cloud_tasks.cli import ExecCommand
from pycodex.cloud_tasks.cli import ListCommand
from pycodex.cloud_tasks.cli import StatusCommand
from pycodex.cloud_tasks.cli import parse_attempts
from pycodex.cloud_tasks.cli import parse_limit
from pycodex.cloud_tasks.new_task import NEW_TASK_HINT_ITEMS
from pycodex.cloud_tasks.new_task import NewTaskPage
from pycodex.cloud_tasks.app import App
from pycodex.cloud_tasks.app import ApplyModalState
from pycodex.cloud_tasks.app import AttemptView
from pycodex.cloud_tasks.app import BestOfModalState
from pycodex.cloud_tasks.app import DetailView
from pycodex.cloud_tasks.app import DiffOverlay
from pycodex.cloud_tasks.app import EnvModalState
from pycodex.cloud_tasks.app import load_tasks


__all__ = [
    "AutodetectSelection",
    "ApplyResultLevel",
    "ApplyCommand",
    "App",
    "ApplyModalState",
    "AttemptView",
    "BestOfModalState",
    "Cli",
    "CloudTasksHttpResponse",
    "Command",
    "CodeEnvironment",
    "EnvironmentRow",
    "DiffCommand",
    "DetailView",
    "DiffOverlay",
    "ExecCommand",
    "AttemptDiffData",
    "EnvModalState",
    "ListCommand",
    "NEW_TASK_HINT_ITEMS",
    "NewTaskPage",
    "ScrollableDiff",
    "ScrollViewState",
    "StatusCommand",
    "autodetect_environment_id",
    "by_repo_environments_url",
    "collect_attempt_diffs",
    "format_relative_time",
    "format_task_list_lines",
    "format_task_status_lines",
    "environment_list_url",
    "get_git_origins",
    "get_json",
    "level_from_status",
    "list_environments",
    "load_tasks",
    "parse_owner_repo",
    "parse_attempts",
    "parse_limit",
    "parse_task_id",
    "pick_environment_row",
    "resolve_environment_id_from_rows",
    "resolve_git_ref_with_git_info",
    "resolve_query_input",
    "select_attempt",
    "summary_line",
    "task_status_label",
    "task_url",
    "uniq",
]


Headers = Mapping[str, str]
Transport = Callable[[str, Headers], "CloudTasksHttpResponse"]


class GitInfoProvider(Protocol):
    def current_branch_name(self) -> str | None: ...

    def default_branch_name(self) -> str | None: ...


@dataclass(frozen=True)
class CodeEnvironment:
    id: str
    label: str | None = None
    is_pinned: bool | None = None
    task_count: int | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CodeEnvironment":
        return cls(
            id=str(value["id"]),
            label=None if value.get("label") is None else str(value.get("label")),
            is_pinned=None
            if value.get("is_pinned") is None
            else bool(value.get("is_pinned")),
            task_count=None
            if value.get("task_count") is None
            else int(value.get("task_count")),
        )


@dataclass(frozen=True)
class AutodetectSelection:
    id: str
    label: str | None = None


@dataclass(frozen=True)
class EnvironmentRow:
    id: str
    label: str | None = None
    is_pinned: bool = False
    repo_hints: str | None = None


@dataclass(frozen=True)
class CloudTasksHttpResponse:
    status: int
    body: str
    content_type: str = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status < 300


class ApplyResultLevel(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass(frozen=True)
class AttemptDiffData:
    placement: int | None
    created_at: datetime | float | None
    diff: str


def normalize_base_url(input_url: str) -> str:
    base_url = input_url
    while base_url.endswith("/"):
        base_url = base_url[:-1]
    if (
        base_url.startswith("https://chatgpt.com")
        or base_url.startswith("https://chat.openai.com")
    ) and "/backend-api" not in base_url:
        base_url = f"{base_url}/backend-api"
    return base_url


def task_url(base_url: str, task_id: str) -> str:
    normalized = normalize_base_url(base_url)
    if normalized.endswith("/backend-api"):
        return f"{normalized[:-len('/backend-api')]}/codex/tasks/{task_id}"
    if normalized.endswith("/api/codex"):
        return f"{normalized[:-len('/api/codex')]}/codex/tasks/{task_id}"
    if normalized.endswith("/codex"):
        return f"{normalized}/tasks/{task_id}"
    return f"{normalized}/codex/tasks/{task_id}"


def parse_task_id(raw: str) -> TaskId:
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError("task id must not be empty")
    without_fragment = trimmed.split("#", 1)[0]
    without_query = without_fragment.split("?", 1)[0]
    task = without_query.rsplit("/", 1)[-1].strip()
    if not task:
        raise ValueError("task id must not be empty")
    return TaskId(task)


def resolve_environment_id_from_rows(
    requested: str, environments: Sequence[EnvironmentRow]
) -> str:
    trimmed = requested.strip()
    if not trimmed:
        raise ValueError("environment id must not be empty")
    if not environments:
        raise ValueError("no cloud environments are available for this workspace")

    for row in environments:
        if row.id == trimmed:
            return row.id

    label_matches = [
        row
        for row in environments
        if row.label is not None and row.label.lower() == trimmed.lower()
    ]
    if not label_matches:
        raise ValueError(
            f"environment '{trimmed}' not found; "
            "run `codex cloud` to list available environments"
        )
    first_id = label_matches[0].id
    if all(row.id == first_id for row in label_matches[1:]):
        return first_id
    raise ValueError(
        f"environment label '{trimmed}' is ambiguous; "
        "run `codex cloud` to pick the desired environment id"
    )


def resolve_query_input(
    query_arg: str | None,
    *,
    stdin_text: str = "",
    stdin_is_terminal: bool = False,
    read_error: Exception | None = None,
) -> str:
    if query_arg is not None and query_arg != "-":
        return query_arg

    force_stdin = query_arg == "-"
    if stdin_is_terminal and not force_stdin:
        raise ValueError("no query provided. Pass one as an argument or pipe it via stdin.")
    if read_error is not None:
        raise ValueError(f"failed to read query from stdin: {read_error}") from read_error
    if not stdin_text.strip():
        raise ValueError("no query provided via stdin (received empty input).")
    return stdin_text


def level_from_status(status: ApplyStatus | str) -> ApplyResultLevel:
    value = status.value if hasattr(status, "value") else str(status)
    return {
        "success": ApplyResultLevel.SUCCESS,
        "partial": ApplyResultLevel.PARTIAL,
        "error": ApplyResultLevel.ERROR,
    }[value]


async def resolve_git_ref_with_git_info(
    branch_override: str | None,
    git_info: GitInfoProvider,
) -> str:
    if branch_override is not None:
        branch = branch_override.strip()
        if branch:
            return branch

    current = await _maybe_await(git_info.current_branch_name())
    if current is not None:
        return current
    default = await _maybe_await(git_info.default_branch_name())
    if default is not None:
        return default
    return "main"


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _attempt_sort_key(attempt: AttemptDiffData) -> tuple[int, int | float]:
    if attempt.placement is not None:
        return 0, attempt.placement
    if attempt.created_at is not None:
        created = attempt.created_at
        if isinstance(created, datetime):
            created = created.timestamp()
        return 1, created
    return 2, 0


async def collect_attempt_diffs(backend: Any, task_id: TaskId) -> list[AttemptDiffData]:
    text = await backend.get_task_text(task_id)
    attempts: list[AttemptDiffData] = []
    diff = await backend.get_task_diff(task_id)
    if diff is not None:
        attempts.append(
            AttemptDiffData(
                placement=getattr(text, "attempt_placement", None),
                created_at=None,
                diff=diff,
            )
        )
    turn_id = getattr(text, "turn_id", None)
    if turn_id is not None:
        siblings = await backend.list_sibling_attempts(task_id, turn_id)
        for sibling in siblings:
            sibling_diff = getattr(sibling, "diff", None)
            if sibling_diff is not None:
                attempts.append(
                    AttemptDiffData(
                        placement=getattr(sibling, "attempt_placement", None),
                        created_at=getattr(sibling, "created_at", None),
                        diff=sibling_diff,
                    )
                )
    attempts.sort(key=_attempt_sort_key)
    if not attempts:
        raise RuntimeError(f"No diff available for task {task_id.value}; it may still be running.")
    return attempts


def select_attempt(
    attempts: Sequence[AttemptDiffData], attempt: int | None = None
) -> AttemptDiffData:
    if not attempts:
        raise ValueError("No attempts available")
    desired = 1 if attempt is None else attempt
    idx = desired - 1
    if idx < 0:
        raise ValueError("attempt must be at least 1")
    if idx >= len(attempts):
        raise ValueError(
            f"Attempt {desired} not available; only {len(attempts)} attempt(s) found"
        )
    return attempts[idx]


def task_status_label(status: TaskStatus | str) -> str:
    value = status.value if hasattr(status, "value") else str(status)
    return {
        "pending": "PENDING",
        "ready": "READY",
        "applied": "APPLIED",
        "error": "ERROR",
    }[value]


def summary_line(summary: DiffSummary, colorize: bool = False) -> str:
    del colorize
    if (
        summary.files_changed == 0
        and summary.lines_added == 0
        and summary.lines_removed == 0
    ):
        return "no diff"
    files = summary.files_changed
    return (
        f"+{summary.lines_added}/-{summary.lines_removed} "
        f"\u2022 {files} file{'' if files == 1 else 's'}"
    )


def format_relative_time(reference: datetime, ts: datetime | float) -> str:
    if isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts, tz=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    secs = int((reference - ts).total_seconds())
    if secs < 0:
        secs = 0
    if secs < 60:
        return f"{secs}s ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    local = ts.astimezone()
    return f"{local.strftime('%b')} {local.day:2d} {local.strftime('%H:%M')}"


def format_task_status_lines(task: Any, now: datetime, colorize: bool = False) -> list[str]:
    del colorize
    lines = [f"[{task_status_label(task.status)}] {task.title}"]
    meta_parts: list[str] = []
    label = getattr(task, "environment_label", None)
    env_id = getattr(task, "environment_id", None)
    if label:
        meta_parts.append(label)
    elif env_id is not None:
        meta_parts.append(env_id)
    meta_parts.append(format_relative_time(now, task.updated_at))
    lines.append("  \u2022  ".join(meta_parts))
    lines.append(summary_line(task.summary, False))
    return lines


def format_task_list_lines(
    tasks: Sequence[Any],
    base_url: str,
    now: datetime,
    colorize: bool = False,
) -> list[str]:
    lines: list[str] = []
    for idx, task in enumerate(tasks):
        task_id = getattr(task.id, "value", str(task.id))
        lines.append(task_url(base_url, task_id))
        for line in format_task_status_lines(task, now, colorize):
            lines.append(f"  {line}")
        if idx + 1 < len(tasks):
            lines.append("")
    return lines


def environment_list_url(base_url: str) -> str:
    if "/backend-api" in base_url:
        return f"{base_url}/wham/environments"
    return f"{base_url}/api/codex/environments"


def by_repo_environments_url(base_url: str, owner: str, repo: str) -> str:
    if "/backend-api" in base_url:
        return f"{base_url}/wham/environments/by-repo/github/{owner}/{repo}"
    return f"{base_url}/api/codex/environments/by-repo/github/{owner}/{repo}"


def parse_owner_repo(url: str) -> tuple[str, str] | None:
    s = url.strip()
    if s.startswith("ssh://"):
        s = s[len("ssh://") :]

    marker = "@github.com:"
    idx = s.find(marker)
    if idx != -1:
        rest = s[idx + len(marker) :].lstrip("/").removesuffix(".git")
        parts = rest.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None

    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "git://github.com/",
        "github.com/",
    ):
        if s.startswith(prefix):
            rest = s[len(prefix) :].lstrip("/").removesuffix(".git")
            parts = rest.split("/", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
            return None
    return None


def uniq(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def pick_environment_row(
    envs: Sequence[CodeEnvironment], desired_label: str | None = None
) -> CodeEnvironment | None:
    if not envs:
        return None
    if desired_label is not None:
        lc = desired_label.lower()
        for env in envs:
            if (env.label or "").lower() == lc:
                return env
    if len(envs) == 1:
        return envs[0]
    for env in envs:
        if env.is_pinned or False:
            return env

    best = envs[0]
    best_key = best.task_count or 0
    for env in envs[1:]:
        key = env.task_count or 0
        if key >= best_key:
            best = env
            best_key = key
    return best


def _default_transport(url: str, headers: Headers) -> CloudTasksHttpResponse:
    req = request.Request(url, headers=dict(headers), method="GET")
    try:
        with request.urlopen(req) as res:  # noqa: S310 - caller controls URL.
            body = res.read().decode("utf-8", errors="replace")
            content_type = res.headers.get("content-type", "")
            return CloudTasksHttpResponse(res.status, body, content_type)
    except request.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        content_type = exc.headers.get("content-type", "") if exc.headers else ""
        return CloudTasksHttpResponse(exc.code, body, content_type)


def get_json(
    url: str,
    headers: Headers | None = None,
    *,
    transport: Transport | None = None,
) -> list[CodeEnvironment]:
    response = (transport or _default_transport)(url, headers or {})
    if not response.is_success:
        raise RuntimeError(
            f"GET {url} failed: {response.status}; "
            f"content-type={response.content_type}; body={response.body}"
        )
    try:
        parsed = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Decode error for {url}: {exc}; "
            f"content-type={response.content_type}; body={response.body}"
        ) from exc
    if not isinstance(parsed, list):
        raise RuntimeError(
            f"Decode error for {url}: expected list; "
            f"content-type={response.content_type}; body={response.body}"
        )
    return [CodeEnvironment.from_mapping(item) for item in parsed]


def get_git_origins(
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] | None = None,
) -> list[str]:
    run = runner or _run_git

    config = run(["git", "config", "--get-regexp", r"remote\..*\.url"])
    if config.returncode == 0:
        urls = []
        for line in config.stdout.splitlines():
            if " " in line:
                _, url = line.split(" ", 1)
                urls.append(url.strip())
        if urls:
            return uniq(urls)

    remote = run(["git", "remote", "-v"])
    if remote.returncode == 0:
        urls = []
        for line in remote.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                urls.append(parts[1])
        if urls:
            return uniq(urls)

    return []


def _run_git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def autodetect_environment_id(
    base_url: str,
    headers: Headers | None = None,
    desired_label: str | None = None,
    *,
    origins: Sequence[str] | None = None,
    transport: Transport | None = None,
) -> AutodetectSelection:
    request_headers = headers or {}
    by_repo_envs: list[CodeEnvironment] = []
    for origin in (origins if origins is not None else get_git_origins()):
        parsed = parse_owner_repo(origin)
        if parsed is None:
            continue
        owner, repo = parsed
        url = by_repo_environments_url(base_url, owner, repo)
        try:
            by_repo_envs.extend(get_json(url, request_headers, transport=transport))
        except Exception:
            continue

    picked = pick_environment_row(by_repo_envs, desired_label)
    if picked is not None:
        return AutodetectSelection(picked.id, picked.label)

    list_url = environment_list_url(base_url)
    all_envs = get_json(list_url, request_headers, transport=transport)
    picked = pick_environment_row(all_envs, desired_label)
    if picked is not None:
        return AutodetectSelection(picked.id, picked.label)
    raise RuntimeError("no environments available")


def list_environments(
    base_url: str,
    headers: Headers | None = None,
    *,
    origins: Sequence[str] | None = None,
    transport: Transport | None = None,
) -> list[EnvironmentRow]:
    request_headers = headers or {}
    rows: MutableMapping[str, EnvironmentRow] = {}

    for origin in (origins if origins is not None else get_git_origins()):
        parsed = parse_owner_repo(origin)
        if parsed is None:
            continue
        owner, repo = parsed
        url = by_repo_environments_url(base_url, owner, repo)
        try:
            envs = get_json(url, request_headers, transport=transport)
        except Exception:
            continue
        repo_hint = f"{owner}/{repo}"
        for env in envs:
            existing = rows.get(env.id)
            if existing is None:
                rows[env.id] = EnvironmentRow(
                    id=env.id,
                    label=env.label,
                    is_pinned=env.is_pinned or False,
                    repo_hints=repo_hint,
                )
            else:
                rows[env.id] = EnvironmentRow(
                    id=existing.id,
                    label=existing.label if existing.label is not None else env.label,
                    is_pinned=existing.is_pinned or (env.is_pinned or False),
                    repo_hints=existing.repo_hints or repo_hint,
                )

    list_url = environment_list_url(base_url)
    try:
        envs = get_json(list_url, request_headers, transport=transport)
    except Exception:
        if not rows:
            raise
    else:
        for env in envs:
            existing = rows.get(env.id)
            if existing is None:
                rows[env.id] = EnvironmentRow(
                    id=env.id,
                    label=env.label,
                    is_pinned=env.is_pinned or False,
                    repo_hints=None,
                )
            else:
                rows[env.id] = EnvironmentRow(
                    id=existing.id,
                    label=existing.label if existing.label is not None else env.label,
                    is_pinned=existing.is_pinned or (env.is_pinned or False),
                    repo_hints=existing.repo_hints,
                )

    return sorted(
        rows.values(),
        key=lambda row: (
            not row.is_pinned,
            (row.label or "").lower(),
            row.id,
        ),
    )
