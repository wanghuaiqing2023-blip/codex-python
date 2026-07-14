from __future__ import annotations

# Rust owners: codex-tui::tui, tui::event_stream, bottom_pane,
# chatwidget::model_popups, app::resize_reflow, and custom_terminal.
import io
import os
from datetime import datetime
from pathlib import Path
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pycodex.tui.tui.terminal_runtime as terminal_runtime
import pycodex.tui.chatwidget.turn_runtime as turn_runtime
import pycodex.tui.custom_terminal as custom_terminal
import pycodex.tui.transcript_reflow as transcript_reflow
from pycodex.app_server_protocol import ThreadGoal, ThreadGoalStatus
from pycodex.protocol import PermissionProfile, ReasoningEffort
from pycodex.tui.app_command import AppCommand
from pycodex.tui.chatwidget.protocol import ServerNotification, ServerRequest
from pycodex.tui.tests.harness.native_compare import vt_screen_text
from pycodex.tui.tui.event_stream import LineTerminalInputSource, TerminalInputEvent
from pycodex.tui.status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay
from pycodex.tui.tui.terminal_runtime import run_terminal_tui


@dataclass
class _ListEventStream:
    events: list[ServerNotification]
    closed: bool = False

    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        if self.events:
            return self.events.pop(0)
        self.closed = True
        return None


@dataclass
class _IdleThenEventStream:
    idle_count: int
    events: list[ServerNotification]
    on_idle: Any | None = None
    closed: bool = False

    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        if self.idle_count > 0:
            self.idle_count -= 1
            if callable(self.on_idle):
                self.on_idle()
            return None
        if self.events:
            return self.events.pop(0)
        self.closed = True
        return None


@dataclass
class _ObservingEventStream:
    events: list[ServerNotification]
    on_before_yield: Any
    index: int = 0
    closed: bool = False

    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        if self.events:
            if callable(self.on_before_yield):
                self.on_before_yield(self.index)
            self.index += 1
            return self.events.pop(0)
        self.closed = True
        return None


class _FakeActiveThreadRuntime:
    thread_id = "primary"
    cwd = "."

    def __init__(self, events: list[ServerNotification], *, model_details: tuple[str, ...] = ("high",)) -> None:
        self.events = events
        self.submitted: list[tuple[str, AppCommand]] = []
        self.shutdowns: list[str] = []

        self.resume_rows: list[Any] = []

        self.resumed_targets: list[Any] = []
        self.model_details = model_details
        self.status_model_details = model_details
        self.session_config = SimpleNamespace(
            model="gpt-test",
            model_details=model_details,
            status_model_details=model_details,
            model_reasoning_effort="high",
            cwd=".",
        )

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> _ListEventStream:
        self.submitted.append((thread_id, op))
        return _ListEventStream(list(self.events))

    def shutdown_thread(self, thread_id: str) -> _ListEventStream:
        self.shutdowns.append(thread_id)
        return _ListEventStream([])

    def list_resume_threads(self) -> tuple[Any, ...]:
        return tuple(self.resume_rows)

    def resume_thread_target(self, target: Any) -> Any:
        self.resumed_targets.append(target)
        return SimpleNamespace(
            thread_id=target.thread_id,
            session=SimpleNamespace(thread_id=target.thread_id, cwd="."),
            turns=(),
        )


class _ApprovalEventStream:
    def __init__(self) -> None:
        self.events: list[object] = [
            ServerNotification("TurnStarted", {"turn": {"id": "turn-approval"}}),
            ServerRequest(
                "CommandExecutionRequestApproval",
                id="approval-1",
                params={
                    "call_id": "call-1",
                    "approval_id": "approval-1",
                    "thread_id": "primary",
                    "turn_id": "turn-approval",
                    "started_at_ms": 1,
                    "command": ["Set-Content hello.txt hi"],
                    "cwd": ".",
                    "reason": "write fixture",
                    "available_decisions": ["accept", "cancel"],
                },
            ),
        ]
        self.closed = False

    def next_event(self, timeout: float | None = None) -> object | None:
        del timeout
        return self.events.pop(0) if self.events else None


class _InteractiveApprovalRuntime(_FakeActiveThreadRuntime):
    def __init__(self) -> None:
        super().__init__([])
        self.turn_stream = _ApprovalEventStream()

    def submit_thread_op(self, thread_id: str, op: AppCommand):
        self.submitted.append((thread_id, op))
        if op.kind == "UserTurn":
            return self.turn_stream
        if op.kind == "ExecApproval":
            self.turn_stream.events.append(
                ServerNotification(
                    "TurnCompleted",
                    {"turn": {"id": "turn-approval", "status": "Completed"}},
                )
            )
        return _ListEventStream([])


class _InteractiveRequestRuntime(_FakeActiveThreadRuntime):
    def __init__(self, request: ServerRequest, terminal_op: str) -> None:
        super().__init__([])
        self.terminal_op = terminal_op
        self.turn_stream = _ListEventStream(
            [
                ServerNotification("TurnStarted", {"turn": {"id": "turn-request"}}),
                request,
            ]
        )

    def submit_thread_op(self, thread_id: str, op: AppCommand):
        self.submitted.append((thread_id, op))
        if op.kind == "UserTurn":
            return self.turn_stream
        if op.kind == self.terminal_op:
            self.turn_stream.events.append(
                ServerNotification(
                    "TurnCompleted",
                    {"turn": {"id": "turn-request", "status": "Completed"}},
                )
            )
        return _ListEventStream([])


class _AssertingSubmitRuntime(_FakeActiveThreadRuntime):
    def __init__(self, events: list[ServerNotification], stdout: io.StringIO) -> None:
        super().__init__(events)
        self.stdout = stdout
        self.output_before_submit = ""

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> _ListEventStream:
        self.output_before_submit = self.stdout.getvalue()
        assert "Working (0s" in self.output_before_submit
        return super().submit_thread_op(thread_id, op)


class _IdleSubmitRuntime(_FakeActiveThreadRuntime):
    def __init__(
        self,
        events: list[ServerNotification],
        *,
        idle_count: int,
        on_idle: Any | None = None,
    ) -> None:
        super().__init__(events)
        self.idle_count = idle_count
        self.on_idle = on_idle

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> _IdleThenEventStream:
        self.submitted.append((thread_id, op))
        return _IdleThenEventStream(self.idle_count, list(self.events), self.on_idle)


class _ObservingSubmitRuntime(_FakeActiveThreadRuntime):
    def __init__(self, events: list[ServerNotification], on_before_yield: Any) -> None:
        super().__init__(events)
        self.on_before_yield = on_before_yield

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> _ObservingEventStream:
        self.submitted.append((thread_id, op))
        return _ObservingEventStream(list(self.events), self.on_before_yield)


class _QueuedSubmitRuntime(_FakeActiveThreadRuntime):
    def __init__(self, event_batches: list[list[ServerNotification]]) -> None:
        super().__init__([])
        self.event_batches = [list(batch) for batch in event_batches]

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> _ListEventStream:
        self.submitted.append((thread_id, op))
        events = self.event_batches.pop(0) if self.event_batches else []
        return _ListEventStream(events)


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class _FakeTerminalInputSource:
    def __init__(self, events: list[Any]) -> None:
        self.events = events

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        if not self.events:
            return TerminalInputEvent("eof")
        event = self.events.pop(0)
        if callable(event):
            return event()
        return event


def _patch_terminal_input_source(monkeypatch: Any, source: Any) -> None:
    monkeypatch.setattr(
        terminal_runtime,
        "TerminalInputSourceProvider",
        lambda stdin: SimpleNamespace(get=lambda: source),
    )


def test_terminal_runtime_turn_input_arbitrates_interrupt_without_losing_text(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f:
    # chatwidget::interaction::on_ctrl_c gives BottomPane first refusal, then
    # submits AppCommand::Interrupt while cancellable work is active.
    # tui::event_stream preserves non-interrupt input ordering.
    monkeypatch.setattr(
        custom_terminal.shutil,
        "get_terminal_size",
        lambda fallback: os.terminal_size((96, 24)),
    )
    monkeypatch.setattr(
        custom_terminal,
        "terminal_size",
        lambda: os.terminal_size((96, 24)),
    )
    monkeypatch.setattr(
        terminal_runtime,
        "terminal_size",
        lambda: os.terminal_size((96, 24)),
    )
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "你"),
            TerminalInputEvent("interrupt"),
        ]
    )
    active_runtime = _FakeActiveThreadRuntime([])
    app_runtime = terminal_runtime.TuiAppRuntime(active_runtime)
    runner = terminal_runtime.TerminalTuiRunner(
        app_runtime,
        stdout=_TtyStringIO(),
        stdin=_TtyStringIO(),
    )
    runner._input_source_provider = SimpleNamespace(get=lambda: source)

    text_event = runner._poll_turn_input(0.0)
    assert runner._handle_turn_input(text_event) is True
    interrupt_event = runner._poll_turn_input(0.0)
    assert runner._handle_turn_input(interrupt_event) is True

    assert [op.kind for _thread_id, op in active_runtime.submitted] == ["Interrupt"]
    composer_source = runner._get_composer_input_source()
    assert composer_source.poll(0.0) == TerminalInputEvent("text", "你")

    assert runner._handle_turn_input(TerminalInputEvent("escape")) is True
    assert [op.kind for _thread_id, op in active_runtime.submitted] == [
        "Interrupt",
        "Interrupt",
    ]


def test_terminal_runtime_ctrl_c_returns_from_side_before_interrupting(monkeypatch) -> None:
    # Fixed Rust app::input checks side_return_shortcut_matches before routing
    # Ctrl+C to chatwidget::interaction::on_ctrl_c.
    monkeypatch.setattr(
        custom_terminal.shutil,
        "get_terminal_size",
        lambda fallback: os.terminal_size((96, 24)),
    )
    monkeypatch.setattr(
        custom_terminal,
        "terminal_size",
        lambda: os.terminal_size((96, 24)),
    )
    monkeypatch.setattr(
        terminal_runtime,
        "terminal_size",
        lambda: os.terminal_size((96, 24)),
    )
    primary = "00000000-0000-0000-0000-000000000241"
    side = "00000000-0000-0000-0000-000000000242"
    active_runtime = _FakeActiveThreadRuntime([])
    app_runtime = terminal_runtime.TuiAppRuntime(active_runtime, thread_id=primary)
    app_runtime.routing_state.active_thread_id = side
    app_runtime.routing_state.primary_thread_id = primary
    app_runtime.upsert_agent_picker_thread(primary)
    app_runtime.upsert_agent_picker_thread(side, agent_nickname="Side")
    app_runtime.register_side_thread(side, primary)
    runner = terminal_runtime.TerminalTuiRunner(
        app_runtime,
        stdout=_TtyStringIO(),
        stdin=_TtyStringIO(),
    )

    assert runner._handle_turn_input(TerminalInputEvent("interrupt")) is True

    assert app_runtime.routing_state.active_thread_id == primary
    assert app_runtime.active_side_parent_thread_id() is None
    assert [op.kind for _thread_id, op in active_runtime.submitted] == []
    assert active_runtime.shutdowns == [side]


