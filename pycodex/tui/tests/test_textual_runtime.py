from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from typing import Any

import pycodex.tui as tui_module
from pycodex.core.agents_md import DEFAULT_AGENTS_MD_FILENAME
from pycodex.core.config.edit import read_toml_mapping
from pycodex.features import Feature, FeatureConfigSource, Features, FeaturesToml
from pycodex.protocol import AskForApproval, ModeKind, ReviewTarget
from pycodex.tui.app.runtime import QueueActiveThreadEventStream, TuiAppRuntime
from pycodex.tui.app_command import AppCommand
from pycodex.tui.bottom_pane.chat_composer import LARGE_PASTE_CHAR_THRESHOLD
from pycodex.tui.bottom_pane.chat_composer_history import HistoryEntry
from pycodex.tui.chatwidget.constructor import PLACEHOLDERS
from pycodex.tui.chatwidget.permission_popups import PermissionProfile as TuiPermissionProfile
from pycodex.tui.chatwidget.protocol import ServerNotification
from pycodex.tui.chatwidget.status_surfaces import DEFAULT_STATUS_LINE_ITEMS, terminal_title_spinner_frame_at
from pycodex.tui.get_git_diff import FakeRunner, null_device, response
from pycodex.tui.status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay
from pycodex.tui.resume_picker import PickerState, Row as ResumePickerRow
from pycodex.tui.textual_compat import Static, Text, events, load_textual_module
from pycodex.tui.textual_runtime import (
    CodexComposerTextArea,
    _PermissionFeatureSet,
    PyCodexTextualApp,
    configure_app_runtime_thread_identity,
    run_textual_tui,
    should_use_textual_tui,
    _runtime_status_line_item_ids,
)
from pycodex.tui.textual_windows_vt_driver import _VtInputDecoder
from pycodex.tui.token_usage import TokenUsage, TokenUsageInfo


_STARTUP_TIP_PREFIX = "Tip: Try the Codex App."


def _transcript_banner_percent(text: object) -> int:
    match = re.search(r"(\d+)%", str(text))
    assert match is not None, str(text)
    return int(match.group(1))


def _non_startup_status_notices(app: PyCodexTextualApp) -> list[str]:
    return [
        block.text
        for block in app._blocks
        if block.label == "status" and not str(block.text).startswith(_STARTUP_TIP_PREFIX)
    ]


class _Tty:
    def isatty(self) -> bool:
        return True


class _Pipe:
    def isatty(self) -> bool:
        return False


@dataclass
class _ListEventStream:
    events: list[ServerNotification]
    closed: bool = False

    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        if self.events:
            return self.events.pop(0)
        self.closed = True
        return None


class _FakeActiveThreadRuntime:
    thread_id = "primary"
    cwd = "."

    def __init__(self, events: list[ServerNotification]) -> None:
        self.events = events
        self.submitted: list[tuple[str, AppCommand]] = []
        self.shutdowns: list[str] = []
        self.session_config = SimpleNamespace(model="gpt-test", model_reasoning_effort="high", cwd=".")

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> _ListEventStream:
        self.submitted.append((thread_id, op))
        return _ListEventStream(list(self.events))

    def shutdown_thread(self, thread_id: str) -> _ListEventStream:
        self.shutdowns.append(thread_id)
        return _ListEventStream([])


class _FakeAppServerRuntime(_FakeActiveThreadRuntime):
    def __init__(self, events: list[ServerNotification], app_server_events: list[object]) -> None:
        super().__init__(events)
        self.app_server_events = list(app_server_events)

    def next_app_server_event(self, timeout: float | None = 0) -> object | None:
        if self.app_server_events:
            return self.app_server_events.pop(0)
        return None


class _WaitingRolloutRuntime(_FakeActiveThreadRuntime):
    def __init__(self, events: list[ServerNotification], rollout_path: Path) -> None:
        super().__init__(events)
        self._waiting_rollout_path = rollout_path
        self.wait_seconds: list[float | None] = []

    def wait_for_rollout_path(self, timeout_seconds: float | None = None) -> Path:
        self.wait_seconds.append(timeout_seconds)
        self._waiting_rollout_path.write_text('{"type":"session_meta"}\n', encoding="utf-8")
        return self._waiting_rollout_path


class _BlockingFirstTurnRuntime(_FakeActiveThreadRuntime):
    def __init__(self) -> None:
        super().__init__([])
        self.first_turn_queue: Queue[Any] = Queue()

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> Any:
        self.submitted.append((thread_id, op))
        if len(self.submitted) == 1:
            return QueueActiveThreadEventStream(self.first_turn_queue)
        return _ListEventStream(
            [
                ServerNotification("TurnStarted", {"turn": {"id": "compact-turn"}}),
                ServerNotification("TurnCompleted", {"turn": {"id": "compact-turn", "status": "Completed"}}),
            ]
        )


def test_should_use_textual_tui_for_product_tty(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::tui owns the interactive terminal event loop.
    # - Python only enters the Textual product runtime for real TTY sessions;
    #   non-TTY startup is rejected rather than routed to a second renderer.
    runtime = _FakeActiveThreadRuntime([])

    assert should_use_textual_tui(
        stdout=_Tty(),
        stdin=_Tty(),
        active_thread_runtime=runtime,
        use_alt_screen=True,
    )
    assert not should_use_textual_tui(
        stdout=_Pipe(),
        stdin=_Tty(),
        active_thread_runtime=runtime,
        use_alt_screen=True,
    )


def test_should_use_textual_tui_ignores_removed_legacy_escape_hatch(monkeypatch) -> None:
    # Product rule: the Textual shell is the only interactive product path.
    # A stale escape-hatch env var must not route around it.
    monkeypatch.setenv("PYCODEX_TUI_LEGACY_TERMINAL", "1")
    runtime = _FakeActiveThreadRuntime([])

    assert should_use_textual_tui(
        stdout=_Tty(),
        stdin=_Tty(),
        active_thread_runtime=runtime,
        use_alt_screen=True,
    )


def test_should_use_textual_tui_ignores_no_alt_screen_for_product_tty(monkeypatch) -> None:
    # Rust's --no-alt-screen is a terminal-mode choice, not permission to
    # re-enter a removed secondary product UI path.
    runtime = _FakeActiveThreadRuntime([])

    assert should_use_textual_tui(
        stdout=_Tty(),
        stdin=_Tty(),
        active_thread_runtime=runtime,
        use_alt_screen=False,
    )


def test_public_run_tui_entry_uses_textual_when_runtime_is_available(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::run_main/run_tui is the product TUI entry boundary.
    # - Python's public compatibility entry must route a real active-thread
    #   runtime into the Textual product shell.
    runtime = _FakeActiveThreadRuntime([])
    observed: dict[str, object] = {}

    def fake_run(self: PyCodexTextualApp) -> int:
        observed["active_thread_runtime"] = self.app_runtime.active_thread_runtime
        return 0

    monkeypatch.setattr(PyCodexTextualApp, "run", fake_run)

    assert tui_module.run_tui(active_thread_runtime=runtime, stderr=io.StringIO()) == 0
    assert observed["active_thread_runtime"] is runtime


def test_textual_product_entry_prints_rust_exit_summary(monkeypatch, tmp_path: Path) -> None:
    # Rust-derived contract:
    # - codex-tui returns AppExitInfo after the app exits.
    # - codex-cli::format_exit_messages prints token usage before the resume
    #   hint for resumable threads.
    thread_id = "123e4567-e89b-12d3-a456-426614174000"
    rollout_path = tmp_path / "rollout.jsonl"
    rollout_path.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    runtime = _FakeActiveThreadRuntime([])
    runtime.thread_id = thread_id
    runtime.rollout_path = rollout_path
    stdout = io.StringIO()

    def fake_run(self: PyCodexTextualApp) -> int:
        self.app_runtime.chat_widget.set_token_info(
            TokenUsageInfo(
                total_token_usage=TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3),
                last_token_usage=TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3),
                model_context_window=200000,
            )
        )
        return 0

    monkeypatch.setattr(PyCodexTextualApp, "run", fake_run)

    assert run_textual_tui(active_thread_runtime=runtime, stdout=stdout) == 0
    output = stdout.getvalue()
    assert "Token usage: total=3 input=1 output=2" in output
    assert f"To continue this session, run codex resume {thread_id}" in output
    assert output.index("Token usage: total=3 input=1 output=2") < output.index("To continue this session")


def test_textual_product_entry_exit_resume_hint_uses_thread_name(monkeypatch, tmp_path: Path) -> None:
    # Rust-derived contract:
    # - codex-tui returns the active thread name in AppExitInfo.
    # - codex-cli::format_exit_messages uses the resume picker wording when a
    #   resumable thread has a human-readable name.
    thread_id = "123e4567-e89b-12d3-a456-426614174001"
    rollout_path = tmp_path / "rollout.jsonl"
    rollout_path.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    runtime = _FakeActiveThreadRuntime([])
    runtime.thread_id = thread_id
    runtime.rollout_path = rollout_path
    stdout = io.StringIO()

    def fake_run(self: PyCodexTextualApp) -> int:
        self.app_runtime.handle_notification(
            ServerNotification("ThreadNameUpdated", {"thread_id": thread_id, "thread_name": "my-thread"})
        )
        return 0

    monkeypatch.setattr(PyCodexTextualApp, "run", fake_run)

    assert run_textual_tui(active_thread_runtime=runtime, stdout=stdout) == 0
    output = stdout.getvalue()
    assert f"To continue this session, run codex resume, then select my-thread ({thread_id})" in output


def test_textual_product_entry_suppresses_resume_hint_without_resumable_rollout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # Rust-derived contract:
    # - codex-tui::app::resumable_thread returns None unless the rollout path is
    #   present and non-empty.
    # - codex-cli::format_exit_messages omits the resume hint in that case.
    thread_id = "123e4567-e89b-12d3-a456-426614174002"
    empty_rollout_path = tmp_path / "empty.jsonl"
    empty_rollout_path.write_text("", encoding="utf-8")
    runtime = _FakeActiveThreadRuntime([])
    runtime.thread_id = thread_id
    runtime.rollout_path = empty_rollout_path
    stdout = io.StringIO()

    monkeypatch.setattr(PyCodexTextualApp, "run", lambda self: 0)

    assert run_textual_tui(active_thread_runtime=runtime, stdout=stdout) == 0
    output = stdout.getvalue()
    assert "To continue this session" not in output


def test_textual_product_entry_waits_for_core_rollout_before_resume_hint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # Rust-derived contract:
    # - codex-tui builds AppExitInfo after app exit.
    # - codex-cli only prints the resume hint when the active rollout is
    #   resumable, so Python must wait for the core worker's post-turn rollout
    #   materialization before formatting exit messages.
    thread_id = "123e4567-e89b-12d3-a456-426614174003"
    rollout_path = tmp_path / "late-rollout.jsonl"
    runtime = _WaitingRolloutRuntime([], rollout_path)
    runtime.thread_id = thread_id
    runtime.rollout_path = None
    stdout = io.StringIO()
    monkeypatch.setenv("PYCODEX_TUI_EXIT_SUMMARY_ROLLOUT_WAIT_SECONDS", "0.25")
    monkeypatch.setattr(PyCodexTextualApp, "run", lambda self: 0)

    assert run_textual_tui(active_thread_runtime=runtime, stdout=stdout) == 0

    output = stdout.getvalue()
    assert runtime.wait_seconds == [0.25]
    assert rollout_path.is_file()
    assert f"To continue this session, run codex resume {thread_id}" in output


def test_textual_thread_identity_prefers_model_client_thread_id_over_session_id() -> None:
    # Rust-derived contract:
    # - codex-tui::app::AppExitInfo carries the active thread id used for
    #   resumable session summaries.
    # - In the core-backed Python adapter, the model-client thread id is the
    #   resumable rollout identity; session_id is a different transport/session
    #   identity and must not replace it.
    thread_id = "123e4567-e89b-12d3-a456-426614174004"
    session_id = "123e4567-e89b-12d3-a456-426614174999"
    runtime = _FakeActiveThreadRuntime([])
    runtime.thread_id = None
    runtime.model_client = SimpleNamespace(state=SimpleNamespace(thread_id=thread_id, session_id=session_id))
    app_runtime = TuiAppRuntime(runtime)

    configure_app_runtime_thread_identity(app_runtime, runtime)

    assert app_runtime.thread_id == thread_id
    assert app_runtime.routing_state.active_thread_id == thread_id
    assert session_id not in {app_runtime.thread_id, app_runtime.routing_state.active_thread_id}


def test_textual_quit_uses_shutdown_first_boundary() -> None:
    # Rust-derived contract:
    # - codex-tui::app::event_dispatch routes user exits through
    #   ExitMode::ShutdownFirst.
    # - bottom_pane::chat_composer shows the shutdown-in-progress surface before
    #   exit rather than silently dropping the active thread.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/quit"
            await pilot.press("enter")
            await pilot.pause(0.05)
            status = str(app.query_one("#status-line", Static).renderable)
            assert "Shutting down..." in status

    asyncio.run(scenario())

    assert runtime.shutdowns == ["primary"]
    assert runtime.submitted == []


def test_textual_logout_dispatches_logout_and_shutdown_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /logout to AppEvent::Logout.
    # - app::event_dispatch handles the successful branch with ShutdownFirst.
    # Rust test: chatwidget/tests/slash_commands.rs::slash_logout_requests_app_server_logout.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/logout"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.shutdowns == ["primary"]
    assert app_runtime.event_dispatch_plans[-1].action == "logout_account_then_shutdown"


def test_textual_startup_surface_uses_rust_session_header_footer_and_notices() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::constructor installs
    #   placeholder_session_header_cell with DEFAULT_MODEL_DISPLAY_NAME
    #   "loading" before SessionConfigured replaces it.
    # - codex-tui::bottom_pane::footer shows the idle status/footer surface
    #   rather than a Python-only "status: Ready" line.
    # - history_cell::session::new_session_info suppresses tooltip cells for
    #   the first event; startup warnings still project through the app surface.
    runtime = _FakeActiveThreadRuntime([])
    cwd = Path("C:/repo")
    runtime.cwd = cwd
    runtime.session_config = SimpleNamespace(
        cwd=cwd,
        model="gpt-startup",
        model_reasoning_effort="high",
        model_details=("high", "fast"),
        model_context_window=200000,
        startup_tooltip_override="Try **/status** for session details.",
        startup_warnings=[
            "Heads up, you have less than 25% of your 5h limit left.",
            "MCP startup incomplete (failed: codex_apps)",
        ],
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))
    startup_footer = app._startup_status_line_text()
    assert " · " in startup_footer
    assert " 路 " not in startup_footer
    assert " �� " not in startup_footer

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            await pilot.pause(0.05)
            header = str(app.query_one("#session-header", Static).renderable)
            footer = str(app.query_one("#status-line", Static).renderable)
            prompt = str(app.query_one("#composer-prompt", Static).renderable)
            assert ">_ OpenAI Codex" in header
            assert "model:" in header
            assert "loading" in header
            assert "gpt-startup high fast" not in header
            assert "/model to change" in header
            assert "directory:" in header
            assert "permissions:" not in header
            assert prompt.startswith("› ")
            assert prompt.removeprefix("› ") in PLACEHOLDERS
            assert "gpt-startup high fast" in footer
            assert "codex-python" in footer
            assert "Context 100% left" not in footer
            assert "status: Ready" not in footer
            assert "Tip: Try /status for session details." not in "\n".join(
                block.text for block in app._blocks if block.label == "status"
            )
            app._mark_session_header_configured()
            app._append_startup_notices()
            configured_header = str(app.query_one("#session-header", Static).renderable)
            assert configured_header.startswith("╭")
            assert "│ >_ OpenAI Codex" in configured_header
            assert "gpt-startup high" in configured_header
            assert "fast" in configured_header
            assert "loading" not in configured_header

    asyncio.run(scenario())

    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Tip: Try /status for session details." in notices
    assert "Heads up, you have less than 25% of your 5h limit left." in notices
    assert "MCP startup incomplete (failed: codex_apps)" in notices


