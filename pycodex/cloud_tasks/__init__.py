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
from pycodex.cloud_tasks.app import ApplyResultLevel
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
from pycodex.cloud_tasks.env_detect import AutodetectSelection
from pycodex.cloud_tasks.env_detect import CloudTasksHttpResponse
from pycodex.cloud_tasks.env_detect import CodeEnvironment
from pycodex.cloud_tasks.env_detect import autodetect_environment_id
from pycodex.cloud_tasks.env_detect import by_repo_environments_url
from pycodex.cloud_tasks.env_detect import environment_list_url
from pycodex.cloud_tasks.env_detect import get_git_origins
from pycodex.cloud_tasks.env_detect import get_json
from pycodex.cloud_tasks.env_detect import list_environments
from pycodex.cloud_tasks.env_detect import parse_owner_repo
from pycodex.cloud_tasks.env_detect import pick_environment_row
from pycodex.cloud_tasks.env_detect import uniq
from pycodex.cloud_tasks.util import _auth_account_id
from pycodex.cloud_tasks.util import _auth_from_manager
from pycodex.cloud_tasks.util import _auth_uses_codex_backend
from pycodex.cloud_tasks.util import _enum_value
from pycodex.cloud_tasks.util import append_error_log
from pycodex.cloud_tasks.util import build_chatgpt_headers
from pycodex.cloud_tasks.util import format_relative_time
from pycodex.cloud_tasks.util import load_auth_manager
from pycodex.cloud_tasks.util import normalize_base_url
from pycodex.cloud_tasks.util import set_user_agent_suffix
from pycodex.cloud_tasks.util import task_url


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


DEFAULT_CLOUD_TASKS_BASE_URL = "https://chatgpt.com/backend-api"
NOT_SIGNED_IN_MESSAGE = (
    "Not signed in. Please run 'codex login' to sign in with ChatGPT, "
    "then re-run 'codex cloud'."
)


class GitInfoProvider(Protocol):
    def current_branch_name(self) -> str | None: ...

    def default_branch_name(self) -> str | None: ...


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