def test_terminal_runtime_resolves_active_turn_exec_approval_with_direction_keys(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f product path:
    # tui::event_stream -> chatwidget::tool_requests -> approval_overlay ->
    # ListSelectionView -> AppEventSender -> AppCommand::ExecApproval.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _InteractiveApprovalRuntime()
    stdout = _TtyStringIO("")
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "write file"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("down"),
            TerminalInputEvent("up"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(
        active_thread_runtime=runtime,
        stdout=stdout,
        stdin=_TtyStringIO(""),
    ) == 0

    approval_ops = [op for _thread_id, op in runtime.submitted if op.kind == "ExecApproval"]
    assert len(approval_ops) == 1
    assert approval_ops[0].payload["id"] == "approval-1"
    assert approval_ops[0].payload["decision"].type == "approved"
    rendered = vt_screen_text(stdout.getvalue(), rows=24, cols=96)
    assert "Would you like to run the following command?" in stdout.getvalue()
    assert "write file" in rendered
    assert rendered.count(
        "You approved codex to run 'Set-Content hello.txt hi' this time"
    ) == 1
    assert "\x1b]0;[ ! ] Action Required\x07" in stdout.getvalue()
    assert "\x1b]0;\x07" in stdout.getvalue()
    assert "\x07" in stdout.getvalue()


def test_terminal_runtime_exec_approval_fullscreen_shortcut_uses_static_pager(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f owners:
    # approval_overlay emits FullScreenApprovalRequest; app::event_dispatch
    # enters the shared alternate-screen pager and returns to the same approval.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _InteractiveApprovalRuntime()
    stdout = _TtyStringIO("")
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "write file"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("key", "ctrl+shift+a"),
            TerminalInputEvent("text", "q"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(
        active_thread_runtime=runtime,
        stdout=stdout,
        stdin=_TtyStringIO(""),
    ) == 0

    raw = stdout.getvalue()
    assert "E X E C" in raw
    assert "Set-Content hello.txt hi" in raw
    assert "\x1b[?1049h" in raw
    assert "\x1b[?1049l" in raw
    assert len([op for _thread_id, op in runtime.submitted if op.kind == "ExecApproval"]) == 1


def test_terminal_runtime_approval_resize_preserves_history_and_view_identity(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f owners:
    # bottom_pane::approval_overlay owns the active request while
    # app::resize_reflow/custom_terminal repair the changing viewport. The
    # prompt and typed decision remain canonical history across both footprint
    # growth and a physical resize during the pending approval.
    size = [os.terminal_size((96, 24))]

    def current_size() -> os.terminal_size:
        return size[0]

    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: current_size())
    monkeypatch.setattr(custom_terminal, "terminal_size", current_size)
    monkeypatch.setattr(terminal_runtime, "terminal_size", current_size)
    runtime = _InteractiveApprovalRuntime()
    stdout = _TtyStringIO("")
    snapshots: dict[str, str] = {}

    def capture_open() -> TerminalInputEvent:
        snapshots["raw_open"] = stdout.getvalue()
        snapshots["open"] = vt_screen_text(stdout.getvalue(), rows=24, cols=96)
        return TerminalInputEvent("resize")

    def resize_smaller() -> TerminalInputEvent:
        size[0] = os.terminal_size((80, 20))
        return TerminalInputEvent("resize")

    def capture_resized() -> TerminalInputEvent:
        snapshots["raw_resized"] = stdout.getvalue()
        snapshots["resized"] = vt_screen_text(stdout.getvalue(), rows=20, cols=80)
        return TerminalInputEvent("enter")

    def capture_completed() -> TerminalInputEvent:
        snapshots["completed"] = vt_screen_text(stdout.getvalue(), rows=20, cols=80)
        return TerminalInputEvent("text", "/quit")

    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "write file"),
            TerminalInputEvent("enter"),
            capture_open,
            resize_smaller,
            capture_resized,
            capture_completed,
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(
        active_thread_runtime=runtime,
        stdout=stdout,
        stdin=_TtyStringIO(""),
    ) == 0

    assert "Would you like to run the following command?" in snapshots["open"]
    assert "\u203a write file" in snapshots["raw_open"]
    assert "Would you like to run the following command?" in snapshots["resized"]
    assert "\u203a write file" in snapshots["raw_resized"]
    assert snapshots["completed"].count("\u203a write file") == 1
    assert snapshots["completed"].count("You approved codex to run") == 1
    assert "Would you like to run the following command?" not in snapshots["completed"]


def test_terminal_runtime_user_input_request_round_trips_and_records_typed_history(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f owners:
    # chatwidget::protocol_requests -> chatwidget::tool_requests ->
    # bottom_pane::push_user_input_request/request_user_input ->
    # AppCommand::UserInputAnswer -> app::app_server_requests.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    request = ServerRequest(
        "ToolRequestUserInput",
        id="rpc-user-input",
        params={
            "thread_id": "primary",
            "turn_id": "turn-request",
            "item_id": "item-question",
            "questions": [
                {
                    "id": "language",
                    "header": "Language",
                    "question": "Which language?",
                    "options": [
                        {"label": "Python", "description": "Use Python."},
                        {"label": "Rust", "description": "Use Rust."},
                    ],
                }
            ],
        },
    )
    runtime = _InteractiveRequestRuntime(request, "UserInputAnswer")
    stdout = _TtyStringIO("")
    _patch_terminal_input_source(
        monkeypatch,
        _FakeTerminalInputSource(
            [
                TerminalInputEvent("text", "ask"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("down"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("text", "/quit"),
                TerminalInputEvent("enter"),
            ]
        ),
    )

    assert run_terminal_tui(
        active_thread_runtime=runtime,
        stdout=stdout,
        stdin=_TtyStringIO(""),
    ) == 0

    answers = [op for _thread_id, op in runtime.submitted if op.kind == "UserInputAnswer"]
    assert len(answers) == 1
    assert answers[0].payload["id"] == "turn-request"
    assert answers[0].payload["response"].answers["language"].answers == ("Python",)
    rendered = vt_screen_text(stdout.getvalue(), rows=24, cols=96)
    assert "Which language?" in stdout.getvalue()
    assert "Questions 1/1 answered" in rendered
    assert rendered.count("Python") == 1
    assert "\x1b]0;[ ! ] Action Required\x07" in stdout.getvalue()
    assert "\x1b]0;\x07" in stdout.getvalue()


def test_terminal_runtime_mcp_form_elicitation_round_trips_through_shared_view(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f owners:
    # chatwidget::tool_requests::handle_elicitation_request_now ->
    # bottom_pane::mcp_server_elicitation -> AppCommand::ResolveElicitation ->
    # app::app_server_requests.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    request = ServerRequest(
        "McpServerElicitationRequest",
        request_id="rpc-mcp",
        params={
            "thread_id": "primary",
            "turn_id": "turn-request",
            "server_name": "fixture-server",
            "mode": "form",
            "message": "Allow the MCP action?",
            "requested_schema": {"type": "object", "properties": {}},
        },
    )
    runtime = _InteractiveRequestRuntime(request, "ResolveElicitation")
    stdout = _TtyStringIO("")
    _patch_terminal_input_source(
        monkeypatch,
        _FakeTerminalInputSource(
            [
                TerminalInputEvent("text", "mcp"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("text", "/quit"),
                TerminalInputEvent("enter"),
            ]
        ),
    )

    assert run_terminal_tui(
        active_thread_runtime=runtime,
        stdout=stdout,
        stdin=_TtyStringIO(""),
    ) == 0

    resolutions = [op for _thread_id, op in runtime.submitted if op.kind == "ResolveElicitation"]
    assert len(resolutions) == 1
    assert resolutions[0].payload["server_name"] == "fixture-server"
    assert resolutions[0].payload["request_id"] == "rpc-mcp"
    assert str(resolutions[0].payload["decision"]).lower().endswith("accept")
    assert "Allow the MCP action?" in stdout.getvalue()


def test_terminal_runtime_mcp_url_elicitation_uses_app_link_view_and_resolves(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f owners:
    # chatwidget::tool_requests first tries AppLinkViewParams for URL
    # elicitation; app_link_view emits OpenUrlInBrowser and then the typed
    # ResolveElicitation decision through the app event executor.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    opened: list[str] = []
    monkeypatch.setattr("pycodex.tui.app.runtime.webbrowser.open", lambda url: opened.append(url) or True)
    request = ServerRequest(
        "McpServerElicitationRequest",
        request_id="rpc-mcp-url",
        params={
            "thread_id": "primary",
            "turn_id": "turn-request",
            "server_name": "fixture-server",
            "mode": "url",
            "message": "Complete the external action.",
            "url": "https://example.com/action",
            "elicitation_id": "external-action",
        },
    )
    runtime = _InteractiveRequestRuntime(request, "ResolveElicitation")
    stdout = _TtyStringIO("")
    _patch_terminal_input_source(
        monkeypatch,
        _FakeTerminalInputSource(
            [
                TerminalInputEvent("text", "mcp url"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("text", "/quit"),
                TerminalInputEvent("enter"),
            ]
        ),
    )

    assert run_terminal_tui(
        active_thread_runtime=runtime,
        stdout=stdout,
        stdin=_TtyStringIO(""),
    ) == 0

    assert opened == ["https://example.com/action"]
    resolutions = [op for _thread_id, op in runtime.submitted if op.kind == "ResolveElicitation"]
    assert len(resolutions) == 1
    assert resolutions[0].payload["request_id"] == "rpc-mcp-url"
    assert str(resolutions[0].payload["decision"]).lower().endswith("accept")
    assert "Complete the external action." in stdout.getvalue()



def test_terminal_runtime_line_input_source_preserves_enter_submission() -> None:
    # Rust-derived contract:
    # - codex-tui::tui::event_stream feeds submitted input into the app loop as
    #   an event without blocking Resize redraw.
    # - The Python Windows product path uses a cooked-line adapter for IME and
    #   paste compatibility, but Enter must still produce a prompt submission
    #   event rather than relying on fragile raw-character reads.
    source = LineTerminalInputSource(io.StringIO("hello\n"))

    event = source.poll(1.0)

    assert event == TerminalInputEvent("line", "hello\n")


def test_terminal_runtime_line_input_source_submits_prompt(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::app receives submitted composer text as an input event and
    #   dispatches the turn once.
    # - The cooked-line Python product path must therefore submit a completed
    #   line through the same run loop that also handles resize redraw.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "ok"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    source = LineTerminalInputSource(io.StringIO("hello?\n/quit\n"))
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert runtime.submitted
    submitted_items = runtime.submitted[0][1].payload.get("items") or []
    assert submitted_items[0].payload.get("text") == "hello?"
    assert _user_history_insert_at(18, "\u203a hello?") in stdout.getvalue()


def test_terminal_runtime_status_command_writes_rust_status_cell_without_user_turn(monkeypatch) -> None:
    # Fixed Rust baseline 1c7832f:
    # - chatwidget::slash_dispatch dispatches SlashCommand::Status locally.
    # - chatwidget::status_controls::add_status_output gathers live state.
    # - status::card writes the composite /status history cell immediately.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.token_info = SimpleNamespace(
        total_token_usage=SimpleNamespace(total_tokens=42, input_tokens=30, output_tokens=12),
        last_token_usage=SimpleNamespace(total_tokens=50_000),
        model_context_window=200_000,
    )
    stdout = io.StringIO()
    source = LineTerminalInputSource(io.StringIO("/status\n/quit\n"))
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    transcript = _strip_ansi_controls(stdout.getvalue())
    assert runtime.submitted == []
    assert "/status" in transcript
    assert "OpenAI Codex" in transcript
    assert "Model" in transcript and "gpt-test (reasoning high)" in transcript
    assert "Token usage" in transcript and "42 total" in transcript
    assert "Context window" in transcript and "75% left" in transcript
    assert "Session" in transcript and "primary" in transcript


def test_terminal_runtime_filtered_popup_enter_dispatches_selected_command(monkeypatch) -> None:
    # bottom_pane::chat_composer must turn the highlighted /st candidate into
    # InputResult::Command(Status), not submit the incomplete text as UserTurn.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime([])
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/"),
            TerminalInputEvent("text", "s"),
            TerminalInputEvent("text", "t"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert runtime.submitted == []
    assert "/status" in _strip_ansi_controls(stdout.getvalue())


def test_terminal_runtime_raw_command_applies_mode_without_user_turn(monkeypatch) -> None:
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = terminal_runtime.TuiAppRuntime(runtime)
    stdout = io.StringIO()
    _patch_terminal_input_source(monkeypatch, LineTerminalInputSource(io.StringIO("/raw on\n/quit\n")))

    assert run_terminal_tui(active_thread_runtime=app_runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert app_runtime.chat_widget.raw_mode is True
    assert runtime.submitted == []
    assert "Raw output mode on" in _strip_ansi_controls(stdout.getvalue())


def test_terminal_runtime_copy_command_uses_last_assistant_markdown(monkeypatch) -> None:
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    copied: list[str] = []
    monkeypatch.setattr("pycodex.tui.clipboard_copy.copy_to_clipboard", lambda text: copied.append(text) or object())
    runtime = _FakeActiveThreadRuntime([])
    app_runtime = terminal_runtime.TuiAppRuntime(runtime)
    app_runtime.chat_widget.transcript.last_agent_markdown = "assistant markdown"
    stdout = io.StringIO()
    _patch_terminal_input_source(monkeypatch, LineTerminalInputSource(io.StringIO("/copy\n/quit\n")))

    assert run_terminal_tui(active_thread_runtime=app_runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert copied == ["assistant markdown"]
    assert runtime.submitted == []
    assert "Copied last message" in _strip_ansi_controls(stdout.getvalue())


def test_terminal_runtime_mention_seeds_composer_without_submitting_command(monkeypatch) -> None:
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [ServerNotification("TurnStarted", {}), ServerNotification("TurnCompleted", {})]
    )
    stdout = io.StringIO()
    _patch_terminal_input_source(
        monkeypatch,
        LineTerminalInputSource(io.StringIO("/mention\nREADME.md\n/quit\n")),
    )

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert len(runtime.submitted) == 1
    submitted_items = runtime.submitted[0][1].payload.get("items") or []
    assert submitted_items[0].payload.get("text") == "@README.md"


def test_terminal_runtime_inline_plan_submits_in_plan_collaboration_mode(monkeypatch) -> None:
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [ServerNotification("TurnStarted", {}), ServerNotification("TurnCompleted", {})]
    )
    stdout = io.StringIO()
    _patch_terminal_input_source(
        monkeypatch,
        LineTerminalInputSource(io.StringIO("/plan inspect the parser\n/quit\n")),
    )

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert len(runtime.submitted) == 1
    operation = runtime.submitted[0][1]
    assert operation.payload["collaboration_mode"].mode.value == "plan"
    assert operation.payload["items"][0].payload["text"] == "inspect the parser"


def test_terminal_runtime_diff_command_runs_workspace_diff_without_user_turn(monkeypatch) -> None:
    from pycodex.tui.workspace_command import LocalWorkspaceCommandRunner

    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 28)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.cwd = str(Path(__file__).parents[4])
    runtime.workspace_command_runner = lambda: LocalWorkspaceCommandRunner(default_cwd=Path(runtime.session_config.cwd))
    stdout = io.StringIO()
    _patch_terminal_input_source(monkeypatch, LineTerminalInputSource(io.StringIO("/diff\n/quit\n")))

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert runtime.submitted == []
    output = _strip_ansi_controls(stdout.getvalue())
    assert "diff --git" in output or "No git changes found" in output


def test_terminal_runtime_settings_opens_bottom_pane_active_view(monkeypatch) -> None:
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime([])
    stdout = _TtyStringIO("")
    _patch_terminal_input_source(
        monkeypatch,
        _FakeTerminalInputSource([TerminalInputEvent("text", "/settings"), TerminalInputEvent("enter"), TerminalInputEvent("eof")]),
    )

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = _strip_ansi_controls(stdout.getvalue())
    assert "device selection is not enabled in this runtime" in output
    assert runtime.submitted == []


def test_terminal_runtime_resume_command_switches_the_active_thread(monkeypatch) -> None:
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime([])
    target = SimpleNamespace(thread_id="saved-thread", thread_name="saved", rollout_path=Path("saved.jsonl"))
    runtime.resume_rows = [target]
    app_runtime = terminal_runtime.TuiAppRuntime(runtime)
    stdout = io.StringIO()
    _patch_terminal_input_source(monkeypatch, LineTerminalInputSource(io.StringIO("/resume saved-thread\n/quit\n")))

    assert run_terminal_tui(active_thread_runtime=app_runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert runtime.submitted == []
    assert runtime.resumed_targets == [target]
    assert app_runtime.routing_state.active_thread_id == "saved-thread"
    assert "Resumed session saved-thread" in _strip_ansi_controls(stdout.getvalue())


def test_terminal_runtime_status_command_refreshes_chatgpt_limits_before_render(monkeypatch) -> None:
    # Fixed Rust baseline 1c7832f:
    # slash_dispatch -> status_controls::add_status_output ->
    # AppEvent::RefreshRateLimits -> finish_status_rate_limit_refresh.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 28)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.auth = SimpleNamespace(auth_mode=lambda: "chatgpt")
    runtime.original_auth = None
    runtime.provider = SimpleNamespace(requires_openai_auth=True)
    runtime.fetch_count = 0

    def fetch_account_rate_limits() -> list[RateLimitSnapshotDisplay]:
        runtime.fetch_count += 1
        return [
            RateLimitSnapshotDisplay(
                "codex",
                datetime.now().astimezone(),
                primary=RateLimitWindowDisplay(25.0, "soon", 300),
            )
        ]

    runtime.fetch_account_rate_limits = fetch_account_rate_limits
    stdout = io.StringIO()
    source = LineTerminalInputSource(io.StringIO("/status\n/quit\n"))
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    transcript = stdout.getvalue()
    assert runtime.fetch_count == 1
    assert runtime.submitted == []
    assert "5h limit" in transcript
    assert "75% left" in transcript
    assert "data not available yet" not in transcript


def test_terminal_runtime_key_stream_submits_ascii_prompt(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::tui::event_stream yields Key events for ordinary text.
    # - codex-tui::bottom_pane::chat_composer appends those chars to the draft,
    #   and Enter submits the current draft as one user turn.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "ok"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "h"),
            TerminalInputEvent("text", "e"),
            TerminalInputEvent("text", "l"),
            TerminalInputEvent("text", "l"),
            TerminalInputEvent("text", "o"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    submitted_items = runtime.submitted[0][1].payload.get("items") or []
    assert submitted_items[0].payload.get("text") == "hello"
    assert _user_history_insert_at(18, "\u203a hello") in stdout.getvalue()


def test_terminal_runtime_left_moves_real_composer_cursor_before_insertion(monkeypatch) -> None:
    # Rust product path: tui::event_stream -> BottomPane -> ChatComposer ->
    # DraftState::textarea. Left must mutate TextArea's cursor before X arrives.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "a"),
            TerminalInputEvent("text", "b"),
            TerminalInputEvent("text", "c"),
            TerminalInputEvent("left"),
            TerminalInputEvent("text", "X"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(
        active_thread_runtime=runtime,
        stdout=io.StringIO(),
        stdin=_TtyStringIO(""),
    ) == 0

    submitted_items = runtime.submitted[0][1].payload.get("items") or []
    assert submitted_items[0].payload.get("text") == "abXc"


def test_terminal_runtime_up_recalls_previous_local_submission(monkeypatch) -> None:
    # Fixed Rust product path:
    # event_stream::Key(Up) -> chat_composer -> chat_composer_history, with the
    # recalled draft submitted through the same UserTurn path on Enter.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "ok"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "history prompt"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("up"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    user_turns = [op for _thread_id, op in runtime.submitted if op.kind == "UserTurn"]
    assert len(user_turns) == 2
    assert [op.payload["items"][0].payload["text"] for op in user_turns] == [
        "history prompt",
        "history prompt",
    ]


def test_terminal_runtime_slash_popup_renders_and_moves_selection(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer syncs the command popup after
    #   each key event while editing a first-line slash command name.
    # - Up/Down is handled by command_popup before normal text submission, and
    #   Tab completes the selected command in the composer without submitting a
    #   user turn.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 28)))
    runtime = _FakeActiveThreadRuntime([])
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/"),
            TerminalInputEvent("text", "m"),
            TerminalInputEvent("down"),
            TerminalInputEvent("tab"),
            TerminalInputEvent("eof"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    assert "/model" in output
    assert "/memories" in output
    assert "\x1b[94m/memories" in output
    assert "\x1b[7m/memories" not in output
    assert runtime.submitted == []


def test_terminal_runtime_goal_feature_is_visible_in_filtered_slash_popup(monkeypatch) -> None:
    # Rust owners: chatwidget::settings projects Feature::Goals into
    # bottom_pane::command_popup before composer filtering.
    from pycodex.features import Features

    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 28)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.features = Features.with_defaults()
    stdout = io.StringIO()
    _patch_terminal_input_source(
        monkeypatch,
        _FakeTerminalInputSource(
            [
                TerminalInputEvent("text", "/"),
                TerminalInputEvent("text", "g"),
                TerminalInputEvent("eof"),
            ]
        ),
    )

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = _strip_ansi_controls(stdout.getvalue())
    assert "/goal" in output
    assert "no matches" not in output
    assert runtime.submitted == []


def test_terminal_runtime_goal_without_args_emits_one_usage_message(monkeypatch) -> None:
    # Rust owners: bottom_pane::chat_composer -> chatwidget::slash_dispatch.
    # One Enter dispatches one local command effect and must not duplicate the
    # history cell while the command popup is active.
    from pycodex.features import Features

    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 28)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.features = Features.with_defaults()
    runtime.thread_goal_get = lambda _thread_id: None
    stdout = io.StringIO()
    _patch_terminal_input_source(
        monkeypatch,
        _FakeTerminalInputSource(
            [
                TerminalInputEvent("text", "/goal"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("text", "/status"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("text", "/quit"),
                TerminalInputEvent("enter"),
            ]
        ),
    )

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = _strip_ansi_controls(stdout.getvalue())
    assert output.count("Usage: /goal <objective>") == 1
    assert output.count("No goal is currently set.") == 1


def test_terminal_runtime_goal_set_accepts_real_app_server_status_once(monkeypatch) -> None:
    # Rust boundary: app::thread_goal_actions receives
    # codex_app_server_protocol::ThreadGoalStatus, not a TUI-local enum.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 28)))
    runtime = _FakeActiveThreadRuntime([])
    calls: list[tuple[object, ...]] = []
    updated = ThreadGoal(
        thread_id="primary",
        objective="compile the sample",
        status=ThreadGoalStatus.ACTIVE,
        token_budget=None,
        tokens_used=0,
        time_used_seconds=0,
        created_at=0,
        updated_at=0,
    )
    runtime.thread_goal_get = lambda thread_id: calls.append(("get", thread_id)) or None
    runtime.thread_goal_set = lambda thread_id, **kwargs: calls.append(
        ("set", thread_id, kwargs)
    ) or updated
    runtime.goal_continuation_op = lambda goal: calls.append(("continue", goal)) or None
    stdout = io.StringIO()
    _patch_terminal_input_source(
        monkeypatch,
        _FakeTerminalInputSource(
            [
                TerminalInputEvent("text", "/goal compile the sample"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("text", "/quit"),
                TerminalInputEvent("enter"),
            ]
        ),
    )

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = _strip_ansi_controls(stdout.getvalue())
    assert "/goal failed" not in output
    assert output.count("Goal active") == 1
    assert calls == [
        ("get", "primary"),
        (
            "set",
            "primary",
            {"objective": "compile the sample", "status": "active"},
        ),
        ("continue", updated),
    ]


def test_terminal_runtime_goal_edit_uses_custom_prompt_and_updates_existing_goal(monkeypatch) -> None:
    # Rust sources:
    # - chatwidget::slash_dispatch emits OpenThreadGoalEditor for /goal edit.
    # - chatwidget::goal_menu opens CustomPromptView and preserves status/budget.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 28)))
    runtime = _FakeActiveThreadRuntime([])
    calls: list[tuple[object, ...]] = []
    current = SimpleNamespace(
        objective="旧目标",
        status=ThreadGoalStatus.PAUSED,
        token_budget=80_000,
        tokens_used=12_500,
        time_used_seconds=90,
    )
    updated = SimpleNamespace(
        objective="新计划补充目标",
        status=ThreadGoalStatus.PAUSED,
        token_budget=80_000,
        tokens_used=12_500,
        time_used_seconds=90,
    )
    runtime.thread_goal_get = lambda thread_id: calls.append(("get", thread_id)) or current
    runtime.thread_goal_set = lambda thread_id, **kwargs: calls.append(
        ("set", thread_id, kwargs)
    ) or updated
    runtime.goal_continuation_op = lambda goal: calls.append(("continue", goal)) or None
    stdout = _TtyStringIO("")
    _patch_terminal_input_source(
        monkeypatch,
        _FakeTerminalInputSource(
            [
                TerminalInputEvent("text", "/goal edit"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("home"),
                TerminalInputEvent("delete"),
                TerminalInputEvent("text", "新计划"),
                TerminalInputEvent("paste", "补充"),
                TerminalInputEvent("enter"),
                TerminalInputEvent("eof"),
            ]
        ),
    )

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert calls == [
        ("get", "primary"),
        (
            "set",
            "primary",
            {
                "objective": "新计划补充目标",
                "status": "paused",
                "token_budget": 80_000,
            },
        ),
        ("continue", updated),
    ]
    assert runtime.submitted == []
    output = _strip_ansi_controls(stdout.getvalue())
    assert "Edit goal" in output
    assert "旧目标" in output
    assert "Goal paused" in output
    assert "OpenAI Codex" in output
    assert runtime.submitted == []


def test_terminal_runtime_model_command_opens_bottom_pane_selection_view(monkeypatch) -> None:
    # Rust-derived contract:
    # - /model is a local chatwidget command that opens a
    #   BottomPaneView/ListSelectionView.
    # - The model picker consumes Down/Enter before the normal composer submit
    #   path, so /model is never sent as a user turn.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.available_models = (
        SimpleNamespace(
            model="gpt-5.5",
            description="Frontier model for complex coding, research, and real-world work.",
            default_reasoning_effort="high",
            supported_reasoning_efforts=(SimpleNamespace(effort="high"),),
        ),
        SimpleNamespace(
            model="gpt-5.4",
            description="Strong model for everyday coding.",
            default_reasoning_effort="high",
            supported_reasoning_efforts=(SimpleNamespace(effort="high"),),
        ),
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/model"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("down"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    assert "Select Model and Effort" in output
    assert "Access legacy models by running codex -m <model_name> or in your config.toml" in output
    assert "\x1b[94m> 2.   gpt-5.4" in output
    assert runtime.submitted == []


def test_terminal_runtime_model_popup_repaints_history_viewport_when_footprint_grows(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane owns active popup/view footprint.
    # - codex-tui::app::resize_reflow repaints the transcript viewport when
    #   that footprint changes so opening /model does not blank prior history.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "ok"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    runtime.session_config.available_models = (
        SimpleNamespace(
            model="gpt-5.5",
            description="Frontier model for complex coding, research, and real-world work.",
            default_reasoning_effort="high",
            supported_reasoning_efforts=(SimpleNamespace(effort="high"),),
        ),
        SimpleNamespace(
            model="gpt-5.4",
            description="Strong model for everyday coding.",
            default_reasoning_effort="high",
            supported_reasoning_efforts=(SimpleNamespace(effort="high"),),
        ),
    )
    stdout = io.StringIO()
    snapshots: dict[str, str] = {}

    def capture_after_model_popup() -> TerminalInputEvent:
        snapshots["model_popup"] = vt_screen_text(stdout.getvalue(), rows=24, cols=96)
        return TerminalInputEvent("eof")

    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "hello?"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/model"),
            TerminalInputEvent("enter"),
            capture_after_model_popup,
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    screen = snapshots["model_popup"]
    assert "Select Model and Effort" in screen
    assert "\u203a hello?" in screen
    assert "\u2022 ok" in screen


def test_terminal_runtime_model_command_pushes_reasoning_selection_view(monkeypatch) -> None:
    # Rust-derived contract:
    # - chatwidget::model_popups opens a child reasoning ListSelectionView for
    #   models with multiple supported reasoning efforts.
    # - The real-terminal path must keep that parent/child flow in the
    #   bottom-pane active-view stack, so Down/Enter on the reasoning popup is
    #   handled before normal composer submission.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.available_models = (
        SimpleNamespace(
            model="gpt-5.5",
            description="Frontier model for complex coding, research, and real-world work.",
            default_reasoning_effort="high",
            supported_reasoning_efforts=(SimpleNamespace(effort="high"),),
        ),
        SimpleNamespace(
            model="gpt-5.4",
            description="Strong model for everyday coding.",
            default_reasoning_effort=ReasoningEffort.MEDIUM,
            supported_reasoning_efforts=(
                SimpleNamespace(effort=ReasoningEffort.MEDIUM, description="Balanced reasoning."),
                SimpleNamespace(effort=ReasoningEffort.HIGH, description="Deeper reasoning."),
            ),
        ),
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/model"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("down"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("down"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    assert "Select Model and Effort" in output
    assert "Select Reasoning Level for gpt-5.4" in output
    assert "\x1b[94m> 2.   High" in output
    assert runtime.session_config.model == "gpt-5.4"
    assert runtime.session_config.model_reasoning_effort == "high"
    assert runtime.submitted == []


def test_terminal_runtime_model_reasoning_selection_updates_footer_details(monkeypatch) -> None:
    # Rust-derived contract:
    # - bottom_pane footer/status surfaces may display resolved runtime
    #   model_details.
    # - Selecting a model reasoning level must update those resolved details
    #   through the shared app/runtime state path, so the footer does not keep
    #   showing the previous effort.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.available_models = (
        SimpleNamespace(
            model="gpt-5.5",
            description="Frontier model for complex coding, research, and real-world work.",
            default_reasoning_effort=ReasoningEffort.HIGH,
            supported_reasoning_efforts=(SimpleNamespace(effort=ReasoningEffort.HIGH),),
        ),
        SimpleNamespace(
            model="gpt-5.4",
            description="Strong model for everyday coding.",
            default_reasoning_effort=ReasoningEffort.MEDIUM,
            supported_reasoning_efforts=(
                SimpleNamespace(effort=ReasoningEffort.LOW, description="Fast responses with lighter reasoning"),
                SimpleNamespace(effort=ReasoningEffort.MEDIUM, description="Balanced reasoning."),
                SimpleNamespace(effort=ReasoningEffort.HIGH, description="Deeper reasoning."),
            ),
        ),
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/model"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("down"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("up"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    assert "Select Reasoning Level for gpt-5.4" in output
    assert "gpt-5.4 low" in output
    assert "gpt-5.4 high" not in output
    assert runtime.session_config.model == "gpt-5.4"
    assert runtime.session_config.model_reasoning_effort == "low"
    assert runtime.session_config.model_details == ("low",)
    assert runtime.submitted == []


def test_terminal_runtime_model_reasoning_text_enter_updates_footer_from_low_to_medium(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::tui::event_stream may surface platform Enter payloads in
    #   crossterm-like key records, but active BottomPaneView handling must
    #   still accept the selected row and update app/runtime model details.
    # - This protects the real Windows terminal path where choosing a reasoning
    #   level after /model must refresh the bottom footer after Enter.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _FakeActiveThreadRuntime([], model_details=("low",))
    runtime.model_details = ("low",)
    runtime.status_model_details = ("low",)
    runtime.model_reasoning_effort = "low"
    runtime.session_config.model = "gpt-5.4"
    runtime.session_config.model_reasoning_effort = "low"
    runtime.session_config.available_models = (
        SimpleNamespace(
            model="gpt-5.5",
            description="Frontier model for complex coding, research, and real-world work.",
            default_reasoning_effort=ReasoningEffort.HIGH,
            supported_reasoning_efforts=(SimpleNamespace(effort=ReasoningEffort.HIGH),),
        ),
        SimpleNamespace(
            model="gpt-5.4",
            description="Strong model for everyday coding.",
            default_reasoning_effort=ReasoningEffort.MEDIUM,
            supported_reasoning_efforts=(
                SimpleNamespace(effort=ReasoningEffort.LOW, description="Fast responses with lighter reasoning"),
                SimpleNamespace(effort=ReasoningEffort.MEDIUM, description="Balanced reasoning."),
                SimpleNamespace(effort=ReasoningEffort.HIGH, description="Deeper reasoning."),
            ),
        ),
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/model"),
            TerminalInputEvent("text", "\r"),
            TerminalInputEvent("text", "\r"),
            TerminalInputEvent("down"),
            TerminalInputEvent("text", "\r"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    assert "Select Reasoning Level for gpt-5.4" in output
    assert output.rfind("gpt-5.4 medium") > output.rfind("Select Reasoning Level for gpt-5.4")
    assert output.rfind("gpt-5.4 medium") > output.rfind("gpt-5.4 low")
    assert runtime.session_config.model == "gpt-5.4"
    assert runtime.session_config.model_reasoning_effort == "medium"
    assert runtime.session_config.model_details == ("medium",)
    assert runtime.model_details == ("medium",)
    assert runtime.submitted == []


def test_terminal_runtime_repaints_final_history_viewport_after_model_selection(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::insert_history retains finalized user and assistant history
    #   cells as the source of truth.
    # - codex-tui::app::resize_reflow repairs the visible history viewport
    #   after stream completion, while bottom_pane owns only the live rows.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "收到"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    runtime.session_config.available_models = (
        SimpleNamespace(
            model="gpt-5.5",
            description="Frontier model for complex coding, research, and real-world work.",
            default_reasoning_effort=ReasoningEffort.HIGH,
            supported_reasoning_efforts=(SimpleNamespace(effort=ReasoningEffort.HIGH),),
        ),
        SimpleNamespace(
            model="gpt-5.4",
            description="Strong model for everyday coding.",
            default_reasoning_effort=ReasoningEffort.MEDIUM,
            supported_reasoning_efforts=(
                SimpleNamespace(effort=ReasoningEffort.LOW, description="Fast responses with lighter reasoning"),
                SimpleNamespace(effort=ReasoningEffort.MEDIUM, description="Balanced reasoning."),
                SimpleNamespace(effort=ReasoningEffort.HIGH, description="Deeper reasoning."),
            ),
        ),
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/model"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("down"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("up"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "你"),
            TerminalInputEvent("text", "好"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("eof"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    screen = vt_screen_text(output, rows=24, cols=96)
    submitted_items = runtime.submitted[0][1].payload.get("items") or []
    assert submitted_items[0].payload.get("text") == "你好"
    assert runtime.session_config.model == "gpt-5.4"
    assert runtime.session_config.model_reasoning_effort == "low"
    assert "\u203a 你好" in screen
    assert "\u2022 收到" in screen


def test_terminal_runtime_keeps_user_prompt_visible_during_assistant_stream(monkeypatch) -> None:
    # Rust-derived contract:
    # - while assistant output is still streaming, the current terminal viewport
    #   is projected from retained history plus the active assistant stream.
    # - A live stream repaint must not temporarily drop the submitted user
    #   prompt from the history area above bottom_pane.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((96, 24)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    stdout = io.StringIO()
    snapshots: dict[int, str] = {}

    def capture_screen(index: int) -> None:
        snapshots[index] = vt_screen_text(stdout.getvalue(), rows=24, cols=96)

    runtime = _ObservingSubmitRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "第一段"}),
            ServerNotification("AgentMessageDelta", {"delta": "第二段"}),
            ServerNotification("TurnCompleted", {}),
        ],
        capture_screen,
    )
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "你知道我是谁吗?"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("eof"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    after_first_delta = snapshots[2]
    after_second_delta = snapshots[3]
    assert "\u203a 你知道我是谁吗?" in after_first_delta
    assert "\u2022第一段" not in after_first_delta.replace(" ", "")
    assert "\u203a 你知道我是谁吗?" in after_second_delta
    assert "\u2022第一段第二段" not in after_second_delta.replace(" ", "")


class _ResizeOnFirstReadTtyStringIO(_TtyStringIO):
    def __init__(self, initial_value: str, on_first_read: Any) -> None:
        super().__init__(initial_value)
        self.on_first_read = on_first_read
        self.did_resize = False

    def readline(self, *args: Any, **kwargs: Any) -> str:
        line = super().readline(*args, **kwargs)
        if not self.did_resize and callable(self.on_first_read):
            self.did_resize = True
            self.on_first_read()
        return line


def _strip_ansi_controls(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text).replace("\r", "")


def _history_insert_at(row: int, text: str, *, bottom: int | None = None) -> str:
    """Rust codex-tui::insert_history shape: scroll-region, cursor, CRLF, text."""

    region_bottom = row if bottom is None else bottom
    return f"\x1b[1;{region_bottom}r\x1b[{row};1H\r\n{text}"


def _user_history_insert_at(row: int, text: str, *, bottom: int | None = None) -> str:
    """Rust history_cell::UserHistoryCell includes leading/trailing blank rows."""

    return _history_insert_at(row, f"\r\n{text}\r\n", bottom=bottom)


RUST_RESIZE_CLEAR_MARKER = "\x1b[r\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[H"


def test_terminal_runtime_writes_transcript_to_terminal_output() -> None:
    # Rust-derived contract:
    # - codex-tui::tui and codex-tui::insert_history keep finalized transcript
    #   text in terminal scrollback, while bottom_pane remains the live input
    #   surface.
    # - The product path must therefore write header, user input, and model
    #   output as ordinary terminal text instead of only rendering a retained
    #   terminal transcript widget.
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    stdin = io.StringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert ">_ OpenAI Codex" in output
    assert "\u203a hello?" in output
    assert "\u2022 hello from model" in output
    assert "you\n" not in output
    assert "codex\n" not in output
    assert runtime.submitted


def test_terminal_runtime_inserts_blank_line_between_history_cells(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::history_cell::base::CompositeHistoryCell inserts a blank
    #   Line between non-empty display parts.
    # - codex-tui::chatwidget::tests::status_and_layout snapshots show
    #   history cells separated by a blank row while live bottom_pane status
    #   remains outside insert_history.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    user_index = output.find(_user_history_insert_at(18, "\u203a hello?"))
    assistant_index = output.find("\u2022 hello from model", user_index)
    assert user_index >= 0
    assert user_index < assistant_index
    assert "\x1b[2K" in output[user_index:assistant_index]

    normalized = _strip_ansi_controls(output)
    assert "\n\u2022 Working (" not in normalized


def test_terminal_runtime_retry_error_is_live_status_not_history() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::protocol handles retryable Error notifications
    #   through on_stream_error rather than insert_history.
    # - codex-tui::chatwidget::streaming::on_stream_error updates the
    #   bottom_pane status indicator with the reconnect header/details.
    # - codex-tui::chatwidget::tests::status_and_layout::
    #   stream_error_updates_status_indicator asserts no history insertion for
    #   "Reconnecting... 2/5".
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification(
                "Error",
                {
                    "will_retry": True,
                    "error": {
                        "message": "Reconnecting... 2/5",
                        "additional_details": "Idle timeout waiting for SSE",
                    },
                },
            ),
            ServerNotification("AgentMessageDelta", {"delta": "recovered"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    stdin = io.StringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert "\r\x1b[2K\u2022 Reconnecting... 2/5 \u2514 Idle timeout waiting for SSE" in output
    assert "\n\u2022 Reconnecting... 2/5" not in output
    assert "elapsed" not in output
    assert "\u2022 recovered" in output


def test_terminal_runtime_review_popup_submits_review_operation_not_user_turn(monkeypatch) -> None:
    # Rust baseline 1c7832f: chatwidget::slash_dispatch -> review_popups;
    # selecting "Review uncommitted changes" emits AppCommand::Review.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 30)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((100, 30)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((100, 30)))
    runtime = _FakeActiveThreadRuntime([])
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/review"), TerminalInputEvent("enter"),
            TerminalInputEvent("down"), TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"), TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)
    stdout = io.StringIO()

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert [op.kind for _, op in runtime.submitted] == ["Review"]
    assert runtime.submitted[0][1].payload["target"].type == "uncommittedChanges"


def test_terminal_runtime_permissions_popup_applies_selection_without_user_turn(monkeypatch, tmp_path) -> None:
    # Rust baseline 1c7832f: slash_dispatch -> permission_popups ->
    # permissions_menu -> AppEvent::SelectPermissionProfile.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 30)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((100, 30)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((100, 30)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.approval_policy = "on-request"
    runtime.session_config.approvals_reviewer = "user"
    runtime.session_config.active_permission_profile = ":read-only"
    runtime.session_config.codex_home = tmp_path
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/permissions"), TerminalInputEvent("enter"),
            TerminalInputEvent("down"), TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"), TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)
    stdout = io.StringIO()

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    assert [op.kind for _, op in runtime.submitted] == ["OverrideTurnContext"]
    assert runtime.session_config.active_permission_profile.id == ":workspace"
    assert runtime.session_config.permission_profile == PermissionProfile.workspace_write()
    assert "\u2022 Permissions updated to Default" in _strip_ansi_controls(stdout.getvalue())


def test_terminal_runtime_keymap_popup_completes_live_edit_flow(monkeypatch, tmp_path) -> None:
    # Rust baseline 1c7832f: slash_dispatch -> chatwidget::keymap_picker ->
    # keymap_setup::picker, rendered as an active BottomPaneView.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((110, 32)))
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((110, 32)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((110, 32)))
    runtime = _FakeActiveThreadRuntime([])
    runtime.session_config.tui_keymap = {}
    runtime.session_config.codex_home = tmp_path
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/keymap"), TerminalInputEvent("enter"),
            TerminalInputEvent("enter"), TerminalInputEvent("enter"),
            TerminalInputEvent("key", "f12"), TerminalInputEvent("escape"),
            TerminalInputEvent("text", "/quit"), TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)
    stdout = io.StringIO()

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    assert "Keymap" in output
    assert "All configurable shortcuts" in output
    assert runtime.submitted == []
    assert "f12" in repr(runtime.session_config.tui_keymap).lower()


def test_terminal_runtime_terminal_footer_is_live_not_history(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::footer renders model/cwd/status in the live
    #   bottom pane, separate from insert_history transcript cells.
    # - codex-tui::insert_history constrains scrolling to the history region
    #   above the composer, so footer text never lands in scrollback.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert "\x1b[1;20r" in output
    assert "\x1b[21;1H\x1b[2K" in output
    assert "\x1b[22;1H\x1b[2K" in output
    assert "\x1b[23;1H\x1b[2K" in output
    assert "\x1b[24;1H\x1b[2K" in output
    assert "\x1b[22;1H\u203a" in output
    assert "\x1b[2K" in output
    assert "gpt-test high" in output
    footer_index = output.rfind("\x1b[24;1Hgpt-test high")
    assert footer_index >= 0
    assert re.search(r"\x1b\[22;\d+H", output[footer_index:])
    assert "\ngpt-test high" not in output
    assert output.count(_user_history_insert_at(18, "\u203a hello?")) == 1
    assert "\x1b[1;18r\x1b[18;1H\u203a hello?" not in output
    assert "\u2022 hello from model" in output
    assert "gpt-test high fast" not in output


def test_terminal_runtime_bottom_pane_reserves_rust_spacing(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::BottomPane::as_renderable_with_composer_right_reserve
    #   inserts live bottom-pane spacing instead of placing composer/footer
    #   directly against history.
    # - codex-tui::bottom_pane::chat_composer::
    #   desired_height_with_textarea_right_reserve reserves textarea + padding
    #   + footer height, so insert_history writes above that footprint.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))

    stdout = io.StringIO()
    runtime = _AssertingSubmitRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ],
        stdout,
    )

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("hello?\n/quit\n")) == 0

    output = stdout.getvalue()
    assert "\x1b[1;20r" in output
    assert "\x1b[21;1H\x1b[2K" in output
    assert "\x1b[22;1H\u203a" in output
    assert "\x1b[23;1H\x1b[2K" in output
    assert "\x1b[24;1Hgpt-test high" in output

    before_submit = runtime.output_before_submit
    assert "\x1b[1;18r" in before_submit
    assert "\x1b[19;1H\u2022 Working (0s \u2022 esc to interrupt)" in before_submit
    assert "\x1b[20;1H\x1b[2K" in before_submit
    assert "\x1b[21;1H\x1b[2K" in before_submit
    assert "\x1b[22;1H\u203a" in before_submit
    assert "\x1b[23;1H\x1b[2K" in before_submit
    assert "\x1b[24;1Hgpt-test high" in before_submit


def test_terminal_runtime_terminal_footer_includes_fast_model_detail(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::tests::status_and_layout::
    #   status_line_model_with_reasoning_includes_fast_for_fast_capable_models
    #   expects the passive footer/status surface to show the resolved fast
    #   service tier beside model and reasoning effort.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ],
        model_details=("high", "fast"),
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert "\x1b[24;1Hgpt-test high fast · ~" in output
    assert "gpt-test high fast fast" not in output


def test_terminal_runtime_turn_completion_keeps_latest_prompt_and_answer_visible(monkeypatch) -> None:
    # Rust owner/source:
    # codex-tui::app::agent_message_consolidation replaces transient streaming
    # cells before the normal frame draw. app::resize_reflow is not required to
    # make the finalized prompt/answer visible.
    monkeypatch.setattr(
        custom_terminal.shutil,
        "get_terminal_size",
        lambda fallback: os.terminal_size((96, 24)),
    )
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: os.terminal_size((96, 24)))
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: os.terminal_size((96, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "final answer"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    snapshots: dict[str, str] = {}

    def capture_after_completion() -> TerminalInputEvent:
        snapshots["screen"] = vt_screen_text(stdout.getvalue(), rows=24, cols=96)
        return TerminalInputEvent("eof")

    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "latest question"),
            TerminalInputEvent("enter"),
            capture_after_completion,
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    screen = snapshots["screen"]
    assert screen.count("latest question") == 1
    assert screen.count("final answer") == 1
    assert "gpt-test high" in screen


def test_terminal_runtime_finalized_tail_does_not_leave_partial_status_card(monkeypatch) -> None:
    # Rust owner/source: status::card creates one composite history cell;
    # app::agent_message_consolidation and insert_history keep cell boundaries
    # when the following finalized turn becomes the visible transcript tail.
    size = os.terminal_size((80, 14))
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: size)
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: size)
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: size)
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification(
                "AgentMessageDelta",
                {"delta": "answer one\nanswer two\nanswer three\nanswer four"},
            ),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    snapshots: dict[str, str] = {}

    def capture_after_completion() -> TerminalInputEvent:
        snapshots["screen"] = vt_screen_text(stdout.getvalue(), rows=size.lines, cols=size.columns)
        return TerminalInputEvent("eof")

    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "/status"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "latest question"),
            TerminalInputEvent("enter"),
            capture_after_completion,
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    screen = snapshots["screen"]
    assert "latest question" in screen
    assert "answer one" in screen and "answer four" in screen
    assert "Context window:" not in screen
    assert "┘" not in screen


def test_terminal_runtime_repaints_bottom_pane_after_terminal_resize(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::tui::event_stream maps crossterm resize events to
    #   TuiEvent::Resize.
    # - codex-tui::app::handle_tui_event handles Resize like Draw and asks
    #   Tui::draw_with_resize_reflow to recompute the inline viewport before
    #   rendering the bottom pane.
    # - The scrollback product path must therefore clear the previous bottom
    #   pane footprint, rebuild the scroll region, and repaint composer/footer
    #   at the new terminal rows after a Windows Terminal resize/maximize.
    monkeypatch.setattr(transcript_reflow, "TRANSCRIPT_REFLOW_DEBOUNCE", 0)
    current_size = [os.terminal_size((80, 24))]
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: current_size[0])

    def resize_terminal() -> TerminalInputEvent:
        current_size[0] = os.terminal_size((100, 30))
        return TerminalInputEvent("resize")

    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            resize_terminal,
            TerminalInputEvent("text", "hello?"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)
    stdin = _TtyStringIO("")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert "\x1b[21;1H\x1b[2K" in output
    assert "\x1b[22;1H\x1b[2K" in output
    assert "\x1b[23;1H\x1b[2K" in output
    assert "\x1b[24;1H\x1b[2K" in output
    assert "\x1b[27;1H\x1b[2K" in output
    assert "\x1b[28;1H\x1b[2K" in output
    assert "\x1b[29;1H\x1b[2K" in output
    assert "\x1b[30;1H\x1b[2K" in output
    assert "\x1b[28;1H\u203a hello?" in output
    assert "\x1b[30;1Hgpt-test high" in output
    assert "\x1b[1;26r" in output
    assert "\x1b[28;3H" in output
    # Rust app::resize_reflow replays the complete typed transcript, including
    # session/startup cells before the user cell.
    replay_index = output.find("\x1b[1;24r\x1b[24;1H")
    user_history_index = output.find("\u203a hello?", replay_index)
    assert replay_index >= 0
    assert user_history_index > replay_index
    assert output.find("\x1b[30;1Hgpt-test high") < user_history_index


def test_terminal_runtime_resize_replays_visible_transcript_tail(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::app::resize_reflow keeps source-backed HistoryCells and
    #   re-emits transcript lines on TuiEvent::Resize.
    # - In the non-alt-screen path, clear_terminal_for_resize_replay calls
    #   clear_scrollback_and_visible_screen_ansi before insert_history rebuilds
    #   the Codex-owned scrollback from retained cells.
    monkeypatch.setattr(transcript_reflow, "TRANSCRIPT_REFLOW_DEBOUNCE", 0)
    current_size = [os.terminal_size((80, 24))]
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: current_size[0])

    def resize_terminal() -> TerminalInputEvent:
        current_size[0] = os.terminal_size((100, 30))
        return TerminalInputEvent("resize")

    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "hello?"),
            TerminalInputEvent("enter"),
            resize_terminal,
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    # Turn completion performs Rust's required consolidation replay first; the
    # last marker is the explicit terminal-resize replay under test here.
    resize_index = output.rfind(RUST_RESIZE_CLEAR_MARKER)
    assert resize_index >= 0
    resize_output = output[resize_index:]
    assert resize_output.count(">_ OpenAI Codex") == 1
    assert _history_insert_at(26, "\u256d", bottom=26) in resize_output
    assert ">_ OpenAI Codex" in resize_output
    assert "\u203a hello?" in resize_output
    assert "\u2022 hello from model" in resize_output
    assert "\x1b[28;1H\u203a " in resize_output
    assert "\x1b[30;1Hgpt-test high" in resize_output
    assert output.count(_user_history_insert_at(18, "\u203a hello?")) == 1


def test_terminal_runtime_resize_shrink_clears_stale_visible_viewport(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::app::resize_reflow::clear_terminal_for_resize_replay clears
    #   scrollback + visible terminal cells before replaying source-backed
    #   HistoryCells in the non-alt-screen path.
    # - After maximize then shrink, stale header fragments from older terminal
    #   heights must not remain mixed with the replayed transcript.
    monkeypatch.setattr(transcript_reflow, "TRANSCRIPT_REFLOW_DEBOUNCE", 0)
    current_size = [os.terminal_size((80, 24))]
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: current_size[0])

    def grow_terminal() -> TerminalInputEvent:
        current_size[0] = os.terminal_size((120, 40))
        return TerminalInputEvent("resize")

    def shrink_terminal() -> TerminalInputEvent:
        current_size[0] = os.terminal_size((80, 24))
        return TerminalInputEvent("resize")

    runtime = _FakeActiveThreadRuntime([])
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            grow_terminal,
            shrink_terminal,
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    assert output.count(RUST_RESIZE_CLEAR_MARKER) >= 2
    final_replay = output[output.rfind(RUST_RESIZE_CLEAR_MARKER) :]
    assert final_replay.count(">_ OpenAI Codex") == 1
    assert _history_insert_at(20, "\u256d", bottom=20) in final_replay
    assert "\x1b[22;1H\u203a " in final_replay
    assert "\x1b[24;1Hgpt-test high" in final_replay


def test_terminal_runtime_grow_shrink_replay_has_single_transcript_copy(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::app::resize_reflow rebuilds from source-backed HistoryCells
    #   after custom_terminal clears scrollback + visible cells.
    # - A grow-then-shrink cycle must therefore leave exactly one replayed copy
    #   of the session header and finalized transcript, not the stale viewport
    #   plus a new replay appended below it.
    monkeypatch.setattr(transcript_reflow, "TRANSCRIPT_REFLOW_DEBOUNCE", 0)
    current_size = [os.terminal_size((80, 24))]
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: current_size[0])

    def grow_terminal() -> TerminalInputEvent:
        current_size[0] = os.terminal_size((120, 40))
        return TerminalInputEvent("resize")

    def shrink_terminal() -> TerminalInputEvent:
        current_size[0] = os.terminal_size((80, 24))
        return TerminalInputEvent("resize")

    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "hello?"),
            TerminalInputEvent("enter"),
            grow_terminal,
            shrink_terminal,
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    output = stdout.getvalue()
    assert output.count(RUST_RESIZE_CLEAR_MARKER) >= 2
    final_replay = output[output.rfind(RUST_RESIZE_CLEAR_MARKER) :]
    assert final_replay.count(">_ OpenAI Codex") == 1
    assert final_replay.count("Tip: Try the Codex App") == 1
    assert final_replay.count("\u203a hello?") == 1
    assert final_replay.count("\u2022 hello from model") == 1
    assert final_replay.find("\u203a hello?") < final_replay.find("\u2022 hello from model")
    assert "\x1b[22;1H\u203a " in final_replay
    assert "\x1b[24;1Hgpt-test high" in final_replay


def test_terminal_runtime_terminal_event_loop_submits_chinese_text_once(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::tui::event_stream yields Key/Paste events to the app loop
    #   while Resize/Draw can repaint bottom_pane independently of submit.
    # - codex-tui::bottom_pane::chat_composer owns a draft buffer; pressing
    #   Enter finalizes that draft once into history.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "ok"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "\u4f60"),
            TerminalInputEvent("text", "\u597d"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)
    stdin = _TtyStringIO("")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert "\x1b[22;1H\u203a \u4f60" in output
    assert "\x1b[22;5H\u597d" in output
    assert output.count(_user_history_insert_at(18, "\u203a 你好")) == 1
    assert "\x1b[24;1Hgpt-test high" in output
    assert runtime.submitted


    submitted_items = runtime.submitted[0][1].payload.get("items") or []
    assert submitted_items[0].payload.get("text") == "你好"


def test_terminal_runtime_key_stream_submits_chinese_text_followed_by_space(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::tui::event_stream treats Space as ordinary text when it is
    #   not consumed by a popup/view key binding.
    # - Windows IME can surface candidate confirmation/continuation as a
    #   virtual Space key, so bottom_pane::chat_composer must preserve it when
    #   followed by more text. Rust submission trimming still removes trailing
    #   whitespace.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "ok"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    source = _FakeTerminalInputSource(
        [
            TerminalInputEvent("text", "\u4f60\u597d"),
            TerminalInputEvent("text", " "),
            TerminalInputEvent("text", "x"),
            TerminalInputEvent("enter"),
            TerminalInputEvent("text", "/quit"),
            TerminalInputEvent("enter"),
        ]
    )
    _patch_terminal_input_source(monkeypatch, source)

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("")) == 0

    submitted_items = runtime.submitted[0][1].payload.get("items") or []
    assert submitted_items[0].payload.get("text") == "\u4f60\u597d x"
    assert _user_history_insert_at(18, "\u203a \u4f60\u597d x") in stdout.getvalue()


def test_terminal_runtime_wraps_prefixed_history_cells_with_continuation_indent(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::history_cell message rendering reserves the prefix width
    #   when wrapping user/model cells, so continuation lines do not restart
    #   at the first terminal column.
    # - codex-tui::insert_history writes those pre-shaped lines into
    #   scrollback instead of relying on terminal natural wrapping.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((16, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "uvwxyzABCDEFGHI"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("你好世界中文换行\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert _user_history_insert_at(18, "\u203a \u4f60\u597d\u4e16\u754c\u4e2d\u6587") in output
    user_start = output.find(_user_history_insert_at(18, "\u203a \u4f60\u597d\u4e16\u754c\u4e2d\u6587"))
    assistant_start = output.find("\u2022 ", user_start)
    assert "\r\n\u203a \u6362\u884c" in output[user_start:assistant_start]
    assistant_index = output.find("\u2022 uvwxyzABCDEFG")
    assert assistant_index >= 0
    assert "\r\n  HI" in output[assistant_index:]


def test_terminal_runtime_terminal_streaming_answer_preserves_footer(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::hide_status_indicator clears only the live
    #   status indicator when final-answer streaming starts.
    # - codex-tui::chatwidget::tests::status_and_layout::
    #   streaming_final_answer_keeps_task_running_state asserts final-answer
    #   streaming hides status while the task/composer/footer remain active.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))

    stdout = io.StringIO()
    mid_stream_output: list[str] = []

    def capture_after_first_delta(index: int) -> None:
        if index == 2:
            mid_stream_output.append(stdout.getvalue())

    runtime = _ObservingSubmitRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "streaming answer"}),
            ServerNotification("AgentMessageDelta", {"delta": " continues"}),
            ServerNotification("TurnCompleted", {}),
        ],
        capture_after_first_delta,
    )
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0
    assert mid_stream_output

    captured = mid_stream_output[0]
    footer_clear_index = captured.rfind("\x1b[24;1H\x1b[2K")
    footer_paint_index = captured.rfind("\x1b[24;1Hgpt-test high")
    assert footer_clear_index >= 0
    assert footer_paint_index > footer_clear_index
    assert "\x1b[22;1H\x1b[2K" in captured
    assert "\u2022 streaming answer" not in captured
    assert "Working (" not in captured[footer_paint_index:]

    output = stdout.getvalue()
    assert "\u2022 streaming answer continues" in output
    assert output.rfind("\x1b[24;1Hgpt-test high") > output.find("\u2022 streaming answer")


def test_terminal_runtime_streaming_deltas_do_not_repaint_unchanged_footer(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::custom_terminal keeps previous/current frame buffers and
    #   only writes changed cells while the active answer stream redraws.
    # - The scrollback product path must preserve that frame diff contract, so
    #   later assistant deltas do not clear or repaint an unchanged footer row.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))

    stdout = io.StringIO()
    snapshots: dict[int, str] = {}

    def capture_before_event(index: int) -> None:
        if index in {2, 3, 4}:
            snapshots[index] = stdout.getvalue()

    runtime = _ObservingSubmitRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "one"}),
            ServerNotification("AgentMessageDelta", {"delta": " two"}),
            ServerNotification("AgentMessageDelta", {"delta": " three"}),
            ServerNotification("TurnCompleted", {}),
        ],
        capture_before_event,
    )
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    assert {2, 3, 4}.issubset(snapshots)
    first_delta_output = snapshots[2]
    second_delta_output = snapshots[3][len(first_delta_output):]
    third_delta_output = snapshots[4][len(snapshots[3]):]

    assert "\x1b[24;1Hgpt-test high" in first_delta_output
    assert "\x1b[24;1Hgpt-test high" not in second_delta_output
    assert "\x1b[24;1H\x1b[2K" not in second_delta_output
    assert "\x1b[1;1H" not in second_delta_output
    assert "\x1b[24;1Hgpt-test high" not in third_delta_output
    assert "\x1b[24;1H\x1b[2K" not in third_delta_output
    assert "\x1b[1;1H" not in third_delta_output


def test_terminal_runtime_stream_resize_replays_after_turn_complete(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::app::resize_reflow avoids corrupting in-flight rendering and
    #   replays source-backed transcript cells once the frame can be redrawn.
    # - The scrollback path must defer resize replay while assistant streaming
    #   is open, then replay the finalized assistant cell on TurnCompleted.
    current_size = [os.terminal_size((80, 24))]
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: current_size[0])

    def resize_before_turn_complete(index: int) -> None:
        if index == 2:
            current_size[0] = os.terminal_size((100, 30))

    runtime = _ObservingSubmitRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "streaming answer"}),
            ServerNotification("TurnCompleted", {}),
        ],
        resize_before_turn_complete,
    )
    stdout = io.StringIO()

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("hello?\n/quit\n")) == 0

    output = stdout.getvalue()
    resize_index = output.find(RUST_RESIZE_CLEAR_MARKER)
    assert resize_index >= 0
    resize_output = output[resize_index:]
    assert resize_output.count(">_ OpenAI Codex") == 1
    assert resize_output.count("\u203a hello?") == 1
    assert resize_output.count("\u2022 streaming answer") == 1
    assert "\x1b[28;1H\u203a " in resize_output
    assert "\x1b[30;1Hgpt-test high" in resize_output


def test_terminal_runtime_terminal_shows_working_before_blocking_submit(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::chat_composer submits input without making the
    #   bottom pane disappear.
    # - codex-tui::history_cell::UserHistoryCell is inserted above the active
    #   status/composer/footer footprint, so the status repaint cannot erase
    #   the submitted prompt.
    # - codex-tui::chatwidget::protocol/streaming show the active turn as
    #   "Working (0s \u2022 esc to interrupt)" while waiting for the first event.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    now = [100.0]
    monkeypatch.setattr(turn_runtime.time, "monotonic", lambda: now[0])

    stdout = io.StringIO()
    runtime = _AssertingSubmitRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "hello from model"}),
            ServerNotification("TurnCompleted", {}),
        ],
        stdout,
    )
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert _user_history_insert_at(18, "\u203a hello?") in runtime.output_before_submit
    assert _history_insert_at(20, "\u203a hello?") not in runtime.output_before_submit
    assert "\x1b[19;1H\x1b[2K" in runtime.output_before_submit
    assert "\x1b[20;1H\x1b[2K" in runtime.output_before_submit
    assert "\x1b[22;1H\x1b[2K" in runtime.output_before_submit
    assert "\x1b[23;1H\x1b[2K" in runtime.output_before_submit
    assert "\x1b[19;1H\u2022 Working (0s \u2022 esc to interrupt)" in runtime.output_before_submit
    assert "\x1b[22;1H\u203a " in runtime.output_before_submit
    assert "\x1b[24;1Hgpt-test high" in runtime.output_before_submit
    replay_index = runtime.output_before_submit.rfind("\x1b[1;1H\x1b[2K")
    assert replay_index >= 0
    replay = runtime.output_before_submit[replay_index:]
    user_repaint = re.search(r"\x1b\[\d+;1H\u203a hello\?", replay)
    assert user_repaint is not None
    assert "\x1b[1;1H\u203a hello?" not in replay
    assert user_repaint.start() < replay.find(
        "\x1b[19;1H\u2022 Working (0s \u2022 esc to interrupt)"
    )
    assert output.find("\u203a hello?") < output.find("Working (0s")
    assert output.find("Working (0s") < output.find("\u2022 hello from model")
    assert output.rfind("\x1b[24;1Hgpt-test high") > output.find("\u2022 hello from model")


def test_terminal_runtime_status_height_change_replays_previous_answer(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane::ensure_status_indicator requests a redraw when
    #   the active-turn status appears.
    # - codex-tui::app::resize_reflow replays retained HistoryCells above the
    #   new bottom pane footprint, so the expanded Working pane cannot erase
    #   the previous finalized assistant cell.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _QueuedSubmitRuntime(
        [
            [
                ServerNotification("TurnStarted", {}),
                ServerNotification("AgentMessageDelta", {"delta": "first answer"}),
                ServerNotification("TurnCompleted", {}),
            ],
            [
                ServerNotification("TurnStarted", {}),
                ServerNotification("AgentMessageDelta", {"delta": "second answer"}),
                ServerNotification("TurnCompleted", {}),
            ],
        ]
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("first?\nsecond?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    second_prompt_index = output.find("\u203a second?")
    second_working_index = output.find("Working (0s", second_prompt_index)
    assert second_prompt_index >= 0
    assert second_working_index > second_prompt_index

    redraw_for_second_turn = output[second_prompt_index:second_working_index]
    assert "\x1b[1;1H" in redraw_for_second_turn
    assert "\u2022 first answer" in redraw_for_second_turn
    assert "\u2022 second answer" in output[second_working_index:]


def test_terminal_runtime_terminal_refreshes_working_while_event_stream_is_idle(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::bottom_pane status is a live active-turn surface; elapsed
    #   time changes there while no history cell is inserted.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    now = [200.0]
    monkeypatch.setattr(turn_runtime.time, "monotonic", lambda: now[0])

    def advance_time() -> None:
        now[0] += 1.2

    runtime = _IdleSubmitRuntime(
        [
            ServerNotification("AgentMessageDelta", {"delta": "after idle"}),
            ServerNotification("TurnCompleted", {}),
        ],
        idle_count=2,
        on_idle=advance_time,
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert "\x1b[19;1H\u2022 Working (0s \u2022 esc to interrupt)" in output
    assert "\x1b[19;1H\u2022 Working (1s \u2022 esc to interrupt)" in output
    assert "\x1b[19;1H\u2022 Working (2s \u2022 esc to interrupt)" in output
    assert "\x1b[24;1Hgpt-test high" in output
    assert "\n\u2022 Working (1s" not in output
    assert "\u2022 after idle" in output


def test_terminal_runtime_terminal_retry_status_is_not_overwritten_by_working(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::streaming::on_stream_error owns the live
    #   reconnect status until another concrete turn event takes over.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    now = [300.0]
    monkeypatch.setattr(turn_runtime.time, "monotonic", lambda: now[0])

    def advance_time() -> None:
        now[0] += 1.2

    runtime = _IdleSubmitRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification(
                "Error",
                {
                    "will_retry": True,
                    "error": {
                        "message": "Reconnecting... 2/5",
                        "additional_details": "Request timed out",
                    },
                },
            ),
            ServerNotification("AgentMessageDelta", {"delta": "recovered"}),
            ServerNotification("TurnCompleted", {}),
        ],
        idle_count=1,
        on_idle=advance_time,
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    reconnect_index = output.find("Reconnecting... 2/5")
    recovered_index = output.find("\u2022 recovered")
    assert reconnect_index > output.find("Working (1s")
    assert recovered_index > reconnect_index
    assert "Working (2s" not in output[reconnect_index:recovered_index]
    assert "\u203a hello?" in output


def test_terminal_runtime_terminal_retry_status_stays_in_bottom_pane(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::streaming::on_stream_error renders retry status
    #   through bottom_pane::status_indicator, not insert_history.
    # - The scrollback product path must therefore paint reconnect text in the
    #   inline status row while preserving the user's finalized transcript line
    #   and footer.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((80, 24)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification(
                "Error",
                {
                    "will_retry": True,
                    "error": {
                        "message": "Reconnecting... 2/5",
                        "additional_details": "Request timed out",
                    },
                },
            ),
            ServerNotification("AgentMessageDelta", {"delta": "recovered"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("hello?\n/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert "\u203a hello?" in output
    assert "\x1b[19;1H\u2022 Reconnecting... 2/5 \u2514 Request timed out" in output
    assert "\x1b[24;1Hgpt-test high" in output
    assert "\n\u2022 Reconnecting... 2/5" not in output
    assert "\u2022 recovered" in output


def test_terminal_runtime_ctrl_t_opens_typed_transcript_overlay_and_restores_composer(monkeypatch) -> None:
    """Fixed Rust 1c7832f: app::input -> app_backtrack -> pager_overlay -> custom_terminal."""

    size = os.terminal_size((72, 18))
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: size)
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: size)
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: size)
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {}),
            ServerNotification("AgentMessageDelta", {"delta": "overlay answer"}),
            ServerNotification("TurnCompleted", {}),
        ]
    )
    stdout = io.StringIO()
    stdin = _TtyStringIO("hello\n\x14q/quit\n")

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=stdin) == 0

    output = stdout.getvalue()
    assert "\x1b[?1049h" in output
    assert "\x1b[?1007h" in output
    assert "T R A N S C R I P T" in output
    assert "hello" in output
    assert "overlay answer" in output
    assert "\x1b[?1007l" in output
    assert "\x1b[?1049l" in output
    assert len(runtime.submitted) == 1


def test_terminal_runtime_command_completion_replaces_active_cell_once(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f:
    # chatwidget/tests/exec_flow.rs::exec_history_cell_shows_working_then_completed
    # requires zero stable cells at start and one stable cell at completion.
    # chatwidget::flush_active_cell takes the mutable cell before emitting
    # AppEvent::InsertHistoryCell, so custom_terminal must clear its previous
    # live footprint before the finalized cell enters scrollback.
    size = os.terminal_size((96, 24))
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: size)
    monkeypatch.setattr(custom_terminal, "terminal_size", lambda: size)
    monkeypatch.setattr(terminal_runtime, "terminal_size", lambda: size)

    stdout = _TtyStringIO()
    app_runtime = terminal_runtime.TuiAppRuntime(_FakeActiveThreadRuntime([]))
    runner = terminal_runtime.TerminalTuiRunner(
        app_runtime,
        stdout=stdout,
        stdin=_TtyStringIO(),
    )
    runner._resize.activate_layout()
    runner._session_header.write()
    runner._startup_notices.write()

    notifications = (
        ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}),
        ServerNotification(
            "ItemStarted",
            {
                "item": {
                    "kind": "CommandExecution",
                    "id": "cmd-1",
                    "command": "echo ok",
                    "source": "Agent",
                    "status": "InProgress",
                }
            },
        ),
        ServerNotification("CommandExecutionOutputDelta", {"item_id": "cmd-1", "delta": "ok\n"}),
        ServerNotification(
            "ItemCompleted",
            {
                "turn_id": "turn-1",
                "item": {
                    "kind": "CommandExecution",
                    "id": "cmd-1",
                    "command": "echo ok",
                    "source": "Agent",
                    "status": "Completed",
                    "aggregated_output": "ok\n",
                    "exit_code": 0,
                },
            },
        ),
    )
    for notification in notifications:
        app_runtime.handle_notification(notification)
        runner._bottom_pane.render_without_resize_check()

    screen = vt_screen_text(stdout.getvalue(), rows=size.lines, cols=size.columns)
    assert screen.count("Ran echo ok") == 1
    assert "Running echo ok" not in screen
    assert sum("Ran echo ok" in cell for cell in runner._history.state.projection_cells) == 1


