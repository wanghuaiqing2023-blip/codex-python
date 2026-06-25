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
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Protocol, Sequence
from urllib import request

from pycodex.config import ConfigToml
from pycodex.core.config.edit import CONFIG_TOML_FILE, read_toml_mapping
from pycodex.login.auth import default_client
from pycodex.login.auth.manager import AuthManager
from pycodex.model_provider import auth_provider_from_auth
from pycodex.utils.home_dir import find_codex_home
from pycodex.cloud_tasks_client import DiffSummary
from pycodex.cloud_tasks_client import ApplyStatus
from pycodex.cloud_tasks_client import HttpClient
from pycodex.cloud_tasks_client import TaskId
from pycodex.cloud_tasks_client import TaskStatus
from pycodex.cloud_tasks_mock_client import MockClient
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
from pycodex.cloud_tasks.app import AppEvent
from pycodex.cloud_tasks.app import ApplyModalState
from pycodex.cloud_tasks.app import AttemptView
from pycodex.cloud_tasks.app import BestOfModalState
from pycodex.cloud_tasks.app import DetailView
from pycodex.cloud_tasks.app import DiffOverlay
from pycodex.cloud_tasks.app import EnvModalState
from pycodex.cloud_tasks.app import EnvironmentRow
from pycodex.cloud_tasks.app import conversation_lines
from pycodex.cloud_tasks.app import handle_app_event
from pycodex.cloud_tasks.app import handle_apply_preflight_finished_event
from pycodex.cloud_tasks.app import handle_apply_finished_event
from pycodex.cloud_tasks.app import handle_attempts_loaded_event
from pycodex.cloud_tasks.app import handle_environment_autodetected_event
from pycodex.cloud_tasks.app import handle_environments_loaded_event
from pycodex.cloud_tasks.app import handle_details_diff_loaded_event
from pycodex.cloud_tasks.app import handle_details_failed_event
from pycodex.cloud_tasks.app import handle_details_messages_loaded_event
from pycodex.cloud_tasks.app import handle_new_task_submitted_event
from pycodex.cloud_tasks.app import handle_tasks_loaded_event
from pycodex.cloud_tasks.app import load_tasks
from pycodex.cloud_tasks.app import pretty_lines_from_error


__all__ = [
    "AutodetectSelection",
    "ApplyJob",
    "ApplyResultLevel",
    "ApplyCommand",
    "App",
    "AppEvent",
    "ApplyModalState",
    "AttemptView",
    "BestOfModalState",
    "Cli",
    "CloudTasksHttpResponse",
    "Command",
    "CodeEnvironment",
    "BackendContext",
    "diff_command_projection",
    "EnvironmentRow",
    "DiffCommand",
    "DetailView",
    "DiffOverlay",
    "ExecCommandProjection",
    "ExecCommand",
    "RunMainDispatchProjection",
    "AttemptDiffData",
    "EnvModalState",
    "ListCommand",
    "NEW_TASK_HINT_ITEMS",
    "NewTaskPage",
    "ScrollableDiff",
    "ScrollViewState",
    "StatusCommand",
    "append_error_log",
    "autodetect_environment_id",
    "by_repo_environments_url",
    "build_chatgpt_headers",
    "collect_attempt_diffs",
    "conversation_lines",
    "format_relative_time",
    "format_list_command_text_lines",
    "list_command_json_payload",
    "format_task_list_lines",
    "format_task_status_lines",
    "apply_command_projection",
    "apply_finished_event_projection",
    "apply_preflight_finished_event_projection",
    "spawn_apply_start_projection",
    "spawn_preflight_start_projection",
    "environment_list_url",
    "exec_command_projection",
    "get_git_origins",
    "get_json",
    "handle_app_event",
    "handle_apply_preflight_finished_event",
    "handle_apply_finished_event",
    "handle_attempts_loaded_event",
    "handle_environment_autodetected_event",
    "handle_environments_loaded_event",
    "handle_details_diff_loaded_event",
    "handle_details_failed_event",
    "handle_details_messages_loaded_event",
    "handle_new_task_submitted_event",
    "handle_tasks_loaded_event",
    "init_backend",
    "level_from_status",
    "list_environments",
    "load_auth_manager",
    "load_tasks",
    "parse_owner_repo",
    "parse_attempts",
    "parse_limit",
    "pretty_lines_from_error",
    "parse_task_id",
    "pick_environment_row",
    "resolve_environment_id_from_rows",
    "resolve_git_ref_with_git_info",
    "resolve_query_input",
    "run_main_dispatch_projection",
    "select_attempt",
    "set_user_agent_suffix",
    "status_command_projection",
    "summary_line",
    "task_status_label",
    "task_url",
    "uniq",
]


Headers = Mapping[str, str]
Transport = Callable[[str, Headers], "CloudTasksHttpResponse"]
DEFAULT_CLOUD_TASKS_BASE_URL = "https://chatgpt.com/backend-api"
NOT_SIGNED_IN_MESSAGE = (
    "Not signed in. Please run 'codex login' to sign in with ChatGPT, "
    "then re-run 'codex cloud'."
)


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