def test_textual_startup_header_indicates_yolo_permissions_like_rust() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::placeholder_session_header_cell uses
    #   DEFAULT_MODEL_DISPLAY_NAME "loading" while preserving yolo mode.
    # - codex-tui::history_cell::session::SessionHeaderHistoryCell renders
    #   "permissions: YOLO mode" when has_yolo_permissions is true.
    # - Rust tests: session_header_indicates_yolo_mode and
    #   yolo_mode_includes_managed_full_access_profiles.
    runtime = _FakeActiveThreadRuntime([])
    cwd = Path("C:/repo")
    runtime.cwd = cwd
    runtime.session_config = SimpleNamespace(
        cwd=cwd,
        model="gpt-yolo",
        model_reasoning_effort="high",
        approval_policy=AskForApproval.NEVER,
        permission_profile=TuiPermissionProfile.disabled(),
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)):
            header = str(app.query_one("#session-header", Static).renderable)
            assert "model:       loading" in header
            assert "directory:   " in header
            assert "permissions: YOLO mode" in header
            app._mark_session_header_configured()
            configured_header = str(app.query_one("#session-header", Static).renderable)
            assert "model:       gpt-yolo high" in configured_header
            assert "permissions: YOLO mode" in configured_header

    asyncio.run(scenario())


def test_textual_session_header_renders_model_literals_like_rust() -> None:
    # Rust-derived contract:
    # - codex-tui::history_cell::session::SessionHeaderHistoryCell::display_lines
    #   renders the model string as a Ratatui Span, so characters like brackets
    #   are literal text rather than markup.
    runtime = _FakeActiveThreadRuntime([])
    cwd = Path("C:/repo")
    runtime.cwd = cwd
    runtime.session_config = SimpleNamespace(
        cwd=cwd,
        model="gpt-[literal]",
        model_reasoning_effort="high",
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)):
            app._mark_session_header_configured()
            configured_header = str(app.query_one("#session-header", Static).renderable)
            assert "gpt-[literal] high" in configured_header

    asyncio.run(scenario())


def test_textual_default_status_line_items_match_rust_chatwidget_default() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::DEFAULT_STATUS_LINE_ITEMS is
    #   ["model-with-reasoning", "current-dir"].
    # - Textual must not add local-only defaults such as context-remaining;
    #   extra status items are available only through explicit configuration.
    runtime = _FakeActiveThreadRuntime([])
    assert _runtime_status_line_item_ids(TuiAppRuntime(runtime)) == tuple(DEFAULT_STATUS_LINE_ITEMS)


def test_textual_idle_footer_includes_active_agent_label_like_rust() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::footer::passive_footer_status_line appends
    #   FooterProps.active_agent_label to the passive status line using ` · `.
    # - Rust snapshots: footer_active_agent_label and
    #   footer_status_line_with_active_agent_label.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config = SimpleNamespace(model="gpt-agent", model_reasoning_effort="high", cwd=Path("C:/repo"))
    app_runtime = TuiAppRuntime(runtime)
    app_runtime.chat_widget.set_active_agent_label("Robie [explorer]")
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            await pilot.pause(0.05)
            footer = str(app.query_one("#status-line", Static).renderable)
            assert "gpt-agent high" in footer
            assert " · Robie [explorer]" in footer

    asyncio.run(scenario())


def test_textual_startup_surface_applies_configured_status_line_after_mount() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::status_surfaces parses configured status-line
    #   items during startup.
    # - codex-tui::bottom_pane::footer renders the configured passive footer
    #   once the session/model snapshot reaches the UI, so a configured
    #   `context-used` row must not remain on the initial `loading` footer.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config = SimpleNamespace(tui_status_line=["context-used"])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            footer = str(app.query_one("#status-line", Static).renderable)
            assert "Context 0% used" in footer
            assert "loading" not in footer

    asyncio.run(scenario())


def test_textual_startup_prompt_uses_runtime_chatwidget_placeholder() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::constructor selects ``normal_placeholder_text``
    #   from ``PLACEHOLDERS``.
    # - codex-tui::bottom_pane::ChatComposer renders that runtime placeholder
    #   in the startup composer instead of a separate hard-coded string.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app_runtime.chat_widget.normal_placeholder_text = "Explain this codebase"
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            prompt = str(app.query_one("#composer-prompt", Static).renderable)
            assert prompt == "› Explain this codebase"
            assert "鈥?" not in prompt

    asyncio.run(scenario())


def test_textual_product_loop_drains_startup_app_server_mcp_events() -> None:
    # Rust-derived contract:
    # - codex-tui::app::App::run selects over app-server events before and
    #   alongside terminal/composer input.
    # - codex-tui::app::app_server_events refreshes expected MCP servers before
    #   forwarding McpServerStatusUpdated to chatwidget.
    # - chatwidget/tests/mcp_startup.rs::app_server_mcp_startup_failure_renders_warning_history
    #   proves failed startup statuses produce both the per-server warning and
    #   final "MCP startup incomplete" summary.
    runtime = _FakeAppServerRuntime(
        [],
        [
            {
                "kind": "ServerNotification",
                "notification": ServerNotification(
                    "McpServerStatusUpdated",
                    {"name": "alpha", "status": "Starting"},
                ),
            },
            {
                "kind": "ServerNotification",
                "notification": ServerNotification(
                    "McpServerStatusUpdated",
                    {
                        "name": "alpha",
                        "status": "Failed",
                        "error": "MCP client for `alpha` failed to start: handshake failed",
                    },
                ),
            },
        ],
    )
    runtime.session_config = SimpleNamespace(
        model="gpt-test",
        cwd=".",
        mcp_servers={"alpha": SimpleNamespace(enabled=True)},
        show_tooltips=False,
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.2)

    asyncio.run(scenario())

    text = "\n".join(f"{block.label}\n{block.text}" for block in app._blocks)
    assert "Booting MCP server: alpha" in text
    assert "MCP client for `alpha` failed to start: handshake failed" in text
    assert "MCP startup incomplete (failed: alpha)" in text
    assert text.count("MCP client for `alpha` failed to start: handshake failed") == 1
    assert text.count("MCP startup incomplete (failed: alpha)") == 1


def test_textual_startup_surface_uses_default_tooltip_unless_disabled() -> None:
    # Rust-derived contract:
    # - codex-tui::history_cell::session suppresses startup tooltips for the
    #   first session event, then adds them only for non-first session info.
    # - codex-tui::tooltips defines the Windows/macOS Codex App tooltip used by
    #   common startup sessions.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def default_scenario() -> None:
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause(0.05)
            notices = [block.text for block in app._blocks if block.label == "status"]
            assert not any("Try the Codex App." in notice for notice in notices)
            app._mark_session_header_configured()
            app._append_startup_notices()
            notices = [block.text for block in app._blocks if block.label == "status"]
            assert any("Try the Codex App." in notice for notice in notices)

    asyncio.run(default_scenario())

    disabled_runtime = _FakeActiveThreadRuntime([])
    disabled_runtime.session_config = SimpleNamespace(show_tooltips=False)
    disabled_app = PyCodexTextualApp(TuiAppRuntime(disabled_runtime))

    async def disabled_scenario() -> None:
        async with disabled_app.run_test(size=(100, 24)) as pilot:
            await pilot.pause(0.05)

    asyncio.run(disabled_scenario())

    disabled_notices = [block.text for block in disabled_app._blocks if block.label == "status"]
    assert not any("Try the Codex App." in notice for notice in disabled_notices)


def test_textual_status_line_invalid_items_warn_once() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::status_surfaces::status_line_items_with_invalids
    #   parses known items and collects unknown ids with insertion-order
    #   deduplication.
    # - codex-tui::chatwidget::status_surfaces::warn_invalid_status_line_items_once
    #   emits exactly one warning history cell after a thread id exists.
    # - chatwidget/tests/status_and_layout.rs::status_line_invalid_items_warn_once
    #   proves duplicate invalid ids are named once and the warning is not
    #   emitted on the next status-line refresh.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config = SimpleNamespace(
        model="gpt-invalid-status-model",
        tui_status_line=[
            "model-name",
            "bogus_item",
            "context-used",
            "bogus_item",
        ],
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            footer = str(app.query_one("#status-line", Static).renderable)
            text = "\n".join(f"{block.label}\n{block.text}" for block in app._blocks)
            warning = 'Ignored invalid status line item: "bogus_item".'

            assert "gpt-invalid-status-model" in footer
            assert "Context 0% used" in footer
            assert text.count(warning) == 1

            app._set_status("Ready")
            await pilot.pause(0.05)
            text = "\n".join(f"{block.label}\n{block.text}" for block in app._blocks)
            assert text.count(warning) == 1

    asyncio.run(scenario())


def test_textual_active_status_tick_preserves_rust_interrupt_shape() -> None:
    # Rust source/snapshot contract:
    # - codex-tui::status_indicator_widget::StatusIndicatorWidget renders
    #   active turn status as "Working (Ns • esc to interrupt)".
    # - chatwidget snapshots such as `preamble_keeps_working_status` and
    #   `status_widget_active` prove custom headers keep the same elapsed /
    #   interrupt suffix rather than becoming a plain `status:` footer line.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._set_active_status("Working", elapsed_seconds=5)
            await pilot.pause(0.05)
            footer = str(app.query_one("#status-line", Static).renderable)
            assert "Working (5s" in footer
            assert "esc to interrupt" in footer
            assert "status: Working 5s" not in footer

            app._set_active_status("Analyzing", elapsed_seconds=12)
            await pilot.pause(0.05)
            footer = str(app.query_one("#status-line", Static).renderable)
            assert "Analyzing (12s" in footer
            assert "esc to interrupt" in footer
            assert "status: Analyzing 12s" not in footer

    asyncio.run(scenario())


def test_textual_terminal_title_follows_default_activity_project_lifecycle(tmp_path: Path) -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::status_surfaces defaults terminal title items to
    #   activity + project-name.
    # - idle omits the activity segment, active turns include it, Ready restores
    #   the project title, and app drop clears the managed title.
    runtime = _FakeActiveThreadRuntime([])
    runtime.cwd = tmp_path / "project-alpha"
    runtime.session_config.cwd = runtime.cwd
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            assert app.title == "project-alpha"

            app._set_status("Working")
            await pilot.pause(0.05)
            assert app.title != "project-alpha"
            assert app.title.endswith(" project-alpha")

            app._set_status("Ready")
            await pilot.pause(0.05)
            assert app.title == "project-alpha"

    asyncio.run(scenario())

    assert app.title == ""


def test_textual_terminal_title_uses_rust_activity_separator_rule(tmp_path: Path) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::title_setup::TerminalTitleItem::separator_from_previous
    #   uses plain spaces when either adjacent title item is the activity
    #   spinner, so `project-name, activity, run-state` renders as
    #   `project <activity> Working` rather than `project | <activity> | Working`.
    runtime = _FakeActiveThreadRuntime([])
    runtime.cwd = tmp_path / "project-alpha"
    runtime.session_config = SimpleNamespace(
        cwd=runtime.cwd,
        model="gpt-test",
        tui_terminal_title=["project-name", "activity", "run-state"],
    )
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._set_status("Working")
            await pilot.pause(0.05)
            activity = terminal_title_spinner_frame_at(timedelta(milliseconds=0))
            assert app.title == f"project-alpha {activity} Working"
            assert " | " not in app.title

    asyncio.run(scenario())


def test_textual_terminal_title_truncates_project_name_like_status_surfaces(tmp_path: Path) -> None:
    # Rust-derived contract:
    # chatwidget::status_surfaces::terminal_title_project_name truncates the
    # project-name title segment to 24 visible characters.
    runtime = _FakeActiveThreadRuntime([])
    runtime.cwd = tmp_path / "project-name-that-is-much-too-long"
    runtime.session_config.cwd = runtime.cwd
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            assert app.title == "project-name-that-is-..."
            assert len(app.title) == 24

    asyncio.run(scenario())


def test_textual_terminal_title_uses_configured_model_item_and_refreshes() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::status_surfaces::configured_terminal_title_items
    #   reads config.tui_terminal_title.
    # - status_and_layout.rs::terminal_title_model_updates_on_model_change_without_manual_refresh
    #   proves `["model"]` renders the model and updates when model changes.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config = SimpleNamespace(model="gpt-title-one", tui_terminal_title=["model"])
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            assert app.title == "gpt-title-one"

            runtime.session_config.model = "gpt-title-two"
            app._set_status("Ready")
            await pilot.pause(0.05)
            assert app.title == "gpt-title-two"

    asyncio.run(scenario())


def test_textual_terminal_title_invalid_items_warn_once() -> None:
    # Rust source contract:
    # - codex-tui::chatwidget::status_surfaces::terminal_title_items_with_invalids
    #   parses known items and deduplicates invalid ids.
    # - warn_invalid_terminal_title_items_once emits the warning once after the
    #   TUI has a thread id. This is the terminal-title twin of the Rust-tested
    #   status_line_invalid_items_warn_once contract.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config = SimpleNamespace(
        model="gpt-title",
        tui_terminal_title=["model", "bad_title", "bad_title"],
    )
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            assert app.title == "gpt-title"
            text = "\n".join(f"{block.label}\n{block.text}" for block in app._blocks)
            warning = 'Ignored invalid terminal title item: "bad_title".'
            assert text.count(warning) == 1

            app._set_status("Ready")
            await pilot.pause(0.05)
            text = "\n".join(f"{block.label}\n{block.text}" for block in app._blocks)
            assert text.count(warning) == 1

    asyncio.run(scenario())


def test_textual_runtime_submits_prompt_and_streams_transcript() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer submits a UserTurn.
    # - codex-tui::app routes it to the active thread.
    # - codex-tui::chatwidget::protocol consumes ReasoningSummaryTextDelta,
    #   AgentMessageDelta, and TurnCompleted without duplicating final text.
    events = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification("ReasoningSummaryTextDelta", {"delta": "**Inspecting** files"}),
        ServerNotification("AgentMessageDelta", {"delta": "hello"}),
        ServerNotification("AgentMessageDelta", {"delta": " world"}),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events)
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "hello?"
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if not app._busy:
                    break
            status = app.query_one("#status-line", Static).renderable
            assert "gpt-test high" in str(status)

    asyncio.run(scenario())

    assert runtime.submitted
    assert runtime.submitted[0][0] == "primary"
    assert runtime.submitted[0][1].kind == "UserTurn"
    blocks = [(block.label, block.text) for block in app._blocks]
    assert ("you", "hello?") in blocks
    reasoning_blocks = [text for label, text in blocks if label == "reasoning"]
    assert any("files" in text for text in reasoning_blocks)
    assert all("**Inspecting**" not in text for text in reasoning_blocks)
    assert ("codex", "hello world") in blocks
    assert blocks.count(("codex", "hello world")) == 1


def test_textual_runtime_renders_done_only_agent_item_without_duplicate_delta() -> None:
    # Rust source/test contract:
    # - codex-rs/core/src/session/turn.rs::ResponseEvent::OutputItemDone
    #   completes assistant messages through TurnItem::AgentMessage.
    # - codex-tui::chatwidget::protocol handles ItemCompleted by routing the
    #   AgentMessage item into transcript/history rendering.
    # Textual keeps a local transcript projection, so completed AgentMessage
    # items must update that projection even when no AgentMessageDelta arrived.
    events = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification(
            "ItemCompleted",
            {
                "turn_id": "t1",
                "item": {
                    "kind": "AgentMessage",
                    "id": "msg-1",
                    "content": [{"type": "Text", "text": "done-only answer"}],
                },
            },
        ),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events)
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "hello?"
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if not app._busy:
                    break

    asyncio.run(scenario())

    blocks = [(block.label, block.text) for block in app._blocks]
    assert ("codex", "done-only answer") in blocks
    assert blocks.count(("codex", "done-only answer")) == 1


def test_textual_runtime_handles_local_slash_commands_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui slash commands with local UI/runtime effects are intercepted
    #   before AppCommand::UserTurn submission.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/model gpt-local"
            await pilot.press("enter")
            await pilot.pause(0.05)
            composer.text = "/status"
            await pilot.press("enter")
            await pilot.pause(0.05)
            composer.text = "/raw on"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.session_config.model == "gpt-local"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any("Model set to gpt-local" in notice for notice in notices)
    assert any("/status" in notice and "OpenAI Codex" in notice for notice in notices)
    assert any("Raw output mode on" in notice for notice in notices)


def test_textual_runtime_consolidated_local_slash_commands_do_not_submit_user_turn() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch keeps local commands such as
    #   /status, /raw, /help, /transcript, and /mention out of
    #   AppCommand::UserTurn submission.
    # - Rust tests in chatwidget/tests/slash_commands.rs and
    #   status_command_tests.rs cover the individual commands; this Textual
    #   product-path regression keeps their composition from drifting.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(110, 34)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            for command in ("/status", "/raw on", "/raw maybe", "/help", "/mention"):
                composer.text = command
                await pilot.press("enter")
                await pilot.pause(0.05)
            assert composer.text == "@"
            composer.text = "/transcript"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert "T R A N S C R I P T" in str(popup.renderable)

    asyncio.run(scenario())

    assert not any(op.kind == "UserTurn" for _thread_id, op in runtime.submitted)
    notices = _non_startup_status_notices(app)
    notice_text = "\n".join(notices)
    assert "/status" in notice_text and "OpenAI Codex" in notice_text
    assert "Raw output mode on" in notice_text
    assert "Usage: /raw [on|off]" in notice_text
    assert "Available: /model [name]" in notice_text
    assert not any(block.label == "you" and block.text.startswith("/") for block in app._blocks)


