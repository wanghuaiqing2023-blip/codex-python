import asyncio
from datetime import datetime, timedelta, timezone
import re

import pytest

import pycodex.cloud_tasks as cloud_tasks_module
from pycodex.cloud_tasks import (
    App,
    ApplyCommand,
    AttemptDiffData,
    ApplyJob,
    ApplyResultLevel,
    BackendContext,
    Cli,
    Command,
    DiffCommand,
    EnvironmentRow,
    ExecCommand,
    ExecCommandProjection,
    ListCommand,
    RunMainDispatchProjection,
    StatusCommand,
    append_error_log,
    apply_finished_event_projection,
    apply_preflight_finished_event_projection,
    build_chatgpt_headers,
    collect_attempt_diffs,
    apply_command_projection,
    diff_command_projection,
    exec_command_projection,
    format_list_command_text_lines,
    format_relative_time,
    format_task_list_lines,
    format_task_status_lines,
    init_backend,
    level_from_status,
    list_command_json_payload,
    load_auth_manager,
    parse_task_id,
    resolve_environment_id_from_rows,
    resolve_git_ref_with_git_info,
    resolve_query_input,
    run_main_dispatch_projection,
    select_attempt,
    spawn_apply_start_projection,
    spawn_preflight_start_projection,
    status_command_projection,
    summary_line,
    task_url,
)
from pycodex.login.auth import default_client
from pycodex.cloud_tasks_client import (
    ApplyOutcome,
    ApplyStatus,
    CreatedTask,
    DiffSummary,
    TaskId,
    TaskStatus,
    TaskSummary,
)
from pycodex.cloud_tasks_mock_client import MockClient


class StubGitInfo:
    def __init__(self, default_branch=None, current_branch=None):
        self.default_branch = default_branch
        self.current_branch = current_branch

    async def default_branch_name(self):
        return self.default_branch

    async def current_branch_name(self):
        return self.current_branch


class FakeCloudTasksAuth:
    def __init__(
        self,
        *,
        token: str | None = "chatgpt-token",
        account_id: str | None = "acct_123",
        uses_backend: bool = True,
    ) -> None:
        self.token = token
        self.account_id = account_id
        self.uses_backend = uses_backend

    def uses_codex_backend(self) -> bool:
        return self.uses_backend

    def get_token(self) -> str | None:
        return self.token

    def get_account_id(self) -> str | None:
        return self.account_id


class FakeCloudTasksAuthManager:
    def __init__(self, auth: FakeCloudTasksAuth | None) -> None:
        self._auth = auth

    async def auth(self) -> FakeCloudTasksAuth | None:
        return self._auth


class FakeCloudTasksHttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.user_agent: str | None = None
        self.auth_provider = None

    @classmethod
    def new(cls, base_url: str) -> "FakeCloudTasksHttpClient":
        return cls(base_url)

    def with_user_agent(self, ua: str) -> "FakeCloudTasksHttpClient":
        self.user_agent = ua
        return self

    def with_auth_provider(self, auth_provider) -> "FakeCloudTasksHttpClient":
        self.auth_provider = auth_provider
        return self


class CapturingAuthManagerFactory:
    calls: list[tuple[object, bool, str, str | None]] = []

    @classmethod
    async def new(
        cls,
        codex_home,
        enable_codex_api_key_env: bool,
        auth_credentials_store_mode: str,
        chatgpt_base_url: str | None = None,
    ):
        cls.calls.append(
            (
                codex_home,
                enable_codex_api_key_env,
                auth_credentials_store_mode,
                chatgpt_base_url,
            )
        )
        return {"auth_manager": len(cls.calls)}


