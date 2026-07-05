from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pycodex.tui.tui.terminal_runtime as terminal_runtime
import pycodex.tui.custom_terminal as custom_terminal
from pycodex.protocol import ReasoningEffort
from pycodex.tui.app_command import AppCommand
from pycodex.tui.chatwidget.protocol import ServerNotification
from pycodex.tui.tests.harness.native_compare import vt_screen_text
from pycodex.tui.tui.event_stream import LineTerminalInputSource, TerminalInputEvent
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
    assert _history_insert_at(18, "\u203a hello?") in stdout.getvalue()


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
    assert _history_insert_at(18, "\u203a hello") in stdout.getvalue()


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
    assert "\u2022 第一段" in after_first_delta
    assert after_first_delta.count("\u2022 第一段") == 1
    assert "\u203a 你知道我是谁吗?" in after_second_delta
    assert "\u2022 第一段第二段" in after_second_delta


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


RUST_RESIZE_CLEAR_MARKER = "\x1b[r\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[H"


def test_terminal_runtime_writes_transcript_to_terminal_output() -> None:
    # Rust-derived contract:
    # - codex-tui::tui and codex-tui::insert_history keep finalized transcript
    #   text in terminal scrollback, while bottom_pane remains the live input
    #   surface.
    # - The product path must therefore write header, user input, and model
    #   output as ordinary terminal text instead of only rendering a retained
    #   Textual transcript widget.
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
    user_index = output.find(_history_insert_at(18, "\u203a hello?"))
    gap_index = output.find(_history_insert_at(20, ""), user_index)
    assistant_index = output.find(_history_insert_at(20, "\u2022 hello from model"), gap_index + 1)
    assert user_index >= 0
    assert user_index < gap_index < assistant_index

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
    assert output.count(_history_insert_at(18, "\u203a hello?")) == 1
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
    user_history_index = output.find("\x1b[1;24r\x1b[24;1H\r\n\r\n\u203a hello?")
    assert user_history_index >= 0
    assert output.find("\x1b[30;1Hgpt-test high") < user_history_index


def test_terminal_runtime_resize_replays_visible_transcript_tail(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::app::resize_reflow keeps source-backed HistoryCells and
    #   re-emits transcript lines on TuiEvent::Resize.
    # - In the non-alt-screen path, clear_terminal_for_resize_replay calls
    #   clear_scrollback_and_visible_screen_ansi before insert_history rebuilds
    #   the Codex-owned scrollback from retained cells.
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
    resize_index = output.find(RUST_RESIZE_CLEAR_MARKER)
    assert resize_index >= 0
    resize_output = output[resize_index:]
    assert resize_output.count(">_ OpenAI Codex") == 1
    assert _history_insert_at(26, "\u256d", bottom=26) in resize_output
    assert ">_ OpenAI Codex" in resize_output
    assert "\u203a hello?" in resize_output
    assert "\u2022 hello from model" in resize_output
    assert "\x1b[28;1H\u203a " in resize_output
    assert "\x1b[30;1Hgpt-test high" in resize_output
    assert output.count(_history_insert_at(18, "\u203a hello?")) == 1


def test_terminal_runtime_resize_shrink_clears_stale_visible_viewport(monkeypatch) -> None:
    # Rust-derived contract:
    # - codex-tui::app::resize_reflow::clear_terminal_for_resize_replay clears
    #   scrollback + visible terminal cells before replaying source-backed
    #   HistoryCells in the non-alt-screen path.
    # - After maximize then shrink, stale header fragments from older terminal
    #   heights must not remain mixed with the replayed transcript.
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
    assert "\x1b[22;1H\u203a 你好" in output
    assert output.count(_history_insert_at(18, "\u203a 你好")) == 1
    assert "\x1b[24;1Hgpt-test high" in output
    assert runtime.submitted


    submitted_items = runtime.submitted[0][1].payload.get("items") or []
    assert submitted_items[0].payload.get("text") == "你好"


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
    assert _history_insert_at(18, "\u203a \u4f60\u597d\u4e16\u754c\u4e2d\u6587") in output
    assert "\r\n  换行" in output
    assert "\u2022 uvwxyzABCDEFG\r\n  HI" in output


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
    assert "\u2022 streaming answer" in captured
    assert "Working (" not in captured[footer_paint_index:]

    output = stdout.getvalue()
    assert "\u2022 streaming answer continues" in output
    assert output.rfind("\x1b[24;1Hgpt-test high") > output.find("\u2022 streaming answer")


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
    monkeypatch.setattr(terminal_runtime.time, "monotonic", lambda: now[0])

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
    assert _history_insert_at(18, "\u203a hello?") in runtime.output_before_submit
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
    assert "\x1b[18;1H\u203a hello?" in replay
    assert "\x1b[1;1H\u203a hello?" not in replay
    assert replay.find("\x1b[18;1H\u203a hello?") < replay.find(
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
    monkeypatch.setattr(terminal_runtime.time, "monotonic", lambda: now[0])

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
    monkeypatch.setattr(terminal_runtime.time, "monotonic", lambda: now[0])

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