def test_textual_keymap_command_opens_picker_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /keymap to
    #   open_keymap_picker(), not AppCommand::UserTurn.
    # - keymap_setup::picker builds a tabbed SelectionViewParams surface with
    #   Rust rows such as Open Transcript, Copy, and Submit.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/keymap"
            await pilot.press("enter")
            await pilot.pause(0.05)

            rendered = str(popup.renderable)
            assert app._active_selection is not None
            assert app._active_selection.kind == "keymap"
            assert "Keymap" in rendered
            assert "[All]" in rendered
            assert "107 actions" in rendered
            assert "Open Transcript" in rendered
            assert "Copy" in rendered
            assert "Submit" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_keymap_tabs_switch_to_debug_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::keymap_setup::picker appends a Debug tab after the action
    #   tabs, and list_selection_view Tab/BackTab changes the active tab before
    #   Enter accepts the visible row.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/keymap"
            await pilot.press("enter")
            await pilot.pause(0.05)

            await pilot.press("shift+tab")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "[Debug]" in rendered
            assert "Inspect keypresses" in rendered

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert app._active_selection.kind == "keymap-debug"
            assert "Keypress Inspector" in str(popup.renderable)

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_keymap_search_filters_visible_rows_without_user_turn() -> None:
    # Rust-derived contract:
    # - keymap_setup::picker marks the keymap picker searchable and each row
    #   carries search_value text; list_selection_view filters visible rows
    #   before Enter accepts the selected action.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/keymap"
            await pilot.press("enter")
            await pilot.pause(0.05)

            await pilot.press("d")
            await pilot.press("e")
            await pilot.press("n")
            await pilot.press("y")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "search: deny" in rendered
            assert "Deny" in rendered
            assert "Open Transcript" not in rendered

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert app._active_selection.kind == "keymap-action-menu"
            action_menu = str(popup.renderable)
            assert "Deny / approval" in action_menu
            assert "search: deny" not in action_menu

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_keymap_selection_opens_action_menu_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::keymap_setup::picker emits OpenKeymapActionMenu for a row.
    # - chatwidget::keymap_picker::open_keymap_action_menu renders the
    #   action-specific Edit Shortcut menu instead of closing /keymap.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/keymap"
            await pilot.press("enter")
            await pilot.pause(0.05)

            await pilot.press("enter")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert app._active_selection is not None
            assert app._active_selection.kind == "keymap-action-menu"
            assert "Edit Shortcut" in rendered
            assert "Open Transcript" in rendered
            assert "Replace binding" in rendered
            assert "Add alternate binding" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_keymap_capture_persists_updates_runtime_and_returns_to_selected_row(tmp_path: Path) -> None:
    # Rust-derived contract:
    # - app::event_dispatch::apply_keymap_capture calls keymap_with_edit,
    #   persists keymap_bindings_edit through ConfigEditsBuilder, refreshes
    #   RuntimeKeymap, applies the update to ChatWidget, returns to the root
    #   picker with the edited action selected, and reports the remap message.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.codex_home = tmp_path
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/keymap"
            await pilot.press("enter")
            await pilot.pause(0.05)

            await pilot.press("enter")
            await pilot.pause(0.05)
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert app._active_selection.kind == "keymap-capture"
            assert "Remap Shortcut" in str(popup.renderable)

            await pilot.press("ctrl+x")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert app._active_selection is not None
            assert app._active_selection.kind == "keymap"
            assert "Open Transcript" in rendered
            assert "Customized (1)" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.session_config.tui_keymap["global"]["open_transcript"] == "ctrl-x"
    assert read_toml_mapping(tmp_path / "config.toml") == {
        "tui": {"keymap": {"global": {"open_transcript": "ctrl-x"}}}
    }
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Remapped `global.open_transcript` to `ctrl-x`." in notices


def test_textual_keymap_clear_persists_and_removes_custom_binding(tmp_path: Path) -> None:
    # Rust-derived contract:
    # - app::event_dispatch::apply_keymap_clear persists
    #   keymap_binding_clear_edit before refreshing RuntimeKeymap and returning
    #   to the root picker.
    (tmp_path / "config.toml").write_text(
        "[tui.keymap.global]\nopen_transcript = \"ctrl-x\"\n",
        encoding="utf-8",
    )
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.codex_home = tmp_path
    runtime.session_config.tui_keymap = {"global": {"open_transcript": "ctrl-x"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/keymap"
            await pilot.press("enter")
            await pilot.pause(0.05)

            await pilot.press("enter")
            await pilot.pause(0.05)
            await pilot.press("down")
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert app._active_selection is not None
            assert app._active_selection.kind == "keymap"
            assert "Open Transcript" in rendered
            assert "Customized (0)" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert read_toml_mapping(tmp_path / "config.toml") == {"tui": {"keymap": {"global": {}}}}
    assert runtime.session_config.tui_keymap == {"global": {}}
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Removed custom shortcut for `global.open_transcript`." in notices


def test_textual_keymap_capture_failure_does_not_update_runtime(tmp_path: Path) -> None:
    # Rust-derived contract:
    # - app::event_dispatch::apply_keymap_capture reports
    #   "Failed to save shortcut: ..." and does not update the live RuntimeKeymap
    #   when ConfigEditsBuilder::apply fails.
    bad_config_path = tmp_path / "as-directory"
    bad_config_path.mkdir()
    layer_stack = SimpleNamespace(get_user_config_file=lambda: bad_config_path)
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.config_layer_stack = layer_stack
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/keymap"
            await pilot.press("enter")
            await pilot.pause(0.05)

            await pilot.press("enter")
            await pilot.pause(0.05)
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert app._active_selection.kind == "keymap-capture"

            await pilot.press("ctrl+x")
            await pilot.pause(0.05)
            assert "Remapped `global.open_transcript` to `ctrl-x`." not in [
                block.text for block in app._blocks if block.label == "status"
            ]

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert not hasattr(runtime.session_config, "tui_keymap")
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any(notice.startswith("Failed to save shortcut:") for notice in notices)


def test_textual_keymap_debug_inspects_shortcut_without_user_turn() -> None:
    # Rust-derived contract:
    # - chatwidget/tests/slash_commands.rs::slash_keymap_debug_opens_keypress_inspector
    #   opens a keypress inspector and Ctrl-O reports global.copy without
    #   running the copy command or sending a core op.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/keymap debug"
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert "Keypress Inspector" in str(popup.renderable)
            assert "Waiting for a keypress" in str(popup.renderable)

            await pilot.press("ctrl+o")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "ctrl-o" in rendered
            assert "global.copy (Copy)" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert _non_startup_status_notices(app) == []


def test_textual_keymap_invalid_args_show_usage_without_user_turn() -> None:
    # Rust-derived contract:
    # - chatwidget/tests/slash_commands.rs::slash_keymap_invalid_args_show_usage
    #   renders Usage: /keymap [debug] and does not send a core op.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/keymap nope"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Usage: /keymap [debug]" in notices


def test_textual_ps_command_renders_background_terminal_summary_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /ps to
    #   chatwidget::add_ps_output, not AppCommand::UserTurn.
    # - codex-tui::history_cell::exec owns the visible background terminal
    #   summary shape.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app_runtime.chat_widget.command_lifecycle.unified_exec_processes.append(
        SimpleNamespace(command_display="python -m http.server", recent_chunks=["Serving HTTP"])
    )
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/ps"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    status_blocks = [block.text for block in app._blocks if block.label == "status"]
    assert any("/ps" in block and "Background terminals" in block for block in status_blocks)
    assert any("python -m http.server" in block and "Serving HTTP" in block for block in status_blocks)


def test_textual_stop_command_submits_background_terminal_cleanup_without_user_turn() -> None:
    # Rust-derived contract:
    # - chatwidget/tests/slash_commands.rs::slash_stop_submits_background_terminal_cleanup
    #   submits Op::CleanBackgroundTerminals and inserts the confirmation
    #   message "Stopping all background terminals."
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app_runtime.chat_widget.command_lifecycle.unified_exec_processes.append(
        SimpleNamespace(command_display="python -m http.server", recent_chunks=["Serving HTTP"])
    )
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/stop"
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    assert runtime.submitted[0][1].kind == "CleanBackgroundTerminals"
    assert app_runtime.chat_widget.command_lifecycle.unified_exec_processes == []
    assert not any(op.kind == "UserTurn" for _thread_id, op in runtime.submitted)
    status_blocks = [block.text for block in app._blocks if block.label == "status"]
    assert any("Stopping all background terminals." in block for block in status_blocks)


def test_textual_vim_command_toggles_composer_mode_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /vim to
    #   ChatWidget::toggle_vim_mode_and_notify.
    # - chatwidget.rs::toggle_vim_mode_and_notify inserts
    #   "Vim mode enabled." / "Vim mode disabled." and does not submit a
    #   model turn.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/vim"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert getattr(app_runtime.chat_widget, "vim_enabled", False) is True

            composer.text = "/vim"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert getattr(app_runtime.chat_widget, "vim_enabled", True) is False

    asyncio.run(scenario())

    assert runtime.submitted == []
    status_blocks = [block.text for block in app._blocks if block.label == "status"]
    assert "Vim mode enabled." in status_blocks
    assert "Vim mode disabled." in status_blocks


def test_textual_vim_mode_keymap_remap_toggles_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::app::input checks keymap.app.toggle_vim_mode before the key
    #   reaches the composer and calls ChatWidget::toggle_vim_mode_and_notify.
    # - keymap.rs defaults leave global.toggle_vim_mode unbound, but configured
    #   bindings replace that empty default.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("f12")
            await pilot.pause(0.05)
            assert getattr(app_runtime.chat_widget, "vim_enabled", False) is False

            runtime.session_config.tui_keymap = {"global": {"toggle_vim_mode": "f12"}}
            await pilot.press("f12")
            await pilot.pause(0.05)
            assert getattr(app_runtime.chat_widget, "vim_enabled", False) is True

            await pilot.press("f12")
            await pilot.pause(0.05)
            assert getattr(app_runtime.chat_widget, "vim_enabled", True) is False

    asyncio.run(scenario())

    assert runtime.submitted == []
    status_blocks = [block.text for block in app._blocks if block.label == "status"]
    assert "Vim mode enabled." in status_blocks
    assert "Vim mode disabled." in status_blocks


def test_textual_status_command_renders_status_card_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /status to a local
    #   status::card history cell, not AppCommand::UserTurn.
    # - codex-tui::status::card::new_status_output_with_rate_limits_handle
    #   owns the visible status card shape.
    runtime = _FakeActiveThreadRuntime([])
    cwd = Path("C:/repo")
    runtime.session_config = SimpleNamespace(
        cwd=cwd,
        model="gpt-status-model",
        active_permission_profile="workspace-write",
        permission_profile="enabled",
        approval_policy=AskForApproval.ON_REQUEST,
        approvals_reviewer="auto-review",
        sandbox="workspace",
        workspace_roots=[cwd, cwd / "extra"],
        agents_summary="AGENTS.md",
    )
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/status"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    status_blocks = [block.text for block in app._blocks if block.label == "status"]
    status_text = "\n".join(status_blocks)
    assert runtime.submitted == []
    assert "/status" in status_text
    assert ">_ OpenAI Codex" in status_text
    assert "Model" in status_text
    assert "gpt-status-model" in status_text
    assert "Directory" in status_text
    assert "C:\\repo" in status_text or "C:/repo" in status_text
    assert "Permissions" in status_text
    assert "Workspace" in status_text
    assert "auto-review" in status_text
    assert "Agents.md" in status_text


def test_textual_status_command_displays_approval_enum_like_rust() -> None:
    # Rust-derived contract:
    # - codex-tui::status::card::status_permissions_label displays
    #   AskForApproval through its kebab-case Display value.
    runtime = _FakeActiveThreadRuntime([])
    cwd = Path("C:/repo")
    runtime.session_config = SimpleNamespace(
        cwd=cwd,
        model="gpt-status-model",
        active_permission_profile="read-only",
        permission_profile="enabled",
        approval_policy=AskForApproval.NEVER,
        sandbox="read-only",
        workspace_roots=[cwd],
    )
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/status"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    status_text = "\n".join(block.text for block in app._blocks if block.label == "status")
    assert "Read Only (never)" in status_text
    assert "AskForApproval.NEVER" not in status_text


def test_textual_clear_command_dispatches_clear_ui_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /clear to AppEvent::ClearUi
    #   while idle, not AppCommand::UserTurn.
    # - Rust test: chatwidget/tests/slash_commands.rs::slash_clear_requests_ui_clear_when_idle.
    events = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification("AgentMessageDelta", {"delta": "old answer"}),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events)
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "hello?"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if any(block.label == "codex" and block.text == "old answer" for block in app._blocks):
                    break
            assert any(block.label == "codex" and block.text == "old answer" for block in app._blocks)
            composer.text = "/clear"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    assert runtime.submitted[0][1].kind == "UserTurn"
    assert app_runtime.event_dispatch_plans[-1].action == "clear_ui_and_start_fresh_session"
    assert not any(block.label == "codex" and block.text == "old answer" for block in app._blocks)
    assert not any(str(block.text).startswith(_STARTUP_TIP_PREFIX) for block in app._blocks)


def test_textual_new_command_dispatches_new_session_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch maps /new to AppEvent::NewSession,
    # and app::event_dispatch starts a fresh session instead of submitting
    # the slash command as AppCommand::UserTurn.
    events = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification("AgentMessageDelta", {"delta": "old answer"}),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events)
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "hello?"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if any(block.label == "codex" and block.text == "old answer" for block in app._blocks):
                    break
            assert any(block.label == "codex" and block.text == "old answer" for block in app._blocks)
            composer.text = "/new"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    assert runtime.submitted[0][1].kind == "UserTurn"
    assert app_runtime.event_dispatch_plans[-1].action == "start_fresh_session_with_summary_hint"
    assert not any(block.label == "codex" and block.text == "old answer" for block in app._blocks)


def test_textual_init_command_skips_when_project_doc_exists_without_user_turn(tmp_path: Path) -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch::SlashCommand::Init checks
    # config.cwd/AGENTS.md and emits a local info message instead of sending a
    # Codex op when the project doc already exists.
    # Rust test: chatwidget/tests/slash_commands.rs::slash_init_skips_when_project_doc_exists.
    existing_path = tmp_path / DEFAULT_AGENTS_MD_FILENAME
    existing_path.write_text("existing instructions", encoding="utf-8")
    runtime = _FakeActiveThreadRuntime([])
    runtime.cwd = tmp_path
    runtime.session_config.cwd = tmp_path
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/init"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert existing_path.read_text(encoding="utf-8") == "existing instructions"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any(DEFAULT_AGENTS_MD_FILENAME in notice and "Skipping /init" in notice for notice in notices)


def test_textual_init_command_submits_rust_init_prompt_when_missing(tmp_path: Path) -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch::SlashCommand::Init submits the
    # include_str!("../../prompt_for_init_command.md") prompt as a user message
    # when cwd/AGENTS.md is absent, rather than submitting the literal /init.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
            ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
        ]
    )
    runtime.cwd = tmp_path
    runtime.session_config.cwd = tmp_path
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/init"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    submitted = runtime.submitted[0][1]
    assert submitted.kind == "UserTurn"
    item = submitted.payload["items"][0]
    assert item.payload["text"].startswith("Generate a file named AGENTS.md")
    assert "Repository Guidelines" in item.payload["text"]
    assert item.payload["text"] != "/init"
    assert not (tmp_path / DEFAULT_AGENTS_MD_FILENAME).exists()


def test_textual_compact_command_submits_compact_op_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch::SlashCommand::Compact clears
    # token usage, marks the task running, and sends AppCommand::Compact via
    # AppEventSender::compact instead of submitting the literal slash text.
    # Rust test: chatwidget/tests/slash_commands.rs::slash_compact_eagerly_queues_follow_up_before_turn_start.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {"turn": {"id": "compact-turn"}}),
            ServerNotification("TurnCompleted", {"turn": {"id": "compact-turn", "status": "Completed"}}),
        ]
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/compact"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    assert runtime.submitted[0][1].kind == "Compact"
    assert not any(block.label == "you" and block.text == "/compact" for block in app._blocks)