@dataclass(frozen=True)
class ApplyJob:
    task_id: TaskId
    diff_override: str | None = None


@dataclass(frozen=True)
class BackendContext:
    backend: Any
    base_url: str


@dataclass(frozen=True)
class ExecCommandProjection:
    env_id: str
    prompt: str
    git_ref: str
    qa_mode: bool
    best_of_n: int
    output_url: str


@dataclass(frozen=True)
class RunMainDispatchProjection:
    handler: str
    command_kind: str | None
    enters_tui: bool


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


def append_error_log(message: object) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with open("error.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except OSError:
        return


def set_user_agent_suffix(suffix: str) -> None:
    default_client.set_user_agent_suffix(suffix)


async def load_auth_manager(chatgpt_base_url: str | None = None) -> Any | None:
    try:
        codex_home = find_codex_home()
        config_toml = ConfigToml.from_mapping(
            read_toml_mapping(Path(codex_home) / CONFIG_TOML_FILE)
        )
        store_mode = config_toml.cli_auth_credentials_store or "file"
        resolved_chatgpt_base_url = chatgpt_base_url or config_toml.chatgpt_base_url
        return await AuthManager.new(
            Path(codex_home),
            False,
            _enum_value(store_mode),
            resolved_chatgpt_base_url,
        )
    except Exception:
        return None


async def build_chatgpt_headers(auth_manager: Any | None = None) -> dict[str, str]:
    set_user_agent_suffix("codex_cloud_tasks_tui")
    headers = {
        default_client.USER_AGENT_HEADER_NAME: default_client.get_codex_user_agent()
    }

    manager = auth_manager
    if manager is None:
        manager = await load_auth_manager(None)
    auth = await _auth_from_manager(manager)
    if auth is not None and _auth_uses_codex_backend(auth):
        headers.update(auth_provider_from_auth(auth).to_auth_headers())
    return headers


async def init_backend(
    user_agent_suffix: str,
    *,
    env: Mapping[str, str] | None = None,
    debug_build: bool = True,
    http_client_factory: Callable[[str], Any] | None = None,
    mock_client_factory: Callable[[], Any] | None = None,
    auth_manager_loader: Callable[..., Any] | None = None,
    logger: Callable[[object], None] | None = None,
) -> BackendContext:
    env_map = os.environ if env is None else env
    base_url = env_map.get("CODEX_CLOUD_TASKS_BASE_URL", DEFAULT_CLOUD_TASKS_BASE_URL)
    set_user_agent_suffix(user_agent_suffix)

    mode = env_map.get("CODEX_CLOUD_TASKS_MODE")
    if debug_build and mode in {"mock", "MOCK"}:
        mock_factory = mock_client_factory or MockClient
        return BackendContext(backend=mock_factory(), base_url=base_url)

    http_factory = http_client_factory or HttpClient.new
    http = http_factory(base_url)
    if hasattr(http, "with_user_agent"):
        http = http.with_user_agent(default_client.get_codex_user_agent())

    log = logger or append_error_log
    style = "wham" if "/backend-api" in base_url else "codex-api"
    log(f"startup: base_url={base_url} path_style={style}")

    loader = auth_manager_loader or load_auth_manager
    auth_manager = loader(base_url)
    if inspect.isawaitable(auth_manager):
        auth_manager = await auth_manager
    auth = await _auth_from_manager(auth_manager)
    if auth is None:
        raise RuntimeError(NOT_SIGNED_IN_MESSAGE)

    account_id = _auth_account_id(auth)
    if account_id is not None:
        log(f"auth: mode=ChatGPT account_id={account_id}")

    if not _auth_uses_codex_backend(auth):
        raise RuntimeError(NOT_SIGNED_IN_MESSAGE)

    if hasattr(http, "with_auth_provider"):
        http = http.with_auth_provider(auth_provider_from_auth(auth))
    if account_id is not None:
        log(f"auth: set ChatGPT-Account-Id header: {account_id}")

    return BackendContext(backend=http, base_url=base_url)


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


async def _auth_from_manager(auth_manager: Any | None) -> Any | None:
    if auth_manager is None:
        return None
    auth_method = getattr(auth_manager, "auth", None)
    if not callable(auth_method):
        return None
    auth = auth_method()
    if inspect.isawaitable(auth):
        auth = await auth
    return auth


def _auth_uses_codex_backend(auth: Any) -> bool:
    uses = getattr(auth, "uses_codex_backend", None)
    if callable(uses):
        return bool(uses())
    if isinstance(auth, Mapping):
        return bool(auth.get("uses_codex_backend"))
    return bool(getattr(auth, "uses_codex_backend", False))


def _auth_account_id(auth: Any) -> str | None:
    getter = getattr(auth, "get_account_id", None)
    if callable(getter):
        value = getter()
    elif isinstance(auth, Mapping):
        value = auth.get("account_id")
    else:
        value = getattr(auth, "account_id", None)
    return None if value is None else str(value)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


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


def diff_command_projection(
    attempts: Sequence[AttemptDiffData],
    attempt: int | None = None,
) -> str:
    return select_attempt(attempts, attempt).diff


def apply_command_projection(outcome: Any) -> tuple[list[str], int]:
    status = getattr(outcome, "status")
    return [str(getattr(outcome, "message"))], 0 if status == ApplyStatus.SUCCESS else 1


def spawn_preflight_start_projection(app: App) -> bool:
    if app.apply_inflight:
        app.status = "An apply is already running; wait for it to finish first."
        return False
    if app.apply_preflight_inflight:
        app.status = "A preflight is already running; wait for it to finish first."
        return False
    app.apply_preflight_inflight = True
    return True


def spawn_apply_start_projection(app: App) -> bool:
    if app.apply_inflight:
        app.status = "An apply is already running; wait for it to finish first."
        return False
    if app.apply_preflight_inflight:
        app.status = "Finish the current preflight before starting another apply."
        return False
    app.apply_inflight = True
    return True


def apply_preflight_finished_event_projection(
    *,
    task_id: TaskId,
    title: str,
    result: Any,
) -> AppEvent:
    if isinstance(result, BaseException) or isinstance(result, str):
        return AppEvent.apply_preflight_finished(
            task_id,
            title,
            f"Preflight failed: {result}",
            ApplyResultLevel.ERROR,
            [],
            [],
        )
    return AppEvent.apply_preflight_finished(
        task_id,
        title,
        str(getattr(result, "message")),
        level_from_status(getattr(result, "status")),
        list(getattr(result, "skipped_paths", [])),
        list(getattr(result, "conflict_paths", [])),
    )


def apply_finished_event_projection(*, task_id: TaskId, result: Any) -> AppEvent:
    if isinstance(result, BaseException) or isinstance(result, str):
        return AppEvent.apply_finished(task_id, str(result))
    return AppEvent.apply_finished(task_id, result)


def run_main_dispatch_projection(cli: Cli) -> RunMainDispatchProjection:
    command = cli.command
    if command is None:
        return RunMainDispatchProjection(
            handler="tui",
            command_kind=None,
            enters_tui=True,
        )
    handler_by_kind = {
        "exec": "run_exec_command",
        "status": "run_status_command",
        "list": "run_list_command",
        "apply": "run_apply_command",
        "diff": "run_diff_command",
    }
    try:
        handler = handler_by_kind[command.kind]
    except KeyError as exc:
        raise ValueError(f"unknown cloud-tasks command: {command.kind}") from exc
    return RunMainDispatchProjection(
        handler=handler,
        command_kind=command.kind,
        enters_tui=False,
    )


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


def list_command_json_payload(
    tasks: Sequence[Any],
    cursor: str | None,
    base_url: str,
) -> dict[str, Any]:
    return {
        "tasks": [
            {
                "id": _task_id_text(task.id),
                "url": task_url(base_url, _task_id_text(task.id)),
                "title": task.title,
                "status": _enum_value(task.status),
                "updated_at": _jsonable_time(task.updated_at),
                "environment_id": task.environment_id,
                "environment_label": task.environment_label,
                "summary": {
                    "files_changed": task.summary.files_changed,
                    "lines_added": task.summary.lines_added,
                    "lines_removed": task.summary.lines_removed,
                },
                "is_review": task.is_review,
                "attempt_total": task.attempt_total,
            }
            for task in tasks
        ],
        "cursor": cursor,
    }


def format_list_command_text_lines(
    tasks: Sequence[Any],
    cursor: str | None,
    base_url: str,
    now: datetime,
    colorize: bool = False,
) -> list[str]:
    if not tasks:
        return ["No tasks found."]
    lines = format_task_list_lines(tasks, base_url, now, colorize)
    if cursor is not None:
        lines.append("")
        lines.append(f"To fetch the next page, run codex cloud list --cursor='{cursor}'")
    return lines


def status_command_projection(
    task: Any,
    now: datetime,
    colorize: bool = False,
) -> tuple[list[str], int]:
    lines = format_task_status_lines(task, now, colorize)
    status = getattr(task, "status")
    return lines, 0 if status == TaskStatus.READY else 1


def _task_id_text(task_id: Any) -> str:
    return str(getattr(task_id, "value", task_id))


def exec_command_projection(
    *,
    env_id: str,
    prompt: str,
    git_ref: str,
    attempts: int,
    created_task: Any,
    base_url: str,
) -> ExecCommandProjection:
    task_id = _task_id_text(getattr(created_task, "id"))
    return ExecCommandProjection(
        env_id=env_id,
        prompt=prompt,
        git_ref=git_ref,
        qa_mode=False,
        best_of_n=attempts,
        output_url=task_url(base_url, task_id),
    )


def _jsonable_time(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return value


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