def test_resolve_git_ref_with_git_info_matches_branch_fallback_tests():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::resolve_git_ref_with_git_info.
    assert (
        asyncio.run(
            resolve_git_ref_with_git_info(
                "feature/override", StubGitInfo(None, None)
            )
        )
        == "feature/override"
    )
    assert (
        asyncio.run(
            resolve_git_ref_with_git_info(
                "  feature/spaces  ", StubGitInfo(None, None)
            )
        )
        == "feature/spaces"
    )
    assert (
        asyncio.run(
            resolve_git_ref_with_git_info(
                None, StubGitInfo("default-main", "feature/current")
            )
        )
        == "feature/current"
    )
    assert (
        asyncio.run(resolve_git_ref_with_git_info(None, StubGitInfo(None, "develop")))
        == "develop"
    )
    assert (
        asyncio.run(resolve_git_ref_with_git_info(None, StubGitInfo(None, None)))
        == "main"
    )


def test_parse_task_id_from_url_and_raw():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::parse_task_id_from_url_and_raw.
    assert parse_task_id("task_i_abc123").value == "task_i_abc123"
    assert (
        parse_task_id("https://chatgpt.com/codex/tasks/task_i_123456?foo=bar").value
        == "task_i_123456"
    )
    assert parse_task_id(" https://chatgpt.com/codex/tasks/T-1000#frag ").value == "T-1000"
    with pytest.raises(ValueError, match="^task id must not be empty$"):
        parse_task_id("   ")
    with pytest.raises(ValueError, match="^task id must not be empty$"):
        parse_task_id("https://chatgpt.com/codex/tasks/")


def test_resolve_environment_id_from_rows_matches_source_contract():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::resolve_environment_id.
    rows = [
        EnvironmentRow(id="env-1", label="Prod", is_pinned=False),
        EnvironmentRow(id="env-2", label="Staging", is_pinned=False),
    ]

    assert resolve_environment_id_from_rows(" env-1 ", rows) == "env-1"
    assert resolve_environment_id_from_rows("prod", rows) == "env-1"
    with pytest.raises(ValueError, match="^environment id must not be empty$"):
        resolve_environment_id_from_rows("   ", rows)
    with pytest.raises(
        ValueError, match="^no cloud environments are available for this workspace$"
    ):
        resolve_environment_id_from_rows("prod", [])
    with pytest.raises(
        ValueError,
        match=(
            "^environment 'missing' not found; "
            "run `codex cloud` to list available environments$"
        ),
    ):
        resolve_environment_id_from_rows("missing", rows)


def test_resolve_environment_id_label_ambiguity_rules():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::resolve_environment_id.
    same_id_rows = [
        EnvironmentRow(id="env-1", label="Prod", is_pinned=False),
        EnvironmentRow(id="env-1", label="prod", is_pinned=True),
    ]
    assert resolve_environment_id_from_rows("PROD", same_id_rows) == "env-1"

    ambiguous_rows = [
        EnvironmentRow(id="env-1", label="Prod", is_pinned=False),
        EnvironmentRow(id="env-2", label="prod", is_pinned=False),
    ]
    with pytest.raises(
        ValueError,
        match=(
            "^environment label 'Prod' is ambiguous; "
            "run `codex cloud` to pick the desired environment id$"
        ),
    ):
        resolve_environment_id_from_rows("Prod", ambiguous_rows)


def test_resolve_query_input_matches_argument_and_stdin_contracts():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::resolve_query_input.
    assert resolve_query_input("hello", stdin_text="ignored", stdin_is_terminal=True) == "hello"
    assert resolve_query_input("-", stdin_text="from stdin", stdin_is_terminal=True) == (
        "from stdin"
    )
    assert resolve_query_input(None, stdin_text="piped stdin", stdin_is_terminal=False) == (
        "piped stdin"
    )
    with pytest.raises(
        ValueError,
        match=(
            "^no query provided\\. Pass one as an argument or pipe it via stdin\\.$"
        ),
    ):
        resolve_query_input(None, stdin_text="", stdin_is_terminal=True)
    with pytest.raises(
        ValueError, match="^no query provided via stdin \\(received empty input\\)\\.$"
    ):
        resolve_query_input("-", stdin_text=" \n\t ", stdin_is_terminal=False)
    with pytest.raises(ValueError, match="^failed to read query from stdin: boom$"):
        resolve_query_input("-", read_error=OSError("boom"))