def test_textual_queued_compact_dispatches_after_active_turn() -> None:
    # Rust-derived contract:
    # chatwidget/tests/slash_commands.rs::queued_slash_compact_dispatches_after_active_turn
    # records queued /compact with ParseSlash semantics and dispatches
    # AppCommand::Compact after the active turn completes.
    runtime = _BlockingFirstTurnRuntime()
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "hello"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if len(runtime.submitted) == 1 and app._busy:
                    break
            assert runtime.submitted[0][1].kind == "UserTurn"
            composer.text = "/compact"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert len(runtime.submitted) == 1
            runtime.first_turn_queue.put(ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}))
            for _ in range(100):
                await pilot.pause(0.02)
                if len(runtime.submitted) == 2:
                    break

    asyncio.run(scenario())

    assert [op.kind for _thread, op in runtime.submitted] == ["UserTurn", "Compact"]


def test_textual_review_with_args_submits_review_op_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch handles `/review <instructions>` by
    # submitting AppCommand::Review with ReviewTarget::Custom, not by submitting
    # the literal slash command as AppCommand::UserTurn.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {"turn": {"id": "review-turn"}}),
            ServerNotification("TurnCompleted", {"turn": {"id": "review-turn", "status": "Completed"}}),
        ]
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/review check regressions"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    op = runtime.submitted[0][1]
    assert op.kind == "Review"
    assert op.payload["target"] == ReviewTarget.custom("check regressions")
    assert not any(block.label == "you" and "/review" in block.text for block in app._blocks)


def test_textual_queued_review_with_args_dispatches_after_active_turn() -> None:
    # Rust-derived contract:
    # chatwidget/tests/slash_commands.rs::queued_slash_review_with_args_dispatches_after_active_turn
    # queues `/review <instructions>` with ParseSlash semantics and dispatches a
    # Review op after the active turn completes.
    runtime = _BlockingFirstTurnRuntime()
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "hello"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if len(runtime.submitted) == 1 and app._busy:
                    break
            composer.text = "/review check regressions"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert len(runtime.submitted) == 1
            runtime.first_turn_queue.put(ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}))
            for _ in range(100):
                await pilot.pause(0.02)
                if len(runtime.submitted) == 2:
                    break

    asyncio.run(scenario())

    assert [op.kind for _thread, op in runtime.submitted] == ["UserTurn", "Review"]
    assert runtime.submitted[1][1].payload["target"] == ReviewTarget.custom("check regressions")


def test_textual_bare_review_opens_preset_picker_without_user_turn() -> None:
    # Rust-derived boundary:
    # bare `/review` opens the TUI-owned review popup and is not submitted as a
    # user prompt.
    # Rust source/test:
    # - codex-tui::chatwidget::slash_dispatch dispatches SlashCommand::Review
    #   to ChatWidget::open_review_popup.
    # - chatwidget/tests/review_mode.rs::review_popup_custom_prompt_action_sends_event
    #   proves the preset picker actions are local TUI events.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/review"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert app._active_selection is not None
    assert app._active_selection.kind == "review"
    assert [item.name for item in app._active_selection.view.items] == [
        "Review against a base branch",
        "Review uncommitted changes",
        "Review a commit",
        "Custom review instructions",
    ]


def test_textual_review_preset_uncommitted_submits_review_op_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::review_popups maps "Review uncommitted changes"
    # to ReviewTarget::UncommittedChanges through the local TUI picker.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {"turn": {"id": "review-turn"}}),
            ServerNotification("TurnCompleted", {"turn": {"id": "review-turn", "status": "Completed"}}),
        ]
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/review"
            await pilot.press("enter")
            await pilot.press("down")
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    op = runtime.submitted[0][1]
    assert op.kind == "Review"
    assert op.payload["target"] == ReviewTarget.uncommitted_changes()
    assert not any(block.label == "you" and "/review" in block.text for block in app._blocks)


def test_textual_review_custom_prompt_submits_trimmed_review_op() -> None:
    # Rust-derived contract:
    # chatwidget/tests/review_mode.rs::custom_prompt_submit_sends_review_op
    # trims the typed custom prompt and sends Op::Review.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {"turn": {"id": "review-turn"}}),
            ServerNotification("TurnCompleted", {"turn": {"id": "review-turn", "status": "Completed"}}),
        ]
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/review"
            await pilot.press("enter")
            await pilot.press("down")
            await pilot.press("down")
            await pilot.press("down")
            await pilot.press("enter")
            assert app._review_custom_prompt_active
            composer.text = "  please audit dependencies  "
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    op = runtime.submitted[0][1]
    assert op.kind == "Review"
    assert op.payload["target"] == ReviewTarget.custom("please audit dependencies")


def test_textual_review_base_branch_picker_submits_selected_branch(monkeypatch) -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::review_popups::show_review_branch_picker renders
    # "current -> branch" rows and selecting one submits ReviewTarget::BaseBranch.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {"turn": {"id": "review-turn"}}),
            ServerNotification("TurnCompleted", {"turn": {"id": "review-turn", "status": "Completed"}}),
        ]
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    monkeypatch.setattr("pycodex.tui.textual_runtime.local_git_branches", lambda cwd: ["main", "feature"])
    monkeypatch.setattr("pycodex.tui.textual_runtime.current_branch_name", lambda cwd: "topic")

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/review"
            await pilot.press("enter")
            await pilot.press("enter")
            assert app._active_selection is not None
            assert app._active_selection.view.title == "Select a base branch"
            assert [item.name for item in app._active_selection.view.items] == ["topic -> main", "topic -> feature"]
            await pilot.press("down")
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    op = runtime.submitted[0][1]
    assert op.kind == "Review"
    assert op.payload["target"] == ReviewTarget.base_branch("feature")


def test_textual_review_branch_picker_escape_returns_to_parent_then_dismisses(monkeypatch) -> None:
    # Rust-derived contract:
    # chatwidget/tests/review_mode.rs::review_branch_picker_escape_navigates_back_then_dismisses
    # keeps review picker navigation local: Esc in the branch picker returns to
    # the preset picker, and a second Esc dismisses without sending Op::Review.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    monkeypatch.setattr("pycodex.tui.textual_runtime.local_git_branches", lambda cwd: ["main"])
    monkeypatch.setattr("pycodex.tui.textual_runtime.current_branch_name", lambda cwd: "topic")

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/review"
            await pilot.press("enter")
            await pilot.press("enter")
            assert app._active_selection is not None
            assert app._active_selection.view.title == "Select a base branch"
            await pilot.press("escape")
            assert app._active_selection is not None
            assert app._active_selection.kind == "review"
            assert app._active_selection.view.title == "Select a review preset"
            await pilot.press("escape")
            assert app._active_selection is None

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_inline_rename_submits_set_thread_name_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch handles `/rename <name>` by
    # normalizing the thread name and sending Op::SetThreadName, not by
    # submitting the literal slash command as a UserTurn.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification(
                "ThreadNameUpdated",
                {"thread_id": "primary", "thread_name": "Better title"},
            )
        ]
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/rename   Better title   "
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    op = runtime.submitted[0][1]
    assert op.kind == "SetThreadName"
    assert op.payload["name"] == "Better title"
    assert not any(block.label == "you" and "/rename" in block.text for block in app._blocks)
    assert app.app_runtime.chat_widget.thread_name == "Better title"


def test_textual_bare_rename_prefills_existing_thread_name_and_submits_prompt() -> None:
    # Rust-derived contract:
    # chatwidget/tests/slash_commands.rs::slash_rename_prefills_existing_thread_name
    # opens the TUI-owned rename prompt with the existing name and Enter submits
    # Op::SetThreadName with that prefilled value.
    runtime = _FakeActiveThreadRuntime([])
    runtime.thread_name = "Current project title"
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/rename"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert composer.text == "Current project title"
            assert app._rename_prompt_active
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    op = runtime.submitted[0][1]
    assert op.kind == "SetThreadName"
    assert op.payload["name"] == "Current project title"


def test_textual_bare_rename_empty_name_does_not_submit() -> None:
    # Rust-derived contract:
    # chatwidget/tests/slash_commands.rs::slash_rename_without_existing_thread_name_starts_empty
    # opens an empty naming prompt and empty Enter does not send SetThreadName.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/rename"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert composer.text == ""
            assert app._rename_prompt_active
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert app._rename_prompt_active


def test_textual_plan_command_switches_to_plan_mode_without_user_turn() -> None:
    # Rust-derived contract:
    # chatwidget/tests/plan_mode.rs::plan_slash_command_switches_to_plan_mode
    # switches the active collaboration mode to Plan and does not emit a model
    # UserTurn for the bare slash command.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/plan"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert getattr(app.app_runtime.chat_widget, "active_collaboration_mask").mode is ModeKind.PLAN
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Switched to Plan mode." in notices


def test_textual_plan_with_args_submits_prompt_in_plan_mode() -> None:
    # Rust-derived contract:
    # chatwidget/tests/plan_mode.rs::plan_slash_command_with_args_submits_prompt_in_plan_mode
    # applies Plan mode and submits only the argument text as a UserTurn.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {"turn": {"id": "plan-turn"}}),
            ServerNotification("TurnCompleted", {"turn": {"id": "plan-turn", "status": "Completed"}}),
        ]
    )
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/plan build the plan"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if runtime.submitted and not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    op = runtime.submitted[0][1]
    assert op.kind == "UserTurn"
    assert op.payload["items"][0].payload["text"] == "build the plan"
    assert op.payload["collaboration_mode"].mode is ModeKind.PLAN
    assert getattr(app.app_runtime.chat_widget, "active_collaboration_mask").mode is ModeKind.PLAN
    assert not any(block.label == "you" and "/plan" in block.text for block in app._blocks)


def test_textual_diff_command_renders_git_diff_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /diff to local
    #   add_diff_in_progress + AppEvent::DiffResult.
    # - codex-tui::get_git_diff concatenates tracked diff and untracked file
    #   diff while disabling the workspace command output cap.
    cwd = Path("C:/repo")
    runner = FakeRunner.new(
        [
            response(["git", "rev-parse", "--is-inside-work-tree"], 0, "true\n"),
            response(["git", "diff", "--color"], 1, "tracked\n"),
            response(["git", "ls-files", "--others", "--exclude-standard"], 0, "new.txt\n"),
            response(["git", "diff", "--color", "--no-index", "--", null_device(), "new.txt"], 1, "untracked\n"),
        ]
    )
    runtime = _FakeActiveThreadRuntime([])
    runtime.cwd = cwd
    runtime.session_config.cwd = cwd
    runtime.workspace_command_runner = runner
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/diff"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if "untracked" in "\n".join(block.text for block in app._blocks):
                    break

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert ("diff", "tracked\nuntracked\n") in [(block.label, block.text) for block in app._blocks]
    assert app.app_runtime.chat_widget.active_cell is None
    assert app.app_runtime.chat_widget.history[-1] == {"diff_complete": "tracked\nuntracked\n"}


def test_textual_diff_command_reports_missing_workspace_runner_without_user_turn() -> None:
    # Rust-derived contract:
    # chatwidget::slash_dispatch keeps /diff local even when the workspace
    # command runner is unavailable; it reports a visible local failure instead
    # of submitting the slash command to the model.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/diff"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    blocks = [(block.label, block.text) for block in app._blocks]
    assert ("diff", "Failed to compute diff: workspace command runner unavailable") in blocks


def test_textual_copy_command_copies_last_agent_markdown_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /copy to
    #   ChatWidget::copy_last_agent_markdown.
    # - codex-tui::chatwidget::interaction copies the transcript's latest
    #   agent markdown and adds a local history notice.
    events = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification("AgentMessageDelta", {"delta": "answer"}),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events)
    app = PyCodexTextualApp(TuiAppRuntime(runtime))
    copied: list[str] = []
    app.copy_to_clipboard = lambda text: copied.append(text) or "test-clipboard"

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "hello?"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                has_answer = any(block.label == "codex" and block.text == "answer" for block in app._blocks)
                if has_answer and not app._busy:
                    break
            assert any(block.label == "codex" and block.text == "answer" for block in app._blocks)
            composer.text = "/copy"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert copied == ["answer"]
    assert len(runtime.submitted) == 1
    assert runtime.submitted[0][1].kind == "UserTurn"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Copied last message to clipboard" in notices


def test_textual_copy_command_reports_missing_agent_response_without_user_turn() -> None:
    # Rust-derived contract:
    # /copy remains a local chatwidget command even when there is no copy
    # source; the visible result is the Rust "No agent response to copy" error.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))
    app.copy_to_clipboard = lambda text: (_ for _ in ()).throw(AssertionError("should not copy"))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/copy"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "No agent response to copy" in notices


def test_textual_copy_shortcut_uses_default_ctrl_o_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::interaction consumes
    #   copy_last_response_binding before normal composer input.
    # - chatwidget/tests/slash_commands.rs::
    #   ctrl_o_copy_reports_when_no_agent_response_exists fixes Ctrl-O as the
    #   default visible copy shortcut and proves it does not submit a UserTurn.
    events = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification("AgentMessageDelta", {"delta": "answer"}),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events)
    app = PyCodexTextualApp(TuiAppRuntime(runtime))
    copied: list[str] = []
    app.copy_to_clipboard = lambda text: copied.append(text) or "test-clipboard"

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "hello?"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if any(block.label == "codex" and block.text == "answer" for block in app._blocks) and not app._busy:
                    break
            composer.text = ""
            await pilot.press("ctrl+o")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert copied == ["answer"]
    assert len(runtime.submitted) == 1
    assert runtime.submitted[0][1].kind == "UserTurn"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Copied last message to clipboard" in notices


def test_textual_copy_shortcut_remap_replaces_default_without_user_turn() -> None:
    # Rust-derived contract:
    # - chatwidget/tests/slash_commands.rs::copy_shortcut_can_be_remapped
    #   proves configured `tui.keymap.global.copy` replaces Ctrl-O.
    # - Python Textual must route the configured app keymap action before the
    #   composer can turn it into user input.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"global": {"copy": "f12"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))
    app.copy_to_clipboard = lambda text: (_ for _ in ()).throw(AssertionError("should not copy"))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = ""
            await pilot.press("ctrl+o")
            await pilot.pause(0.05)
            assert "No agent response to copy" not in [block.text for block in app._blocks if block.label == "status"]
            await pilot.press("f12")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "No agent response to copy" in notices


def test_textual_mention_command_inserts_at_sign_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch maps /mention to insert_str("@")
    # rather than AppCommand::UserTurn.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/mention"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert composer.text == "@"

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_rollout_command_displays_current_path_without_user_turn(tmp_path: Path) -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch::SlashCommand::Rollout reads
    # ChatWidget::rollout_path and adds an info history cell with the path.
    # Rust test: chatwidget/tests/slash_commands.rs::slash_rollout_displays_current_path.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    rollout_path = tmp_path / "codex-test-rollout.jsonl"
    app_runtime.rollout_path = rollout_path
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/rollout"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any("Current rollout path:" in notice and str(rollout_path) in notice for notice in notices)


def test_textual_rollout_command_reports_missing_path_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch::SlashCommand::Rollout remains
    # local and reports that the rollout path is unavailable when none is known.
    # Rust test: chatwidget/tests/slash_commands.rs::slash_rollout_handles_missing_path.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/rollout"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Rollout path is not available yet." in notices


def test_textual_resume_command_opens_picker_from_runtime_rows_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch maps /resume to
    # AppEvent::OpenResumePicker, and codex-tui::resume_picker renders
    # "Resume a previous session" rows whose Enter selection resumes the
    # selected thread.
    # Rust tests/snapshots:
    # - chatwidget/tests/slash_commands.rs::slash_resume_opens_picker.
    # - resume_picker snapshot resume_picker_screen.
    runtime = _FakeActiveThreadRuntime([])
    runtime.resume_picker_rows = [
        ResumePickerRow(Path("C:/tmp/old.jsonl"), "thread-old", "older work", cwd=Path("C:/repo")),
        ResumePickerRow(Path("C:/tmp/new.jsonl"), "thread-new", "newer work", cwd=Path("C:/repo"), thread_name="Named session"),
    ]
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/resume"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert app._active_selection.kind == "resume"
            assert app._active_selection.view.title == "Resume a previous session"
            assert [item.name for item in app._active_selection.view.items] == ["older work", "Named session"]
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert [plan.action for plan in app_runtime.event_dispatch_plans] == [
        "open_resume_picker",
        "resume_session_by_id_or_name",
    ]
    assert app_runtime.event_dispatch_plans[-1].updates == (
        ("resume_session_by_id_or_name", {"id_or_name": "thread-new"}),
    )
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert f"Resume requested: {Path('C:/tmp/new.jsonl')}" in notices