def test_terminal_runtime_renders_structured_complex_task_history(monkeypatch) -> None:
    # Fixed Rust commit 1c7832f: chatwidget owners emit typed cells through
    # AppEvent::InsertHistoryCell before custom_terminal projects the viewport.
    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", lambda fallback: os.terminal_size((100, 30)))
    runtime = _FakeActiveThreadRuntime(
        [
            ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}),
            ServerNotification("ReasoningSummaryTextDelta", {"delta": "**Checking** workspace"}),
            ServerNotification("ItemCompleted", {"turn_id": "turn-1", "item": {"kind": "Reasoning", "summary": []}}),
            ServerNotification("ItemStarted", {"item": {"kind": "CommandExecution", "id": "cmd-1", "command": "Get-ChildItem hello.c", "source": "Agent", "status": "InProgress"}}),
            ServerNotification("CommandExecutionOutputDelta", {"item_id": "cmd-1", "delta": "missing\n"}),
            ServerNotification("ItemCompleted", {"turn_id": "turn-1", "item": {"kind": "CommandExecution", "id": "cmd-1", "command": "Get-ChildItem hello.c", "source": "Agent", "status": "Failed", "aggregated_output": "missing\n", "exit_code": 1}}),
            ServerNotification("ItemStarted", {"item": {"kind": "FileChange", "id": "patch-1", "changes": [{"path": "hello.c", "kind": "add", "diff": "#include <stdio.h>\nint main(void) { return 0; }\n"}]}}),
            ServerNotification("ItemCompleted", {"turn_id": "turn-1", "item": {"kind": "FileChange", "id": "patch-1", "status": "Completed", "changes": []}}),
            ServerNotification("AgentMessageDelta", {"delta": "Created hello.c"}),
            ServerNotification("TurnCompleted", {"turn": {"id": "turn-1", "status": "Completed"}}),
        ]
    )
    stdout = io.StringIO()

    assert run_terminal_tui(active_thread_runtime=runtime, stdout=stdout, stdin=_TtyStringIO("build\n/quit\n")) == 0

    output = _strip_ansi_controls(stdout.getvalue())
    assert "workspace" in output
    assert "Ran Get-ChildItem hello.c" in output
    assert "missing" in output
    assert "Added hello.c (+2 -0)" in output
    assert "1 + #include <stdio.h>" in output
    assert "Created hello.c" in output
    assert "─" * 20 in output

