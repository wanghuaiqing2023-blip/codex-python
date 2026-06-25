"""TUI conversation integration coverage.

Rust evidence:
- ``codex/codex-rs/tui/tests/suite/vt100_live_commit.rs`` covers live-row
  commit behavior inside the TUI terminal backend.
- ``codex/codex-rs/tui/tests/suite/resize_reflow.rs`` runs ignored tmux smoke
  tests with a mocked Responses SSE endpoint and dummy auth.
- ``codex/codex-rs/core/tests/suite/live_cli.rs`` provides ignored real
  OpenAI ``/v1/responses`` smoke tests for the CLI exec path.
- ``codex/codex-rs/login/tests/suite/login_server_e2e.rs`` and
  ``codex/codex-rs/core/tests/suite/client.rs::provider_auth_command_refreshes_after_401``
  cover OAuth/login and auth-refresh behavior separately.

Upstream does not currently provide a single ignored test that launches the
interactive TUI with real ChatGPT OAuth credentials against the live service, so
the final test in this file is a Python-designed parity smoke. It is opt-in to
avoid spending live quota in normal test runs.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pycodex.tui import run_terminal_tui
from pycodex.tui.app.runtime import ExecFunctionActiveThreadRuntime, QueueActiveThreadEventStream
from pycodex.tui.chatwidget.protocol import ServerNotification


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_LIVE_ENV = "PYCODEX_RUN_LIVE_OAUTH_TUI"


class _TtyInput(io.StringIO):
    def isatty(self) -> bool:
        return True


def _strip_ansi(value: str) -> str:
    return _ANSI_RE.sub("", value)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _active_thread_runtime(reply):
    return ExecFunctionActiveThreadRuntime(reply)


class _ManualActiveThreadRuntime:
    def __init__(self) -> None:
        self.queue: Queue[object] = Queue()
        self.submitted = threading.Event()

    def submit_thread_op(self, thread_id, op):
        self.submitted.set()
        return QueueActiveThreadEventStream(self.queue)


def _codex_home_from_env() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codex"


def _has_chatgpt_oauth_auth(codex_home: Path) -> bool:
    auth_path = codex_home / "auth.json"
    try:
        raw = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict):
        return False
    mode = str(raw.get("auth_mode") or raw.get("mode") or "").lower()
    tokens = raw.get("tokens")
    if not isinstance(tokens, dict):
        return False
    access_token = tokens.get("access_token")
    return "chatgpt" in mode and isinstance(access_token, str) and bool(access_token.strip())


def test_terminal_tui_error_reply_remains_visible_and_returns_exec_code() -> None:
    # Rust boundary: codex-cli/src/main.rs dispatches no-subcommand input into
    # codex_tui::run_main, and codex-tui/src/tui.rs keeps terminal output visible
    # until the app exits.
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run_terminal_tui(
        stdout=stdout,
        stderr=stderr,
        stdin=io.StringIO("trigger error\n"),
        active_thread_runtime=_active_thread_runtime(lambda _prompt: (7, "ERROR: live auth failed\nTry `codex login`.")),
    )

    output = _strip_ansi(stdout.getvalue())
    assert code == 7
    assert "you" in output
    assert "trigger error" in output
    assert "codex" in output
    assert "ERROR: live auth failed" in output
    assert "Try `codex login`." in output
    assert stderr.getvalue() == ""


def test_terminal_tui_shows_progress_while_waiting_for_model(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust boundary: codex-tui keeps a visible status surface while a turn is
    # running. Python's terminal entrypoint must not look frozen while the
    # core/model request is still in flight.
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setenv("PYCODEX_TUI_PROGRESS_INTERVAL_SECONDS", "0.01")

    def slow_reply(_prompt: str) -> tuple[int, str]:
        time.sleep(0.05)
        return 0, "done after visible progress"

    code = run_terminal_tui(
        stdout=stdout,
        stderr=stderr,
        stdin=io.StringIO("slow\n/quit\n"),
        active_thread_runtime=_active_thread_runtime(slow_reply),
    )

    output = _strip_ansi(stdout.getvalue())
    assert code == 0
    assert "waiting for model..." in output
    assert "done after visible progress" in output
    assert "status: Ready" in output
    assert stderr.getvalue() == ""


def test_terminal_tui_renders_agent_delta_before_turn_completed() -> None:
    # Source: Rust integration/source contract
    # Rust crate: codex-tui
    # Rust modules: chatwidget::streaming, chatwidget::protocol, tui terminal loop
    # Rust evidence:
    # - tui/tests/suite/vt100_live_commit.rs keeps live rows visible before commit.
    # - chatwidget/streaming.rs::handle_streaming_delta syncs the active stream tail
    #   and requests redraw before TurnCompleted.
    stdout = io.StringIO()
    stderr = io.StringIO()
    runtime = _ManualActiveThreadRuntime()
    result: dict[str, int] = {}

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "code",
            run_terminal_tui(
                stdout=stdout,
                stderr=stderr,
                stdin=io.StringIO("stream please\n/quit\n"),
                active_thread_runtime=runtime,
            ),
        ),
        daemon=True,
    )
    thread.start()

    assert runtime.submitted.wait(1.0)
    runtime.queue.put(ServerNotification("TurnStarted", {"turn": {"id": "turn-1", "thread_id": "primary"}}))
    runtime.queue.put(ServerNotification("AgentMessageDelta", {"delta": "partial live output", "thread_id": "primary"}))

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and "partial live output" not in _strip_ansi(stdout.getvalue()):
        time.sleep(0.01)

    output_before_completion = _strip_ansi(stdout.getvalue())
    assert "codex" in output_before_completion
    assert "partial live output" in output_before_completion
    assert "Type another message. /quit exits." not in output_before_completion.split("partial live output", 1)[-1]

    runtime.queue.put(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "thread_id": "primary", "status": "Completed", "duration_ms": 10}},
        )
    )
    thread.join(1.0)

    output = _strip_ansi(stdout.getvalue())
    assert result["code"] == 0
    assert output.count("partial live output") == 1
    assert "status: Ready" in output
    assert stderr.getvalue() == ""


def test_terminal_tui_waits_for_delayed_turn_started_instead_of_exiting_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    # Source: Rust source contract
    # Rust crate: codex-tui
    # Rust module: app event loop
    # Rust evidence: app.rs keeps polling the TUI/app-server event stream; an
    # empty poll interval is not the same as the active thread shutting down.
    stdout = io.StringIO()
    stderr = io.StringIO()
    runtime = _ManualActiveThreadRuntime()
    result: dict[str, int] = {}
    monkeypatch.setenv("PYCODEX_TUI_PROGRESS_INTERVAL_SECONDS", "0.01")

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "code",
            run_terminal_tui(
                stdout=stdout,
                stderr=stderr,
                stdin=io.StringIO("complex long question\n/quit\n"),
                active_thread_runtime=runtime,
            ),
        ),
        daemon=True,
    )
    thread.start()

    assert runtime.submitted.wait(1.0)
    time.sleep(0.15)
    output_while_waiting = _strip_ansi(stdout.getvalue())
    assert "delayed response" not in output_while_waiting
    assert thread.is_alive()

    runtime.queue.put(ServerNotification("TurnStarted", {"turn": {"id": "turn-1", "thread_id": "primary"}}))
    runtime.queue.put(ServerNotification("AgentMessageDelta", {"delta": "delayed response", "thread_id": "primary"}))
    runtime.queue.put(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "thread_id": "primary", "status": "Completed", "duration_ms": 25}},
        )
    )
    thread.join(1.0)

    output = _strip_ansi(stdout.getvalue())
    assert result["code"] == 0
    assert "delayed response" in output
    assert output.count("delayed response") == 1
    assert "status: Ready" in output
    assert stderr.getvalue() == ""


def test_terminal_tui_renders_reasoning_lifecycle_before_agent_text(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust source contract:
    # - codex-tui::chatwidget::protocol routes Reasoning notifications into
    #   chatwidget streaming/status state.
    # - chatwidget::streaming::on_agent_reasoning_delta and status surfaces use
    #   Thinking as a visible run-state before final answer text arrives.
    # Python's terminal entrypoint must not keep saying "waiting for model" once
    # the active thread has delivered reasoning lifecycle events.
    stdout = io.StringIO()
    stderr = io.StringIO()
    runtime = _ManualActiveThreadRuntime()
    result: dict[str, int] = {}
    monkeypatch.setenv("PYCODEX_TUI_PROGRESS_INTERVAL_SECONDS", "0.01")

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "code",
            run_terminal_tui(
                stdout=stdout,
                stderr=stderr,
                stdin=io.StringIO("complex reasoning\n/quit\n"),
                active_thread_runtime=runtime,
            ),
        ),
        daemon=True,
    )
    thread.start()

    assert runtime.submitted.wait(1.0)
    runtime.queue.put(ServerNotification("TurnStarted", {"turn": {"id": "turn-1", "thread_id": "primary"}}))
    runtime.queue.put(
        ServerNotification(
            "ItemStarted",
            {
                "thread_id": "primary",
                "turn_id": "turn-1",
                "item": {"kind": "Reasoning", "id": "reasoning-1"},
            },
        )
    )

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and "reasoning..." not in _strip_ansi(stdout.getvalue()):
        time.sleep(0.01)

    output_before_text = _strip_ansi(stdout.getvalue())
    assert "Thinking" in output_before_text
    assert "reasoning..." in output_before_text
    assert "waiting for model..." not in output_before_text.split("Thinking", 1)[-1]

    runtime.queue.put(ServerNotification("AgentMessageDelta", {"delta": "final text", "thread_id": "primary"}))
    runtime.queue.put(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "thread_id": "primary", "status": "Completed", "duration_ms": 25}},
        )
    )
    thread.join(1.0)

    output = _strip_ansi(stdout.getvalue())
    assert result["code"] == 0
    assert "final text" in output
    assert "status: Ready" in output
    assert stderr.getvalue() == ""


def test_terminal_tui_renders_reasoning_summary_header_and_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust source contract:
    # - chatwidget::streaming::on_agent_reasoning_delta extracts the first
    #   bold header from reasoning summary deltas for live status.
    # - chatwidget::streaming::on_agent_reasoning_final records transcript-only
    #   reasoning summary content at turn completion.
    stdout = io.StringIO()
    stderr = io.StringIO()
    runtime = _ManualActiveThreadRuntime()
    result: dict[str, int] = {}
    monkeypatch.setenv("PYCODEX_TUI_PROGRESS_INTERVAL_SECONDS", "0.01")

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "code",
            run_terminal_tui(
                stdout=stdout,
                stderr=stderr,
                stdin=io.StringIO("complex reasoning\n/transcript\nq\n/quit\n"),
                active_thread_runtime=runtime,
            ),
        ),
        daemon=True,
    )
    thread.start()

    assert runtime.submitted.wait(1.0)
    runtime.queue.put(ServerNotification("TurnStarted", {"turn": {"id": "turn-1", "thread_id": "primary"}}))
    runtime.queue.put(ServerNotification("ReasoningSummaryTextDelta", {"delta": "**Inspecting** files", "thread_id": "primary"}))
    runtime.queue.put(ServerNotification("ReasoningSummaryTextDelta", {"delta": " carefully", "thread_id": "primary"}))

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and "Inspecting" not in _strip_ansi(stdout.getvalue()):
        time.sleep(0.01)

    output_before_text = _strip_ansi(stdout.getvalue())
    assert "Thinking: Inspecting" in output_before_text
    assert output_before_text.count("Thinking: Inspecting") == 1
    assert "waiting for model..." not in output_before_text.split("Inspecting", 1)[-1]

    runtime.queue.put(ServerNotification("ReasoningSummaryPartAdded", {"thread_id": "primary"}))
    runtime.queue.put(ServerNotification("ReasoningSummaryTextDelta", {"delta": "**Planning** answer", "thread_id": "primary"}))
    runtime.queue.put(ServerNotification("ReasoningTextDelta", {"delta": "raw hidden", "thread_id": "primary"}))
    runtime.queue.put(ServerNotification("AgentMessageDelta", {"delta": "final text", "thread_id": "primary"}))
    runtime.queue.put(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "thread_id": "primary", "status": "Completed", "duration_ms": 25}},
        )
    )
    thread.join(1.0)

    output = _strip_ansi(stdout.getvalue())
    assert result["code"] == 0
    assert "reasoning" in output
    assert "**Inspecting** files" in output
    assert "**Planning** answer" in output
    assert "raw hidden" not in output
    transcript = output.split("T R A N S C R I P T", 1)[-1]
    assert transcript.count("final text") == 1
    assert stderr.getvalue() == ""


def test_terminal_tui_stops_inline_progress_after_agent_text_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust source contract:
    # codex-tui redraws status and streaming assistant text as separate
    # surfaces. Python's lightweight terminal entrypoint must not write
    # periodic status text into the assistant stream after AgentMessageDelta has
    # started.
    stdout = io.StringIO()
    stderr = io.StringIO()
    runtime = _ManualActiveThreadRuntime()
    result: dict[str, int] = {}
    monkeypatch.setenv("PYCODEX_TUI_PROGRESS_INTERVAL_SECONDS", "0.01")

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "code",
            run_terminal_tui(
                stdout=stdout,
                stderr=stderr,
                stdin=io.StringIO("stream cleanly\n/quit\n"),
                active_thread_runtime=runtime,
            ),
        ),
        daemon=True,
    )
    thread.start()

    assert runtime.submitted.wait(1.0)
    runtime.queue.put(ServerNotification("TurnStarted", {"turn": {"id": "turn-1", "thread_id": "primary"}}))
    runtime.queue.put(
        ServerNotification(
            "ItemStarted",
            {
                "thread_id": "primary",
                "turn_id": "turn-1",
                "item": {"kind": "Reasoning", "id": "reasoning-1"},
            },
        )
    )

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and "reasoning..." not in _strip_ansi(stdout.getvalue()):
        time.sleep(0.01)

    runtime.queue.put(ServerNotification("AgentMessageDelta", {"delta": "clean", "thread_id": "primary"}))
    time.sleep(0.08)
    output_after_text = _strip_ansi(stdout.getvalue())

    runtime.queue.put(ServerNotification("AgentMessageDelta", {"delta": " stream", "thread_id": "primary"}))
    runtime.queue.put(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "thread_id": "primary", "status": "Completed", "duration_ms": 25}},
        )
    )
    thread.join(1.0)

    output = _strip_ansi(stdout.getvalue())
    assert result["code"] == 0
    assert "clean stream" in output
    assistant_segment = output_after_text.split("codex", 1)[-1]
    assert "elapsed;" not in assistant_segment.split("clean", 1)[-1]
    assert stderr.getvalue() == ""


def test_terminal_tui_live_delta_overflow_remains_visible_before_completion() -> None:
    # Source: Rust integration/source contract
    # Rust crate: codex-tui
    # Rust modules: chatwidget::streaming, chatwidget::protocol, insert_history
    # Rust evidence:
    # - tui/tests/suite/vt100_live_commit.rs::live_001_commit_on_overflow keeps
    #   early live rows committed when the live ring overflows.
    # - chatwidget/streaming.rs::handle_streaming_delta redraws active stream
    #   rows before TurnCompleted.
    stdout = io.StringIO()
    stderr = io.StringIO()
    runtime = _ManualActiveThreadRuntime()
    result: dict[str, int] = {}

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "code",
            run_terminal_tui(
                stdout=stdout,
                stderr=stderr,
                stdin=io.StringIO("overflow live\n/quit\n"),
                active_thread_runtime=runtime,
            ),
        ),
        daemon=True,
    )

    with patch("pycodex.tui.shutil.get_terminal_size", return_value=os.terminal_size((24, 6))):
        thread.start()
        assert runtime.submitted.wait(1.0)
        runtime.queue.put(ServerNotification("TurnStarted", {"turn": {"id": "turn-1", "thread_id": "primary"}}))
        for index in range(1, 10):
            runtime.queue.put(
                ServerNotification(
                    "AgentMessageDelta",
                    {"delta": f"live overflow line {index:02d}\n", "thread_id": "primary"},
                )
            )

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and "live overflow line 09" not in _strip_ansi(stdout.getvalue()):
            time.sleep(0.01)

        output_before_completion = _strip_ansi(stdout.getvalue())
        assert "live overflow line 01" in output_before_completion
        assert "live overflow line 09" in output_before_completion
        assert "status: Ready" not in output_before_completion.split("live overflow line 09", 1)[-1]

        runtime.queue.put(
            ServerNotification(
                "TurnCompleted",
                {"turn": {"id": "turn-1", "thread_id": "primary", "status": "Completed", "duration_ms": 10}},
            )
        )
        thread.join(1.0)

    output = _strip_ansi(stdout.getvalue())
    assert result["code"] == 0
    assert output.count("live overflow line") == 9
    assert "status: Ready" in output
    assert stderr.getvalue() == ""


def test_terminal_tui_replaces_unencodable_model_output_instead_of_crashing() -> None:
    # Rust terminal output is byte/terminal-backend based and should not crash
    # the app because a model response contains an unusual Unicode control
    # character. Python must preserve that product boundary on Windows codepage
    # streams such as GBK/cp936.
    raw = io.BytesIO()
    writer = io.TextIOWrapper(raw, encoding="gbk", errors="strict")

    code = run_terminal_tui(
        stdout=writer,
        stderr=io.StringIO(),
        stdin=io.StringIO("unicode\n/quit\n"),
        active_thread_runtime=_active_thread_runtime(lambda _prompt: (0, "ok \u200f done")),
    )
    writer.flush()

    output = raw.getvalue().decode("gbk", errors="replace")
    assert code == 0
    assert "ok ? done" in output


def test_cli_tui_uses_text_stdin_for_interactive_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust terminal input is character-event based. Python's interactive TUI
    # must not decode sys.stdin.buffer as UTF-8 on Windows code pages.
    from pycodex.cli import parser as cli_parser

    fake_buffer = io.BytesIO()
    fake_text_stdin = SimpleNamespace(buffer=fake_buffer)
    captured: dict[str, object] = {}

    monkeypatch.setattr(sys, "stdin", fake_text_stdin)
    monkeypatch.setattr(cli_parser, "_build_tui_core_active_thread_runtime", lambda parsed, *, stderr: object())
    def fake_run_terminal_tui(**kwargs):
        captured["stdin"] = kwargs["stdin"]
        return 0

    monkeypatch.setattr(cli_parser, "run_terminal_tui", fake_run_terminal_tui)

    code = cli_parser._run_tui(
        cli_parser.parse_args([]),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        stdin=fake_buffer,
        stdin_is_terminal=True,
    )

    assert code == 0
    assert captured["stdin"] is fake_text_stdin


def test_terminal_tui_long_reply_auto_pager_preserves_last_live_lines() -> None:
    # Rust boundary: codex-tui/src/pager_overlay.rs owns TranscriptOverlay and
    # PagerView; codex-tui/tests/suite/vt100_live_commit.rs verifies live rows
    # are committed instead of clipped.
    stdout = io.StringIO()
    stderr = io.StringIO()
    long_reply = "\n".join(f"live pager line {index:02d}" for index in range(1, 33))

    code = run_terminal_tui(
        stdout=stdout,
        stderr=stderr,
        stdin=_TtyInput("make it long\n\n\nq\n/quit\n"),
        active_thread_runtime=_active_thread_runtime(lambda _prompt: (0, long_reply)),
    )

    output = _strip_ansi(stdout.getvalue())
    assert code == 0
    assert "T R A N S C R I P T" in output
    assert "Enter/space next" in output
    assert "live pager line 01" in output
    assert "live pager line 32" in output
    assert stderr.getvalue() == ""


def test_terminal_tui_commits_long_noninteractive_reply_without_clipping() -> None:
    # Rust boundary:
    # - codex-tui/tests/suite/vt100_live_commit.rs::live_001_commit_on_overflow
    #   commits overflow rows instead of losing them from the live ring.
    # - codex-tui/src/insert_history.rs inserts finalized rows into terminal
    #   history so completed replies remain inspectable outside live repaint.
    stdout = io.StringIO()
    stderr = io.StringIO()
    long_reply = "\n".join(f"committed terminal line {index:02d}" for index in range(1, 46))

    with patch("pycodex.tui.shutil.get_terminal_size", return_value=os.terminal_size((32, 8))):
        code = run_terminal_tui(
            stdout=stdout,
            stderr=stderr,
            stdin=io.StringIO("overflow\n/quit\n"),
            active_thread_runtime=_active_thread_runtime(lambda _prompt: (0, long_reply)),
        )

    output = _strip_ansi(stdout.getvalue())
    assert code == 0
    assert "T R A N S C R I P T" not in output
    assert "committed terminal line 01" in output
    assert "committed terminal line 23" in output
    assert "committed terminal line 45" in output
    assert output.count("committed terminal line") == 45
    assert stderr.getvalue() == ""


def test_live_oauth_tui_conversation_against_real_service() -> None:
    # Python-designed live parity smoke because upstream Rust has live CLI tests
    # and TUI terminal tests, but no combined real OAuth + interactive TUI test.
    if os.environ.get(_LIVE_ENV) != "1":
        pytest.skip(f"set {_LIVE_ENV}=1 to call the real service")
    codex_home = _codex_home_from_env()
    if not _has_chatgpt_oauth_auth(codex_home):
        pytest.skip(f"{codex_home / 'auth.json'} does not contain ChatGPT OAuth auth")

    sentinel_lines = [f"pycodex-live-oauth-line-{index:02d}" for index in range(1, 13)]
    prompt = "Reply with exactly these 12 lines, separated by newlines, and no extra text: " + "; ".join(
        sentinel_lines
    )
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CODEX_API_KEY", None)

    completed = subprocess.run(
        [sys.executable, "-m", "pycodex"],
        cwd=_repo_root(),
        env=env,
        input=f"{prompt}\n/quit\n",
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )

    combined = _strip_ansi(completed.stdout + "\n" + completed.stderr)
    assert completed.returncode == 0, combined
    assert "OPENAI_API_KEY" not in combined
    assert "CODEX_API_KEY" not in combined
    assert sentinel_lines[0] in combined
    assert sentinel_lines[-1] in combined