def test_textual_resume_picker_uses_rust_state_for_search_space_and_expansion() -> None:
    # Rust-derived contract:
    # codex-tui::resume_picker::PickerState owns live search, space insertion,
    # backspace editing, Ctrl+E expansion, and toolbar state.  The Textual
    # product shell must route /resume keys through that state rather than the
    # generic list-selection filter.
    # Rust tests:
    # - resume_picker.rs::space_appends_to_search_query.
    # - resume_picker.rs::ctrl_e_toggles_selected_session_expansion.
    # - resume_picker.rs::search_line_renders_sort_and_filter_tabs.
    runtime = _FakeActiveThreadRuntime([])
    runtime.resume_picker_rows = [
        ResumePickerRow(Path("C:/tmp/alpha.jsonl"), "thread-alpha", "alpha work", cwd=Path("C:/repo")),
        ResumePickerRow(Path("C:/tmp/beta.jsonl"), "thread-beta", "beta space match", cwd=Path("C:/repo")),
    ]
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/resume"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert isinstance(app._active_selection.context, PickerState)

            for key in ("b", "e", "t", "a", "space", "s"):
                assert app.handle_selection_key(key)
            state = app._active_selection.context
            assert state.query == "beta s"
            assert [row.thread_id for row in state.filtered_rows] == ["thread-beta"]
            assert [item.name for item in app._active_selection.view.items] == ["beta space match"]

            assert app.handle_selection_key("backspace")
            assert state.query == "beta "
            assert app.handle_selection_key("ctrl+e")
            assert state.filtered_rows[state.selected].expanded is True
            assert "beta space match" in app._active_selection.view.items[0].description

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert [plan.action for plan in app_runtime.event_dispatch_plans] == ["open_resume_picker"]


def test_textual_resume_picker_ctrl_t_loads_transcript_overlay_without_raw_reasoning() -> None:
    # Rust-derived contract:
    # codex-tui::resume_picker::open_selected_transcript emits
    # PickerLoadRequest::Transcript for the selected thread.  The app-server
    # response is converted by resume_picker::transcript into transcript cells,
    # and raw reasoning is hidden unless show_raw_agent_reasoning is enabled.
    # Rust tests:
    # - resume_picker.rs::ctrl_t_requests_selected_session_transcript.
    # - resume_picker.rs::loaded_transcript_waits_for_loading_frame_before_opening_overlay.
    # - resume_picker.rs::thread_to_transcript_cells_hides_raw_reasoning_when_not_enabled.
    class _TranscriptRuntime(_FakeActiveThreadRuntime):
        def __init__(self) -> None:
            super().__init__([])
            self.resume_picker_rows = [
                ResumePickerRow(Path("C:/tmp/thread.jsonl"), "thread-1", "saved work", cwd=Path("C:/repo")),
            ]
            self.read_calls: list[tuple[str, bool]] = []

        def thread_read(self, thread_id: str, include_history: bool) -> dict[str, Any]:
            self.read_calls.append((thread_id, include_history))
            return {
                "id": thread_id,
                "cwd": "C:/repo",
                "turns": [
                    {
                        "items": [
                            {"kind": "UserMessage", "content": [{"text": "hello from saved turn"}]},
                            {"kind": "AgentMessage", "text": "hello from saved assistant"},
                            {
                                "kind": "Reasoning",
                                "summary": ["public summary"],
                                "content": ["private raw reasoning"],
                            },
                        ]
                    }
                ],
            }

    runtime = _TranscriptRuntime()
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/resume"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is not None

            assert app.handle_selection_key("ctrl+t")
            await pilot.pause(0.05)
            popup = str(app.query_one("#slash-popup", Static).renderable)
            assert "T R A N S C R I P T" in popup
            assert "hello from saved turn" in popup
            assert "hello from saved assistant" in popup
            assert "public summary" in popup
            assert "private raw reasoning" not in popup

            assert app.handle_selection_key("q")
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert app._active_selection.context.overlay is None

    asyncio.run(scenario())

    assert runtime.read_calls == [("thread-1", True)]
    assert runtime.submitted == []


def test_textual_startup_fork_picker_uses_runtime_rows_without_user_turn() -> None:
    # Rust-derived contract:
    # `codex fork` without a session id is converted by
    # codex-cli::finalize_fork_interactive into a TUI launch with fork_picker.
    # codex-tui::lib then calls resume_picker::run_fork_picker_with_app_server,
    # whose SessionPickerAction::Fork title is "Fork a previous session".
    # Rust tests:
    # - cli/src/main.rs::fork_picker_logic_none_and_not_last.
    # - resume_picker tests/snapshots for SessionPickerAction::Fork.
    runtime = _FakeActiveThreadRuntime([])
    runtime.resume_picker_rows = [
        ResumePickerRow(Path("C:/tmp/parent.jsonl"), "thread-parent", "parent work", cwd=Path("C:/repo")),
    ]
    app_runtime = TuiAppRuntime(runtime, startup_session_action="fork")
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert app._active_selection.kind == "fork"
            assert app._active_selection.view.title == "Fork a previous session"
            assert [item.name for item in app._active_selection.view.items] == ["parent work"]
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert app_runtime.event_dispatch_plans == []
    assert app_runtime.startup_session_selected_action == "fork"
    assert app_runtime.startup_session_selected_thread_id == "thread-parent"
    assert app_runtime.startup_session_selected_path == Path("C:/tmp/parent.jsonl")
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert f"Fork requested: {Path('C:/tmp/parent.jsonl')}" in notices


def test_textual_startup_fork_picker_calls_backend_and_switches_thread() -> None:
    # Rust-derived contract:
    # - codex-tui/src/app.rs handles SessionSelection::Fork(target_session) by
    #   calling AppServerSession::fork_thread(config, target_session.thread_id).
    # - The returned AppServerStartedThread is installed as the active/primary
    #   chat session, and the selection must not be submitted as a UserTurn.
    class _ForkRuntime(_FakeActiveThreadRuntime):
        def __init__(self) -> None:
            super().__init__([])
            self.resume_picker_rows = [
                ResumePickerRow(Path("C:/tmp/parent.jsonl"), "thread-parent", "parent work", cwd=Path("C:/repo")),
            ]
            self.fork_calls: list[tuple[Any, str]] = []

        def fork_thread(self, config: Any, source_thread_id: str) -> Any:
            self.fork_calls.append((config, source_thread_id))
            return {
                "session": {
                    "thread_id": "thread-forked",
                    "forked_from_id": source_thread_id,
                    "thread_name": "Forked work",
                    "cwd": "C:/repo",
                    "rollout_path": "C:/tmp/forked.jsonl",
                },
                "turns": [],
            }

    runtime = _ForkRuntime()
    app_runtime = TuiAppRuntime(runtime, startup_session_action="fork")
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert app._active_selection.kind == "fork"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert [(call[1]) for call in runtime.fork_calls] == ["thread-parent"]
    assert app_runtime.thread_id == "thread-forked"
    assert app_runtime.routing_state.active_thread_id == "thread-forked"
    assert app_runtime.routing_state.primary_thread_id == "thread-forked"
    assert app_runtime.startup_session_selected_action == "fork"
    assert app_runtime.startup_session_selected_thread_id == "thread-parent"
    assert app_runtime.startup_session_forked_thread_id == "thread-forked"
    assert app_runtime.rollout_path == Path("C:/tmp/forked.jsonl")


def test_textual_startup_fork_replays_returned_turns_before_ready_notice() -> None:
    # Rust-derived contract:
    # - codex-tui/src/app.rs installs AppServerStartedThread returned by
    #   SessionSelection::Fork.
    # - codex-tui/src/app/thread_routing.rs::enqueue_primary_thread_session
    #   calls ChatWidget::replay_thread_turns(turns, ResumeInitialMessages)
    #   after handle_thread_session and before normal input continues.
    # - codex-tui/src/app/tests.rs::
    #   enqueue_primary_thread_session_replays_turns_before_initial_prompt_submit.
    class _ForkRuntime(_FakeActiveThreadRuntime):
        def __init__(self) -> None:
            super().__init__([])
            self.resume_picker_rows = [
                ResumePickerRow(Path("C:/tmp/parent.jsonl"), "thread-parent", "parent work", cwd=Path("C:/repo")),
            ]

        def fork_thread(self, _config: Any, source_thread_id: str) -> Any:
            return {
                "session": {
                    "thread_id": "thread-forked",
                    "forked_from_id": source_thread_id,
                    "thread_name": "Forked work",
                    "cwd": "C:/repo",
                    "rollout_path": "C:/tmp/forked.jsonl",
                },
                "turns": [
                    {
                        "id": "turn-1",
                        "status": "Completed",
                        "duration_ms": 17,
                        "items": [
                            {
                                "kind": "UserMessage",
                                "content": [{"type": "Text", "text": "earlier prompt"}],
                            },
                            {
                                "kind": "AgentMessage",
                                "content": [{"type": "Text", "text": "earlier answer"}],
                                "phase": "final",
                            },
                        ],
                    }
                ],
            }

    runtime = _ForkRuntime()
    app_runtime = TuiAppRuntime(runtime, startup_session_action="fork")
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            await pilot.pause(0.05)
            assert app._active_selection is not None
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    visible = [(block.label, block.text) for block in app._blocks]
    assert ("you", "earlier prompt") in visible
    assert ("codex", "earlier answer") in visible
    assert app_runtime.take_startup_session_replay_history() == []
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert f"Forked session from {Path('C:/tmp/parent.jsonl')} as thread-forked." in notices


def test_textual_resume_command_reports_missing_picker_provider_without_user_turn() -> None:
    # Rust-derived boundary:
    # /resume is still a local TUI AppEvent and must not become a UserTurn even
    # when the Python active-thread runtime cannot provide a session list.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/resume"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert app_runtime.event_dispatch_plans[-1].action == "open_resume_picker"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Resume picker is not available in the Textual shell yet." in notices


def test_textual_resume_with_arg_dispatches_named_resume_without_user_turn() -> None:
    # Rust-derived contract:
    # slash_dispatch dispatches /resume <id-or-name> as
    # AppEvent::ResumeSessionByIdOrName with the trimmed inline argument.
    # Rust test: chatwidget/tests/slash_commands.rs::slash_resume_with_arg_requests_named_session.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/resume my-saved-thread"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    plan = app_runtime.event_dispatch_plans[-1]
    assert plan.action == "resume_session_by_id_or_name"
    assert plan.updates == (("resume_session_by_id_or_name", {"id_or_name": "my-saved-thread"}),)


def test_textual_fork_command_dispatches_fork_without_user_turn() -> None:
    # Rust-derived contract:
    # codex-tui::chatwidget::slash_dispatch maps /fork to
    # AppEvent::ForkCurrentSession, not AppCommand::UserTurn.
    # Rust test: chatwidget/tests/slash_commands.rs::slash_fork_requests_current_fork.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/fork"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert app_runtime.event_dispatch_plans[-1].action == "fork_current_session"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Fork current session requested." in notices


def test_textual_status_command_uses_and_refreshes_rate_limit_snapshots() -> None:
    # Rust-derived contract:
    # - chatwidget/tests/status_command_tests.rs proves /status renders from
    #   cached rate limits immediately and a refresh updates future cards.
    runtime = _FakeActiveThreadRuntime([])
    runtime.should_refresh_rate_limits = True
    runtime.rate_limit_snapshots_by_limit_id = {
        "codex": RateLimitSnapshotDisplay(
            "codex",
            datetime.now().astimezone(),
            primary=RateLimitWindowDisplay(10.0, "soon", 300),
        )
    }
    runtime.fetch_account_rate_limits = lambda: [
        RateLimitSnapshotDisplay(
            "codex",
            datetime.now().astimezone(),
            primary=RateLimitWindowDisplay(92.0, "soon", 300),
        )
    ]
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(120, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/status"
            await pilot.press("enter")
            await pilot.pause(0.05)
            composer.text = "/status"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    status_text = "\n".join(block.text for block in app._blocks if block.label == "status")
    assert runtime.submitted == []
    assert "refresh requested; run /status again shortly." not in status_text
    assert "5h limit" in status_text
    assert "8% left" in status_text


def test_textual_composer_shift_enter_keeps_multiline_draft_until_submit() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer treats plain Enter as submit.
    # - Shift+Enter inserts a newline and does not submit until a later Enter.
    events = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification("AgentMessageDelta", {"delta": "ok"}),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events)
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "line one"
            composer.move_cursor((0, len("line one")))
            await pilot.press("shift+enter")
            await pilot.pause(0.05)
            assert runtime.submitted == []
            assert composer.text == "line one\n"
            composer.insert("line two")
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if not app._busy:
                    break

    asyncio.run(scenario())

    assert runtime.submitted
    submitted = runtime.submitted[0][1]
    assert submitted.kind == "UserTurn"
    item = submitted.payload["items"][0]
    assert item.payload["text"] == "line one\nline two"
    assert ("you", "line one\nline two") in [(block.label, block.text) for block in app._blocks]


def test_textual_composer_history_navigation_uses_ported_history_model() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer_history records local submissions.
    # - Empty composer Up recalls newest-to-oldest; Down moves newer and clears
    #   after the newest entry.
    events = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events)
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "first"
            composer.move_cursor((0, len("first")))
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if not app._busy:
                    break
            composer.text = "second"
            composer.move_cursor((0, len("second")))
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if not app._busy:
                    break

            composer.text = ""
            await pilot.press("up")
            await pilot.pause(0.05)
            assert composer.text == "second"
            await pilot.press("up")
            await pilot.pause(0.05)
            assert composer.text == "first"
            await pilot.press("down")
            await pilot.pause(0.05)
            assert composer.text == "second"
            await pilot.press("down")
            await pilot.pause(0.05)
            assert composer.text == ""

    asyncio.run(scenario())

    assert [op.payload["items"][0].payload["text"] for _thread, op in runtime.submitted] == ["first", "second"]


def test_textual_composer_history_navigation_fetches_persistent_entries() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer_history::navigate_up emits
    #   AppEvent::LookupMessageHistoryEntry when a persistent offset is not
    #   cached.
    # - codex-tui::bottom_pane::chat_composer::on_history_entry_response
    #   routes HistoryEntryResponse::Found through apply_history_entry, so the
    #   composer is rehydrated when the async response arrives.
    class _HistoryRuntime(_FakeActiveThreadRuntime):
        def __init__(self) -> None:
            super().__init__([])
            self.lookups: list[tuple[str, int, int]] = []
            self.entries = {
                0: "older persistent prompt",
                1: "newest persistent prompt",
            }

        def lookup_message_history_entry(self, thread_id: str, log_id: int, offset: int) -> str | None:
            self.lookups.append((thread_id, log_id, offset))
            return self.entries.get(offset)

    runtime = _HistoryRuntime()
    app_runtime = TuiAppRuntime(runtime)
    app_runtime.chat_widget.bottom_history_metadata = ("primary", 9, 2)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            assert composer.text == ""

            await pilot.press("up")
            await pilot.pause(0.05)
            assert composer.text == "newest persistent prompt"

            await pilot.press("up")
            await pilot.pause(0.05)
            assert composer.text == "older persistent prompt"

            await pilot.press("down")
            await pilot.pause(0.05)
            assert composer.text == "newest persistent prompt"

    asyncio.run(scenario())

    assert runtime.lookups == [("primary", 9, 1), ("primary", 9, 0)]
    assert runtime.submitted == []


def test_textual_composer_history_metadata_sync_does_not_clear_local_history() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer_history::set_metadata resets the
    #   history offset space when a new persistent log snapshot is installed.
    # - Product composition must not call it repeatedly for the same snapshot,
    #   because current-session submissions live in the same history model and
    #   should remain navigable until the session metadata actually changes.
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = TuiAppRuntime(runtime)
    app_runtime.chat_widget.bottom_history_metadata = ("primary", 11, 0)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)

            composer.text = "first local"
            await pilot.press("enter")
            await pilot.pause(0.05)
            composer.text = "second local"
            await pilot.press("enter")
            await pilot.pause(0.05)

            app._sync_composer_history_metadata_from_runtime()
            app._sync_composer_history_metadata_from_runtime()

            await pilot.press("up")
            await pilot.pause(0.05)
            assert composer.text == "second local"
            await pilot.press("up")
            await pilot.pause(0.05)
            assert composer.text == "first local"

    asyncio.run(scenario())

    assert [op.payload["items"][0].payload["text"] for _thread, op in runtime.submitted] == [
        "first local",
        "second local",
    ]