def test_level_from_status_maps_apply_status_to_modal_level():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::level_from_status.
    assert level_from_status(ApplyStatus.SUCCESS) is ApplyResultLevel.SUCCESS
    assert level_from_status(ApplyStatus.PARTIAL) is ApplyResultLevel.PARTIAL
    assert level_from_status(ApplyStatus.ERROR) is ApplyResultLevel.ERROR


def test_task_url_and_summary_line_contracts():
    # Rust crate/module: codex-cloud-tasks/src/util.rs::task_url and src/lib.rs::summary_line.
    assert (
        task_url("https://chatgpt.com/backend-api", "task_1")
        == "https://chatgpt.com/codex/tasks/task_1"
    )
    assert (
        task_url("https://example.test/api/codex", "task_1")
        == "https://example.test/codex/tasks/task_1"
    )
    assert task_url("https://example.test/codex", "task_1") == (
        "https://example.test/codex/tasks/task_1"
    )
    assert task_url("https://example.test/root", "task_1") == (
        "https://example.test/root/codex/tasks/task_1"
    )
    assert summary_line(DiffSummary()) == "no diff"
    assert summary_line(DiffSummary(files_changed=1, lines_added=5, lines_removed=2)) == (
        "+5/-2 \u2022 1 file"
    )
    assert summary_line(DiffSummary(files_changed=3, lines_added=5, lines_removed=2)) == (
        "+5/-2 \u2022 3 files"
    )


def test_format_relative_time_source_contracts():
    # Rust crate/module: codex-cloud-tasks/src/util.rs::format_relative_time.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    assert format_relative_time(now, now + timedelta(seconds=5)) == "0s ago"
    assert format_relative_time(now, now - timedelta(seconds=59)) == "59s ago"
    assert format_relative_time(now, now - timedelta(minutes=5)) == "5m ago"
    assert format_relative_time(now, now - timedelta(hours=3)) == "3h ago"


def test_append_error_log_appends_rfc3339_timestamped_lines(tmp_path, monkeypatch):
    # Rust crate/module: codex-cloud-tasks/src/util.rs::append_error_log.
    # Source contract: create/append `error.log`, write `[{Utc::now().to_rfc3339()}] {message}`,
    # and ignore open/write failures.
    monkeypatch.chdir(tmp_path)

    append_error_log("first failure")
    append_error_log("second failure")

    lines = (tmp_path / "error.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert re.match(
        r"^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00\] first failure$",
        lines[0],
    )
    assert re.match(
        r"^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00\] second failure$",
        lines[1],
    )


def test_build_chatgpt_headers_sets_user_agent_and_codex_backend_auth():
    # Rust crate/module: codex-cloud-tasks/src/util.rs::build_chatgpt_headers.
    # Source contract: set the cloud-tasks TUI User-Agent suffix and extend
    # ChatGPT-backed auth headers only when auth.uses_codex_backend().
    default_client._reset_for_tests()

    headers = asyncio.run(
        build_chatgpt_headers(FakeCloudTasksAuthManager(FakeCloudTasksAuth()))
    )

    assert "codex_cloud_tasks_tui" in headers["user-agent"]
    assert headers["Authorization"] == "Bearer chatgpt-token"
    assert headers["ChatGPT-Account-ID"] == "acct_123"


def test_build_chatgpt_headers_skips_non_codex_backend_auth():
    # Rust crate/module: codex-cloud-tasks/src/util.rs::build_chatgpt_headers.
    default_client._reset_for_tests()

    headers = asyncio.run(
        build_chatgpt_headers(
            FakeCloudTasksAuthManager(FakeCloudTasksAuth(uses_backend=False))
        )
    )

    assert "codex_cloud_tasks_tui" in headers["user-agent"]
    assert "Authorization" not in headers
    assert "ChatGPT-Account-ID" not in headers


