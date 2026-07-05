"""TUI conversation integration boundary tests.

Rust evidence:
- ``codex/codex-rs/tui/src/chatwidget/tests/status_and_layout.rs`` covers
  status-line rendering contracts.
- ``codex/codex-rs/tui/src/app/event_dispatch.rs`` applies model update app
  events before the footer/status surfaces render them.
- ``codex/codex-rs/cli/src/main.rs::run_interactive_tui`` dispatches
  interactive sessions into ``codex_tui::run_main``.

This file keeps only product-neutral runtime/status assertions that describe
the terminal TUI boundary.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
from types import SimpleNamespace

import pytest

from pycodex.tui.app.runtime import QueueActiveThreadEventStream, TuiAppRuntime
from pycodex.tui.app_event import AppEvent
from pycodex.tui.bottom_pane.status_line_setup import StatusLineItem
from pycodex.tui.runtime_projection import (
    _runtime_display_model,
    _runtime_model_with_reasoning,
    _runtime_status_line_value,
)


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_LIVE_ENV = "PYCODEX_RUN_LIVE_OAUTH_TUI"


class _TtyOutput(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flushed = False

    def isatty(self) -> bool:
        return True

    def flush(self) -> None:
        self.flushed = True
        super().flush()


def _strip_ansi(value: str) -> str:
    return _ANSI_RE.sub("", value)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class _ManualActiveThreadRuntime:
    def __init__(self, *, thread_id: str | None = None, rollout_path: Path | None = None) -> None:
        self.queue: Queue[object] = Queue()
        self.app_server_events: Queue[object] = Queue()
        self.submitted = threading.Event()
        self.thread_id = thread_id
        self.rollout_path = rollout_path
        self.ops: list[object] = []

    def submit_thread_op(self, thread_id, op):
        self.ops.append(op)
        if getattr(op, "kind", None) == "UserTurn":
            self.submitted.set()
        return QueueActiveThreadEventStream(self.queue)

    def next_app_server_event(self, timeout: float | None = 0) -> object | None:
        try:
            return self.app_server_events.get(timeout=0 if timeout is None else timeout)
        except Empty:
            return None


def _codex_home_from_env() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codex"


def _has_chatgpt_oauth_auth(codex_home: Path) -> bool:
    auth_path = codex_home / "auth.json"
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    tokens = data.get("tokens")
    if isinstance(tokens, dict) and tokens.get("id_token"):
        return True
    return isinstance(data.get("OPENAI_API_KEY"), str)


def test_terminal_status_footer_projects_context_used_without_context_window() -> None:
    # Rust source contract:
    # codex-tui::chatwidget::status_controls::status_line_context_remaining_percent
    # returns Some(100) when no context window is known, so ContextUsed remains
    # a visible "Context 0% used" item instead of being omitted.
    runtime = _ManualActiveThreadRuntime()
    runtime.session_config = SimpleNamespace(tui_status_line=["ContextUsed", "Status"])
    app_runtime = TuiAppRuntime(active_thread_runtime=runtime)

    assert _runtime_status_line_value(app_runtime, StatusLineItem.CONTEXT_USED, "Ready") == "Context 0% used"
    assert _runtime_status_line_value(app_runtime, StatusLineItem.STATUS, "Ready") == "Ready"


def test_terminal_status_footer_projects_rust_named_session_id_item_without_token_usage() -> None:
    # Rust source contract:
    # codex-tui::chatwidget::status_surfaces::status_line_value_for_item handles
    # StatusLineItem::SessionId independently from token usage fields.
    thread_id = "123e4567-e89b-12d3-a456-426614174000"
    runtime = _ManualActiveThreadRuntime(thread_id=thread_id)
    runtime.session_config = SimpleNamespace(tui_status_line=["SessionId", "Status"])
    app_runtime = TuiAppRuntime(active_thread_runtime=runtime)
    app_runtime.thread_id = thread_id
    app_runtime.routing_state.primary_thread_id = thread_id
    app_runtime.routing_state.active_thread_id = thread_id

    assert _runtime_status_line_value(app_runtime, StatusLineItem.SESSION_ID, "Ready") == thread_id
    assert _runtime_status_line_value(app_runtime, StatusLineItem.STATUS, "Ready") == "Ready"


def test_terminal_status_footer_prefers_runtime_model_details() -> None:
    # Rust product contract:
    # App/session configuration can supply the resolved visible model details
    # used by model/status surfaces; the footer should not reconstruct a
    # different value when that runtime detail is already available.
    runtime = _ManualActiveThreadRuntime(thread_id="model-thread")
    runtime.model = "gpt-live"
    runtime.session_config = SimpleNamespace(
        model="gpt-live",
        model_details=("high", "fast"),
        model_reasoning_effort="xhigh",
    )
    app_runtime = TuiAppRuntime(active_thread_runtime=runtime)

    assert _runtime_model_with_reasoning(app_runtime) == "gpt-live high fast"
    assert _runtime_status_line_value(app_runtime, StatusLineItem.MODEL_WITH_REASONING, "Ready") == "gpt-live high fast"


def test_terminal_status_footer_uses_updated_model_from_app_event() -> None:
    # Rust product contract:
    # - model popup selection emits AppEvent::UpdateModel.
    # - app::event_dispatch applies it through ChatWidget::set_model.
    # - bottom_pane::footer/status_surface_preview then render the updated
    #   model in the passive status line.
    active_runtime = _ManualActiveThreadRuntime(thread_id="model-thread")
    active_runtime.model = "gpt-old"
    app_runtime = TuiAppRuntime(active_thread_runtime=active_runtime)

    app_runtime.handle_app_event(AppEvent.update_model("gpt-new"))

    assert _runtime_display_model(app_runtime) == "gpt-new"
    footer = _runtime_status_line_value(app_runtime, StatusLineItem.MODEL_WITH_REASONING, "Ready")
    assert "gpt-new" in footer
    assert "gpt-old" not in footer


def test_cli_tui_uses_text_stdin_for_interactive_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust terminal input is character-event based. Python's interactive TUI
    # must not decode sys.stdin.buffer as UTF-8 on Windows code pages.
    from pycodex.cli import parser as cli_parser

    fake_buffer = io.BytesIO()
    fake_text_stdin = SimpleNamespace(buffer=fake_buffer, isatty=lambda: True)
    captured: dict[str, object] = {}

    monkeypatch.setattr(sys, "stdin", fake_text_stdin)
    monkeypatch.setattr(cli_parser, "_build_tui_core_active_thread_runtime", lambda parsed, *, stderr: object())

    import pycodex.tui.tui.terminal_runtime as terminal_runtime

    def fake_run_terminal_tui(**kwargs):
        captured["runtime"] = kwargs["active_thread_runtime"]
        captured["stdout"] = kwargs["stdout"]
        captured["stdin"] = kwargs["stdin"]
        return 0

    monkeypatch.setattr(terminal_runtime, "run_terminal_tui", fake_run_terminal_tui)
    stdout = _TtyOutput()

    code = cli_parser._run_tui(
        cli_parser.parse_args([]),
        stdout=stdout,
        stderr=_TtyOutput(),
        stdin=fake_buffer,
        stdin_is_terminal=True,
    )

    assert code == 0
    assert captured["stdin"] is fake_text_stdin
    assert captured["stdout"] is stdout


def test_live_oauth_tui_conversation_against_real_service() -> None:
    # Python-designed live parity smoke because upstream Rust has live CLI tests
    # and TUI terminal tests, but no combined real OAuth + interactive TUI test.
    # The old stdin-driven smoke was removed with the legacy terminal renderer;
    # real terminal live smoke should run through the ConPTY/native comparison
    # harness rather than reviving a second product path.
    if os.environ.get(_LIVE_ENV) != "1":
        pytest.skip(f"set {_LIVE_ENV}=1 to call the real service")
    codex_home = _codex_home_from_env()
    if not _has_chatgpt_oauth_auth(codex_home):
        pytest.skip(f"{codex_home / 'auth.json'} does not contain ChatGPT OAuth auth")

    completed = subprocess.run(
        [sys.executable, "-m", "pycodex"],
        cwd=_repo_root(),
        env={**os.environ, "PYCODEX_TUI_LIVE_SMOKE": "1"},
        input="hello\n/quit\n",
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    combined = _strip_ansi(completed.stdout + "\n" + completed.stderr)
    assert completed.returncode != 0
    assert "stdin is not a terminal" in combined