def test_textual_composer_submission_persists_message_history_for_next_session(tmp_path) -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::input_submission appends accepted user messages
    #   to codex-message-history.
    # - codex-tui::app_server_session installs message-history metadata during
    #   session configuration, allowing a later TUI session to recall entries
    #   through Up-arrow persistent lookup.
    from pycodex.config.types import History
    from pycodex.message_history import HistoryConfig, append_entry, history_metadata, lookup
    from pycodex.tui.app.runtime import _run_coro_blocking

    class _PersistentHistoryRuntime(_FakeActiveThreadRuntime):
        def __init__(self) -> None:
            super().__init__([])
            self.session_config = SimpleNamespace(codex_home=tmp_path, history=History())

        def message_history_metadata(self) -> tuple[int, int]:
            return _run_coro_blocking(history_metadata(HistoryConfig.new(tmp_path, self.session_config.history)))

        def append_message_history_entry(self, text: str) -> None:
            _run_coro_blocking(append_entry(text, "primary", HistoryConfig.new(tmp_path, self.session_config.history)))

        def lookup_message_history_entry(self, _thread_id: str, log_id: int, offset: int):
            return lookup(log_id, offset, HistoryConfig.new(tmp_path, self.session_config.history))

    writer = _PersistentHistoryRuntime()
    writer_app = PyCodexTextualApp(TuiAppRuntime(writer))

    async def write_session() -> None:
        async with writer_app.run_test(size=(100, 32)) as pilot:
            composer = writer_app.query_one("#composer", CodexComposerTextArea)
            composer.text = "persisted from first session"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(write_session())

    reader = _PersistentHistoryRuntime()
    reader_app = PyCodexTextualApp(TuiAppRuntime(reader))

    async def read_session() -> None:
        async with reader_app.run_test(size=(100, 32)) as pilot:
            composer = reader_app.query_one("#composer", CodexComposerTextArea)
            await pilot.press("up")
            await pilot.pause(0.05)
            assert composer.text == "persisted from first session"

    asyncio.run(read_session())


def test_textual_composer_ctrl_r_search_accepts_match_without_submitting() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer::history_search opens with
    #   Ctrl-R, previews matching history as query text is typed, and Enter
    #   accepts the preview as draft text without submitting a UserTurn.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            app._prompt_history.record_local_submission(HistoryEntry.new("git status"))
            app._prompt_history.record_local_submission(HistoryEntry.new("cargo test"))
            composer = app.query_one("#composer", CodexComposerTextArea)
            await pilot.press("ctrl+r")
            await pilot.press("g")
            await pilot.press("i")
            await pilot.pause(0.05)
            assert composer.text == "git status"
            assert composer.history_search is not None
            assert composer.history_search.query == "gi"
            status = app.query_one("#status-line", Static).renderable
            assert "reverse-i-search: gi" in str(status)
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert composer.text == "git status"
            assert composer.history_search is None

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_composer_history_search_steps_older_and_newer_matches() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer::history_search handles
    #   repeated history_search_previous/Ctrl-R or Up as Older.
    # - It handles history_search_next/Ctrl-S or Down as Newer while the
    #   footer-owned search session is active.
    # - Query edits restart traversal from newest-to-oldest, but navigation
    #   keys continue from the current selected match.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            app._prompt_history.record_local_submission(HistoryEntry.new("git status"))
            app._prompt_history.record_local_submission(HistoryEntry.new("git branch"))
            app._prompt_history.record_local_submission(HistoryEntry.new("git diff"))
            composer = app.query_one("#composer", CodexComposerTextArea)

            await pilot.press("ctrl+r")
            await pilot.press("g")
            await pilot.press("i")
            await pilot.pause(0.05)
            assert composer.text == "git diff"

            await pilot.press("ctrl+r")
            await pilot.pause(0.05)
            assert composer.text == "git branch"

            await pilot.press("down")
            await pilot.pause(0.05)
            assert composer.text == "git diff"
            assert composer.history_search is not None
            assert composer.history_search.query == "gi"

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_composer_history_search_uses_runtime_keymap_remap() -> None:
    # Rust-derived contract:
    # - codex-tui::keymap resolves tui.keymap.composer.history_search_previous.
    # - codex-tui::bottom_pane::chat_composer::set_keymap_bindings updates the
    #   history-search trigger and remapped_history_search_does_not_fall_back_to_ctrl_r
    #   proves Ctrl-R no longer opens search once the action is remapped.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"composer": {"history_search_previous": "z"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            app._prompt_history.record_local_submission(HistoryEntry.new("git status"))
            composer = app.query_one("#composer", CodexComposerTextArea)

            await pilot.press("ctrl+r")
            await pilot.pause(0.05)
            assert composer.history_search is None

            await pilot.press("z")
            await pilot.press("g")
            await pilot.press("i")
            await pilot.pause(0.05)
            assert composer.text == "git status"
            assert composer.history_search is not None
            assert composer.history_search.query == "gi"

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_shortcut_overlay_uses_runtime_keymap_history_search_hint() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer::set_keymap_bindings writes
    #   primary_binding(keymap.composer.history_search_previous) into footer
    #   key hints.
    # - codex-tui::bottom_pane::footer::shortcut_overlay_lines renders the
    #   HistorySearch row from FooterKeyHints instead of a fixed Ctrl-R label.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"composer": {"history_search_previous": "z"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            popup = app.query_one("#slash-popup", Static)

            await pilot.press("?")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)

            assert "z search history" in rendered
            assert "ctrl + r search history" not in rendered
            assert "customize shortcuts with /keymap" in rendered

    asyncio.run(scenario())


def test_textual_shortcut_overlay_toggle_uses_runtime_keymap_remap() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer::handle_shortcut_overlay_key
    #   checks RuntimeKeymap.composer.toggle_shortcuts, so remapping that
    #   action replaces the default '?' toggle instead of adding to it.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"composer": {"toggle_shortcuts": "z"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)

            await pilot.press("?")
            await pilot.pause(0.05)
            assert composer.text == "?"
            assert str(popup.renderable) == ""

            composer.text = ""
            await pilot.press("z")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert composer.text == ""
            assert "customize shortcuts with /keymap" in rendered

    asyncio.run(scenario())


def test_textual_composer_ctrl_r_search_continues_after_persistent_response() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer_history::advance_search_from
    #   requests missing persistent offsets and marks the search Pending.
    # - on_entry_response continues the same search scan after a non-match and
    #   applies the first unique matching persistent entry to the composer.
    class _HistoryRuntime(_FakeActiveThreadRuntime):
        def __init__(self) -> None:
            super().__init__([])
            self.lookups: list[tuple[str, int, int]] = []
            self.entries = {
                0: "git older persistent",
                1: "git status persistent",
                2: "plain newest persistent",
            }

        def lookup_message_history_entry(self, thread_id: str, log_id: int, offset: int) -> str | None:
            self.lookups.append((thread_id, log_id, offset))
            return self.entries.get(offset)

    runtime = _HistoryRuntime()
    app_runtime = TuiAppRuntime(runtime)
    app_runtime.chat_widget.bottom_history_metadata = ("primary", 7, 3)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            await pilot.press("ctrl+r")
            await pilot.press("g")
            await pilot.press("i")
            await pilot.pause(0.05)

            assert composer.text == "git status persistent"
            assert composer.history_search is not None
            assert composer.history_search.query == "gi"
            assert composer.history_search.status is not None
            assert "reverse-i-search: gi" in str(app.query_one("#status-line", Static).renderable)

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert composer.text == "git status persistent"
            assert composer.history_search is None

    asyncio.run(scenario())

    assert runtime.lookups == [("primary", 7, 2), ("primary", 7, 1)]
    assert runtime.submitted == []


def test_textual_composer_ctrl_r_escape_restores_original_draft() -> None:
    # Rust-derived contract:
    # - history search stores the original draft and Esc/Ctrl-C restores it.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            app._prompt_history.record_local_submission(HistoryEntry.new("git diff"))
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "draft"
            composer.move_cursor((0, len("draft")))
            await pilot.press("ctrl+r")
            await pilot.press("z")
            await pilot.pause(0.05)
            assert composer.text == "draft"
            assert composer.history_search is not None
            assert composer.history_search.query == "z"
            status = app.query_one("#status-line", Static).renderable
            assert "no match" in str(status)
            await pilot.press("escape")
            await pilot.pause(0.05)
            assert composer.text == "draft"
            assert composer.history_search is None

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_composer_small_paste_normalizes_crlf() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer handles explicit paste text.
    # - Pasted CRLF/CR text is normalized to LF before it enters the draft.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)):
            composer = app.query_one("#composer", CodexComposerTextArea)
            await composer._on_paste(events.Paste("a\r\nb\rc"))
            assert composer.text == "a\nb\nc"
            assert composer.pending_pastes == []

    asyncio.run(scenario())


def test_textual_composer_large_paste_placeholder_expands_on_submit() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer stores large pasted text behind
    #   a placeholder in the draft.
    # - Submitted UserTurn text expands the pending paste exactly once.
    events_for_turn = [
        ServerNotification("TurnStarted", {"turn": {"id": "t1"}}),
        ServerNotification("AgentMessageDelta", {"delta": "ok"}),
        ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}),
    ]
    runtime = _FakeActiveThreadRuntime(events_for_turn)
    app = PyCodexTextualApp(TuiAppRuntime(runtime))
    payload = "x" * (LARGE_PASTE_CHAR_THRESHOLD + 1)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            await composer._on_paste(events.Paste(payload))
            assert composer.text == f"[Pasted Content {len(payload)} chars]"
            assert composer.pending_pastes == [(composer.text, payload)]

            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if not app._busy:
                    break

            assert composer.text == ""
            assert composer.pending_pastes == []

    asyncio.run(scenario())

    submitted = runtime.submitted[0][1]
    assert submitted.kind == "UserTurn"
    item = submitted.payload["items"][0]
    assert item.payload["text"] == payload
    assert ("you", payload) in [(block.label, block.text) for block in app._blocks]


def test_textual_ctrl_t_focuses_scrollable_transcript_and_q_returns_composer() -> None:
    # Rust-derived contract:
    # - codex-tui::app::input maps Ctrl-T to the transcript overlay.
    # - codex-tui::pager_overlay handles pager-family transcript navigation and
    #   closes back to the main composer.
    #
    # Textual keeps the transcript pane mounted instead of opening a second
    # Ratatui overlay, so Ctrl-T focuses the scrollable RichLog and advertises
    # the same key family; q/Esc returns focus to the composer.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(80, 18)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            transcript = app.query_one("#transcript")
            popup = app.query_one("#slash-popup", Static)
            for index in range(40):
                app._append_block("codex", f"line {index}")
            await pilot.pause(0.05)

            await pilot.press("ctrl+t")
            await pilot.pause(0.05)
            assert app._transcript_mode
            assert app.focused is transcript
            status = app.query_one("#status-line", Static).renderable
            assert "pgup/pgdn page" in str(status)
            banner = str(popup.renderable)
            assert "T R A N S C R I P T" in banner
            assert "↑/↓ to scroll" in banner
            assert "鈫?" not in banner
            assert "q to quit" in banner
            assert _transcript_banner_percent(banner) == 100

            await pilot.press("home")
            await pilot.pause(0.05)
            assert getattr(transcript, "scroll_y", 1) == 0
            assert _transcript_banner_percent(app.query_one("#slash-popup", Static).renderable) == 0
            assert _transcript_banner_percent(popup.renderable) == 0

            await pilot.press("down")
            await pilot.pause(0.05)
            one_line_down = getattr(transcript, "scroll_y", 0)
            assert one_line_down > 0
            assert _transcript_banner_percent(popup.renderable) > 0

            await pilot.press("up")
            await pilot.pause(0.05)
            assert getattr(transcript, "scroll_y", 1) < one_line_down

            await pilot.press("pagedown")
            await pilot.pause(0.05)
            one_page_down = getattr(transcript, "scroll_y", 0)
            assert one_page_down > 0
            # Rust codex-tui::pager_overlay::PagerView::page_height scrolls by
            # the rendered content area height. For an 18-row transcript
            # overlay, TranscriptOverlay reserves 3 hint rows and PagerView
            # reserves 1 header + 1 footer row, leaving 13 content rows.
            assert one_page_down >= 13

            await pilot.press("pageup")
            await pilot.pause(0.05)
            assert getattr(transcript, "scroll_y", 0) < one_page_down

            await pilot.press("ctrl+d")
            await pilot.pause(0.05)
            half_page_down = getattr(transcript, "scroll_y", 0)
            assert half_page_down > 0
            assert half_page_down >= 7

            await pilot.press("ctrl+u")
            await pilot.pause(0.05)
            assert getattr(transcript, "scroll_y", 0) < half_page_down

            await pilot.press("end")
            await pilot.pause(0.05)
            assert getattr(transcript, "scroll_y", 0) > 0
            assert _transcript_banner_percent(popup.renderable) == 100
            # Rust codex-tui::pager_overlay keeps the tail content visible at
            # the bottom-pinned transcript page.  Do not let a Textual block
            # separator/trailing blank line consume the final viewport row.
            visible_height = max(int(getattr(getattr(transcript, "size", object()), "height", 1) or 1), 1)
            visible_text = "\n".join(transcript.render_line(row).text for row in range(visible_height))
            assert "line 39" in visible_text

            await pilot.press("ctrl+t")
            await pilot.pause(0.05)
            assert not app._transcript_mode
            assert app.focused is composer
            assert str(popup.renderable) == ""

    asyncio.run(scenario())


def test_textual_open_transcript_uses_runtime_keymap_remap() -> None:
    # Rust-derived contract:
    # - codex-tui::app::input checks keymap.app.open_transcript, whose default
    #   is Ctrl-T but whose configured binding replaces that default.
    # - Rust module anchors: codex-tui::keymap::RuntimeKeymap and
    #   codex-tui::app::input::handle_key_event.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"global": {"open_transcript": "ctrl-x"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(80, 18)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            transcript = app.query_one("#transcript")

            await pilot.press("ctrl+t")
            await pilot.pause(0.05)
            assert not app._transcript_mode
            assert app.focused is composer

            await pilot.press("ctrl+x")
            await pilot.pause(0.05)
            assert app._transcript_mode
            assert app.focused is transcript

    asyncio.run(scenario())


def test_textual_raw_ctrl_t_control_character_respects_open_transcript_remap() -> None:
    # Rust-derived contract:
    # - Raw Ctrl-T compatibility is only a transport representation of the
    #   configured open_transcript binding. Once the action is remapped, the old
    #   Ctrl-T byte must not bypass RuntimeKeymap.app.open_transcript.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"global": {"open_transcript": "ctrl-x"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)):
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "\x14"
            assert not app._consume_composer_control_shortcuts()
            assert composer.text == "\x14"
            assert not app._transcript_mode

    asyncio.run(scenario())


def test_textual_consumes_raw_ctrl_t_control_character_as_transcript_shortcut() -> None:
    # Rust source/test contract:
    # codex-tui::app::input treats Ctrl-T as a global transcript overlay key
    # while the composer is focused. Some Windows ConPTY/Textual paths can
    # surface the raw control byte in the editor instead of a named key event;
    # Python consumes that byte as the same action rather than submitting it.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "\x14"
            assert app._consume_composer_control_shortcuts()
            await pilot.pause(0.05)
            assert composer.text == ""
            assert app._transcript_mode
            assert app.focused is app.query_one("#transcript")
            assert not runtime.submitted

    asyncio.run(scenario())


def test_textual_transcript_escape_backtrack_preview_enter_submits_rollback() -> None:
    # Rust-derived contract:
    # - codex-tui::app_backtrack::handle_backtrack_overlay_event routes Esc in
    #   an open transcript overlay into BeginBacktrack, then Esc/Left selects
    #   older user turns and Enter confirms.
    # - codex-tui::app_backtrack::apply_backtrack_rollback submits
    #   AppCommand::thread_rollback(num_turns) and immediately prefills the
    #   composer, but does not trim local transcript cells until core confirms
    #   rollback success.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            app._append_block("you", "first [literal] question")
            app._append_block("codex", "first answer")
            app._append_block("you", "second [literal] question")
            app._append_block("codex", "second answer")

            await pilot.press("ctrl+t")
            await pilot.pause(0.05)
            assert app._transcript_mode

            await pilot.press("escape")
            await pilot.pause(0.05)
            assert app._backtrack_state.overlay_preview_active
            assert app._backtrack_state.nth_user_message == 1
            assert isinstance(popup.renderable, Text)
            assert "B A C K T R A C K" in str(popup.renderable)
            assert "second [literal] question" in str(popup.renderable)

            await pilot.press("left")
            await pilot.pause(0.05)
            assert app._backtrack_state.nth_user_message == 0
            assert isinstance(popup.renderable, Text)
            assert "first [literal] question" in str(popup.renderable)

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert not app._transcript_mode
            assert composer.text == "first [literal] question"
            assert runtime.submitted
            submitted = runtime.submitted[-1][1]
            assert submitted.kind == "ThreadRollback"
            assert submitted.payload["num_turns"] == 2
            conversation_blocks = [
                (block.label, block.text)
                for block in app._blocks
                if block.label in {"you", "codex"}
            ]
            assert conversation_blocks == [
                ("you", "first [literal] question"),
                ("codex", "first answer"),
                ("you", "second [literal] question"),
                ("codex", "second answer"),
            ]

    asyncio.run(scenario())