def test_load_auth_manager_uses_codex_home_config_and_disables_api_key_env(tmp_path, monkeypatch):
    # Rust crate/module: codex-cloud-tasks/src/util.rs::load_auth_manager.
    # Source contract: Config::load_with_cli_overrides(Vec::new()), AuthManager::new(
    # config.codex_home, enable_codex_api_key_env=false, config.cli_auth_credentials_store_mode,
    # chatgpt_base_url.or(Some(config.chatgpt_base_url))).
    (tmp_path / "config.toml").write_text(
        'cli_auth_credentials_store = "ephemeral"\n'
        'chatgpt_base_url = "https://configured.example/backend-api"\n',
        encoding="utf-8",
    )
    CapturingAuthManagerFactory.calls = []
    monkeypatch.setattr(cloud_tasks_module, "find_codex_home", lambda: tmp_path)
    monkeypatch.setattr(cloud_tasks_module, "AuthManager", CapturingAuthManagerFactory)

    manager = asyncio.run(load_auth_manager())

    assert manager == {"auth_manager": 1}
    assert CapturingAuthManagerFactory.calls == [
        (tmp_path, False, "ephemeral", "https://configured.example/backend-api")
    ]


def test_load_auth_manager_prefers_explicit_base_url_and_returns_none_on_config_error(
    tmp_path, monkeypatch
):
    # Rust crate/module: codex-cloud-tasks/src/util.rs::load_auth_manager.
    CapturingAuthManagerFactory.calls = []
    (tmp_path / "config.toml").write_text(
        'chatgpt_base_url = "https://configured.example/backend-api"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cloud_tasks_module, "find_codex_home", lambda: tmp_path)
    monkeypatch.setattr(cloud_tasks_module, "AuthManager", CapturingAuthManagerFactory)

    manager = asyncio.run(load_auth_manager("https://override.example/backend-api"))

    assert manager == {"auth_manager": 1}
    assert CapturingAuthManagerFactory.calls == [
        (tmp_path, False, "file", "https://override.example/backend-api")
    ]

    monkeypatch.setattr(
        cloud_tasks_module,
        "find_codex_home",
        lambda: (_ for _ in ()).throw(FileNotFoundError("missing CODEX_HOME")),
    )
    assert asyncio.run(load_auth_manager()) is None


def test_init_backend_uses_mock_client_in_debug_mock_mode():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::init_backend.
    # Source contract: debug builds honor CODEX_CLOUD_TASKS_MODE=mock and return MockClient
    # with the configured/default base URL before auth loading.
    default_client._reset_for_tests()
    calls = []

    async def fail_loader(_base_url):
        calls.append(_base_url)
        raise AssertionError("auth loader should not run for mock mode")

    ctx = asyncio.run(
        init_backend(
            "codex_cloud_tasks_tui",
            env={"CODEX_CLOUD_TASKS_MODE": "mock"},
            auth_manager_loader=fail_loader,
        )
    )

    assert isinstance(ctx, BackendContext)
    assert isinstance(ctx.backend, MockClient)
    assert ctx.base_url == "https://chatgpt.com/backend-api"
    assert calls == []


def test_init_backend_builds_http_backend_with_user_agent_auth_and_logs():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::init_backend.
    # Source contract: base URL from env, set user-agent suffix, build HttpClient,
    # load auth with that base URL, require Codex backend auth, inject auth provider,
    # and append startup/account log lines.
    default_client._reset_for_tests()
    logs = []
    loader_calls = []

    async def loader(base_url):
        loader_calls.append(base_url)
        return FakeCloudTasksAuthManager(FakeCloudTasksAuth())

    ctx = asyncio.run(
        init_backend(
            "codex_cloud_tasks_exec",
            env={"CODEX_CLOUD_TASKS_BASE_URL": "https://example.test/api/codex"},
            http_client_factory=FakeCloudTasksHttpClient.new,
            auth_manager_loader=loader,
            logger=logs.append,
        )
    )

    assert ctx.base_url == "https://example.test/api/codex"
    assert isinstance(ctx.backend, FakeCloudTasksHttpClient)
    assert "codex_cloud_tasks_exec" in ctx.backend.user_agent
    assert ctx.backend.auth_provider.to_auth_headers() == {
        "Authorization": "Bearer chatgpt-token",
        "ChatGPT-Account-ID": "acct_123",
    }
    assert loader_calls == ["https://example.test/api/codex"]
    assert logs == [
        "startup: base_url=https://example.test/api/codex path_style=codex-api",
        "auth: mode=ChatGPT account_id=acct_123",
        "auth: set ChatGPT-Account-Id header: acct_123",
    ]


def test_init_backend_rejects_missing_or_non_codex_backend_auth():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::init_backend.
    default_client._reset_for_tests()

    async def missing_loader(_base_url):
        return FakeCloudTasksAuthManager(None)

    with pytest.raises(RuntimeError, match="^Not signed in\\."):
        asyncio.run(
            init_backend(
                "codex_cloud_tasks_exec",
                http_client_factory=FakeCloudTasksHttpClient.new,
                auth_manager_loader=missing_loader,
                logger=lambda _message: None,
            )
        )

    async def non_backend_loader(_base_url):
        return FakeCloudTasksAuthManager(FakeCloudTasksAuth(uses_backend=False))

    with pytest.raises(RuntimeError, match="^Not signed in\\."):
        asyncio.run(
            init_backend(
                "codex_cloud_tasks_exec",
                http_client_factory=FakeCloudTasksHttpClient.new,
                auth_manager_loader=non_backend_loader,
                logger=lambda _message: None,
            )
        )


def test_format_task_status_lines_with_diff_and_label():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::format_task_status_lines_with_diff_and_label.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    task = TaskSummary(
        id=TaskId("task_1"),
        title="Example task",
        status=TaskStatus.READY,
        updated_at=now,
        environment_id="env-1",
        environment_label="Env",
        summary=DiffSummary(files_changed=3, lines_added=5, lines_removed=2),
        is_review=False,
        attempt_total=None,
    )

    assert format_task_status_lines(task, now, colorize=False) == [
        "[READY] Example task",
        "Env  \u2022  0s ago",
        "+5/-2 \u2022 3 files",
    ]


def test_format_task_status_lines_without_diff_falls_back():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::format_task_status_lines_without_diff_falls_back.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    task = TaskSummary(
        id=TaskId("task_2"),
        title="No diff task",
        status=TaskStatus.PENDING,
        updated_at=now,
        environment_id="env-2",
        environment_label=None,
        summary=DiffSummary(),
        is_review=False,
        attempt_total=1,
    )

    assert format_task_status_lines(task, now, colorize=False) == [
        "[PENDING] No diff task",
        "env-2  \u2022  0s ago",
        "no diff",
    ]


def test_format_task_list_lines_formats_urls():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::format_task_list_lines_formats_urls.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    tasks = [
        TaskSummary(
            id=TaskId("task_1"),
            title="Example task",
            status=TaskStatus.READY,
            updated_at=now,
            environment_id="env-1",
            environment_label="Env",
            summary=DiffSummary(files_changed=3, lines_added=5, lines_removed=2),
            is_review=False,
            attempt_total=None,
        ),
        TaskSummary(
            id=TaskId("task_2"),
            title="No diff task",
            status=TaskStatus.PENDING,
            updated_at=now,
            environment_id="env-2",
            environment_label=None,
            summary=DiffSummary(),
            is_review=False,
            attempt_total=1,
        ),
    ]

    assert format_task_list_lines(
        tasks,
        "https://chatgpt.com/backend-api",
        now,
        colorize=False,
    ) == [
        "https://chatgpt.com/codex/tasks/task_1",
        "  [READY] Example task",
        "  Env  \u2022  0s ago",
        "  +5/-2 \u2022 3 files",
        "",
        "https://chatgpt.com/codex/tasks/task_2",
        "  [PENDING] No diff task",
        "  env-2  \u2022  0s ago",
        "  no diff",
    ]


def test_list_command_json_payload_matches_rust_shape():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::run_list_command --json branch.
    updated_at = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    task = TaskSummary(
        id=TaskId("task_1"),
        title="Example task",
        status=TaskStatus.READY,
        updated_at=updated_at,
        environment_id="env-1",
        environment_label="Env",
        summary=DiffSummary(files_changed=3, lines_added=5, lines_removed=2),
        is_review=False,
        attempt_total=4,
    )

    assert list_command_json_payload(
        [task],
        cursor="next-cursor",
        base_url="https://chatgpt.com/backend-api",
    ) == {
        "tasks": [
            {
                "id": "task_1",
                "url": "https://chatgpt.com/codex/tasks/task_1",
                "title": "Example task",
                "status": "ready",
                "updated_at": "2026-06-22T12:00:00Z",
                "environment_id": "env-1",
                "environment_label": "Env",
                "summary": {
                    "files_changed": 3,
                    "lines_added": 5,
                    "lines_removed": 2,
                },
                "is_review": False,
                "attempt_total": 4,
            }
        ],
        "cursor": "next-cursor",
    }


def test_format_list_command_text_lines_empty_and_cursor_hint():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::run_list_command non-json branch.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    assert format_list_command_text_lines(
        [],
        cursor="ignored",
        base_url="https://chatgpt.com/backend-api",
        now=now,
        colorize=False,
    ) == ["No tasks found."]

    task = TaskSummary(
        id=TaskId("task_1"),
        title="Example task",
        status=TaskStatus.READY,
        updated_at=now,
        environment_id="env-1",
        environment_label="Env",
        summary=DiffSummary(files_changed=1, lines_added=2, lines_removed=0),
        is_review=False,
        attempt_total=None,
    )

    assert format_list_command_text_lines(
        [task],
        cursor="next cursor",
        base_url="https://chatgpt.com/backend-api",
        now=now,
        colorize=False,
    ) == [
        "https://chatgpt.com/codex/tasks/task_1",
        "  [READY] Example task",
        "  Env  \u2022  0s ago",
        "  +2/-0 \u2022 1 file",
        "",
        "To fetch the next page, run codex cloud list --cursor='next cursor'",
    ]


def test_status_command_projection_matches_output_and_exit_code():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::run_status_command.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    ready_task = TaskSummary(
        id=TaskId("task_ready"),
        title="Ready task",
        status=TaskStatus.READY,
        updated_at=now,
        environment_id="env-1",
        environment_label="Env",
        summary=DiffSummary(files_changed=1, lines_added=2, lines_removed=0),
        is_review=False,
        attempt_total=None,
    )
    pending_task = TaskSummary(
        id=TaskId("task_pending"),
        title="Pending task",
        status=TaskStatus.PENDING,
        updated_at=now,
        environment_id="env-1",
        environment_label=None,
        summary=DiffSummary(),
        is_review=False,
        attempt_total=None,
    )

    assert status_command_projection(ready_task, now, colorize=False) == (
        [
            "[READY] Ready task",
            "Env  \u2022  0s ago",
            "+2/-0 \u2022 1 file",
        ],
        0,
    )
    assert status_command_projection(pending_task, now, colorize=False) == (
        [
            "[PENDING] Pending task",
            "env-1  \u2022  0s ago",
            "no diff",
        ],
        1,
    )


def test_diff_command_projection_selects_attempt_diff():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::run_diff_command.
    attempts = [
        AttemptDiffData(placement=0, created_at=None, diff="diff --git a/first b/first\n"),
        AttemptDiffData(placement=1, created_at=None, diff="diff --git a/second b/second\n"),
    ]

    assert diff_command_projection(attempts, None) == "diff --git a/first b/first\n"
    assert diff_command_projection(attempts, 2) == "diff --git a/second b/second\n"


def test_exec_command_projection_matches_create_task_call_and_output_url():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::run_exec_command.
    # Contract: calls CloudBackend::create_task(env_id, prompt, git_ref, false, attempts)
    # and prints util::task_url(base_url, created.id).
    projection = exec_command_projection(
        env_id="env-1",
        prompt="ship it",
        git_ref="feature/demo",
        attempts=3,
        created_task=CreatedTask(id=TaskId("task_123")),
        base_url="https://chatgpt.com/backend-api",
    )

    assert projection == ExecCommandProjection(
        env_id="env-1",
        prompt="ship it",
        git_ref="feature/demo",
        qa_mode=False,
        best_of_n=3,
        output_url="https://chatgpt.com/codex/tasks/task_123",
    )


def test_apply_command_projection_matches_message_and_exit_code():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::run_apply_command.
    success = ApplyOutcome(
        applied=True,
        status=ApplyStatus.SUCCESS,
        message="Applied cleanly",
    )
    partial = ApplyOutcome(
        applied=False,
        status=ApplyStatus.PARTIAL,
        message="Applied with conflicts",
    )
    error = ApplyOutcome(
        applied=False,
        status=ApplyStatus.ERROR,
        message="Apply failed",
    )

    assert apply_command_projection(success) == (["Applied cleanly"], 0)
    assert apply_command_projection(partial) == (["Applied with conflicts"], 1)
    assert apply_command_projection(error) == (["Apply failed"], 1)


def test_spawn_preflight_start_projection_matches_guard_state_contract():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::spawn_preflight.
    # Contract: active apply/preflight guards update status and return false;
    # otherwise the preflight flag is set before scheduling background work.
    app = App.new()
    app.apply_inflight = True

    assert spawn_preflight_start_projection(app) is False
    assert app.status == "An apply is already running; wait for it to finish first."
    assert app.apply_preflight_inflight is False

    app = App.new()
    app.apply_preflight_inflight = True

    assert spawn_preflight_start_projection(app) is False
    assert app.status == "A preflight is already running; wait for it to finish first."
    assert app.apply_preflight_inflight is True

    app = App.new()

    assert spawn_preflight_start_projection(app) is True
    assert app.apply_preflight_inflight is True
    assert app.apply_inflight is False
    assert ApplyJob(task_id=TaskId("task-1"), diff_override="diff").diff_override == "diff"


def test_spawn_apply_start_projection_matches_guard_state_contract():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::spawn_apply.
    # Contract: active apply/preflight guards update status and return false;
    # otherwise the apply flag is set before scheduling background work.
    app = App.new()
    app.apply_inflight = True

    assert spawn_apply_start_projection(app) is False
    assert app.status == "An apply is already running; wait for it to finish first."
    assert app.apply_inflight is True

    app = App.new()
    app.apply_preflight_inflight = True

    assert spawn_apply_start_projection(app) is False
    assert app.status == "Finish the current preflight before starting another apply."
    assert app.apply_inflight is False

    app = App.new()

    assert spawn_apply_start_projection(app) is True
    assert app.apply_inflight is True
    assert app.apply_preflight_inflight is False


def test_apply_preflight_event_projection_matches_spawn_preflight_result_mapping():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::spawn_preflight.
    # Contract: successful preflight maps outcome fields into ApplyPreflightFinished;
    # failed preflight maps to "Preflight failed: {error}" and Error level.
    outcome = ApplyOutcome(
        applied=False,
        status=ApplyStatus.PARTIAL,
        message="Needs manual edits",
        skipped_paths=["vendor.py"],
        conflict_paths=["main.py"],
    )

    event = apply_preflight_finished_event_projection(
        task_id=TaskId("task-1"),
        title="Task title",
        result=outcome,
    )

    assert event.kind == "ApplyPreflightFinished"
    assert event.payload == {
        "id": TaskId("task-1"),
        "title": "Task title",
        "message": "Needs manual edits",
        "level": ApplyResultLevel.PARTIAL,
        "skipped": ["vendor.py"],
        "conflicts": ["main.py"],
    }

    failed = apply_preflight_finished_event_projection(
        task_id=TaskId("task-2"),
        title="Broken task",
        result=RuntimeError("backend unavailable"),
    )

    assert failed.kind == "ApplyPreflightFinished"
    assert failed.payload == {
        "id": TaskId("task-2"),
        "title": "Broken task",
        "message": "Preflight failed: backend unavailable",
        "level": ApplyResultLevel.ERROR,
        "skipped": [],
        "conflicts": [],
    }


def test_apply_finished_event_projection_matches_spawn_apply_result_mapping():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::spawn_apply.
    # Contract: successful apply wraps the outcome in ApplyFinished::Ok; failed
    # apply wraps the display error string in ApplyFinished::Err.
    outcome = ApplyOutcome(
        applied=True,
        status=ApplyStatus.SUCCESS,
        message="Applied",
    )

    event = apply_finished_event_projection(task_id=TaskId("task-1"), result=outcome)

    assert event.kind == "ApplyFinished"
    assert event.payload == {"id": TaskId("task-1"), "result": outcome}

    failed = apply_finished_event_projection(
        task_id=TaskId("task-2"),
        result=RuntimeError("patch rejected"),
    )

    assert failed.kind == "ApplyFinished"
    assert failed.payload == {"id": TaskId("task-2"), "result": "patch rejected"}


def test_run_main_dispatch_projection_matches_subcommand_match_arms():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::run_main.
    # Contract: Some(command) returns the corresponding run_*_command branch
    # before any TUI initialization; None enters the list TUI path.
    cases = [
        (
            Cli(command=Command.exec(ExecCommand("hello", "env-1"))),
            RunMainDispatchProjection("run_exec_command", "exec", False),
        ),
        (
            Cli(command=Command.status(StatusCommand("task-1"))),
            RunMainDispatchProjection("run_status_command", "status", False),
        ),
        (
            Cli(command=Command.list(ListCommand(environment="env-1"))),
            RunMainDispatchProjection("run_list_command", "list", False),
        ),
        (
            Cli(command=Command.apply(ApplyCommand("task-1"))),
            RunMainDispatchProjection("run_apply_command", "apply", False),
        ),
        (
            Cli(command=Command.diff(DiffCommand("task-1"))),
            RunMainDispatchProjection("run_diff_command", "diff", False),
        ),
        (
            Cli(command=None),
            RunMainDispatchProjection("tui", None, True),
        ),
    ]

    for cli, expected in cases:
        assert run_main_dispatch_projection(cli) == expected


def test_collect_attempt_diffs_includes_sibling_attempts():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::collect_attempt_diffs_includes_sibling_attempts.
    task_id = parse_task_id("https://chatgpt.com/codex/tasks/T-1000")
    attempts = asyncio.run(collect_attempt_diffs(MockClient(), task_id))

    assert len(attempts) == 2
    assert attempts[0].placement == 0
    assert attempts[1].placement == 1
    assert attempts[0].diff
    assert attempts[1].diff


def test_select_attempt_validates_bounds():
    # Rust crate/module/test: codex-cloud-tasks/src/lib.rs::select_attempt_validates_bounds.
    attempts = [
        AttemptDiffData(
            placement=0,
            created_at=None,
            diff="diff --git a/file b/file\n",
        )
    ]
    assert select_attempt(attempts, 1).diff == "diff --git a/file b/file\n"
    assert select_attempt(attempts, None).diff == "diff --git a/file b/file\n"
    with pytest.raises(ValueError, match=r"^Attempt 2 not available; only 1 attempt\(s\) found$"):
        select_attempt(attempts, 2)
    with pytest.raises(ValueError, match="^attempt must be at least 1$"):
        select_attempt(attempts, 0)
    with pytest.raises(ValueError, match="^No attempts available$"):
        select_attempt([], 1)