def test_textual_transcript_escape_without_user_turn_closes_with_backtrack_notice() -> None:
    # Rust-derived contract:
    # codex-tui::app_backtrack::begin_overlay_backtrack_preview_state returns
    # no_target_close_overlay plus "No previous message to edit." when the
    # transcript has no user message. The TUI closes the overlay and shows the
    # info message without submitting an AppCommand.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 24)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            app._append_block("codex", "assistant only")

            await pilot.press("ctrl+t")
            await pilot.pause(0.05)
            assert app._transcript_mode

            await pilot.press("escape")
            await pilot.pause(0.05)
            assert not app._transcript_mode
            assert app.focused is composer
            assert runtime.submitted == []
            assert "No previous message to edit." in [
                block.text for block in app._blocks if block.label == "status"
            ]

    asyncio.run(scenario())


def test_windows_vt_input_decoder_accepts_codepage_chinese_enter() -> None:
    # Rust source contract:
    # codex-tui::tui::event_stream receives decoded crossterm KeyEvents from
    # Windows terminal input. Python's Textual VT adapter reads bytes, so it
    # must accept local console-codepage IME bytes as well as UTF-8 VT bytes.
    chinese_prompt = "\u4f60\u597d\r"
    decoder = _VtInputDecoder(("cp936", "utf-8"))
    text = decoder.decode(chinese_prompt.encode("cp936"))

    assert text == chinese_prompt

    parser = load_textual_module("textual._xterm_parser").XTermParser(lambda: False, False)
    events_out = list(parser.feed(text))

    assert [getattr(event, "character", None) for event in events_out] == ["你", "好", "\r"]
    assert [getattr(event, "key", None) for event in events_out][-1] == "enter"


def test_windows_vt_input_decoder_prefers_codepage_when_bytes_are_valid_utf8_mojibake() -> None:
    # Rust source contract:
    # codex-tui::tui::event_stream receives already-decoded Windows key events.
    # Python must not decode local-codepage IME bytes as accidental valid UTF-8
    # mojibake. CP936 bytes for "what" are valid UTF-8 for unrelated glyphs.
    chinese_prompt = "\u4ec0\u4e48"
    assert chinese_prompt.encode("cp936").decode("utf-8") == "\u02b2\u00f4"

    decoder = _VtInputDecoder(("cp936", "utf-8"))

    assert decoder.decode(chinese_prompt.encode("cp936")) == chinese_prompt


def test_windows_vt_input_decoder_prefers_codepage_even_when_utf8_is_first() -> None:
    # Rust source contract:
    # codex-tui receives decoded Windows key events from crossterm. Python's
    # byte adapter must therefore repair the host case where PowerShell sends
    # CP936 bytes while sys.stdin.encoding reports UTF-8. CP936 bytes for
    # "what" are valid UTF-8 mojibake, so a strict UTF-8 decode is not enough.
    chinese_prompt = "\u4ec0\u4e48"
    assert chinese_prompt.encode("cp936").decode("utf-8") == "\u02b2\u00f4"

    decoder = _VtInputDecoder(("utf-8", "cp936"))

    assert decoder.decode(chinese_prompt.encode("cp936")) == chinese_prompt


def test_windows_vt_input_decoder_prefers_utf8_when_codepage_is_first() -> None:
    # Rust source contract:
    # crossterm surfaces decoded characters regardless of whether the terminal
    # transport uses UTF-8 or a Windows code page. If Python tries CP936 first,
    # UTF-8 CJK bytes such as "hello" must not become "娴ｇ姴銈? mojibake.
    chinese_prompt = "\u4f60\u597d"
    assert chinese_prompt.encode("utf-8").decode("cp936") == "\u6d63\u72b2\u30bd"

    decoder = _VtInputDecoder(("cp936", "utf-8"))

    assert decoder.decode(chinese_prompt.encode("utf-8")) == chinese_prompt


def test_windows_vt_input_decoder_buffers_split_codepage_character() -> None:
    # Rust source contract:
    # crossterm does not surface half a Windows IME character. The byte adapter
    # must likewise buffer split local-codepage lead/trail bytes.
    encoded = "\u4ec0".encode("cp936")
    decoder = _VtInputDecoder(("cp936", "utf-8"))

    assert decoder.decode(encoded[:1]) == ""
    assert decoder.decode(encoded[1:]) == "\u4ec0"


def test_textual_transcript_mode_accepts_mouse_wheel_scroll() -> None:
    # Rust-derived contract:
    # - codex-tui::tui enables alternate scroll in alt-screen mode so terminals
    #   may translate wheel movement into pager scroll keys.
    # - codex-tui::tui::event_stream skips raw Mouse events; Rust pager behavior
    #   remains owned by key-style transcript scrolling, not model turns.
    #
    # Textual owns concrete mouse dispatch, so the parity proof here is that
    # the retained transcript RichLog receives host MouseScroll events while
    # focused and changes the same transcript scroll offset used by pager keys.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(80, 12)) as pilot:
            transcript = app.query_one("#transcript")
            for index in range(60):
                app._append_block("codex", f"wheel line {index:02d}")
            await pilot.pause(0.05)

            await pilot.press("ctrl+t")
            await pilot.pause(0.05)
            assert app._transcript_mode
            assert app.focused is transcript

            await pilot.press("home")
            await pilot.pause(0.05)
            assert getattr(transcript, "scroll_y", 1) == 0

            transcript.post_message(
                events.MouseScrollDown(
                    x=2,
                    y=2,
                    delta_x=0,
                    delta_y=1,
                    button=0,
                    shift=False,
                    meta=False,
                    ctrl=False,
                )
            )
            await pilot.pause(0.05)
            assert getattr(transcript, "scroll_y", 0) > 0
            assert _transcript_banner_percent(app.query_one("#slash-popup", Static).renderable) > 0

            before_up = getattr(transcript, "scroll_y", 0)
            before_up_percent = _transcript_banner_percent(app.query_one("#slash-popup", Static).renderable)
            transcript.post_message(
                events.MouseScrollUp(
                    x=2,
                    y=2,
                    delta_x=0,
                    delta_y=-1,
                    button=0,
                    shift=False,
                    meta=False,
                    ctrl=False,
                )
            )
            await pilot.pause(0.05)
            assert getattr(transcript, "scroll_y", 0) < before_up
            assert _transcript_banner_percent(app.query_one("#slash-popup", Static).renderable) < before_up_percent

    asyncio.run(scenario())


def test_textual_transcript_slash_command_focuses_scrollable_transcript_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui keeps transcript/history navigation local to the TUI input
    #   layer; it must not be submitted as AppCommand::UserTurn.
    # - Python Textual maps /transcript and /history to the same scrollable
    #   transcript surface as Ctrl-T.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(80, 18)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            transcript = app.query_one("#transcript")
            popup = app.query_one("#slash-popup", Static)
            for index in range(30):
                app._append_block("codex", f"history line {index}")
            composer.text = "/transcript"
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert app._transcript_mode
            assert app.focused is transcript
            assert runtime.submitted == []
            assert "pgup/pgdn page" in str(app.query_one("#status-line", Static).renderable)
            assert "T R A N S C R I P T" in str(popup.renderable)

            await pilot.press("q")
            await pilot.pause(0.05)
            assert not app._transcript_mode
            assert app.focused is composer
            assert str(popup.renderable) == ""

    asyncio.run(scenario())


def test_textual_empty_question_mark_toggles_shortcut_overlay() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer::handle_shortcut_overlay_key
    #   toggles FooterMode::ShortcutOverlay only when the composer is empty.
    # - codex-tui::bottom_pane::footer::shortcut_overlay_lines owns the
    #   visible shortcut rows, including transcript and /keymap hints.
    # - Rust tests: shift_question_mark_toggles_shortcut_overlay_when_empty
    #   and shortcut_overlay_persists_while_task_running.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)

            await pilot.press("?")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)

            assert composer.text == ""
            assert "/ for commands" in rendered
            assert "! for shell commands" in rendered
            assert "ctrl + t to view transcript" in rendered
            assert "customize shortcuts with /keymap" in rendered

            await pilot.press("?")
            await pilot.pause(0.05)
            assert composer.text == ""
            assert str(popup.renderable) == ""

    asyncio.run(scenario())


def test_textual_question_mark_after_text_is_literal() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer test
    #   question_mark_only_toggles_on_first_char keeps '?' literal after text.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)

            await pilot.press("h")
            await pilot.press("?")
            await pilot.pause(0.05)

            assert composer.text == "h?"
            assert "ctrl + t to view transcript" not in str(popup.renderable)
            assert "customize shortcuts with /keymap" not in str(popup.renderable)

    asyncio.run(scenario())


def test_textual_slash_popup_filters_moves_and_completes_with_tab() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::command_popup filters slash commands in
    #   declaration order and moves the selected row with Up/Down.
    # - codex-tui::bottom_pane::chat_composer::slash_input completes the
    #   selected slash command at the composer boundary.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)

            await pilot.press("/")
            await pilot.press("m")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "> /model" in rendered
            assert " /memories" in rendered

            await pilot.press("down")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "> /memories" in rendered

            await pilot.press("tab")
            await pilot.pause(0.05)
            assert composer.text == "/memories "
            assert str(popup.renderable) == ""
            assert runtime.submitted == []

    asyncio.run(scenario())


def test_textual_slash_popup_uses_runtime_feature_flags_and_service_tiers() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer::builtin_command_flags derives
    #   command popup visibility from runtime feature/config state.
    # - codex-tui::bottom_pane::command_popup::new receives those flags plus
    #   current service-tier commands instead of a hard-coded default catalog.
    runtime = _FakeActiveThreadRuntime([])
    runtime.features = {"fast_mode": True, "multi_agent": True}
    runtime.session_config.features = runtime.features
    runtime.session_config.available_models = [
        {
            "model": "gpt-test",
            "service_tiers": [
                {
                    "id": "priority",
                    "name": "fast",
                    "description": "Fastest inference with increased plan usage",
                }
            ],
        }
    ]
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)):
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)

            composer.text = "/fa"
            composer._sync_command_popup_with_app()
            await asyncio.sleep(0)
            rendered = str(popup.renderable)
            assert "> /fast" in rendered
            assert "Fastest inference with increased plan usage" in rendered

            composer.text = "/pl"
            composer.command_popup = None
            composer._sync_command_popup_with_app()
            await asyncio.sleep(0)
            rendered = str(popup.renderable)
            assert "> /plan" in rendered
            assert "/plugins" not in rendered
            assert runtime.submitted == []

    asyncio.run(scenario())


def test_textual_model_command_opens_picker_and_selects_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /model to
    #   chatwidget::model_popups, not to AppCommand::UserTurn.
    # - Selecting a model applies the popup's UpdateModel/UpdateReasoningEffort
    #   actions through the app runtime.
    requests: list[Any] = []

    class RequestHandle:
        def request_typed(self, request: Any) -> SimpleNamespace:
            requests.append(request)
            return SimpleNamespace(ok=True)

    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.model = "codex-auto-fast"
    runtime.request_handle = RequestHandle()
    runtime.session_config.available_models = [
        {
            "model": "codex-auto-fast",
            "description": "Fast auto mode",
            "default_reasoning_effort": "low",
            "show_in_picker": True,
            "supported_reasoning_efforts": [{"effort": "low", "description": "low"}],
        },
        {
            "model": "codex-auto-balanced",
            "description": "Balanced auto mode",
            "default_reasoning_effort": "medium",
            "show_in_picker": True,
            "supported_reasoning_efforts": [{"effort": "medium", "description": "medium"}],
        },
        {
            "model": "codex-auto-thorough",
            "description": "Thorough auto mode",
            "default_reasoning_effort": "high",
            "show_in_picker": True,
            "supported_reasoning_efforts": [{"effort": "high", "description": "high"}],
        },
        {
            "model": "gpt-extra",
            "description": "General model",
            "default_reasoning_effort": "medium",
            "show_in_picker": True,
            "supported_reasoning_efforts": [{"effort": "medium", "description": "medium"}],
        },
        {
            "model": "hidden-model",
            "description": "Hidden model",
            "show_in_picker": False,
        },
    ]
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/model"
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert app._active_selection is not None
            rendered = str(popup.renderable)
            assert "Select Model" in rendered
            assert "Pick a quick auto mode or browse all models." in rendered
            assert "> codex-auto-fast" in rendered
            assert "codex-auto-balanced" in rendered
            assert "codex-auto-thorough" in rendered
            assert "All models" in rendered
            assert "hidden-model" not in rendered

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is None
            assert str(popup.renderable) == ""

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.session_config.model == "codex-auto-fast"
    assert runtime.session_config.model_reasoning_effort == "low"
    assert len(requests) == 1
    assert [(edit.key_path, edit.value) for edit in requests[0].params.edits] == [
        ("model", "codex-auto-fast"),
        ("model_reasoning_effort", "low"),
    ]
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any("Model changed to codex-auto-fast" in notice for notice in notices)


def test_textual_model_command_initial_selection_prefers_current_all_models_row() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::list_selection_view::apply_filter restores the
    #   current enabled row before falling back to initial_selected_idx or row 0.
    # - codex-tui::chatwidget::model_popups marks "All models" current when the
    #   active model is not one of the quick auto rows.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.model = "gpt-extra"
    runtime.session_config.model_reasoning_effort = "medium"
    runtime.session_config.available_models = [
        {
            "model": "codex-auto-fast",
            "description": "Fast auto mode",
            "default_reasoning_effort": "low",
            "show_in_picker": True,
            "supported_reasoning_efforts": [{"effort": "low", "description": "low"}],
        },
        {
            "model": "codex-auto-balanced",
            "description": "Balanced auto mode",
            "default_reasoning_effort": "medium",
            "show_in_picker": True,
            "supported_reasoning_efforts": [{"effort": "medium", "description": "medium"}],
        },
        {
            "model": "gpt-extra",
            "description": "General model",
            "default_reasoning_effort": "medium",
            "show_in_picker": True,
            "supported_reasoning_efforts": [
                {"effort": "medium", "description": "medium"},
                {"effort": "high", "description": "high"},
            ],
        },
    ]
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/model"
            await pilot.press("enter")
            await pilot.pause(0.05)

            rendered = str(popup.renderable)
            assert "Select Model" in rendered
            assert "> All models (current)" in rendered
            assert "> codex-auto-fast" not in rendered

            await pilot.press("enter")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "Select Model and Effort" in rendered
            assert "> gpt-extra (current) (default)" in rendered

            await pilot.press("enter")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "Select Reasoning Level for gpt-extra" in rendered
            assert "> Medium (default)" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.session_config.model == "gpt-extra"


def test_textual_model_command_without_runtime_catalog_opens_current_reasoning_picker() -> None:
    # Rust-derived contract:
    # - codex-tui receives a ModelCatalog from the app session; when the current
    #   model is the only visible model, accepting /model opens the multi-effort
    #   reasoning picker for that model instead of closing the popup.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.model = "gpt-5.5"
    runtime.session_config.model_reasoning_effort = "medium"
    runtime.session_config.available_models = []
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/model"
            await pilot.press("enter")
            await pilot.pause(0.05)

            rendered = str(popup.renderable)
            assert "Select Model and Effort" in rendered
            assert "> gpt-5.5 (current) (default)" in rendered

            await pilot.press("enter")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "Select Reasoning Level for gpt-5.5" in rendered
            assert "> Medium (default)" in rendered
            assert "Extra high" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.session_config.model == "gpt-5.5"


def test_textual_model_reasoning_keyboard_selection_updates_footer_state() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::list_selection_view::handle_key_event routes
    #   Down/Enter inside selection views.
    # - codex-tui::chatwidget::model_popups::open_reasoning_popup emits
    #   UpdateModel, UpdateReasoningEffort, and PersistModelSelection for the
    #   accepted reasoning effort row.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.model = "gpt-5.5"
    runtime.session_config.model_reasoning_effort = "medium"
    runtime.session_config.available_models = []
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            header = app.query_one("#session-header", Static)
            composer.text = "/model"
            await pilot.press("enter")
            await pilot.pause(0.05)
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert "Select Reasoning Level for gpt-5.5" in str(popup.renderable)
            await pilot.press("down")
            await pilot.pause(0.05)
            assert "> High" in str(popup.renderable)

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is None
            assert str(popup.renderable) == ""
            assert "gpt-5.5 high" in str(header.renderable)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.session_config.model == "gpt-5.5"
    assert runtime.session_config.model_reasoning_effort == "high"


def test_textual_model_command_escape_cancels_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::selection_view_esc_respects_remapped_list_cancel
    #   proves Esc is handled by the active selection view cancellation path.
    # - Cancelling /model must not submit AppCommand::UserTurn or mutate the
    #   current model.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.available_models = [
        {
            "model": "codex-auto-balanced",
            "description": "Balanced auto mode",
            "show_in_picker": True,
        },
        {
            "model": "codex-auto-thorough",
            "description": "Thorough auto mode",
            "show_in_picker": True,
        },
    ]
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/model"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is not None
            assert "Select Model" in str(popup.renderable)

            await pilot.press("escape")
            await pilot.pause(0.05)
            assert app._active_selection is None
            assert str(popup.renderable) == ""

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.session_config.model == "gpt-test"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any("Model selection cancelled." in notice for notice in notices)


def test_textual_raw_command_toggles_and_reports_usage_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /raw to local raw-output
    #   mode toggling and reports RAW_USAGE for invalid args.
    # - The command is not submitted as AppCommand::UserTurn.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            for command in ("/raw", "/raw off", "/raw on", "/raw maybe"):
                composer.text = command
                await pilot.press("enter")
                await pilot.pause(0.05)

    asyncio.run(scenario())

    assert runtime.submitted == []
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any("Raw output mode on" in notice for notice in notices)
    assert any("Raw output mode off" in notice for notice in notices)
    assert any("Usage: /raw [on|off]" in notice for notice in notices)


def test_textual_raw_output_toggle_key_updates_status_without_notice_or_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::app::input handles keymap.app.toggle_raw_output before a
    #   model turn and calls apply_raw_output_mode(..., notify=false).
    # - keymap.rs::tests::raw_output_toggle_defaults_to_alt_r fixes Alt+R as
    #   the default binding.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("alt+r")
            await pilot.pause(0.05)
            status = str(app.query_one("#status-line", Static).renderable)
            assert "Raw output mode on" in status

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert _non_startup_status_notices(app) == []
    assert getattr(app.app_runtime.chat_widget, "raw_mode", False) is True


def test_textual_raw_output_toggle_uses_runtime_keymap_remap() -> None:
    # Rust-derived contract:
    # - codex-tui::app::input checks keymap.app.toggle_raw_output before a
    #   model turn.
    # - keymap.rs::tests::raw_output_toggle_can_be_remapped proves the action
    #   can be reassigned away from Alt-R.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"global": {"toggle_raw_output": "f12"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("alt+r")
            await pilot.pause(0.05)
            assert getattr(app.app_runtime.chat_widget, "raw_mode", False) is False
            assert "Raw output mode on" not in str(app.query_one("#status-line", Static).renderable)

            await pilot.press("f12")
            await pilot.pause(0.05)
            assert getattr(app.app_runtime.chat_widget, "raw_mode", False) is True
            assert "Raw output mode on" in str(app.query_one("#status-line", Static).renderable)

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_external_editor_uses_runtime_keymap_remap(monkeypatch: Any) -> None:
    # Rust-derived contract:
    # - codex-tui::app::input checks keymap.app.open_external_editor, whose
    #   default is Ctrl-G but whose configured binding replaces that default.
    # - Rust module anchors: codex-tui::keymap::RuntimeKeymap and
    #   codex-tui::app::input::handle_key_event.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"global": {"open_external_editor": "f12"}}
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def fake_run_editor(seed: str, editor_cmd: list[str]) -> str:
        assert seed == "draft"
        assert editor_cmd == ["fake-editor"]
        return "edited from external editor\n\n"

    monkeypatch.setattr("pycodex.tui.textual_runtime.external_editor.resolve_editor_command", lambda: ["fake-editor"])
    monkeypatch.setattr("pycodex.tui.textual_runtime.external_editor.run_editor", fake_run_editor)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "draft"

            await pilot.press("ctrl+g")
            await pilot.pause(0.1)
            assert composer.text == "draft"

            await pilot.press("f12")
            await pilot.pause(0.2)
            assert composer.text == "edited from external editor"
            assert getattr(app.app_runtime.chat_widget, "external_editor_state", "Closed") == "Closed"
            assert runtime.submitted == []

    asyncio.run(scenario())


def test_textual_external_editor_missing_editor_matches_rust_message(monkeypatch: Any) -> None:
    # Rust-derived contract:
    # codex-tui::app::input::launch_external_editor reports the exact
    # MissingEditor copy when neither $VISUAL nor $EDITOR resolves.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    def missing_editor() -> list[str]:
        from pycodex.tui.external_editor import EditorError, ExternalEditorError

        raise ExternalEditorError(EditorError.MISSING_EDITOR.value)

    monkeypatch.setattr("pycodex.tui.textual_runtime.external_editor.resolve_editor_command", missing_editor)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("ctrl+g")
            await pilot.pause(0.2)

    asyncio.run(scenario())

    notices = _non_startup_status_notices(app)
    assert "Cannot open external editor: set $VISUAL or $EDITOR before starting Codex." in notices
    assert runtime.submitted == []


def test_textual_clear_terminal_uses_runtime_keymap_remap() -> None:
    # Rust-derived contract:
    # - codex-tui::app::input checks keymap.app.clear_terminal, whose default
    #   is Ctrl-L but whose configured binding replaces that default.
    # - Rust module anchors: codex-tui::keymap::RuntimeKeymap and
    #   codex-tui::app::input::handle_key_event.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {"global": {"clear_terminal": "f12"}}
    app_runtime = TuiAppRuntime(runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            app._append_block("codex", "old answer")
            await pilot.press("ctrl+l")
            await pilot.pause(0.05)
            assert any(block.label == "codex" and block.text == "old answer" for block in app._blocks)

            await pilot.press("f12")
            await pilot.pause(0.05)
            assert not any(block.label == "codex" and block.text == "old answer" for block in app._blocks)
            assert not any(str(block.text).startswith(_STARTUP_TIP_PREFIX) for block in app._blocks)

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert app_runtime.event_dispatch_plans[-1].action == "clear_ui_and_start_fresh_session"


def test_textual_clear_terminal_key_is_disabled_while_task_running() -> None:
    # Rust-derived contract:
    # - codex-tui::app::input checks ChatWidget::can_run_ctrl_l_clear_now
    #   before Ctrl-L clears the UI.
    # - chatwidget::interaction reports
    #   "Ctrl+L is disabled while a task is in progress." and preserves the
    #   active transcript while a task is running.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            app._append_block("codex", "still running")
            app._busy = True
            await pilot.press("ctrl+l")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert any(block.label == "codex" and block.text == "still running" for block in app._blocks)
    assert "Ctrl+L is disabled while a task is in progress." in _non_startup_status_notices(app)
    assert runtime.submitted == []


def test_textual_active_turn_disables_model_slash_command_without_queueing() -> None:
    # Rust-derived contract:
    # - codex-tui::slash_command::SlashCommand::available_during_task gates
    #   slash commands while a turn is running.
    # - /model during an active task is handled locally and must not become a
    #   queued follow-up UserTurn.
    class _QueueRuntime(_FakeActiveThreadRuntime):
        def __init__(self) -> None:
            super().__init__([])
            self.queue: Queue[object] = Queue()

        def submit_thread_op(self, thread_id: str, op: AppCommand) -> QueueActiveThreadEventStream:
            self.submitted.append((thread_id, op))
            return QueueActiveThreadEventStream(self.queue)

    runtime = _QueueRuntime()
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "first"
            await pilot.press("enter")
            await pilot.pause(0.05)
            runtime.queue.put(ServerNotification("TurnStarted", {"turn": {"id": "t1"}}))
            await pilot.pause(0.05)
            assert app._busy
            composer.text = "/model"
            await pilot.press("enter")
            await pilot.pause(0.05)
            runtime.queue.put(ServerNotification("AgentMessageDelta", {"delta": "done"}))
            runtime.queue.put(ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed"}}))
            for _ in range(50):
                await pilot.pause(0.02)
                if not app._busy:
                    break

    asyncio.run(scenario())

    assert len(runtime.submitted) == 1
    assert runtime.submitted[0][1].kind == "UserTurn"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any("'/model' is disabled while a task is in progress." in notice for notice in notices)


def test_textual_agent_command_opens_picker_and_selects_thread() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /agent to
    #   AppEvent::OpenAgentPicker.
    # - codex-tui::app::agent_navigation owns ordered thread rows and active
    #   label projection.
    primary = "00000000-0000-0000-0000-000000000101"
    agent = "00000000-0000-0000-0000-000000000102"
    runtime = _FakeActiveThreadRuntime([])
    runtime.thread_id = primary
    runtime.primary_thread_id = primary
    runtime.agent_navigation_entries = [
        {"thread_id": primary},
        {"thread_id": agent, "agent_nickname": "Robie", "agent_role": "explorer"},
    ]
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/agent"
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert app._active_selection is not None
            assert "Select Agent" in str(popup.renderable)
            assert "Main [default]" in str(popup.renderable)
            assert "Robie [explorer]" in str(popup.renderable)

            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is None

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert app_runtime.current_displayed_thread_id() == agent
    assert app_runtime.chat_widget.active_agent_label == "Robie [explorer]"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any("Watching Robie [explorer]" in notice for notice in notices)


def test_textual_agent_command_prompts_to_enable_collab_when_no_subagents() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /agent to
    #   AppEvent::OpenAgentPicker.
    # - codex-tui::app::session_lifecycle::open_agent_picker prompts with
    #   open_multi_agent_enable_prompt when Feature::Collab is disabled and no
    #   non-primary agent thread exists.
    # Rust tests:
    # - app/tests.rs::open_agent_picker_prompts_to_enable_multi_agent_when_disabled
    # - chatwidget/tests/popups_and_settings.rs::multi_agent_enable_prompt_updates_feature_and_emits_notice
    runtime = _FakeActiveThreadRuntime([])
    runtime.features = {"Collab": False}
    runtime.session_config.features = runtime.features
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/agent"
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert app._active_selection is not None
            assert app._active_selection.kind == "multi-agent-enable"
            assert "Enable subagents?" in str(popup.renderable)
            assert "Yes, enable" in str(popup.renderable)
            assert "Not now" in str(popup.renderable)

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is None

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.features["Collab"] is True
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert "Subagents will be enabled in the next session." in notices


def test_textual_feature_adapter_resolves_multi_agent_canonical_key() -> None:
    # Rust-derived contract:
    # - codex_features::Feature::Collab has canonical key `multi_agent`.
    # - features/src/tests.rs::collab_is_legacy_alias_for_multi_agent and
    #   multi_agent_is_stable_and_enabled_by_default cover the registry.
    features = Features.from_sources(
        FeatureConfigSource(features=FeaturesToml.from_mapping({"multi_agent": False}))
    )

    assert not features.enabled(Feature.COLLAB)
    assert not _PermissionFeatureSet(features).enabled("Collab")


def test_textual_agent_command_reads_session_config_features_object() -> None:
    # Rust-derived contract:
    # - codex-cLI/exec config projects `[features].multi_agent = false` into
    #   the TUI runtime Config/Features object.
    # - codex-tui::app::session_lifecycle::open_agent_picker reads
    #   Feature::Collab from that runtime config before choosing picker vs.
    #   enable prompt.
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.features = Features.from_sources(
        FeatureConfigSource(features=FeaturesToml.from_mapping({"multi_agent": False}))
    )
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/agent"
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert app._active_selection is not None
            assert app._active_selection.kind == "multi-agent-enable"
            assert "Enable subagents?" in str(popup.renderable)

    asyncio.run(scenario())


def test_textual_agent_next_uses_agent_navigation_state() -> None:
    primary = "00000000-0000-0000-0000-000000000101"
    agent = "00000000-0000-0000-0000-000000000102"
    runtime = _FakeActiveThreadRuntime([])
    runtime.thread_id = primary
    runtime.primary_thread_id = primary
    runtime.agent_navigation_entries = [
        {"thread_id": primary},
        {"thread_id": agent, "agent_nickname": "Robie", "agent_role": "explorer"},
    ]
    app_runtime = TuiAppRuntime(runtime)
    configure_app_runtime_thread_identity(app_runtime, runtime)
    app = PyCodexTextualApp(app_runtime)

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            composer.text = "/agent next"
            await pilot.press("enter")
            await pilot.pause(0.05)

    asyncio.run(scenario())

    assert app_runtime.current_displayed_thread_id() == agent
    assert app_runtime.chat_widget.active_agent_label == "Robie [explorer]"
    assert runtime.submitted == []


def test_textual_permissions_command_opens_picker_and_applies_agent_mode_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /permissions to the
    #   chatwidget::permission_popups selection surface.
    # - Selecting a permission preset sends OverrideTurnContext plus local
    #   approval/profile/reviewer update events; it is not a UserTurn prompt.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/permissions"
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert app._active_selection is not None
            assert app._active_selection.kind == "permissions"
            rendered = str(popup.renderable)
            assert "Update Model Permissions" in rendered
            assert "Read Only" in rendered
            assert "> Default" in rendered
            assert "Full Access" in rendered

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is None
            assert str(popup.renderable) == ""

    asyncio.run(scenario())

    assert runtime.submitted
    assert runtime.submitted[0][1].kind == "OverrideTurnContext"
    assert runtime.submitted[0][1].payload["approval_policy"].value == "on-request"
    assert runtime.submitted[0][1].payload["active_permission_profile"].id == ":workspace"
    notices = [block.text for block in app._blocks if block.label == "status"]
    assert any("Permissions updated to Default" in notice for notice in notices)


def test_textual_permissions_full_access_uses_confirmation_before_override() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::permission_popups routes unacknowledged Full
    #   Access through OpenFullAccessConfirmation before applying the override.
    runtime = _FakeActiveThreadRuntime([])
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/permissions"
            await pilot.press("enter")
            await pilot.pause(0.05)
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert app._active_selection is not None
            rendered = str(popup.renderable)
            assert "Enable full access?" in rendered
            assert "> Yes, continue anyway" in rendered
            assert runtime.submitted == []

            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app._active_selection is None

    asyncio.run(scenario())

    assert runtime.submitted
    op = runtime.submitted[0][1]
    assert op.kind == "OverrideTurnContext"
    assert op.payload["approval_policy"].value == "never"
    assert op.payload["permission_profile"].has_full_disk_write_access()


def test_textual_settings_command_opens_realtime_audio_popup_without_user_turn() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /settings to
    #   chatwidget::settings_popups::open_realtime_audio_popup when realtime
    #   audio device selection is enabled.
    runtime = _FakeActiveThreadRuntime([])
    runtime.speaker_device = "Desk Speaker"
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/settings"
            await pilot.press("enter")
            await pilot.pause(0.05)

            assert app._active_selection is not None
            assert app._active_selection.kind == "settings"
            rendered = str(popup.renderable)
            assert "Settings" in rendered
            assert "> Microphone" in rendered
            assert "Speaker" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []


def test_textual_settings_device_selection_persists_device_then_opens_restart_prompt() -> None:
    # Rust-derived contract:
    # - settings_popups::OpenRealtimeAudioDeviceSelection opens a device picker.
    # - PersistRealtimeAudioDeviceSelection stores the selection and then the UI
    #   can offer the restart prompt for local realtime audio.
    runtime = _FakeActiveThreadRuntime([])

    def list_devices(kind):
        if getattr(kind, "noun", lambda: "")() == "speaker":
            return ["Desk Speaker", "Headphones"]
        return ["Studio Mic"]

    runtime.list_realtime_audio_device_names = list_devices
    app = PyCodexTextualApp(TuiAppRuntime(runtime))

    async def scenario() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            composer = app.query_one("#composer", CodexComposerTextArea)
            popup = app.query_one("#slash-popup", Static)
            composer.text = "/settings"
            await pilot.press("enter")
            await pilot.pause(0.05)

            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert "Select Speaker" in str(popup.renderable)

            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.05)
            rendered = str(popup.renderable)
            assert "Restart Speaker now?" in rendered
            assert "> Restart now" in rendered

    asyncio.run(scenario())

    assert runtime.submitted == []
    assert runtime.speaker_device == "Desk Speaker"
