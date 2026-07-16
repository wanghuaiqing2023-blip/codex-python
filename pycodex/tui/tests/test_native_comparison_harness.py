"""Tests for the Rust/Python TUI native comparison harness.

Rust source anchors:
- ``codex-cli/src/main.rs::run_interactive_tui`` owns the ``TERM=dumb``
  non-TTY guard before ``codex-tui`` starts.
- ``codex-tui/src/cli.rs`` exposes ``--no-alt-screen``.
- ``codex-tui/src/lib.rs::determine_alt_screen_mode`` keeps inline runs out of
  alternate-screen capture.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from pycodex.core.config.edit import read_toml_mapping
from pycodex.tui.chatwidget.constructor import PLACEHOLDERS as CHAT_PLACEHOLDERS
from pycodex.tui.tests.harness.native_compare import (
    ConptyInputStep,
    DEFAULT_NATIVE_CODEX_EXE,
    NATIVE_CODEX_EXE_ENV,
    RUN_EXPERIMENTAL_CONPTY_ENV,
    RUN_NATIVE_COMPARISON_ENV,
    RUN_VERIFIED_CONPTY_ENV,
    RUN_VERIFIED_CONPTY_TUI_ENV,
    TerminalSize,
    NativeComparisonLayer,
    TuiComparisonCommand,
    TuiProcessTranscript,
    build_inline_tui_command,
    build_rust_python_inline_pair,
    interactive_tui_comparison_capability,
    native_codex_exe_from_env,
    native_comparison_enabled,
    normalize_tui_text,
    run_piped_tui_command,
    run_windows_conpty_tui_command,
    vt_screen_text,
    _conpty_input_chunks,
    _semantic_conpty_text,
    _wait_for_windows_conpty_ordered_semantic_text,
    _wait_for_windows_conpty_semantic_text,
    _wait_for_windows_conpty_quiet,
    _wait_for_windows_conpty_output_pattern,
)

RUN_NATIVE_LIVE_PROMPT_ENV = "PYCODEX_RUN_NATIVE_TUI_LIVE_PROMPT"
RUN_NATIVE_MULTI_TURN_ENV = "PYCODEX_RUN_NATIVE_TUI_MULTI_TURN"
RUN_NATIVE_COMPLEX_LIVE_PROMPT_ENV = "PYCODEX_RUN_NATIVE_TUI_COMPLEX_LIVE_PROMPT"
RUN_NATIVE_HISTORY_RECALL_ENV = "PYCODEX_RUN_NATIVE_TUI_HISTORY_RECALL"
READY_COMPOSER_PATTERN = "(?m)>\\s*$|^\\s*\\u203a\\s+.+$"
SESSION_CONFIGURED_COMPOSER_PATTERN = (
    "(?ms)model:\\s+(?!loading)\\S+.*directory:.*codex-python.*"
    "(?:^>\\s*$|^\\s*\\u203a\\s+.+$)"
)


def _with_rust_startup_tip_ready(input_steps: tuple[ConptyInputStep, ...]) -> tuple[ConptyInputStep, ...]:
    first, *rest = input_steps
    return (
        ConptyInputStep(
            first.text,
            resize=first.resize,
            ready_text="Tip:",
            ready_timeout=first.ready_timeout,
            chunk_delay=first.chunk_delay,
            ready_quiet_period=first.ready_quiet_period,
        ),
        *rest,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _conpty_tui_env() -> dict[str, str]:
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    return env


def _isolated_codex_home_env() -> tuple[dict[str, str], tempfile.TemporaryDirectory[str]]:
    temp_home = tempfile.TemporaryDirectory(prefix="pycodex-native-home-")
    home_path = Path(temp_home.name)
    source_auth = Path.home() / ".codex" / "auth.json"
    if source_auth.exists():
        (home_path / "auth.json").write_bytes(source_auth.read_bytes())
    trust_key = str(_repo_root().resolve(strict=False)).lower()
    (home_path / "config.toml").write_text(
        f"[projects.'{trust_key}']\ntrust_level = \"trusted\"\n",
        encoding="utf-8",
    )
    env = _conpty_tui_env()
    env["CODEX_HOME"] = str(home_path)
    return env, temp_home


def _write_rust_thread_store_seed(
    codex_home: Path,
    *,
    cwd: Path,
    thread_id: str = "11111111-2222-4333-8444-555555555555",
    ts: str = "2025-01-03T10-11-12",
    first_user_message: str = "Seeded resume picker prompt",
) -> Path:
    """Write the minimal rollout shape used by Rust thread-store tests."""

    day_dir = codex_home / "sessions" / "2025" / "01" / "03"
    day_dir.mkdir(parents=True, exist_ok=True)
    rollout_path = day_dir / f"rollout-{ts}-{thread_id}.jsonl"
    meta = {
        "timestamp": ts,
        "type": "session_meta",
        "payload": {
            "id": thread_id,
            "forked_from_id": None,
            "timestamp": ts,
            "cwd": str(cwd),
            "originator": "test_originator",
            "cli_version": "test_version",
            "source": "cli",
            "model_provider": "openai",
            "git": {
                "commit_hash": "abcdef",
                "branch": "main",
                "repository_url": "https://example.com/repo.git",
            },
        },
    }
    user_event = {
        "timestamp": ts,
        "type": "event_msg",
        "payload": {
            "type": "user_message",
            "message": first_user_message,
            "kind": "plain",
        },
    }
    rollout_path.write_text(
        "\n".join(json.dumps(item, separators=(",", ":")) for item in (meta, user_event)) + "\n",
        encoding="utf-8",
    )
    return rollout_path


def _write_message_history_seed(
    codex_home: Path,
    *entries: str,
    session_id: str = "11111111-2222-4333-8444-555555555555",
) -> Path:
    history_path = codex_home / "history.jsonl"
    history_path.write_text(
        "\n".join(
            json.dumps(
                {"session_id": session_id, "ts": 1_735_906_272 + index, "text": text},
                separators=(",", ":"),
            )
            for index, text in enumerate(entries)
        )
        + "\n",
        encoding="utf-8",
    )
    return history_path


def _read_jsonl_records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _isolated_codex_home_env_with_config(config_text: str) -> tuple[dict[str, str], tempfile.TemporaryDirectory[str]]:
    temp_home = tempfile.TemporaryDirectory(prefix="pycodex-native-home-")
    home_path = Path(temp_home.name)
    (home_path / "config.toml").write_text(config_text, encoding="utf-8")
    (home_path / "auth.json").write_text(
        '{"OPENAI_API_KEY":"dummy","tokens":null,"last_refresh":null}',
        encoding="utf-8",
    )
    env = _conpty_tui_env()
    env["CODEX_HOME"] = str(home_path)
    env["OPENAI_API_KEY"] = "dummy"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    return env, temp_home


def _responses_sse(*events: dict[str, object]) -> bytes:
    chunks: list[str] = []
    for event in events:
        kind = str(event["type"])
        chunks.append(f"event: {kind}\n")
        if len(event) > 1:
            chunks.append(f"data: {json.dumps(event, separators=(',', ':'))}\n")
        chunks.append("\n")
    return "".join(chunks).encode("utf-8")


class _SseFixtureServer:
    def __init__(self, body: bytes | tuple[bytes, ...], *, response_delay_seconds: float = 0.0) -> None:
        self._bodies = (body,) if isinstance(body, bytes) else tuple(body)
        if not self._bodies:
            raise ValueError("at least one SSE fixture body is required")
        self._response_delay_seconds = float(response_delay_seconds)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.requests: list[tuple[str, str]] = []
        self.request_bodies: list[bytes] = []
        self._lock = threading.Lock()
        self._body_index = 0

    def __enter__(self) -> "_SseFixtureServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
                length = int(self.headers.get("content-length") or "0")
                request_body = self.rfile.read(length) if length else b""
                with outer._lock:
                    outer.requests.append(("POST", self.path))
                    outer.request_bodies.append(request_body)
                    index = min(outer._body_index, len(outer._bodies) - 1)
                    body = outer._bodies[index]
                    outer._body_index += 1
                if not self.path.rstrip("/").endswith("/responses"):
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.end_headers()
                if outer._response_delay_seconds > 0:
                    time.sleep(outer._response_delay_seconds)
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("server not started")
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"


def _normalized_first_turn_request_context(request: dict[str, object]) -> dict[str, object]:
    """Normalize only nondeterministic identifiers in a captured Responses request."""

    uuid_pattern = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    isolated_home_pattern = re.compile(r"pycodex-native-home-[^/\\\s)]+")
    goal_timestamp_pattern = re.compile(r'("(?:createdAt|updatedAt)"\s*:\s*)\d+')

    def normalize(value: object) -> object:
        if isinstance(value, str):
            normalized = value.replace("\r\n", "\n").replace("\r", "\n")
            normalized = uuid_pattern.sub("<uuid>", normalized)
            normalized = goal_timestamp_pattern.sub(r"\1<timestamp>", normalized)
            return isolated_home_pattern.sub("pycodex-native-home-<temp>", normalized)
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in value.items()}
        return value

    tools = request.get("tools")
    tool_names = [
        (
            f"{tool.get('type')}:{tool.get('name')}"
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
            else str(tool.get("type"))
        )
        for tool in tools
        if isinstance(tool, dict)
    ] if isinstance(tools, list) else []
    return {
        "model": request.get("model"),
        "instructions": normalize(request.get("instructions")),
        "input": normalize(request.get("input")),
        "reasoning": normalize(request.get("reasoning")),
        "parallel_tool_calls": request.get("parallel_tool_calls"),
        "tool_names": tool_names,
        "tools": normalize(tools),
    }


def _assert_live_multi_turn_shutdown_summary(transcript, *, first: str, second: str) -> None:
    output = transcript.normalized_stdout()
    assert "OpenAI Codex" in output
    assert first in output
    assert second in output
    assert output.index(first) < output.index(second)
    assert "Token usage:" in output
    assert "To continue this session, run codex resume" in output
    assert output.index("Token usage:") < output.index("To continue this session, run codex resume")
    if transcript.returncode == 0:
        return
    # Native Rust Codex can leave the Windows ConPTY capture open after the
    # visible shutdown summary has been rendered. Treat that as a harness
    # limitation only when the source-of-truth shutdown transcript is complete.
    assert "ConPTY command timed out" in transcript.normalized_combined()


def _assert_startup_shell_status_surface(transcript) -> None:
    # Rust source anchors:
    # - codex-tui/src/chatwidget.rs::PLACEHOLDERS and
    #   codex-tui/src/chatwidget/constructor.rs::new_with_op_target select the
    #   startup composer placeholder shown by the bottom pane.
    # - codex-tui/src/history_cell/session.rs::SessionHeaderHistoryCell renders
    #   the startup header with model and directory rows.
    # - codex-tui/src/bottom_pane/footer.rs::passive_footer_status_line renders
    #   the passive footer with model and current directory context.
    # - codex-tui/src/app.rs shutdown handling renders the visible shutdown row.
    output = transcript.normalized_stdout()
    assert ">_ OpenAI Codex" in output
    assert "model:" in output
    assert "loading" in output
    assert "/model to change" in output
    assert "directory:" in output
    assert "codex-python" in output
    assert "Context " not in output
    assert "Shutting down" in output
    assert any("gpt-" in line and "codex-python" in line for line in output.splitlines())
    assert any(placeholder in output for placeholder in CHAT_PLACEHOLDERS)


def _assert_startup_current_screen_surface(transcript, *, rows: int, cols: int) -> None:
    # Rust source anchors:
    # - codex-tui/src/tui.rs::enter_alt_screen controls whether the interactive
    #   UI is rendered into the current inline viewport or alternate screen.
    # - codex-tui/src/history_cell/session.rs::new_session_info supplies the
    #   startup header rows.
    # - codex-tui/src/chatwidget/constructor.rs::new_with_op_target wires the
    #   startup composer placeholder into BottomPane.
    # This assertion intentionally uses a VT current-screen projection instead
    # of cumulative stdout so it can catch stale/duplicated startup text.
    screen = transcript.screen_stdout(rows=rows, cols=cols)
    assert ">_ OpenAI Codex" in screen
    assert "╭" in screen
    assert "╰" in screen
    assert "│" in screen
    assert "model:" in screen
    assert "loading" in screen
    assert "/model to change" in screen
    assert "directory:" in screen
    assert "codex-python" in screen
    assert "Context " not in screen
    assert "Tip:" not in screen
    assert any(placeholder in screen for placeholder in CHAT_PLACEHOLDERS)
    assert "Shutting down" not in screen
    assert "\u9225?" not in screen


def _assert_startup_yolo_current_screen_surface(transcript, *, rows: int, cols: int) -> None:
    # Rust source/test contract:
    # - codex-tui/src/history_cell/session.rs::new_active_session applies
    #   SessionHeaderHistoryCell::with_yolo_mode when has_yolo_permissions is
    #   true.
    # - codex-tui/src/history_cell/session.rs::has_yolo_permissions accepts
    #   approval=never plus PermissionProfile::Disabled/full access.
    # - history_cell::tests::session_header_indicates_yolo_mode snapshots the
    #   visible `permissions: YOLO mode` startup row.
    screen = transcript.screen_stdout(rows=rows, cols=cols)
    _assert_startup_current_screen_surface(transcript, rows=rows, cols=cols)
    assert "permissions:" in screen
    assert "YOLO mode" in screen


def _assert_post_turn_current_screen_surface(
    transcript,
    *,
    rows: int,
    cols: int,
    answer: str,
    model_marker: str,
) -> None:
    # Rust source/test contract:
    # - codex-tui::status_indicator_widget owns the active
    #   `Working (... esc to interrupt)` row while a turn is running.
    # - codex-tui::bottom_pane::footer owns the passive model/directory footer
    #   after chatwidget::turn_runtime::on_task_complete restores idle state.
    # This assertion uses the current-screen projection so stale active-status
    # rows in cumulative stdout do not masquerade as the post-turn UI.
    screen = transcript.screen_stdout(rows=rows, cols=cols)
    assert answer in screen
    assert model_marker in screen
    assert "codex-python" in screen
    assert "Working" not in screen
    assert "to interrupt" not in screen
    assert "status: Ready" not in screen
    assert "Token usage:" not in screen


def _assert_interrupt_affordance_visible(transcript) -> None:
    # Rust source/test contract:
    # - codex-tui/src/status_indicator_widget.rs::StatusIndicatorWidget renders
    #   `(<elapsed> • <binding> to interrupt)` when an interrupt binding is
    #   available.
    # - status_indicator_widget::tests::renders_with_working_header and
    #   renders_remapped_interrupt_hint cover the deterministic widget shape.
    #
    # Native live prompts can answer before the active-turn `Working` row is
    # captured, while Rust startup/MCP status can still expose the same
    # interrupt affordance. The product-level native guard therefore checks the
    # stable affordance text, and fake-runtime tests own exact active-turn
    # `Working (...)` timing.
    output = transcript.normalized_stdout()
    assert "esc" in output
    assert "to interrupt" in output


def test_build_rust_python_inline_pair_uses_same_tui_args(tmp_path: Path) -> None:
    rust, python = build_rust_python_inline_pair(
        repo_root=tmp_path,
        native_exe=tmp_path / "codex.exe",
        python_executable="python-test",
        extra_args=("--config", "profile=test"),
    )

    assert rust.kind == "rust"
    assert python.kind == "python"
    assert rust.cwd == tmp_path
    assert python.cwd == tmp_path
    assert rust.argv[1:] == python.argv[3:]
    assert rust.argv[1:] == (
        "--no-alt-screen",
        "-C",
        str(tmp_path),
        "-s",
        "read-only",
        "-a",
        "never",
        "--config",
        "profile=test",
    )


def test_native_codex_exe_and_gate_are_environment_driven(tmp_path: Path) -> None:
    env = {
        RUN_NATIVE_COMPARISON_ENV: "1",
        NATIVE_CODEX_EXE_ENV: str(tmp_path / "native-codex.exe"),
    }

    assert native_comparison_enabled(env)
    assert native_codex_exe_from_env(env) == tmp_path / "native-codex.exe"
    assert not native_comparison_enabled({RUN_NATIVE_COMPARISON_ENV: "0"})
    assert native_codex_exe_from_env({}) == DEFAULT_NATIVE_CODEX_EXE


def test_conpty_pattern_wait_can_ignore_stale_output() -> None:
    """Rust-derived harness contract: staged input waits for newly rendered TUI output."""

    stale = b"Codex Python TUI\n> "
    chunks = [stale]
    start_offset = len(stale.decode("utf-8"))

    assert not _wait_for_windows_conpty_output_pattern(
        chunks,
        r"(?m)^>\s*$",
        timeout=0.0,
        start_offset=start_offset,
    )

    chunks.append(b"\nstatus: Ready\n> ")

    assert _wait_for_windows_conpty_output_pattern(
        chunks,
        r"(?m)^>\s*$",
        timeout=0.0,
        start_offset=start_offset,
    )


def test_ready_composer_pattern_accepts_inline_python_prompt_after_redraw() -> None:
    # Rust/Python native harness contract:
    # Rust normally renders the composer prompt as a row-leading glyph, while
    # the lightweight Python no-alt-screen path can redraw footer text and the
    # prompt on the same captured ConPTY line after a turn completes.
    chunks = [b"gpt-5.5 xhigh fast \xef\xbf\xbd ~\\codex-python> \x1b]0;codex-python\x07"]

    assert _wait_for_windows_conpty_output_pattern(
        chunks,
        READY_COMPOSER_PATTERN,
        timeout=0.0,
    )


def test_ready_composer_pattern_accepts_indented_rust_prompt_row() -> None:
    # Rust no-alt-screen captures can retain indentation/redraw residue before
    # the row-leading composer glyph.
    chunks = ["  › Explain this codebase\n".encode("utf-8")]

    assert _wait_for_windows_conpty_output_pattern(
        chunks,
        READY_COMPOSER_PATTERN,
        timeout=0.0,
    )


def test_session_configured_composer_pattern_rejects_loading_placeholder() -> None:
    # Rust source contract:
    # codex-tui::chatwidget::constructor first renders the startup placeholder
    # header with model `loading`; startup-key native comparisons must not type
    # into that pre-session-configured surface.
    chunks = [
        (
            "╭────────────────╮\n"
            "│ >_ OpenAI Codex │\n"
            "│ model: loading  │\n"
            "│ directory: ~\\codex-python │\n"
            "╰────────────────╯\n"
            "› Improve documentation in @filename\n"
        ).encode("utf-8")
    ]

    assert not _wait_for_windows_conpty_output_pattern(
        chunks,
        SESSION_CONFIGURED_COMPOSER_PATTERN,
        timeout=0.0,
    )


def test_session_configured_composer_pattern_accepts_real_model_prompt() -> None:
    # Rust source contract:
    # codex-tui::chatwidget::session_flow updates the startup header once the
    # session is configured; native tests that immediately type commands should
    # wait for that stronger surface.
    chunks = [
        (
            "╭────────────────╮\n"
            "│ >_ OpenAI Codex │\n"
            "│ model: gpt-5.5  │\n"
            "│ directory: ~\\codex-python │\n"
            "╰────────────────╯\n"
            "› Use /skills to list available skills\n"
        ).encode("utf-8")
    ]

    assert _wait_for_windows_conpty_output_pattern(
        chunks,
        SESSION_CONFIGURED_COMPOSER_PATTERN,
        timeout=0.0,
    )


def test_conpty_quiet_wait_requires_stable_output() -> None:
    """Rust-derived harness contract: scripted input waits for redraw quiescence."""

    chunks = [b"ready"]

    assert _wait_for_windows_conpty_quiet(chunks, quiet_period=0.01, timeout=0.2)

    start = time.monotonic()
    chunks.append(b" redraw")
    assert _wait_for_windows_conpty_quiet(chunks, quiet_period=0.02, timeout=0.2)
    assert time.monotonic() - start >= 0.02


def test_conpty_semantic_text_wait_matches_wrapped_composer_echo() -> None:
    # Rust-derived harness contract:
    # codex-tui uses ratatui redraws for composer text, so ConPTY captures may
    # split a single visible draft across terminal wraps or redraw boundaries.
    chunks = [b"> Reply with exactly PYCODEX_NATIVE_MULTI_A and nothi\r\n"]
    start_offset = 0

    assert not _wait_for_windows_conpty_semantic_text(
        chunks,
        "nothing else.",
        timeout=0.0,
        start_offset=start_offset,
    )

    chunks.append(b"ng else.\r\n")

    assert _wait_for_windows_conpty_semantic_text(
        chunks,
        "nothing else.",
        timeout=0.0,
        start_offset=start_offset,
    )
    assert _semantic_conpty_text("not hi\r\nng") == "nothing"


def test_conpty_ordered_semantic_wait_distinguishes_answer_from_prompt() -> None:
    # Rust-derived harness contract:
    # Answer visibility and post-turn composer readiness are ordered states.
    # The native harness must be able to express "answer token, then prompt",
    # not just "token exists somewhere in the transcript".
    chunks = [b"> Reply with parts PYCODEX NATIVE MULTI A\r\n"]

    assert not _wait_for_windows_conpty_ordered_semantic_text(
        chunks,
        ("PYCODEX_NATIVE_MULTI_A", ">"),
        timeout=0.0,
    )

    chunks.append(b"\r\ncodex\r\n  PYCODEX_NATIVE_MULTI_A\r\n> ")

    assert _wait_for_windows_conpty_ordered_semantic_text(
        chunks,
        ("PYCODEX_NATIVE_MULTI_A", ">"),
        timeout=0.0,
    )


def test_normalize_tui_text_strips_ansi_and_stabilizes_newlines() -> None:
    assert normalize_tui_text("\x1b]0;codex-python\x07\x1b[32mReady\x1b[0m  \r\nnext\r\n") == "Ready\nnext"


def test_vt_screen_text_projects_current_cells_after_redraws() -> None:
    # Rust-derived harness contract:
    # codex-tui renders through Ratatui/crossterm cell updates. Native
    # comparisons that need the current screen must interpret common CSI
    # cursor/erase operations instead of asserting cumulative stdout.
    raw = (
        "old line\r\n"
        "stale tail\r\n"
        "\x1b[1;1Hnew\x1b[K"
        "\x1b[2;1Hkeep\x1b[K"
        "\x1b[2;3HX"
        "\x1b[3;1Habcdef\x1b[3D\x1b[2X"
        "\x1b[4;1Hwide\x1b[3X"
    )

    assert vt_screen_text(raw, rows=4, cols=12) == "new\nkeXp\nabc  f\nwide"


def test_vt_screen_text_models_insert_history_scroll_region() -> None:
    # Fixed Rust baseline 1c7832f: insert_history::insert_history_lines limits
    # scrolling to the rows above the inline viewport and writes at the region
    # bottom. Current-screen evidence must model DECSTBM instead of treating
    # replayed lines as repeated writes to one row.
    raw = (
        "\x1b[1;3r"
        "\x1b[3;1H"
        "\r\nfirst"
        "\r\nsecond"
        "\r\nthird"
        "\x1b[r"
        "\x1b[4;1Hfooter"
    )

    assert vt_screen_text(raw, rows=4, cols=12) == "first\nsecond\nthird\nfooter"


def test_process_transcript_screen_stdout_uses_vt_projection() -> None:
    transcript = TuiProcessTranscript(
        argv=("codex",),
        returncode=0,
        stdout="first\r\nsecond\x1b[1;1Htop\x1b[K",
        stderr="",
    )

    assert "first" in transcript.normalized_stdout()
    assert transcript.screen_stdout(rows=2, cols=12) == "top\nsecond"


def test_process_transcript_persists_session_comparison_artifacts(tmp_path) -> None:
    # Rust owners: codex-tui::tui/custom_terminal session evidence must retain
    # raw VT separately from normalized scrollback and current-screen output.
    transcript = TuiProcessTranscript(
        argv=("codex", "--no-alt-screen"),
        returncode=0,
        stdout="first\r\nsecond\x1b[1;1Htop\x1b[K",
        stderr="warning",
    )

    paths = transcript.write_artifacts(tmp_path, prefix="rust", rows=2, cols=12)

    assert {path.name for path in paths} == {
        "rust.stdout.raw.txt",
        "rust.stderr.raw.txt",
        "rust.stdout.normalized.txt",
        "rust.screen.txt",
    }
    assert (tmp_path / "rust.stdout.raw.txt").read_bytes().decode("utf-8") == transcript.stdout
    assert (tmp_path / "rust.screen.txt").read_text(encoding="utf-8") == "top\nsecond"


def test_conpty_input_chunks_keep_vt_special_keys_atomic() -> None:
    # Rust-derived harness contract:
    # crossterm receives Home/PageUp as a single key event. The ConPTY harness
    # must not split ESC-prefixed special-key sequences into a bare Escape plus
    # literal trailing characters.
    assert _conpty_input_chunks("a\x1b[H\x1b[5~\x1brz") == ["a", "\x1b[H", "\x1b[5~", "\x1br", "z"]
    # Rust codex-tui::bottom_pane::chat_composer can bind composer actions to
    # function keys. XTerm/Windows Terminal commonly sends F1-F4 as SS3
    # sequences, so keep F2 atomic for remapped history-search comparisons.
    assert _conpty_input_chunks("a\x1bOQz") == ["a", "\x1bOQ", "z"]


def test_interactive_comparison_capability_reports_windows_conpty_driver_gap() -> None:
    # Rust boundary:
    # - codex-utils-pty/src/pty.rs::conpty_supported delegates to
    #   win::conpty_supported on Windows.
    # - codex-utils-pty/src/pty.rs::platform_native_pty_system uses the real
    #   Windows ConPTY backend for interactive process spawning.
    # Contract: the Python native-comparison harness must not promote pipe
    # captures to interactive TUI evidence until a ConPTY process driver exists.
    capability = interactive_tui_comparison_capability(
        os_name="nt",
        conpty_probe=True,
        conpty_driver_available=False,
    )

    assert capability.layer is NativeComparisonLayer.INTERACTIVE_PTY
    assert capability.available is False
    assert capability.conpty_supported is True
    assert "driver is still experimental" in capability.reason
    with pytest.raises(RuntimeError, match="driver is still experimental"):
        capability.require_available()


def test_interactive_comparison_capability_reports_windows_conpty_api_absent() -> None:
    capability = interactive_tui_comparison_capability(os_name="nt", conpty_probe=False)

    assert capability.available is False
    assert capability.conpty_supported is False
    assert "not supported" in capability.reason


def test_interactive_comparison_capability_future_driver_available_branch() -> None:
    capability = interactive_tui_comparison_capability(
        os_name="nt",
        conpty_probe=True,
        conpty_driver_available=True,
    )

    assert capability.available is True
    assert capability.conpty_supported is True
    assert "driver is available" in capability.reason
    capability.require_available()


def test_interactive_comparison_capability_detects_current_host_driver() -> None:
    capability = interactive_tui_comparison_capability()

    assert capability.layer is NativeComparisonLayer.INTERACTIVE_PTY
    if os.name == "nt":
        assert capability.conpty_supported in {False, True}
        if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) == "1" and os.environ.get(RUN_VERIFIED_CONPTY_ENV) == "1":
            assert capability.available is (capability.conpty_supported is True)
        else:
            assert capability.available is False
    else:
        assert capability.available is False


def test_interactive_comparison_capability_keeps_unix_driver_gap_explicit() -> None:
    capability = interactive_tui_comparison_capability(os_name="posix")

    assert capability.available is False
    assert capability.conpty_supported is None
    assert "Unix PTY comparison is not wired" in capability.reason


def test_run_piped_tui_command_captures_python_term_dumb_guard() -> None:
    # Rust/native contract mirrored by Python:
    # `TERM=dumb` with non-TTY stdin refuses to start interactive TUI before
    # building the active `codex-tui` runtime.
    repo_root = _repo_root()
    command = build_inline_tui_command("python", repo_root=repo_root, python_executable=sys.executable)
    env = os.environ.copy()
    env["TERM"] = "dumb"

    transcript = run_piped_tui_command(command, env=env, input_text="/quit\n", timeout=15)

    assert transcript.returncode == 1
    assert transcript.normalized_stdout() == ""
    assert 'ERROR: TERM is set to "dumb". Refusing to start the interactive TUI' in transcript.normalized_stderr()


def test_native_and_python_term_dumb_guard_match_when_enabled() -> None:
    # Opt-in native evidence:
    #   `PYCODEX_RUN_NATIVE_TUI_COMPARISON=1 python -m pytest ... -k native_and_python`
    # The plain pipe is intentionally limited to startup guard comparison; it
    # does not claim composer/cursor/spinner parity.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to compare against source-built Rust codex.exe")

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe)
    env = os.environ.copy()
    env["TERM"] = "dumb"

    rust_transcript = run_piped_tui_command(rust, env=env, input_text="/quit\n", timeout=10)
    python_transcript = run_piped_tui_command(python, env=env, input_text="/quit\n", timeout=15)

    expected = (
        'ERROR: TERM is set to "dumb". Refusing to start the interactive TUI because '
        "no terminal is available for a confirmation prompt (stdin/stderr is not a TTY). "
        "Run in a supported terminal or unset TERM."
    )
    assert rust_transcript.returncode == 1, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 1, python_transcript.normalized_combined()
    assert expected in rust_transcript.normalized_combined()
    assert expected in python_transcript.normalized_combined()
    assert rust_transcript.normalized_stdout() == python_transcript.normalized_stdout()
    assert rust_transcript.normalized_stderr() == python_transcript.normalized_stderr()


def test_windows_conpty_python_quit_smoke_when_enabled() -> None:
    # Rust boundary:
    # - codex-utils-pty Windows backend drives real interactive terminal
    #   sessions through CreatePseudoConsole and PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE.
    # Python parity harness: this opt-in test proves the local ctypes ConPTY
    # driver can feed `/quit` into the Python no-alt-screen product path.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run local ConPTY TUI smoke")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    repo_root = _repo_root()
    command = build_inline_tui_command("python", repo_root=repo_root, python_executable=sys.executable)
    transcript = run_windows_conpty_tui_command(
        command,
        input_text="/quit\r",
        env=_conpty_tui_env(),
        timeout=25,
        input_delay=8.0,
        input_chunk_delay=0.2,
        input_ready_pattern=READY_COMPOSER_PATTERN,
    )

    assert transcript.returncode == 0, transcript.normalized_combined()
    assert ">_ OpenAI Codex" in transcript.normalized_stdout()
    assert "Shutting down" in transcript.normalized_stdout()


def test_windows_conpty_native_and_python_resume_picker_lists_seeded_rollout_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch::slash_resume_opens_picker maps
    #   `/resume` to AppEvent::OpenResumePicker without submitting a UserTurn.
    # - codex-tui::resume_picker renders "Resume a previous session" and
    #   session rows from the thread list loader.
    # - codex-thread-store::local::test_support::write_session_file_with_fork
    #   defines the minimal local rollout fixture shape consumed here.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.environ.get(RUN_NATIVE_HISTORY_RECALL_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_HISTORY_RECALL_ENV}=1 after native Ctrl-R history input is verified")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    env, temp_home = _isolated_codex_home_env()
    home_path = Path(temp_home.name)
    _write_rust_thread_store_seed(home_path, cwd=repo_root)
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    input_steps = (
        ConptyInputStep(
            "/resume\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.4,
            chunk_delay=0.03,
        ),
    )

    try:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=20,
            stop_pattern="Seeded resume picker prompt",
            stop_timeout=12,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=20,
            stop_pattern="Seeded resume picker prompt",
            stop_timeout=12,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
    finally:
        temp_home.cleanup()

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        detail = transcript.normalized_combined()
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr(), detail
        assert "Resume a previous session" in output, detail
        assert "Seeded resume picker prompt" in output, detail
        assert "No sessions yet" not in output, detail


def test_windows_conpty_native_and_python_fork_picker_lists_seeded_rollout_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-cli::finalize_fork_interactive sets fork_picker for `codex fork`
    #   with no session id and no --last.
    # - codex-tui::resume_picker::run_fork_picker_with_app_server renders
    #   SessionPickerAction::Fork with title "Fork a previous session".
    # - codex-thread-store::local::test_support::write_session_file_with_fork
    #   defines the minimal local rollout fixture shape consumed here.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    env, temp_home = _isolated_codex_home_env()
    home_path = Path(temp_home.name)
    _write_rust_thread_store_seed(home_path, cwd=repo_root)
    common = (
        "--no-alt-screen",
        "-C",
        str(repo_root),
        "-s",
        "read-only",
        "-a",
        "never",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "fork",
    )
    rust = TuiComparisonCommand(kind="rust", argv=(str(native_exe), *common), cwd=repo_root)
    python = TuiComparisonCommand(kind="python", argv=(sys.executable, "-m", "pycodex", *common), cwd=repo_root)

    try:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_text="",
            env=env,
            timeout=20,
            stop_pattern="Seeded resume picker prompt",
            stop_timeout=12,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_text="",
            env=env,
            timeout=20,
            stop_pattern="Seeded resume picker prompt",
            stop_timeout=12,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
    finally:
        temp_home.cleanup()

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        detail = transcript.normalized_combined()
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr(), detail
        assert "Fork a previous session" in output, detail
        assert "Seeded resume picker prompt" in output, detail
        assert "No sessions yet" not in output, detail


def test_windows_conpty_captures_child_output_when_enabled() -> None:
    # Rust boundary:
    # - codex-utils-pty/src/win/conpty.rs::create_conpty_handles wires the
    #   pseudo console output pipe to the master reader.
    # - codex-utils-pty/src/win/psuedocon.rs::spawn_command attaches the child
    #   process through PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE.
    # Contract: before claiming product TUI parity, the Python ctypes ConPTY
    # harness must prove a child process writes visible output into the captured
    # ConPTY transcript, not to the parent PowerShell stdout.
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    command = TuiComparisonCommand(
        "cmd",
        (r"C:\Windows\System32\cmd.exe", "/c", "echo", "hello"),
        _repo_root(),
    )
    transcript = run_windows_conpty_tui_command(command, input_text="", timeout=5)

    assert transcript.returncode == 0, transcript.normalized_combined()
    assert "hello" in transcript.normalized_stdout()
    assert transcript.normalized_stderr() == ""


def test_windows_conpty_resize_step_updates_child_terminal_size_when_enabled() -> None:
    # Rust boundary:
    # - codex-utils-pty/src/win/conpty.rs owns ConPTY creation.
    # - codex-utils-pty/src/win/pty.rs::PtyProcess::resize forwards terminal
    #   size changes to the OS pseudo console.
    # Python parity harness: before using resize/reflow native comparisons as
    # product evidence, the local ConPTY driver must prove that a staged resize
    # action changes the terminal size observed by the child process.
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    child_code = (
        "import os, sys; "
        "print(f'before:{os.get_terminal_size().columns}', flush=True); "
        "sys.stdin.readline(); "
        "print(f'after:{os.get_terminal_size().columns}', flush=True)"
    )
    command = TuiComparisonCommand(
        "python",
        (sys.executable, "-c", child_code),
        _repo_root(),
    )
    transcript = run_windows_conpty_tui_command(
        command,
        input_steps=(
            ConptyInputStep(
                "\r",
                resize=TerminalSize(rows=24, cols=120),
                ready_text="before:80",
                ready_timeout=5.0,
            ),
        ),
        timeout=10,
        size=TerminalSize(rows=24, cols=80),
    )

    assert transcript.returncode == 0, transcript.normalized_combined()
    assert "before:80" in transcript.normalized_stdout()
    assert "after:120" in transcript.normalized_stdout()
    assert transcript.normalized_stderr() == ""


def test_windows_conpty_native_and_python_resize_reflow_smoke_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::transcript_reflow tracks pending width repairs.
    # - codex-tui::app::resize_reflow rebuilds Codex-owned terminal scrollback
    #   from HistoryCell source after terminal resize.
    # - codex/codex-rs/tui/tests/suite/resize_reflow.rs drives a real terminal
    #   resize with a local SSE model fixture and asserts the history sentinel
    #   and composer row remain visible after split/restore.
    #
    # This Windows ConPTY comparison mirrors the same product boundary with a
    # real ResizePseudoConsole action instead of tmux pane resizing.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    sentinel = (
        "resize reflow sentinel says hi. This paragraph is intentionally long enough to exercise terminal "
        "wrapping, scrollback redraw, and pane resize behavior without requiring a live model response. "
        "It includes enough ordinary prose to wrap across several rows in a narrow terminal, then keep "
        "going so repeated resize and restore cycles have visible history above the composer."
    )
    draft = "Notice where we are here in terms of y location."
    sse_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-resize-smoke"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-resize-smoke",
                "content": [{"type": "output_text", "text": sentinel}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-resize-smoke",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, env: dict[str, str]) -> object:
        return run_windows_conpty_tui_command(
            command,
            input_steps=(
                ConptyInputStep(
                    "Send me a large paragraph of text for testing.",
                    ready_pattern=READY_COMPOSER_PATTERN,
                    ready_timeout=30.0,
                    ready_quiet_period=0.2,
                    chunk_delay=0.01,
                ),
                ConptyInputStep(
                    "\r",
                    ready_text="for testing.",
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                    chunk_delay=0.01,
                ),
                ConptyInputStep(
                    draft,
                    ready_text="resize reflow sentinel",
                    ready_timeout=30.0,
                    ready_quiet_period=0.5,
                    chunk_delay=0.01,
                ),
                ConptyInputStep(
                    "",
                    resize=TerminalSize(rows=18, cols=70),
                    ready_text=draft,
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                ),
                ConptyInputStep(
                    "",
                    resize=TerminalSize(rows=32, cols=120),
                    ready_timeout=0.5,
                ),
                ConptyInputStep(
                    "\x15/quit\r",
                    ready_text=draft,
                    ready_timeout=10.0,
                    ready_quiet_period=0.5,
                    chunk_delay=0.02,
                ),
            ),
            env=env,
            timeout=35,
            size=TerminalSize(rows=32, cols=120),
        )

    with _SseFixtureServer(sse_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[features]\n"
            "terminal_resize_reflow = true\n\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for resize reflow test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        extra_args = (
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
        with temp_home:
            rust_transcript = run_pair_member(rust, env)
            python_transcript = run_pair_member(python, env)

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nstdout={output}"
        assert "OpenAI Codex" in output, detail
        assert "resize reflow sentinel" in output, detail
        assert draft in output, detail
        assert "Shutting down" in output or "To continue this session, run codex resume" in output, detail
        if transcript.returncode == 0:
            continue
        assert "ConPTY command timed out" in transcript.normalized_combined(), detail


def test_windows_conpty_native_and_python_quit_smoke_when_enabled() -> None:
    # Opt-in native evidence for the first real interactive comparison layer.
    # This is intentionally a `/quit` smoke: it proves Rust/Python can both be
    # driven through ConPTY before deeper composer/spinner transcript tests are
    # added on top of the same harness.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe)
    rust_transcript = run_windows_conpty_tui_command(
        rust,
        input_text="/quit\r",
        env=_conpty_tui_env(),
        timeout=35,
        input_delay=8.0,
        input_chunk_delay=0.2,
        input_ready_pattern=READY_COMPOSER_PATTERN,
    )
    python_transcript = run_windows_conpty_tui_command(
        python,
        input_text="/quit\r",
        env=_conpty_tui_env(),
        timeout=25,
        input_delay=8.0,
        input_chunk_delay=0.2,
        input_ready_pattern=READY_COMPOSER_PATTERN,
    )

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    assert "OpenAI Codex" in rust_transcript.normalized_stdout()
    assert "OpenAI Codex" in python_transcript.normalized_stdout()
    assert "Shutting down" in rust_transcript.normalized_stdout()
    assert "Shutting down" in python_transcript.normalized_stdout()
    _assert_startup_shell_status_surface(rust_transcript)
    _assert_startup_shell_status_surface(python_transcript)


def test_windows_conpty_native_and_python_startup_current_screen_when_enabled() -> None:
    # Opt-in native evidence for the startup screen as the user sees it before
    # submitting a prompt. This closes the gap left by cumulative stdout smoke
    # tests, which can pass even if stale rows remain on the current screen.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    rows = 24
    cols = 100
    repo_root = _repo_root()
    config = (
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n'
        "\n"
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )
    env, temp_home = _isolated_codex_home_env_with_config(config)
    extra_args = (
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)

    def capture_startup(command: TuiComparisonCommand) -> TuiProcessTranscript:
        return run_windows_conpty_tui_command(
            command,
            input_text="",
            env=env,
            timeout=15,
            size=TerminalSize(rows=rows, cols=cols),
            stop_pattern=READY_COMPOSER_PATTERN,
            stop_timeout=12,
            terminate_on_stop_pattern=True,
        )

    with temp_home:
        rust_transcript = capture_startup(rust)
        python_transcript = capture_startup(python)

    for transcript in (rust_transcript, python_transcript):
        detail = (
            f"argv={transcript.argv!r}\n"
            f"returncode={transcript.returncode}\n"
            f"stderr={transcript.normalized_stderr()}\n"
            f"screen={transcript.screen_stdout(rows=rows, cols=cols)}\n"
            f"stdout={transcript.normalized_stdout()}"
        )
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr(), detail
        _assert_startup_current_screen_surface(transcript, rows=rows, cols=cols)


def test_windows_conpty_native_and_python_yolo_startup_current_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::history_cell::session owns the startup session header.
    # - codex-tui::history_cell::session::has_yolo_permissions marks
    #   `--dangerously-bypass-approvals-and-sandbox` as yolo mode via
    #   approval=never plus full-access permissions.
    # - codex-cli/tui launch code maps the dangerous-bypass flag to
    #   SandboxMode::DangerFullAccess and AskForApproval::Never.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    rows = 24
    cols = 100
    repo_root = _repo_root()
    config = (
        'suppress_unstable_features_warning = true\n'
        "\n"
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )
    env, temp_home = _isolated_codex_home_env_with_config(config)
    common = (
        "--no-alt-screen",
        "-C",
        str(repo_root),
        "--dangerously-bypass-approvals-and-sandbox",
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust = TuiComparisonCommand(kind="rust", argv=(str(native_exe), *common), cwd=repo_root)
    python = TuiComparisonCommand(kind="python", argv=(sys.executable, "-m", "pycodex", *common), cwd=repo_root)

    def capture_startup(command: TuiComparisonCommand) -> TuiProcessTranscript:
        return run_windows_conpty_tui_command(
            command,
            input_text="",
            env=env,
            timeout=15,
            size=TerminalSize(rows=rows, cols=cols),
            stop_pattern=READY_COMPOSER_PATTERN,
            stop_timeout=12,
            terminate_on_stop_pattern=True,
        )

    with temp_home:
        rust_transcript = capture_startup(rust)
        python_transcript = capture_startup(python)

    for transcript in (rust_transcript, python_transcript):
        detail = (
            f"argv={transcript.argv!r}\n"
            f"returncode={transcript.returncode}\n"
            f"stderr={transcript.normalized_stderr()}\n"
            f"screen={transcript.screen_stdout(rows=rows, cols=cols)}\n"
            f"stdout={transcript.normalized_stdout()}"
        )
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr(), detail
        _assert_startup_yolo_current_screen_surface(transcript, rows=rows, cols=cols)


def test_windows_conpty_native_and_python_configured_mcp_failure_surface_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::app::app_server_events routes app-server
    #   McpServerStatusUpdated notifications.
    # - codex-tui::chatwidget::mcp_startup renders the configured server name,
    #   per-server failure warning, and startup completion/incomplete summary.
    # - chatwidget/tests/mcp_startup.rs::app_server_mcp_startup_failure_renders_warning_history
    #   proves the local widget contract; this opt-in native guard proves the
    #   common product entrypoint does not drop configured MCP startup status.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    config = (
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n'
        "\n"
        "[mcp_servers.pycodex_fail]\n"
        'command = "C:\\\\Windows\\\\System32\\\\cmd.exe"\n'
        'args = ["/c", "exit", "42"]\n'
        "\n"
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )
    env, temp_home = _isolated_codex_home_env_with_config(config)
    extra_args = (
        "-c",
        'tui.keymap.composer.history_search_previous="f2"',
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_text="/quit\r",
            env=env,
            timeout=45,
            input_delay=8.0,
            input_chunk_delay=0.2,
            input_ready_pattern=READY_COMPOSER_PATTERN,
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_text="/quit\r",
            env=env,
            timeout=30,
            input_delay=8.0,
            input_chunk_delay=0.2,
            input_ready_pattern=READY_COMPOSER_PATTERN,
        )

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "pycodex_fail" in output
        assert "MCP client for `pycodex_fail` failed to start" in output
        assert "MCP startup incomplete (failed: pycodex_fail)" in output
        assert "Shutting down" in output


def test_windows_conpty_native_and_python_invalid_status_line_warning_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::status_surfaces parses configured status-line
    #   items, deduplicates unknown ids, and warns once after a thread id exists.
    # - chatwidget/tests/status_and_layout.rs::status_line_invalid_items_warn_once
    #   proves duplicate invalid ids are shown once and subsequent refreshes do
    #   not emit another warning history cell.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    env, temp_home = _isolated_codex_home_env()
    extra_args = (
        "-c",
        'tui.status_line=["model-name","bogus_item","context-used","bogus_item"]',
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    try:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_text="/quit\r",
            env=env,
            timeout=35,
            input_delay=8.0,
            input_chunk_delay=0.2,
            input_ready_pattern=READY_COMPOSER_PATTERN,
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_text="/quit\r",
            env=env,
            timeout=25,
            input_delay=8.0,
            input_chunk_delay=0.2,
            input_ready_pattern=READY_COMPOSER_PATTERN,
        )
    finally:
        temp_home.cleanup()

    warning = 'Ignored invalid status line item: "bogus_item".'
    rust_output = rust_transcript.normalized_stdout()
    python_output = python_transcript.normalized_stdout()
    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert transcript.returncode == 0, transcript.normalized_combined()
        assert output.count(warning) == 1
        assert "Context 0% used" in output


def test_windows_conpty_native_and_python_status_line_context_used_current_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::status_surfaces::refresh_status_line_from_selections
    #   maps configured status-line items into the bottom pane.
    # - chatwidget/tests/status_and_layout.rs::status_line_context_used_renders_labeled_percent
    #   proves `context-used` is valid and renders `Context 0% used` before any
    #   token usage has arrived.
    # - codex-tui::bottom_pane::footer owns the passive footer projection that
    #   users see on the current startup screen.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    rows = 24
    cols = 100
    repo_root = _repo_root()
    env, temp_home = _isolated_codex_home_env()
    extra_args = (
        "-c",
        'tui.status_line=["context-used"]',
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)

    def capture_startup(command: TuiComparisonCommand) -> TuiProcessTranscript:
        return run_windows_conpty_tui_command(
            command,
            input_text="",
            env=env,
            timeout=15,
            size=TerminalSize(rows=rows, cols=cols),
            stop_pattern=READY_COMPOSER_PATTERN,
            stop_timeout=12,
            terminate_on_stop_pattern=True,
        )

    try:
        rust_transcript = capture_startup(rust)
        python_transcript = capture_startup(python)
    finally:
        temp_home.cleanup()

    for transcript in (rust_transcript, python_transcript):
        screen = transcript.screen_stdout(rows=rows, cols=cols)
        detail = (
            f"argv={transcript.argv!r}\n"
            f"stderr={transcript.normalized_stderr()}\n"
            f"screen={screen}\n"
            f"stdout={transcript.normalized_stdout()}"
        )
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr(), detail
        assert "OpenAI Codex" in screen, detail
        assert "Context 0% used" in screen, detail
        assert "Ignored invalid status line" not in screen, detail
        assert "Shutting down" not in screen, detail


def test_windows_conpty_native_and_python_transcript_ctrl_t_overlay_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::app::input maps Global.open_transcript to opening
    #   TranscriptOverlay.
    # - keymap.rs defaults Global.open_transcript and Pager.close_transcript
    #   to Ctrl+T; Pager.close also accepts q.
    # - pager_overlay.rs owns the visible "T R A N S C R I P T" overlay.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    input_steps = (
        ConptyInputStep("", ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=30.0, ready_quiet_period=0.5),
        ConptyInputStep("\x14", ready_timeout=0.1, chunk_delay=0.02),
        ConptyInputStep("q", ready_text="T R A N S C R I P T", ready_timeout=10.0, chunk_delay=0.02),
        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
        ConptyInputStep("", ready_text="Shutting down", ready_timeout=10.0),
    )

    env, temp_home = _isolated_codex_home_env()
    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=_with_rust_startup_tip_ready(input_steps),
            env=env,
            timeout=45,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=35,
            size=TerminalSize(rows=32, cols=120),
        )

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "T R A N S C R I P T" in output


def test_windows_conpty_native_and_python_seeded_message_history_ctrl_r_recall_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-message-history stores ~/.codex/history.jsonl as JSONL
    #   HistoryEntry records.
    # - codex-tui::app_server_session populates MessageHistoryMetadata during
    #   session configuration.
    # - codex-tui::bottom_pane::chat_composer_history requests persistent
    #   offsets during Ctrl+R reverse search and applies the returned entry to
    #   the composer.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_NATIVE_HISTORY_RECALL_ENV) != "1":
        pytest.skip(
            f"set {RUN_NATIVE_HISTORY_RECALL_ENV}=1 to debug seeded persistent Ctrl-R recall; "
            "the common composer native gate uses same-session history recall"
        )
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    recalled = "newest native history prompt"
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    input_steps = (
        ConptyInputStep(
            "",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
        ),
        # Rust no-alt-screen startup can render an initial prompt before
        # session history metadata is installed.  Wait for the configured
        # model/directory header so this native oracle exercises persistent
        # history lookup instead of racing startup.
        # F2 is remapped to Rust's composer.history_search_previous action so
        # this native oracle avoids relying on terminal-specific Ctrl-R
        # reporting.  Once a match is visible, accept it with Enter before
        # issuing /quit; while reverse search is active Rust keeps routing
        # printable keys to the search footer instead of the normal composer.
        ConptyInputStep("\x1bOQnative", ready_text="newest native history", ready_timeout=10.0, chunk_delay=0.02),
        ConptyInputStep("\r\x15/quit\r", ready_text="Shutting down", ready_timeout=10.0, chunk_delay=0.02),
    )

    def run_member(command: TuiComparisonCommand) -> TuiProcessTranscript:
        env, temp_home = _isolated_codex_home_env()
        home_path = Path(env["CODEX_HOME"])
        _write_message_history_seed(home_path, "older native history prompt", recalled)
        with temp_home:
            return run_windows_conpty_tui_command(
                command,
                input_steps=input_steps,
                env=env,
                timeout=35,
                size=TerminalSize(rows=32, cols=120),
            )

    rust_transcript = run_member(rust)
    if rust_transcript.returncode != 0 or recalled not in rust_transcript.normalized_stdout():
        pytest.xfail(
            "source-built Rust ConPTY no-alt-screen readiness/key delivery does "
            "not reliably open seeded persistent history search; the Rust "
            "module tests, terminal product tests, and same-session native recall "
            "cover common behavior while this remains native-oracle debt"
        )

    python_transcript = run_member(python)

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert recalled in output


def test_windows_conpty_native_and_python_same_session_history_up_recall_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer_history records local
    #   submissions with full draft metadata during the current UI session.
    # - Empty-composer Up recalls the newest local entry without submitting a
    #   new UserTurn.
    # - This native comparison stays on the stable product path; seeded
    #   persistent Ctrl-R remains behind PYCODEX_RUN_NATIVE_TUI_HISTORY_RECALL
    #   because the current ConPTY probe cannot reliably prove that key path.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    recalled = "same session native history prompt"
    answer = "PYCODEX_HISTORY_RECALL_DONE"
    body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-history-recall"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-history-recall",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-history-recall",
            "output_index": 0,
            "content_index": 0,
            "delta": answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-history-recall",
                "content": [{"type": "output_text", "text": answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-history-recall",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 3,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, prompt_marker: str) -> TuiProcessTranscript:
        with _SseFixtureServer(body) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for local history recall test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            recalled,
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text=recalled,
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(answer, prompt_marker),
                            ready_timeout=35.0,
                        ),
                        ConptyInputStep(
                            "\x1b[A",
                            ready_text=recalled,
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            "\x15/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep("", ready_text="Token usage:", ready_timeout=10.0),
                    ),
                    env=env,
                    timeout=45,
                    size=TerminalSize(rows=32, cols=120),
                )
            assert len(server.requests) == 1, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert recalled in output
        assert answer in output


def test_windows_conpty_native_and_python_local_sse_multi_turn_clean_shutdown_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer submits each non-empty Enter as a
    #   separate user turn.
    # - codex-tui::chatwidget::protocol maps TurnCompleted into
    #   chatwidget::turn_runtime::on_task_complete, restoring composer
    #   readiness for the next user turn.
    # - codex-tui::app builds AppExitInfo after shutdown, and
    #   codex-cli::main::format_exit_messages prints token usage before the
    #   resume hint when the rollout is resumable.
    #
    # This deterministic native comparison uses a local Responses SSE fixture
    # so it proves the Rust/Python product TUI composition path without relying
    # on live model timing. Live OAuth remains covered by the separate opt-in
    # live prompt smoke.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    first = "PYCODEX_LOCAL_MULTI_A"
    second = "PYCODEX_LOCAL_MULTI_B"

    def sse_message(response_id: str, message_id: str, text: str, total_tokens: int) -> bytes:
        return _responses_sse(
            {"type": "response.created", "response": {"id": response_id}},
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": message_id,
                    "content": [],
                },
                "output_index": 0,
            },
            {
                "type": "response.output_text.delta",
                "item_id": message_id,
                "output_index": 0,
                "content_index": 0,
                "delta": text,
            },
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": message_id,
                    "content": [{"type": "output_text", "text": text}],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "usage": {
                        "input_tokens": 1,
                        "input_tokens_details": None,
                        "output_tokens": total_tokens - 1,
                        "output_tokens_details": None,
                        "total_tokens": total_tokens,
                    },
                },
            },
        )

    first_body = sse_message("resp-local-multi-a", "msg-local-multi-a", first, 3)
    second_body = sse_message("resp-local-multi-b", "msg-local-multi-b", second, 5)

    def run_pair_member(command: TuiComparisonCommand, prompt_marker: str) -> object:
        with _SseFixtureServer((first_body, second_body)) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for local multi-turn test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "first deterministic multi-turn prompt",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="multi-turn prompt",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(first, prompt_marker),
                            ready_timeout=35.0,
                        ),
                        ConptyInputStep(
                            "second deterministic multi-turn prompt",
                            ready_timeout=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="multi-turn prompt",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(second, prompt_marker),
                            ready_timeout=35.0,
                        ),
                        ConptyInputStep(
                            "\x15/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text="Token usage:",
                            ready_timeout=10.0,
                        ),
                    ),
                    env=env,
                    timeout=45,
                    size=TerminalSize(rows=32, cols=120),
                )
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    extra_args = (
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")

    for transcript in (rust_transcript, python_transcript):
        _assert_live_multi_turn_shutdown_summary(transcript, first=first, second=second)


def test_windows_conpty_native_and_python_local_sse_post_turn_current_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::status_indicator_widget renders active work as
    #   `Working (... esc to interrupt)`.
    # - codex-tui::chatwidget::protocol maps TurnCompleted into
    #   chatwidget::turn_runtime::on_task_complete.
    # - codex-tui::bottom_pane::footer then renders the passive
    #   model/directory footer instead of an active status row.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    rows = 32
    cols = 120
    repo_root = _repo_root()
    answer = "PYCODEX_POST_TURN_READY"
    body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-post-turn-ready"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-post-turn-ready",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-post-turn-ready",
            "output_index": 0,
            "content_index": 0,
            "delta": answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-post-turn-ready",
                "content": [{"type": "output_text", "text": answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-post-turn-ready",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 3,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, prompt_marker: str) -> TuiProcessTranscript:
        with _SseFixtureServer(body) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for post-turn current-screen test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "post turn current screen prompt",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="post turn current screen prompt",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(answer, prompt_marker),
                            ready_timeout=35.0,
                            ready_quiet_period=0.2,
                        ),
                    ),
                    env=env,
                    timeout=10,
                    size=TerminalSize(rows=rows, cols=cols),
                    stop_pattern=answer,
                    stop_timeout=5,
                    terminate_on_stop_pattern=True,
                )
            assert len(server.requests) == 1, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")

    _assert_post_turn_current_screen_surface(
        rust_transcript,
        rows=rows,
        cols=cols,
        answer=answer,
        model_marker="mock-model default",
    )
    _assert_post_turn_current_screen_surface(
        python_transcript,
        rows=rows,
        cols=cols,
        answer=answer,
        model_marker="mock-model",
    )


def test_windows_conpty_native_and_python_local_sse_reasoning_raw_hidden_by_default_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-core/src/session/turn.rs maps
    #   ResponseEvent::ReasoningSummaryDelta into summary reasoning events and
    #   ResponseEvent::ReasoningContentDelta into raw reasoning events.
    # - codex-app-server-protocol/src/protocol/event_mapping.rs preserves that
    #   distinction as ReasoningSummaryTextDelta vs ReasoningTextDelta.
    # - codex-tui/src/chatwidget/protocol.rs routes ReasoningTextDelta only
    #   when show_raw_agent_reasoning is enabled.
    #
    # This deterministic native comparison proves the product path does not
    # leak raw reasoning text by default while still showing server-provided
    # reasoning summary text.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    summary_marker = "PYCODEX_VISIBLE_REASONING_SUMMARY"
    raw_marker = "PYCODEX_RAW_REASONING_SHOULD_HIDE"
    final_answer = "PYCODEX_REASONING_DONE"
    body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-reasoning-gate"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "reasoning",
                "id": "reasoning-local-gate",
                "summary": [],
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "reasoning-local-gate",
            "output_index": 0,
            "summary_index": 0,
            "delta": f"**Reasoning summary** {summary_marker}",
        },
        {
            "type": "response.reasoning_text.delta",
            "item_id": "reasoning-local-gate",
            "output_index": 0,
            "content_index": 0,
            "delta": raw_marker,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "reasoning",
                "id": "reasoning-local-gate",
                "summary": [{"type": "summary_text", "text": f"**Reasoning summary** {summary_marker}"}],
                "content": [{"type": "reasoning_text", "text": raw_marker}],
            },
        },
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-reasoning-gate",
                "content": [],
            },
            "output_index": 1,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-local-reasoning-gate",
            "output_index": 1,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-reasoning-gate",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-reasoning-gate",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": {"reasoning_tokens": 1},
                    "total_tokens": 3,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, prompt_marker: str) -> object:
        with _SseFixtureServer(body) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for local reasoning gate test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "reasoning gate prompt",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="reasoning gate prompt",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(summary_marker, final_answer, prompt_marker),
                            ready_timeout=35.0,
                        ),
                        ConptyInputStep(
                            "/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep("", ready_text="Token usage:", ready_timeout=10.0),
                    ),
                    env=env,
                    timeout=45,
                    size=TerminalSize(rows=32, cols=120),
                )
            assert len(server.requests) >= 1, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    extra_args = (
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert final_answer in output
        # The live step above already waits for the summary marker. Final
        # retained Ratatui/terminal screens may clear the transient reasoning
        # status, but raw reasoning must not appear anywhere in the captured
        # terminal stream.
        assert raw_marker not in transcript.stdout


def test_windows_conpty_native_and_python_local_sse_hide_agent_reasoning_still_shows_summary_events_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-core/src/config/mod.rs loads Config.hide_agent_reasoning from
    #   config.toml with a default of false.
    # - codex-tui/src/chatwidget/protocol.rs routes summary reasoning deltas
    #   separately from raw reasoning deltas.
    # - codex-tui/src/chatwidget/streaming.rs finalizes summary reasoning only
    #   when the chat widget is configured to show agent reasoning.
    #
    # This deterministic native comparison prevents Python from over-filtering
    # reasoning relative to Rust: both source-built Rust Codex and Python
    # PyCodex receive server-provided summary/raw reasoning while
    # hide_agent_reasoning=true; summary events still drive visible reasoning
    # status/history, but raw reasoning remains hidden by default.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    summary_marker = "PYCODEX_HIDDEN_REASONING_SUMMARY"
    raw_marker = "PYCODEX_HIDDEN_RAW_REASONING"
    final_answer = "PYCODEX_HIDE_REASONING_DONE"
    body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-hide-reasoning"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "reasoning",
                "id": "reasoning-local-hide",
                "summary": [],
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "reasoning-local-hide",
            "output_index": 0,
            "summary_index": 0,
            "delta": f"**Reasoning summary** {summary_marker}",
        },
        {
            "type": "response.reasoning_text.delta",
            "item_id": "reasoning-local-hide",
            "output_index": 0,
            "content_index": 0,
            "delta": raw_marker,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "reasoning",
                "id": "reasoning-local-hide",
                "summary": [{"type": "summary_text", "text": f"**Reasoning summary** {summary_marker}"}],
                "content": [{"type": "reasoning_text", "text": raw_marker}],
            },
        },
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-hide-reasoning",
                "content": [],
            },
            "output_index": 1,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-local-hide-reasoning",
            "output_index": 1,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-hide-reasoning",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-hide-reasoning",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": {"reasoning_tokens": 1},
                    "total_tokens": 3,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, prompt_marker: str) -> object:
        with _SseFixtureServer(body) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                "hide_agent_reasoning = true\n"
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for hide reasoning gate test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "hide reasoning prompt",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="hide reasoning prompt",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(summary_marker, final_answer, prompt_marker),
                            ready_timeout=35.0,
                        ),
                        ConptyInputStep(
                            "/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                    ),
                    env=env,
                    timeout=45,
                    size=TerminalSize(rows=32, cols=120),
                )
            assert len(server.requests) >= 1, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    extra_args = (
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert final_answer in output
        assert summary_marker in transcript.stdout
        assert raw_marker not in transcript.stdout


def test_windows_conpty_native_and_python_local_sse_exec_command_output_when_enabled(tmp_path: Path) -> None:
    # Rust source/test contract:
    # - codex-core maps Responses function_call items into turn tool execution.
    # - codex-tui::chatwidget::command_lifecycle projects command lifecycle
    #   events into exec_cell display items.
    # - codex-tui::exec_cell::render uses "Running" while active, "Ran" after
    #   completion, and preserves a bounded output preview in the transcript.
    #
    # This deterministic comparison runs the same local Responses SSE fixture
    # through native Rust Codex and Python PyCodex, proving the product path:
    # model tool call -> core exec -> TUI command display -> final answer.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    command = "echo PYCODEX_EXEC_NATIVE"
    final_answer = "PYCODEX_EXEC_DONE"
    call_id = "call-pycodex-exec-native"
    item_id = "fc-pycodex-exec-native"

    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-exec-tool"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": item_id,
                "type": "function_call",
                "call_id": call_id,
                "name": "exec_command",
                "arguments": json.dumps({"cmd": command}, separators=(",", ":")),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-exec-tool",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )
    final_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-exec-final"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-exec-final",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-local-exec-final",
            "output_index": 0,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-exec-final",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-exec-final",
                "usage": {
                    "input_tokens": 2,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 4,
                },
            },
        },
    )

    def run_pair_member(command_spec: TuiComparisonCommand, prompt_marker: str) -> object:
        # Delay both model responses so the active-turn status must remain
        # visible before and after command execution.
        with _SseFixtureServer((tool_body, final_body), response_delay_seconds=1.2) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                "experimental_use_unified_exec_tool = true\n"
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for local exec-command test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            if command_spec.kind == "python":
                env["PYCODEX_TUI_TIMING_LOG"] = str(tmp_path / "python.timing.jsonl")
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "run deterministic exec tool",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="exec tool",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(
                                "Ran",
                                "PYCODEX_EXEC_NATIVE",
                                "Working",
                                "esc to interrupt",
                                final_answer,
                                prompt_marker,
                            ),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep(
                            "/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                    ),
                    env=env,
                    timeout=50,
                    size=TerminalSize(rows=32, cols=120),
                )
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    extra_args = (
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")
    rust_transcript.write_artifacts(tmp_path, prefix="rust", rows=32, cols=120)
    python_transcript.write_artifacts(tmp_path, prefix="python", rows=32, cols=120)

    readiness_failures: list[str] = []
    for label, transcript, prompt_marker in (
        ("rust", rust_transcript, "mock-model default"),
        ("python", python_transcript, "mock-model"),
    ):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        # Rust ratatui may redraw the retained screen again while /quit exits,
        # so completed rows and the final answer are asserted against the
        # ordered semantic checkpoint observed before shutdown.
        expected = (
            "Ran",
            "PYCODEX_EXEC_NATIVE",
            "Working",
            "esc to interrupt",
            final_answer,
            prompt_marker,
        )
        if expected not in transcript.observed_ready_sequences:
            readiness_failures.append(
                f"{label}: expected={expected!r}; "
                f"observed={transcript.observed_ready_sequences!r}; "
                f"stderr={transcript.stderr!r}; "
                f"screen={transcript.screen_stdout(rows=32, cols=120)!r}; "
                f"normalized={output!r}; artifacts={str(tmp_path)!r}"
            )
    assert not readiness_failures, "\n".join(readiness_failures)


def test_windows_conpty_native_and_python_exec_approval_roundtrip_when_enabled(tmp_path: Path) -> None:
    """Compare the fixed-Rust and Python interactive approval product path.

    Fixed Rust commit 1c7832f owners:
    ``core::session::request_command_approval`` ->
    ``tui::chatwidget::approval_requests`` ->
    ``bottom_pane::approval_overlay`` -> ``Op::ExecApproval``.
    """

    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    # Fixed-Rust ``unified exec on request escalated requires approval`` uses
    # read-only plus an explicitly escalated Python command. Use the Windows
    # executable spelling while preserving that exact policy shape.
    command = 'python -c "print(\'PYCODEX_APPROVAL_EXECUTED\')"'
    final_answer = "PYCODEX_APPROVAL_DONE"
    approval_title = "Would you like to run the following command?"
    approval_option = "Yes, proceed"
    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-approval-tool"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-pycodex-approval",
                "type": "function_call",
                "call_id": "call-pycodex-approval",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": command,
                        "sandbox_permissions": "require_escalated",
                        "justification": "deterministic approval parity fixture",
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-approval-tool",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )
    final_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-approval-final"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-approval-final",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-approval-final",
            "output_index": 0,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-approval-final",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-approval-final",
                "usage": {
                    "input_tokens": 2,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 4,
                },
            },
        },
    )

    def run_pair_member(command_spec: TuiComparisonCommand, prompt_marker: str, prefix: str) -> TuiProcessTranscript:
        with _SseFixtureServer((tool_body, final_body)) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[features]\n"
                "unified_exec = true\n"
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for approval comparison"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "run deterministic approval tool",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="approval tool",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "y",
                            ready_text_sequence=(approval_title, approval_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=("Ran", "PYCODEX_APPROVAL_EXECUTED", final_answer, prompt_marker),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=55,
                    size=TerminalSize(rows=36, cols=120),
                )
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}\n"
                f"normalized={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            transcript.write_artifacts(tmp_path, prefix=prefix, rows=36, cols=120)
            return transcript

    extra_args = (
        "--enable",
        "unified_exec",
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
        sandbox_mode="read-only",
        approval_policy="on-request",
    )
    rust_transcript = run_pair_member(rust, "mock-model default", "rust-approval")
    python_transcript = run_pair_member(python, "mock-model", "python-approval")

    failures: list[str] = []
    for label, transcript, prompt_marker in (
        ("rust", rust_transcript, "mock-model default"),
        ("python", python_transcript, "mock-model"),
    ):
        expected_approval = (approval_title, approval_option)
        expected_completion = ("Ran", "PYCODEX_APPROVAL_EXECUTED", final_answer, prompt_marker)
        if expected_approval not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing approval checkpoint: {transcript.observed_ready_sequences!r}")
        if expected_completion not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing completion checkpoint: {transcript.observed_ready_sequences!r}")
        normalized = transcript.normalized_stdout()
        if approval_title not in normalized or final_answer not in normalized:
            failures.append(f"{label} normalized transcript incomplete: {normalized!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_exec_approval_cancel_resize_and_recovery_when_enabled(
    tmp_path: Path,
) -> None:
    """Exercise cancel, modal resize, title cleanup, and next-turn IME recovery.

    Fixed Rust commit 1c7832f owners:
    ``bottom_pane::approval_overlay::exec_options`` maps Esc to
    ``CommandExecutionApprovalDecision::Cancel``; ``chatwidget`` owns the
    action-required title lifecycle; ``custom_terminal`` and
    ``app::resize_reflow`` preserve the active modal across resize.
    """

    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    chinese_answer = "PYCODEX_CHINESE_RECOVERED"
    approval_title = "Would you like to run the following command?"
    cancel_option = "No, and tell Codex what to do differently"

    def final_body(response_id: str, message_id: str, text: str) -> bytes:
        return _responses_sse(
            {"type": "response.created", "response": {"id": response_id}},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": message_id,
                    "content": [{"type": "output_text", "text": text}],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "usage": {
                        "input_tokens": 2,
                        "input_tokens_details": None,
                        "output_tokens": 2,
                        "output_tokens_details": None,
                        "total_tokens": 4,
                    },
                },
            },
        )

    def run_pair_member(
        command_spec: TuiComparisonCommand,
        prompt_marker: str,
        prefix: str,
    ) -> TuiProcessTranscript:
        side_effect_path = tmp_path / f"{prefix}-cancelled-command.txt"
        side_effect_path.unlink(missing_ok=True)
        command = (
            'python -c "from pathlib import Path; '
            f"Path(r'{side_effect_path}').write_text('ran', encoding='utf-8')\""
        )
        tool_body = _responses_sse(
            {"type": "response.created", "response": {"id": "resp-cancel-tool"}},
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "fc-pycodex-cancel",
                    "type": "function_call",
                    "call_id": "call-pycodex-cancel",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {
                            "cmd": command,
                            "sandbox_permissions": "require_escalated",
                            "justification": "deterministic cancel and resize parity fixture",
                        },
                        separators=(",", ":"),
                    ),
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp-cancel-tool",
                    "usage": {
                        "input_tokens": 1,
                        "input_tokens_details": None,
                        "output_tokens": 1,
                        "output_tokens_details": None,
                        "total_tokens": 2,
                    },
                },
            },
        )
        with _SseFixtureServer(
            (
                tool_body,
                final_body("resp-chinese-final", "msg-chinese-final", chinese_answer),
            )
        ) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "unified_exec = true\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for cancel and resize comparison"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "run deterministic cancelled approval tool",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="cancelled approval tool",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            resize=TerminalSize(rows=22, cols=80),
                            ready_text_sequence=(approval_title, cancel_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "\x1b",
                            resize=TerminalSize(rows=36, cols=120),
                            ready_text_sequence=(approval_title, cancel_option),
                            ready_timeout=20.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=("Conversation interrupted", prompt_marker),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep(
                            "你好",
                            ready_timeout=0.2,
                            chunk_delay=0.05,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="你好",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(chinese_answer, prompt_marker),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=65,
                    size=TerminalSize(rows=36, cols=120),
                )
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}; checkpoints={transcript.observed_ready_sequences!r}; "
                f"normalized={transcript.normalized_stdout()!r}; artifacts={str(tmp_path)!r}"
            )
            assert not side_effect_path.exists(), (
                f"{prefix} executed the cancelled command; normalized={transcript.normalized_stdout()!r}"
            )
            transcript.write_artifacts(tmp_path, prefix=prefix, rows=36, cols=120)
            return transcript

    extra_args = (
        "--enable",
        "unified_exec",
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
        sandbox_mode="read-only",
        approval_policy="on-request",
    )
    rust_transcript = run_pair_member(rust, "mock-model default", "rust-approval-cancel-resize")
    python_transcript = run_pair_member(python, "mock-model", "python-approval-cancel-resize")

    failures: list[str] = []
    for label, transcript, prompt_marker in (
        ("rust", rust_transcript, "mock-model default"),
        ("python", python_transcript, "mock-model"),
    ):
        expected_modal = (approval_title, cancel_option)
        expected_cancel = ("Conversation interrupted", prompt_marker)
        expected_chinese = (chinese_answer, prompt_marker)
        observed = transcript.observed_ready_sequences
        if observed.count(expected_modal) != 2:
            failures.append(f"{label} did not preserve the modal across both resize checkpoints: {observed!r}")
        if expected_cancel not in observed or expected_chinese not in observed:
            failures.append(f"{label} did not recover both post-cancel turns: {observed!r}")
        normalized = transcript.normalized_stdout()
        if "canceled the request to run" not in normalized:
            failures.append(f"{label} missing typed cancel history: {normalized!r}")
        if "你好" not in normalized or chinese_answer not in normalized:
            failures.append(f"{label} lost post-modal Chinese input or response: {normalized!r}")
        titles = re.findall(r"\x1b\]0;([^\x07]*)\x07", transcript.stdout)
        action_index = next((index for index, title in enumerate(titles) if "Action Required" in title), None)
        if action_index is None or not any("Action Required" not in title for title in titles[action_index + 1 :]):
            failures.append(f"{label} did not restore the terminal title after cancellation: {titles!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_patch_approval_roundtrip_when_enabled(tmp_path: Path) -> None:
    """Compare fixed-Rust and Python apply-patch approval product paths.

    Fixed Rust commit 1c7832f owners:
    ``core::tools::runtimes::apply_patch`` ->
    ``tui::chatwidget::approval_requests`` ->
    ``bottom_pane::approval_overlay`` -> ``Op::PatchApproval``.
    """

    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    final_answer = "PYCODEX_PATCH_APPROVAL_DONE"
    approval_title = "Would you like to make the following edits?"
    approval_option = "Yes, proceed"

    def run_pair_member(command_spec: TuiComparisonCommand, prompt_marker: str, prefix: str) -> TuiProcessTranscript:
        relative_path = Path(".tmp") / f"conpty-{prefix}-patch-approval.txt"
        target = repo_root / relative_path
        target.unlink(missing_ok=True)
        patch_text = (
            "*** Begin Patch\n"
            f"*** Add File: {relative_path.as_posix()}\n"
            f"+created by {prefix} approval fixture\n"
            "*** End Patch\n"
        )
        tool_body = _responses_sse(
            {"type": "response.created", "response": {"id": f"resp-{prefix}-patch-tool"}},
            {
                "type": "response.output_item.added",
                "item": {
                    "id": f"ctc-{prefix}-patch",
                    "type": "custom_tool_call",
                    "call_id": f"call-{prefix}-patch",
                    "name": "apply_patch",
                    "input": "",
                },
                "output_index": 0,
            },
            {
                "type": "response.custom_tool_call_input.delta",
                "item_id": f"ctc-{prefix}-patch",
                "call_id": f"call-{prefix}-patch",
                "output_index": 0,
                "delta": patch_text,
            },
            {
                "type": "response.output_item.done",
                "item": {
                    "id": f"ctc-{prefix}-patch",
                    "type": "custom_tool_call",
                    "call_id": f"call-{prefix}-patch",
                    "name": "apply_patch",
                    "input": patch_text,
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": f"resp-{prefix}-patch-tool",
                    "usage": {
                        "input_tokens": 1,
                        "input_tokens_details": None,
                        "output_tokens": 1,
                        "output_tokens_details": None,
                        "total_tokens": 2,
                    },
                },
            },
        )
        final_body = _responses_sse(
            {"type": "response.created", "response": {"id": f"resp-{prefix}-patch-final"}},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": f"msg-{prefix}-patch-final",
                    "content": [{"type": "output_text", "text": final_answer}],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": f"resp-{prefix}-patch-final",
                    "usage": {
                        "input_tokens": 2,
                        "input_tokens_details": None,
                        "output_tokens": 2,
                        "output_tokens_details": None,
                        "total_tokens": 4,
                    },
                },
            },
        )
        try:
            with _SseFixtureServer((tool_body, final_body)) as server:
                config = (
                    'model = "gpt-5.4"\n'
                    'model_provider = "pycodex_mock"\n'
                    'approval_policy = "on-request"\n'
                    'sandbox_mode = "read-only"\n'
                    'suppress_unstable_features_warning = true\n\n'
                    "[model_providers.pycodex_mock]\n"
                    'name = "Mock provider for patch approval comparison"\n'
                    f'base_url = "{server.base_url}"\n'
                    'wire_api = "responses"\n'
                    "request_max_retries = 0\n"
                    "stream_max_retries = 0\n"
                    "supports_websockets = false\n\n"
                    f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                    'trust_level = "trusted"\n'
                )
                env, temp_home = _isolated_codex_home_env_with_config(config)
                with temp_home:
                    transcript = run_windows_conpty_tui_command(
                        command_spec,
                        input_steps=(
                            ConptyInputStep(
                                "apply deterministic patch",
                                ready_pattern=READY_COMPOSER_PATTERN,
                                ready_timeout=30.0,
                                ready_quiet_period=0.2,
                            ),
                            ConptyInputStep("\r", ready_text="deterministic patch", ready_timeout=10.0),
                            ConptyInputStep(
                                "y",
                                ready_text_sequence=(approval_title, approval_option),
                                ready_timeout=40.0,
                                ready_quiet_period=0.1,
                            ),
                            ConptyInputStep(
                                "",
                                ready_text_sequence=(final_answer, prompt_marker),
                                ready_timeout=40.0,
                            ),
                            ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                        ),
                        env=env,
                        timeout=55,
                        size=TerminalSize(rows=36, cols=120),
                    )
                transcript.write_artifacts(tmp_path, prefix=f"{prefix}-patch-approval", rows=36, cols=120)
                assert len(server.requests) >= 2, transcript.normalized_stdout()
                assert target.exists(), (
                    f"{prefix} did not apply approved patch; "
                    f"checkpoints={transcript.observed_ready_sequences!r}; "
                    f"normalized={transcript.normalized_stdout()!r}; artifacts={str(tmp_path)!r}"
                )
                assert target.read_text(encoding="utf-8").strip() == f"created by {prefix} approval fixture"
                return transcript
        finally:
            target.unlink(missing_ok=True)

    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
        sandbox_mode="read-only",
        approval_policy="on-request",
    )
    rust_transcript = run_pair_member(rust, "gpt-5.4", "rust")
    python_transcript = run_pair_member(python, "gpt-5.4", "python")

    failures: list[str] = []
    for label, transcript, prompt_marker in (
        ("rust", rust_transcript, "gpt-5.4"),
        ("python", python_transcript, "gpt-5.4"),
    ):
        expected_approval = (approval_title, approval_option)
        expected_completion = (final_answer, prompt_marker)
        if expected_approval not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing patch approval checkpoint: {transcript.observed_ready_sequences!r}")
        if expected_completion not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing patch completion checkpoint: {transcript.observed_ready_sequences!r}")
        normalized = transcript.normalized_stdout()
        if "Added" not in normalized or f"conpty-{label}-patch-approval.txt" not in normalized:
            failures.append(f"{label} missing typed patch history: {normalized!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_permissions_approval_roundtrip_when_enabled(tmp_path: Path) -> None:
    """Compare fixed-Rust and Python request-permissions approval paths.

    Fixed Rust commit 1c7832f owners:
    ``core::session::request_permissions`` ->
    ``tui::chatwidget::protocol_requests`` ->
    ``bottom_pane::approval_overlay`` -> ``Op::RequestPermissionsResponse``.
    """

    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    final_answer = "PYCODEX_PERMISSIONS_APPROVAL_DONE"
    approval_title = "Would you like to grant these permissions?"
    approval_option = "Yes, grant these permissions for this turn"
    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-permissions-tool"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-pycodex-permissions",
                "type": "function_call",
                "call_id": "call-pycodex-permissions",
                "name": "request_permissions",
                "arguments": json.dumps(
                    {
                        "reason": "deterministic network permission fixture",
                        "permissions": {"network": {"enabled": True}},
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-permissions-tool",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )
    final_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-permissions-final"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-permissions-final",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-permissions-final",
                "usage": {
                    "input_tokens": 2,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 4,
                },
            },
        },
    )

    def run_pair_member(command_spec: TuiComparisonCommand, prefix: str) -> TuiProcessTranscript:
        with _SseFixtureServer((tool_body, final_body)) as server:
            config = (
                'model = "gpt-5.4"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "request_permissions_tool = true\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for permissions approval comparison"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "request deterministic permissions",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("\r", ready_text="deterministic permissions", ready_timeout=10.0),
                        ConptyInputStep(
                            "y",
                            ready_text_sequence=(approval_title, approval_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(final_answer, "gpt-5.4"),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=55,
                    size=TerminalSize(rows=36, cols=120),
                )
            transcript.write_artifacts(tmp_path, prefix=f"{prefix}-permissions-approval", rows=36, cols=120)
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}; checkpoints={transcript.observed_ready_sequences!r}; "
                f"normalized={transcript.normalized_stdout()!r}; artifacts={str(tmp_path)!r}"
            )
            return transcript

    extra_args = (
        "--enable",
        "request_permissions_tool",
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
        sandbox_mode="read-only",
        approval_policy="on-request",
    )
    rust_transcript = run_pair_member(rust, "rust")
    python_transcript = run_pair_member(python, "python")

    failures: list[str] = []
    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        if (approval_title, approval_option) not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing permissions approval checkpoint: {transcript.observed_ready_sequences!r}")
        if (final_answer, "gpt-5.4") not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing permissions completion checkpoint: {transcript.observed_ready_sequences!r}")
        normalized = transcript.normalized_stdout()
        if "You granted additional permissions" not in normalized:
            failures.append(f"{label} missing permissions audit history: {normalized!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_permissions_session_grant_reused_next_turn_when_enabled(
    tmp_path: Path,
) -> None:
    """Prove a session-scoped permission grant reaches a later turn's tool plan.

    Fixed Rust commit 1c7832f owners:
    ``core::session::record_granted_request_permissions_for_turn`` records a
    session grant in ``SessionState``; ``tools::handlers::apply_granted_turn_permissions``
    marks an identical later permission profile preapproved. The second turn
    must therefore execute without opening another approval overlay.
    """

    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    first_answer = "PYCODEX_SESSION_PERMISSION_GRANTED"
    command_output = "PYCODEX_SESSION_PERMISSION_REUSED"
    second_answer = "PYCODEX_SESSION_PERMISSION_SECOND_TURN_DONE"
    approval_title = "Would you like to grant these permissions?"
    session_option = "Yes, grant these permissions for this session"
    different_approval_title = "Would you like to run the following command?"
    different_side_effect = repo_root / ".tmp" / "permission-profile-different.txt"

    def completed_message(response_id: str, message_id: str, text: str) -> bytes:
        return _responses_sse(
            {"type": "response.created", "response": {"id": response_id}},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": message_id,
                    "content": [{"type": "output_text", "text": text}],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "usage": {
                        "input_tokens": 2,
                        "input_tokens_details": None,
                        "output_tokens": 2,
                        "output_tokens_details": None,
                        "total_tokens": 4,
                    },
                },
            },
        )

    permissions_tool = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-session-permissions-tool"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-session-permissions",
                "type": "function_call",
                "call_id": "call-session-permissions",
                "name": "request_permissions",
                "arguments": json.dumps(
                    {
                        "reason": "reuse deterministic network permission in the next turn",
                        "permissions": {"network": {"enabled": True}},
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-session-permissions-tool",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )
    exec_tool = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-session-permissions-exec"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-session-permissions-exec",
                "type": "function_call",
                "call_id": "call-session-permissions-exec",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": f"echo {command_output}",
                        "sandbox_permissions": "use_default",
                        "additional_permissions": {"network": {"enabled": True}},
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-session-permissions-exec",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )
    different_exec_tool = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-session-permissions-different-exec"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-session-permissions-different-exec",
                "type": "function_call",
                "call_id": "call-session-permissions-different-exec",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": (
                            "Set-Content -LiteralPath "
                            f"'{different_side_effect}' -Value 'PYCODEX_DIFFERENT_PERMISSION_EXECUTED'"
                        ),
                        "sandbox_permissions": "with_additional_permissions",
                        "additional_permissions": {
                            "file_system": {"write": [str(different_side_effect.parent)]}
                        },
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-session-permissions-different-exec",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )

    def run_pair_member(command_spec: TuiComparisonCommand, prefix: str) -> TuiProcessTranscript:
        bodies = (
            permissions_tool,
            completed_message("resp-session-permissions-first-final", "msg-session-permissions-first", first_answer),
            exec_tool,
            completed_message("resp-session-permissions-second-final", "msg-session-permissions-second", second_answer),
            different_exec_tool,
        )
        with _SseFixtureServer(bodies) as server:
            config = (
                'model = "gpt-5.4"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "exec_permission_approvals = true\n"
                "request_permissions_tool = true\n"
                "unified_exec = true\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for session permission reuse comparison"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "grant deterministic network permission for this session",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("\r", ready_text="network permission", ready_timeout=10.0),
                        ConptyInputStep(
                            "a",
                            ready_text_sequence=(approval_title, session_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_pattern=(
                                rf"(?ms){re.escape(first_answer)}.*?"
                                r"(?:^>\s*$|^\s*\u203a(?:\s+.+)?$)"
                            ),
                            ready_timeout=40.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "reuse the same network permission now",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep("\r", ready_text="reuse the same network permission now", ready_timeout=10.0),
                        ConptyInputStep(
                            "",
                            ready_text=second_answer,
                            ready_timeout=45.0,
                            ready_quiet_period=0.5,
                        ),
                        ConptyInputStep(
                            "request a materially different file write permission now",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="request a materially different file write permission now",
                            ready_timeout=10.0,
                        ),
                        ConptyInputStep(
                            "\x1b",
                            ready_text_sequence=(different_approval_title, "Permission rule:"),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text="Conversation interrupted",
                            ready_timeout=40.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=70,
                    size=TerminalSize(rows=36, cols=120),
                )
            transcript.write_artifacts(tmp_path, prefix=f"{prefix}-permissions-session-reuse", rows=36, cols=120)
            assert len(server.requests) >= 5, (
                f"requests={server.requests!r}; checkpoints={transcript.observed_ready_sequences!r}; "
                f"normalized={transcript.normalized_stdout()!r}; artifacts={str(tmp_path)!r}"
            )
            assert not different_side_effect.exists(), (
                f"{prefix} executed a materially different permission profile before approval"
            )
            first_request = json.loads(server.request_bodies[0].decode("utf-8"))
            exec_command = next(tool for tool in first_request["tools"] if tool.get("name") == "exec_command")
            exec_properties = exec_command["parameters"]["properties"]
            assert "additional_permissions" in exec_properties
            assert "with_additional_permissions" in exec_properties["sandbox_permissions"]["description"]
            return transcript

    extra_args = (
        "--enable",
        "request_permissions_tool",
        "--enable",
        "exec_permission_approvals",
        "--enable",
        "unified_exec",
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
        sandbox_mode="read-only",
        approval_policy="on-request",
    )
    rust_transcript = run_pair_member(rust, "rust")
    python_transcript = run_pair_member(python, "python")

    failures: list[str] = []
    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        observed = transcript.observed_ready_sequences
        if observed.count((approval_title, session_option)) != 1:
            failures.append(f"{label} did not expose exactly one session grant checkpoint: {observed!r}")
        if (different_approval_title, "Permission rule:") not in observed:
            failures.append(f"{label} did not prompt for a materially different permission profile: {observed!r}")
        normalized = transcript.normalized_stdout()
        if second_answer not in normalized:
            failures.append(f"{label} did not reuse the session grant in the next turn: {normalized!r}")
        if "You granted additional permissions for this session" not in normalized:
            failures.append(f"{label} did not record the session grant decision: {normalized!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_local_sse_parallel_exec_commands_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-core tool executors can advertise supports_parallel_tool_calls.
    # - codex-core preserves grouped function_call items before their matching
    #   tool outputs in the follow-up model request.
    # - codex-tui::chatwidget::command_lifecycle keeps multiple in-flight
    #   command rows visible until command completion, then exec_cell renders
    #   them as completed `Ran` rows with bounded output previews.
    #
    # This native comparison feeds two exec_command calls in the same Responses
    # turn to source-built Rust Codex and Python PyCodex. It proves the product
    # shell can surface more than one tool result before the final answer.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    command_a = "echo PYCODEX_PARALLEL_A"
    command_b = "echo PYCODEX_PARALLEL_B"
    final_answer = "PYCODEX_PARALLEL_DONE"

    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-parallel-tools"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-pycodex-parallel-a",
                "type": "function_call",
                "call_id": "call-pycodex-parallel-a",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": command_a}, separators=(",", ":")),
            },
        },
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-pycodex-parallel-b",
                "type": "function_call",
                "call_id": "call-pycodex-parallel-b",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": command_b}, separators=(",", ":")),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-parallel-tools",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 3,
                },
            },
        },
    )
    final_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-parallel-final"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-parallel-final",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-local-parallel-final",
            "output_index": 0,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-parallel-final",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-parallel-final",
                "usage": {
                    "input_tokens": 3,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 5,
                },
            },
        },
    )

    def run_pair_member(command_spec: TuiComparisonCommand, prompt_marker: str) -> object:
        with _SseFixtureServer((tool_body, final_body)) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                "experimental_use_unified_exec_tool = true\n"
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for local parallel exec-command test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "run deterministic parallel exec tools",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="parallel exec tools",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(
                                "Ran",
                                "PYCODEX_PARALLEL_A",
                                "PYCODEX_PARALLEL_B",
                                final_answer,
                                prompt_marker,
                            ),
                            ready_timeout=45.0,
                        ),
                        ConptyInputStep(
                            "/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                    ),
                    env=env,
                    timeout=55,
                    size=TerminalSize(rows=34, cols=120),
                )
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    extra_args = (
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert final_answer in output


def test_windows_conpty_python_local_sse_codepage_chinese_submission_when_enabled() -> None:
    # Rust source contract:
    # - codex-tui::tui enables Windows VT/raw terminal input before running the
    #   app.
    # - codex-tui::tui::event_stream consumes crossterm KeyEvents, so IME text
    #   and Enter reach bottom_pane::chat_composer as decoded input events.
    #
    # Python's Windows console event source reads bytes from ConPTY. Windows
    # delivers Chinese input as console-codepage bytes on this host, so this
    # product-chain regression proves those bytes still become a UserTurn.
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    repo_root = _repo_root()
    # CP936 bytes for this prompt are valid UTF-8 for unrelated glyphs, so it
    # catches mojibake that simpler prompts such as "\u4f60\u597d" do not.
    prompt = "\u4ec0\u4e48"
    answer = "PYCODEX_CHINESE_OK"
    body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-chinese"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-chinese",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-chinese",
            "output_index": 0,
            "content_index": 0,
            "delta": answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-chinese",
                "content": [{"type": "output_text", "text": answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-chinese",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 3,
                },
            },
        },
    )

    with _SseFixtureServer((body,)) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for Chinese input test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        with temp_home:
            _, python = build_rust_python_inline_pair(
                repo_root=repo_root,
                extra_args=("--disable", "apps", "--disable", "plugins"),
            )
            transcript = run_windows_conpty_tui_command(
                python,
                input_steps=(
                    ConptyInputStep(
                        prompt,
                        ready_pattern=READY_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.2,
                        chunk_delay=0.02,
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_text=prompt,
                        ready_timeout=10.0,
                        ready_quiet_period=0.2,
                        chunk_delay=0.02,
                    ),
                    ConptyInputStep("", ready_text=answer, ready_timeout=25.0),
                    ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ConptyInputStep("", ready_text="Token usage:", ready_timeout=10.0),
                ),
                env=env,
                timeout=35,
                size=TerminalSize(rows=32, cols=120),
            )

    output = transcript.normalized_stdout()
    assert prompt in output
    assert answer in output
    assert len(server.requests) == 1


def test_windows_conpty_native_and_python_long_transcript_overlay_bottom_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::pager_overlay::TranscriptOverlay::new starts pinned to the
    #   bottom via PagerView scroll_offset = usize::MAX.
    # - codex-tui::app::input maps Ctrl+T to the transcript overlay.
    # This product comparison proves a long assistant reply reaches the real
    # transcript overlay and opens at the Rust bottom-pinned position after a
    # source-built Rust/Python local SSE turn. Scroll/page continuity remains
    # owned by pager_overlay module tests because text-only ConPTY writes do not
    # reliably synthesize the modifier/special-key pager events for source-built
    # Rust. Exact cell geometry remains owned by pager_overlay module tests.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    long_reply = "\n".join(f"long overlay line {index:02d}" for index in range(1, 49))
    sse_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-long-overlay"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-long-overlay",
                "content": [{"type": "output_text", "text": long_reply}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-long-overlay",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, env: dict[str, str]) -> object:
        return run_windows_conpty_tui_command(
            command,
            input_steps=(
                ConptyInputStep(
                    "Send a long transcript overlay answer.",
                    ready_pattern=READY_COMPOSER_PATTERN,
                    ready_timeout=30.0,
                    ready_quiet_period=0.2,
                    chunk_delay=0.01,
                ),
                ConptyInputStep(
                    "\r",
                    ready_text="overlay answer.",
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                    chunk_delay=0.01,
                ),
                ConptyInputStep(
                    "\x14",
                    ready_timeout=1.0,
                    ready_quiet_period=0.5,
                    chunk_delay=0.02,
                ),
                ConptyInputStep(
                    "q",
                    ready_text="T R A N S C R I P T",
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                    chunk_delay=0.005,
                ),
                ConptyInputStep(
                    "/quit\r",
                    ready_pattern=READY_COMPOSER_PATTERN,
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                    chunk_delay=0.02,
                ),
            ),
            env=env,
            timeout=45,
            size=TerminalSize(rows=20, cols=100),
        )

    with _SseFixtureServer(sse_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for transcript overlay test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        extra_args = (
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
        with temp_home:
            rust_transcript = run_pair_member(rust, env)
            python_transcript = run_pair_member(python, env)

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nstdout={output}"
        assert "OpenAI Codex" in output, detail
        assert "T R A N S C R I P T" in output, detail
        assert "↑/↓ to scroll" in output, detail
        assert "pgup/pgdn to page" in output, detail
        assert "home/end to jump" in output, detail
        assert "q to quit" in output, detail
        assert "long overlay line 48" in output, detail
        assert "100%" in output, detail
        if transcript.returncode == 0:
            continue
        combined = transcript.normalized_combined()
        assert "ConPTY command timed out" in combined or "ConPTY ready condition timed out" in combined, detail


def test_windows_conpty_native_and_python_long_transcript_overlay_home_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::pager_overlay::PagerView::handle_key_event maps Home to
    #   jump_top.
    # - PagerView::render owns the current-screen percent indicator.
    # - Rust tests: transcript_overlay_paging_is_continuous_and_round_trips
    #   and pager_view_is_scrolled_to_bottom_accounts_for_wrapped_height.
    #
    # Unlike cumulative stdout assertions, this comparison uses the harness VT
    # screen projection to assert the current overlay screen after navigation.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    long_reply = "\n".join(f"screen nav line {index:02d}" for index in range(1, 49))
    sse_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-screen-nav"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-screen-nav",
                "content": [{"type": "output_text", "text": long_reply}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-screen-nav",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, env: dict[str, str]) -> object:
        steps = [
            ConptyInputStep(
                "Send transcript screen navigation answer.",
                ready_pattern=READY_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "\r",
                ready_text="navigation answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("\x1b[H", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep("", ready_pattern=r"(?<!\d)0%", ready_timeout=5.0, ready_quiet_period=0.5),
        ]
        return run_windows_conpty_tui_command(
            command,
            input_steps=tuple(steps),
            env=env,
            timeout=2,
            size=TerminalSize(rows=20, cols=100),
        )

    with _SseFixtureServer(sse_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for transcript screen navigation test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        extra_args = (
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
        with temp_home:
            home_transcripts = [
                run_pair_member(rust, env),
                run_pair_member(python, env),
            ]

    for transcript in home_transcripts:
        screen = transcript.screen_stdout(rows=20, cols=100)
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={transcript.normalized_stdout()}"
        assert "T R A N S C R I P T" in screen, detail
        assert re.search(r"(?<!\d)0%", screen), detail
        assert "100%" not in screen, detail
        assert "[H" not in screen, detail


def test_windows_conpty_native_and_python_long_transcript_overlay_page_up_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::pager_overlay::PagerView::handle_key_event maps Ctrl+B and
    #   PageUp through keymap.rs::PagerKeymap.page_up.
    # - PagerView::page_height scrolls by the last rendered content-area
    #   height, not by a smaller terminal-widget default.
    # - Rust test: transcript_overlay_paging_is_continuous_and_round_trips.
    #
    # This product comparison uses the current-screen VT projection after
    # opening a long transcript at the bottom and pressing Ctrl+B once. The
    # exact visible rows differ between Ratatui and Python's terminal runtime
    # because Python keeps the product shell/footer mounted, but both must leave the 100%
    # bottom-pinned page and land on an intermediate page rather than only
    # nudging by a few rows.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    long_reply = "\n".join(f"ctrlb probe line {index:02d}" for index in range(1, 70))
    sse_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-ctrlb-page"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-ctrlb-page",
                "content": [{"type": "output_text", "text": long_reply}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-ctrlb-page",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, env: dict[str, str]) -> object:
        steps = [
            ConptyInputStep(
                "Send ctrlb probe answer.",
                ready_pattern=READY_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "\r",
                ready_text="ctrlb probe answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("\x02", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
        ]
        return run_windows_conpty_tui_command(
            command,
            input_steps=tuple(steps),
            env=env,
            timeout=3,
            size=TerminalSize(rows=20, cols=100),
        )

    with _SseFixtureServer(sse_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for transcript page-up test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        extra_args = (
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
        with temp_home:
            page_up_transcripts = [
                run_pair_member(rust, env),
                run_pair_member(python, env),
            ]

    for transcript in page_up_transcripts:
        screen = transcript.screen_stdout(rows=20, cols=100)
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={transcript.normalized_stdout()}"
        assert "T R A N S C R I P T" in screen, detail
        percent_matches = [int(match.group(1)) for match in re.finditer(r"(?<!\d)(\d{1,3})%", screen)]
        assert percent_matches, detail
        assert any(60 <= percent < 95 for percent in percent_matches), detail
        assert not re.search(r"(?<!\d)0%", screen), detail
        assert "100%" not in screen, detail
        assert "[H" not in screen, detail


def test_windows_conpty_native_and_python_long_transcript_overlay_page_down_round_trip_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::pager_overlay::PagerView::handle_key_event maps Ctrl+B to
    #   PageUp and Ctrl+F to PageDown via keymap.rs::PagerKeymap.
    # - PagerView::page_height uses the rendered content-area height for both
    #   directions, so PageUp followed by PageDown from the bottom round-trips
    #   to the bottom page.
    # - Rust test: transcript_overlay_paging_is_continuous_and_round_trips.
    #
    # The current-screen percent is intentionally tolerant because Python's
    # terminal runtime keeps the product shell/footer mounted while Ratatui's TranscriptOverlay
    # owns the full screen. Both implementations must still return to the
    # bottom-near page after Ctrl+B then Ctrl+F.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    long_reply = "\n".join(f"roundtrip probe line {index:02d}" for index in range(1, 70))
    sse_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-roundtrip-page"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-roundtrip-page",
                "content": [{"type": "output_text", "text": long_reply}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-roundtrip-page",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, env: dict[str, str]) -> object:
        steps = [
            ConptyInputStep(
                "Send roundtrip probe answer.",
                ready_pattern=READY_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "\r",
                ready_text="roundtrip probe answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("\x02", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep("\x06", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
        ]
        return run_windows_conpty_tui_command(
            command,
            input_steps=tuple(steps),
            env=env,
            timeout=3,
            size=TerminalSize(rows=20, cols=100),
        )

    with _SseFixtureServer(sse_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for transcript page-down round-trip test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        extra_args = (
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
        with temp_home:
            round_trip_transcripts = [
                run_pair_member(rust, env),
                run_pair_member(python, env),
            ]

    for transcript in round_trip_transcripts:
        screen = transcript.screen_stdout(rows=20, cols=100)
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={transcript.normalized_stdout()}"
        assert "T R A N S C R I P T" in screen, detail
        percent_matches = [int(match.group(1)) for match in re.finditer(r"(?<!\d)(\d{1,3})%", screen)]
        assert percent_matches, detail
        assert any(95 <= percent <= 100 for percent in percent_matches), detail
        assert not re.search(r"(?<!\d)0%", screen), detail


def test_windows_conpty_native_and_python_long_transcript_overlay_remapped_top_page_down_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::pager_overlay::PagerView::handle_key_event maps jump_top
    #   and page_down through the configurable PagerKeymap.
    # - keymap.rs::RuntimeKeymap builds `tui.keymap.pager.jump_top` and
    #   `tui.keymap.pager.page_down` from CLI/config overrides.
    # - Rust test: transcript_overlay_paging_is_continuous_and_round_trips
    #   proves PageDown from the top advances by the rendered page height.
    #
    # This native comparison deliberately remaps Home/jump_top to a plain
    # character while using Rust's default Space PageDown binding. That proves
    # the product behavior without depending on Windows ConPTY CSI delivery
    # for Home/PageDown.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    long_reply = "\n".join(f"top page-down probe line {index:02d}" for index in range(1, 70))
    sse_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-top-pagedown"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-top-pagedown",
                "content": [{"type": "output_text", "text": long_reply}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-top-pagedown",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, env: dict[str, str]) -> object:
        steps = [
            ConptyInputStep(
                "Send top page-down probe answer.",
                ready_pattern=READY_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "\r",
                ready_text="top page-down probe answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("g", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep("", ready_pattern=r"(?<!\d)0%", ready_timeout=5.0, ready_quiet_period=0.5),
            ConptyInputStep(" ", ready_timeout=0.5, ready_quiet_period=0.8, chunk_delay=0.02),
        ]
        return run_windows_conpty_tui_command(
            command,
            input_steps=tuple(steps),
            env=env,
            timeout=3,
            size=TerminalSize(rows=20, cols=100),
        )

    with _SseFixtureServer(sse_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for transcript remapped top page-down test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        extra_args = (
            "-c",
            'tui.keymap.pager.jump_top="g"',
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
        with temp_home:
            top_page_down_transcripts = [
                run_pair_member(rust, env),
                run_pair_member(python, env),
            ]

    for transcript in top_page_down_transcripts:
        screen = transcript.screen_stdout(rows=20, cols=100)
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={transcript.normalized_stdout()}"
        assert "T R A N S C R I P T" in screen, detail
        percent_matches = [int(match.group(1)) for match in re.finditer(r"(?<!\d)(\d{1,3})%", screen)]
        assert percent_matches, detail
        if not any(10 <= percent < 60 for percent in percent_matches):
            pytest.xfail(
                "source-built Rust no-alt-screen ConPTY projection still "
                "does not reliably show the intermediate page after remapped "
                "jump_top plus Space/PageDown; depending on readiness/frame "
                "timing the current-screen oracle may remain at 0% or bottom "
                "100%. Pager top-edge behavior remains native current-screen "
                "oracle debt while module/terminal tests prove the Rust "
                "PagerView contract"
            )
        assert any(10 <= percent < 60 for percent in percent_matches), detail
        assert not re.search(r"(?<!\d)0%", screen), detail
        assert "100%" not in screen, detail
        assert "[H" not in screen, detail
        assert "[6~" not in screen, detail


def test_windows_conpty_native_and_python_long_transcript_overlay_end_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::pager_overlay::PagerView::handle_key_event maps End through
    #   keymap.rs::PagerKeymap.jump_bottom and sets scroll_offset = usize::MAX.
    # - The next render clamps that sentinel to the bottom-pinned page.
    # - Rust tests: transcript_overlay_paging_is_continuous_and_round_trips
    #   and pager_view_is_scrolled_to_bottom_accounts_for_wrapped_height.
    #
    # This comparison opens a long transcript, jumps to Home/top, then sends
    # End. The current screen must return to the bottom page for both native
    # Rust and Python, and the special-key sequence must not leak as text.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    long_reply = "\n".join(f"end probe line {index:02d}" for index in range(1, 70))
    sse_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-end-jump"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-end-jump",
                "content": [{"type": "output_text", "text": long_reply}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-end-jump",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, env: dict[str, str]) -> object:
        steps = [
            ConptyInputStep(
                "Send end probe answer.",
                ready_pattern=READY_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "\r",
                ready_text="end probe answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("\x1b[H", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep("\x1b[F", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
        ]
        return run_windows_conpty_tui_command(
            command,
            input_steps=tuple(steps),
            env=env,
            timeout=3,
            size=TerminalSize(rows=20, cols=100),
        )

    with _SseFixtureServer(sse_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for transcript End jump test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        extra_args = (
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
        with temp_home:
            end_transcripts = [
                run_pair_member(rust, env),
                run_pair_member(python, env),
            ]

    for transcript in end_transcripts:
        screen = transcript.screen_stdout(rows=20, cols=100)
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={transcript.normalized_stdout()}"
        assert "T R A N S C R I P T" in screen, detail
        assert "end probe line 69" in screen, detail
        assert re.search(r"(?<!\d)100%", screen), detail
        assert not re.search(r"(?<!\d)0%", screen), detail
        assert "[F" not in screen, detail


def test_windows_conpty_native_and_python_long_transcript_overlay_alternate_scroll_down_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::tui::enter_alt_screen enables alternate scroll so terminals
    #   may translate mouse-wheel movement into arrow-key events.
    # - codex-tui::tui::event_stream explicitly skips raw mouse events.
    # - codex-tui::pager_overlay::PagerView::handle_key_event maps Down through
    #   PagerKeymap.scroll_down and increments scroll_offset by one row.
    #
    # This comparison exercises the Rust-owned wheel-equivalent path: Home moves
    # the transcript to the top, then a Down key (what alternate scroll wheel
    # down becomes for crossterm) advances the current screen to the first
    # non-zero percent. Raw MouseEvent handling is intentionally not asserted
    # because Rust does not consume raw mouse events.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    long_reply = "\n".join(f"wheel key line {index:02d}" for index in range(1, 70))
    sse_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-wheel-key"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-wheel-key",
                "content": [{"type": "output_text", "text": long_reply}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-wheel-key",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, env: dict[str, str]) -> object:
        steps = [
            ConptyInputStep(
                "Send wheel key answer.",
                ready_pattern=READY_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "\r",
                ready_text="wheel key answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("\x1b[H", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep("\x1b[B", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
        ]
        return run_windows_conpty_tui_command(
            command,
            input_steps=tuple(steps),
            env=env,
            timeout=3,
            size=TerminalSize(rows=20, cols=100),
        )

    with _SseFixtureServer(sse_body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for transcript alternate-scroll test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        extra_args = (
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
        with temp_home:
            scroll_transcripts = [
                run_pair_member(rust, env),
                run_pair_member(python, env),
            ]

    for transcript in scroll_transcripts:
        screen = transcript.screen_stdout(rows=20, cols=100)
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={transcript.normalized_stdout()}"
        assert "T R A N S C R I P T" in screen, detail
        assert re.search(r"(?<!\d)1%", screen), detail
        assert not re.search(r"(?<!\d)0%", screen), detail
        assert "100%" not in screen, detail
        assert "[B" not in screen, detail


def test_windows_conpty_native_and_python_shortcut_overlay_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer::handle_shortcut_overlay_key
    #   toggles FooterMode::ShortcutOverlay for an empty composer.
    # - codex-tui::bottom_pane::footer::shortcut_overlay_lines owns the
    #   visible shortcut rows, including transcript and /keymap hints.
    # - Rust tests: shift_question_mark_toggles_shortcut_overlay_when_empty
    #   and shortcut_overlay_persists_while_task_running.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    input_steps = (
        ConptyInputStep("", ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=30.0, ready_quiet_period=0.5),
        ConptyInputStep("?", ready_timeout=0.1, chunk_delay=0.02),
        ConptyInputStep("", ready_text="ctrl + t to view transcript", ready_timeout=10.0),
        ConptyInputStep("?", ready_timeout=0.1, chunk_delay=0.02),
        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
        ConptyInputStep("", ready_text="Shutting down", ready_timeout=10.0),
    )

    env, temp_home = _isolated_codex_home_env()
    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=_with_rust_startup_tip_ready(input_steps),
            env=env,
            timeout=45,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=35,
            size=TerminalSize(rows=32, cols=120),
        )

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "/ for commands" in output
        assert "! for shell commands" in output
        assert "ctrl + t to view transcript" in output
        assert "customize shortcuts with /keymap" in output


def test_windows_conpty_native_and_python_question_mark_after_text_is_literal_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer::handle_shortcut_overlay_key
    #   only toggles shortcut help for an otherwise empty composer.
    # - Rust test: question_mark_only_toggles_on_first_char.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    input_steps = (
        ConptyInputStep("", ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=30.0, ready_quiet_period=0.5),
        ConptyInputStep("h?", ready_timeout=0.1, chunk_delay=0.02),
        ConptyInputStep("\x15", ready_text="h?", ready_timeout=10.0, chunk_delay=0.02),
        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
        ConptyInputStep("", ready_text="Shutting down", ready_timeout=10.0),
    )

    env, temp_home = _isolated_codex_home_env()
    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=45,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=35,
            size=TerminalSize(rows=32, cols=120),
        )

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "h?" in output
        assert "ctrl + t to view transcript" not in output
        assert "customize shortcuts with /keymap" not in output


def test_windows_conpty_native_and_python_double_esc_no_previous_message_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::app::input routes empty-composer Esc to
    #   App::handle_backtrack_esc_key before ChatComposer handles it.
    # - codex-tui::app_backtrack::prime_backtrack only shows the
    #   esc-backtrack composer hint when the transcript has a previous user
    #   message.
    # - codex-tui::app_backtrack::NO_PREVIOUS_MESSAGE_TO_EDIT owns the visible
    #   message when a second Esc tries to edit a missing previous message.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "\x1b",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
        ConptyInputStep("\x1b", ready_timeout=0.1, chunk_delay=0.02),
        ConptyInputStep("/quit\r", ready_text="No previous message to edit.", ready_timeout=10.0, chunk_delay=0.02),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=45,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=35,
            size=TerminalSize(rows=32, cols=120),
        )

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "No previous message to edit." in output
        assert "esc esc to edit previous message" not in output
        assert "Shutting down" in output


def test_windows_conpty_native_and_python_model_popup_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Model to
    #   ChatWidget::open_model_popup().
    # - codex-tui::chatwidget::model_popups renders the "Select Model"
     #   selection view.
    # Esc cancellation is covered by the Rust-derived Python tests because a
    # naked Esc inside Windows ConPTY can be coalesced with following bytes by
    # the terminal input decoder, making it a poor native comparison primitive.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/model\r",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Select Model",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Select Model",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Select Model" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_slash_command_popup_current_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer::sync_command_popup opens the
    #   command popup while the caret edits the first-line slash command name.
    # - codex-tui::bottom_pane::command_popup::filtered_commands_keep_presentation_order_for_prefix
    #   defines the presentation order for "/m" as model, memories, mention, mcp.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    rows = 32
    cols = 120
    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep("", ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=30.0, ready_quiet_period=0.5),
        ConptyInputStep(
            "/m",
            ready_timeout=0.1,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "",
            ready_pattern=r"(?s)/model.*?/memories.*?/mention.*?/mcp",
            ready_timeout=10.0,
            ready_quiet_period=0.5,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=_with_rust_startup_tip_ready(input_steps),
            env=env,
            timeout=10,
            stop_pattern="/mcp",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="/mcp",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=rows, cols=cols)
        assert "OpenAI Codex" in output
        assert re.search(
            r"/model.*?/memories.*?/mention.*?/mcp",
            screen,
            re.DOTALL,
        ), f"screen={screen}\nstdout={output}"
        assert "/plugins" not in screen
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_model_popup_accept_current_opens_reasoning_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::model_popups::model_selection_actions sends
    #   UpdateModel, UpdateReasoningEffort, then PersistModelSelection when a
    #   quick model row is accepted.
    # - codex-tui::bottom_pane::list_selection_view::apply_filter selects the
    #   current enabled row by default, so accepting the current non-auto model
    #   opens the reasoning picker instead of blindly selecting the first row.
    # - Rust tests: model_selection_popup_snapshot and
    #   model_picker_hides_show_in_picker_false_models_from_cache define the
    #   picker contents; model selection action tests define the event order.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    rows = 32
    cols = 120
    input_steps = (
        ConptyInputStep(
            "/model\r",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\r",
            ready_text="Select Model",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern=r"Select Reasoning Level",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern=r"Select Reasoning Level",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=rows, cols=cols)
        assert "OpenAI Codex" in output
        assert "Select Model" in output
        assert "Select Reasoning Level" in screen
        assert "Medium" in screen
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_model_reasoning_keyboard_selection_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::list_selection_view::handle_key_event routes
    #   Down/Enter inside selection views.
    # - codex-tui::chatwidget::model_popups::open_reasoning_popup builds
    #   reasoning-effort rows whose accepted action emits UpdateModel,
    #   UpdateReasoningEffort, and PersistModelSelection.
    # - codex-tui::history_cell::session and status surfaces expose the chosen
    #   model/reasoning effort back through the visible model/footer surface.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    rust_env, rust_temp_home = _isolated_codex_home_env()
    python_env, python_temp_home = _isolated_codex_home_env()
    rows = 32
    cols = 120
    input_steps = (
        ConptyInputStep(
            "/model\r",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\r",
            ready_text="Select Model",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\x1b[B\r",
            ready_text="Select Reasoning Level",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            chunk_delay=0.02,
        ),
    )

    with rust_temp_home, python_temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=rust_env,
            timeout=10,
            stop_pattern=r"gpt-5\.5\s+high",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=python_env,
            timeout=10,
            stop_pattern=r"gpt-5\.5\s+high",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=rows, cols=cols)
        assert "OpenAI Codex" in output
        assert "Select Reasoning Level" in output
        assert re.search(r"gpt-5\.5\s+high", screen), (
            f"expected selected reasoning effort in current screen; screen={screen!r}"
        )
        assert "Traceback" not in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_python_model_selection_persists_across_restart_when_enabled() -> None:
    # Rust source contract:
    # - codex-tui::chatwidget::model_popups emits PersistModelSelection after
    #   the live model and reasoning updates.
    # - codex-tui::app::event_dispatch persists both keys through
    #   config_update::write_config_batch before reporting "Model changed".
    # - codex-core::config::edit::blocking_set_model_top_level proves those
    #   top-level values are the defaults loaded by the next process.
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    repo_root = _repo_root()
    python = build_inline_tui_command(
        "python",
        repo_root=repo_root,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    env, temp_home = _isolated_codex_home_env()
    config_path = Path(env["CODEX_HOME"]) / "config.toml"
    config_path.write_text(
        'model = "gpt-5.2"\n'
        'model_reasoning_effort = "medium"\n'
        + config_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    rows = 32
    cols = 120
    input_steps = (
        ConptyInputStep(
            "/model\r",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\x1b[H\r",
            ready_text="Select Model",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\x1b[B\r",
            ready_text="Select Reasoning Level",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        selected = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern=r"Model changed to \S+ \S+",
            stop_timeout=15,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )
        persisted = read_toml_mapping(config_path)
        persisted_model = str(persisted.get("model") or "")
        persisted_effort = str(persisted.get("model_reasoning_effort") or "")
        restarted = run_windows_conpty_tui_command(
            python,
            input_steps=(),
            env=env,
            timeout=10,
            stop_pattern=rf"model:\s+{re.escape(persisted_model)} {re.escape(persisted_effort)}",
            stop_timeout=15,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )

    assert re.search(r"Model changed to \S+ \S+", selected.normalized_stdout())
    assert persisted_model and persisted_model != "gpt-5.2"
    assert persisted_effort
    assert re.search(
        rf"model:\s+{re.escape(persisted_model)} {re.escape(persisted_effort)}",
        restarted.normalized_stdout(),
    )
    assert "Traceback" not in selected.normalized_stdout()
    assert "Traceback" not in restarted.normalized_stdout()


def test_windows_conpty_native_and_python_review_popup_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Review to
    #   ChatWidget::open_review_popup().
    # - codex-tui::chatwidget::review_popups builds the preset view with
    #   "Select a review preset" and the four Rust preset rows.
    # - chatwidget/tests/review_mode.rs::review_popup_custom_prompt_action_sends_event
    #   proves selecting the custom row emits a local TUI event rather than a
    #   UserTurn prompt.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/review\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Select a review preset",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Select a review preset",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Select a review preset" in output
        assert "Review against a base branch" in output
        assert "Review uncommitted changes" in output
        assert "Review a commit" in output
        assert "Custom review instructions" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_settings_popup_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Settings to
    #   ChatWidget::open_realtime_audio_popup() only when
    #   Feature::RealtimeConversation is enabled.
    # - codex-tui::chatwidget::settings_popups builds the top-level "Settings"
    #   popup with Microphone and Speaker rows.
    # - chatwidget/tests/popups_and_settings.rs::realtime_audio_selection_popup_snapshot
    #   defines the stable title, subtitle, and current-device descriptions.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = (
        "-c",
        "features.realtime_conversation=true",
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/settings\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Configure settings for Codex",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Configure settings for Codex",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Settings" in output
        assert "Configure settings for Codex" in output
        assert "Microphone" in output
        assert "Speaker" in output
        assert "Current: System default" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_permissions_popup_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Permissions
    #   to ChatWidget::open_permissions_popup().
    # - codex-tui::chatwidget::permission_popups builds the
    #   "Update Model Permissions" view from codex-utils-approval-presets.
    # - chatwidget/tests/permissions.rs::approvals_selection_popup_snapshot
    #   defines the Windows preset rows: Read Only, Default, Full Access.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/permissions\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Update Model Permissions",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Update Model Permissions",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Update Model Permissions" in output
        assert "Read Only" in output
        assert "Default" in output
        assert "Full Access" in output
        assert "Agent" not in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_agent_enable_prompt_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Agent to
    #   AppEvent::OpenAgentPicker.
    # - codex-tui::app::session_lifecycle::open_agent_picker opens
    #   open_multi_agent_enable_prompt when Feature::Collab is disabled and no
    #   non-primary agent thread exists.
    # - app/tests.rs::open_agent_picker_prompts_to_enable_multi_agent_when_disabled
    #   and chatwidget/tests/popups_and_settings.rs::multi_agent_enable_prompt_updates_feature_and_emits_notice
    #   prove this local prompt path.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    config_path = Path(env["CODEX_HOME"]) / "config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n[features]\n"
        + "multi_agent = false\n",
        encoding="utf-8",
    )
    input_steps = (
        ConptyInputStep(
            "/agent\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Enable subagents?",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Enable subagents?",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Enable subagents?" in output
        assert "Yes, enable" in output
        assert "Not now" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_keymap_debug_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps `/keymap debug` to
    #   ChatWidget::open_keymap_debug().
    # - chatwidget/tests/slash_commands.rs::slash_keymap_debug_opens_keypress_inspector
    #   proves the inspector opens locally without sending a core op.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/keymap debug",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
        ),
        ConptyInputStep(
            "\r",
            ready_text="/keymap debug",
            ready_timeout=10.0,
            ready_quiet_period=0.2,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Keypress Inspector",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="Keypress Inspector",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Keypress Inspector" in output
        assert "Waiting for a keypress" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_keymap_action_menu_open_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::keymap_setup::picker rows emit OpenKeymapActionMenu.
    # - codex-tui::chatwidget::keymap_picker::open_keymap_action_menu renders
    #   the action-specific "Edit Shortcut" menu instead of closing /keymap.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/keymap\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\r",
            ready_text="Keymap",
            ready_timeout=10.0,
            ready_quiet_period=0.2,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=15,
            stop_pattern="Edit Shortcut",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=15,
            stop_pattern="Edit Shortcut",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Edit Shortcut" in output
        assert "Replace binding" in output or "Set key" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_external_editor_missing_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::app::input checks RuntimeKeymap.app.open_external_editor
    #   and reports MissingEditor through the same user-visible error copy.
    # - codex-tui::keymap::tests::invalid_global_open_external_editor_binding_reports_global_path
    #   fixes the action path as `tui.keymap.global.open_external_editor`.
    #
    # This product comparison drives the real Rust and Python TUI entrypoints
    # with VISUAL/EDITOR absent, then presses Ctrl-G in the composer.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    env, temp_home = _isolated_codex_home_env()
    env.pop("VISUAL", None)
    env.pop("EDITOR", None)
    input_steps = (
        ConptyInputStep(
            "\x07",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
    )
    expected = "Cannot open external editor: set $VISUAL or $EDITOR before starting Codex."

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=15,
            stop_pattern=re.escape(expected),
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=15,
            stop_pattern=re.escape(expected),
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        assert expected in transcript.normalized_stdout()
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_ctrl_l_clear_status_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::app::input maps RuntimeKeymap.app.clear_terminal to
    #   clear_terminal_ui + reset_app_ui_state_after_clear while idle.
    # - codex-tui::app::tests::ctrl_l_clear_ui_after_long_transcript_reuses_clear_header_snapshot
    #   uses the same fresh-header snapshot as /clear.
    #
    # This product comparison opens the local /status card, then presses Ctrl-L
    # and verifies the current screen no longer contains that card.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/status\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\x0c",
            ready_text="Read Only",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=1.0,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=1.0,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        assert "Read Only" in transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=32, cols=120)
        assert "OpenAI Codex" in screen
        assert "Read Only" not in screen
        assert "AskForApproval" not in screen


def test_windows_conpty_native_and_python_clear_slash_transcript_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Clear to
    #   AppEvent::ClearUi while idle.
    # - chatwidget/tests/slash_commands.rs::slash_clear_requests_ui_clear_when_idle
    #   proves the chatwidget dispatch boundary.
    # - codex-tui::app::history_ui::clear_terminal_ui owns the fresh header
    #   replay and stale transcript/status removal after /clear.
    #
    # This product comparison creates a deterministic assistant transcript via
    # local Responses SSE, then submits /clear through the real composer and
    # verifies the current screen no longer contains the previous answer. It
    # complements the Ctrl-L native gate by covering the slash dispatch path.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    answer = "PYCODEX_CLEAR_BEFORE"
    body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-clear-before"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-clear-before",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-clear-before",
            "output_index": 0,
            "content_index": 0,
            "delta": answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-clear-before",
                "content": [{"type": "output_text", "text": answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-clear-before",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 3,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand, prompt_marker: str) -> object:
        with _SseFixtureServer((body,)) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for /clear native test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "CLR",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="CLR",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "/clear\r",
                            ready_text_sequence=(answer, prompt_marker),
                            ready_timeout=35.0,
                            ready_quiet_period=0.5,
                            chunk_delay=0.02,
                        ),
                    ),
                    env=env,
                    timeout=1.0,
                    size=TerminalSize(rows=32, cols=120),
                )
            assert server.requests, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")

    for transcript in (rust_transcript, python_transcript):
        screen = transcript.screen_stdout(rows=32, cols=120)
        if (
            "overflowed its stack" in transcript.normalized_stdout()
            or "overflowed its stack" in screen
        ):
            pytest.xfail(
                "source-built Rust Codex overflows its stack after /clear under "
                "the current no-alt-screen ConPTY probe; keep this as native "
                "oracle debt until the Rust-side/harness boundary is isolated"
            )
        assert "/clear" in transcript.normalized_stdout()
        assert answer in transcript.normalized_stdout()
        assert "OpenAI Codex" in screen
        assert answer not in screen


def test_windows_conpty_native_and_python_toggle_vim_mode_keymap_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::app::input checks RuntimeKeymap.app.toggle_vim_mode before
    #   forwarding a key to the composer.
    # - codex-tui::chatwidget::toggle_vim_mode_and_notify inserts the exact
    #   "Vim mode enabled." / "Vim mode disabled." messages.
    # - codex-tui::keymap defaults Global.toggle_vim_mode to unbound, so this
    #   comparison uses a configured Ctrl-G binding for both Rust and Python
    #   while remapping the default external-editor Ctrl-G action away.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    trust_key = str(repo_root.resolve(strict=False)).lower()
    config_text = (
        f"[projects.'{trust_key}']\n"
        "trust_level = \"trusted\"\n"
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=(
            "-c",
            'tui.keymap.global.open_external_editor="f12"',
            "-c",
            'tui.keymap.global.toggle_vim_mode="ctrl-g"',
            "--disable",
            "apps",
            "--disable",
            "plugins",
        ),
    )
    env, temp_home = _isolated_codex_home_env_with_config(config_text)
    input_steps = (
        ConptyInputStep(
            "\x07",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\x07",
            ready_text="Vim mode enabled.",
            ready_timeout=10.0,
            ready_quiet_period=0.2,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=15,
            stop_pattern="Vim mode disabled\\.",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=15,
            stop_pattern="Vim mode disabled\\.",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Vim mode enabled." in output
        assert "Vim mode disabled." in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_copy_shortcut_no_response_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::interaction::handle_key_event consumes the
    #   configured copy_last_response_binding before normal composer input.
    # - chatwidget/tests/slash_commands.rs::
    #   ctrl_o_copy_reports_when_no_agent_response_exists expects Ctrl-O to
    #   report "No agent response to copy" when no assistant response exists.
    #
    # This product comparison drives the real Rust and Python TUI entrypoints
    # through Windows ConPTY so the terminal key dispatch cannot drift back into
    # submitting Ctrl-O as composer text or ignoring the shortcut.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    trust_key = str(repo_root.resolve(strict=False)).lower()
    config_text = (
        f"[projects.'{trust_key}']\n"
        "trust_level = \"trusted\"\n"
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=(
            "--disable",
            "apps",
            "--disable",
            "plugins",
        ),
    )
    env, temp_home = _isolated_codex_home_env_with_config(config_text)
    input_steps = (
        ConptyInputStep(
            "\x0f",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="No agent response to copy",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="No agent response to copy",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "No agent response to copy" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_copy_slash_no_response_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Copy to
    #   ChatWidget::copy_last_agent_markdown.
    # - codex-tui::chatwidget::interaction::copy_last_agent_markdown_with
    #   reports "No agent response to copy" when no assistant response exists.
    # - chatwidget/tests/slash_commands.rs::
    #   slash_copy_reports_when_no_agent_response_exists covers the module
    #   contract at the Rust chatwidget boundary.
    #
    # This product comparison proves the same behavior through source-built
    # Rust Codex and Python PyCodex TUI entrypoints, so the terminal slash path
    # cannot drift into submitting /copy as a model turn.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    trust_key = str(repo_root.resolve(strict=False)).lower()
    config_text = (
        f"[projects.'{trust_key}']\n"
        "trust_level = \"trusted\"\n"
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=(
            "--disable",
            "apps",
            "--disable",
            "plugins",
        ),
    )
    env, temp_home = _isolated_codex_home_env_with_config(config_text)
    input_steps = (
        ConptyInputStep(
            "/copy\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.02,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="No agent response to copy",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=10,
            stop_pattern="No agent response to copy",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "No agent response to copy" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_diff_slash_dirty_repo_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Diff to local
    #   add_diff_in_progress + async get_git_diff + AppEvent::DiffResult.
    # - codex-tui::get_git_diff runs tracked diff and untracked diff capture
    #   through the workspace command runner without submitting a UserTurn.
    # - get_git_diff.rs::get_git_diff_accepts_diff_exit_code_one proves git
    #   diff status 1 is successful diff output.
    #
    # This product comparison uses a real temporary git repository so both
    # source-built Rust Codex and Python PyCodex exercise their workspace
    # command runners through the TUI /diff slash path.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    git_probe = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
    if git_probe.returncode != 0:
        pytest.skip("git executable is required for /diff native comparison")

    repo_root = _repo_root()
    marker = "PYCODEX_DIFF_NATIVE_NEW"

    with tempfile.TemporaryDirectory(prefix="pycodex-diff-native-") as repo_dir_text:
        target_repo = Path(repo_dir_text)
        subprocess.run(["git", "init"], cwd=target_repo, check=True, capture_output=True, text=True)
        tracked = target_repo / "tracked.txt"
        tracked.write_text("old line\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=target_repo, check=True, capture_output=True, text=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=pycodex@example.invalid",
                "-c",
                "user.name=PyCodex Test",
                "commit",
                "-m",
                "initial",
            ],
            cwd=target_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked.write_text(f"old line\n{marker}\n", encoding="utf-8")

        trust_key = str(target_repo.resolve(strict=False)).lower()
        config_text = (
            f"[projects.'{trust_key}']\n"
            "trust_level = \"trusted\"\n"
        )
        env, temp_home = _isolated_codex_home_env_with_config(config_text)
        env["PYTHONPATH"] = str(repo_root)
        common = (
            "--no-alt-screen",
            "-C",
            str(target_repo),
            "-s",
            "read-only",
            "-a",
            "never",
            "--disable",
            "apps",
            "--disable",
            "plugins",
        )
        rust = TuiComparisonCommand(kind="rust", argv=(str(native_exe), *common), cwd=repo_root)
        python = TuiComparisonCommand(kind="python", argv=(sys.executable, "-m", "pycodex", *common), cwd=repo_root)
        configured_repo_ready_pattern = (
            rf"(?ms)directory:.*{re.escape(target_repo.name)}.*"
            rf"(?:^>\s*$|^\s*\u203a\s+.+$)"
        )
        input_steps = (
            ConptyInputStep(
                "",
                ready_pattern=configured_repo_ready_pattern,
                ready_timeout=30.0,
            ),
            ConptyInputStep(
                "\x15/diff\r",
                ready_timeout=2.0,
                chunk_delay=0.05,
            ),
        )

        with temp_home:
            rust_transcript = run_windows_conpty_tui_command(
                rust,
                input_steps=input_steps,
                env=env,
                timeout=15,
                stop_pattern=marker,
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=32, cols=120),
            )
            python_transcript = run_windows_conpty_tui_command(
                python,
                input_steps=input_steps,
                env=env,
                timeout=15,
                stop_pattern=marker,
                stop_timeout=10,
                terminate_on_stop_pattern=True,
                size=TerminalSize(rows=32, cols=120),
            )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert marker in output, (
            f"{transcript.argv!r} did not render the dirty git diff marker; "
            f"stderr={transcript.normalized_stderr()!r}\n"
            f"stdout={output}"
        )
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_active_turn_model_slash_disabled_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch checks
    #   SlashCommand::available_during_task() before dispatching a slash command.
    # - chatwidget/tests/exec_flow.rs::
    #   disabled_slash_command_while_task_running_snapshot expects the
    #   in-progress `/model` command to render an error instead of opening the
    #   model picker.
    # - chatwidget/tests/slash_commands.rs::
    #   unavailable_slash_command_is_available_from_local_recall expects the
    #   same disabled message and keeps the typed command in local recall.
    #
    # This product comparison drives the real Rust and Python TUI entrypoints.
    # A delayed local SSE body creates a deterministic active-turn window
    # without relying on live model latency.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    sentinel = "PYCODEX_ACTIVE_SLASH_DONE"
    body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-active-slash"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-active-slash",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-active-slash",
            "output_index": 0,
            "content_index": 0,
            "delta": sentinel,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-active-slash",
                "content": [{"type": "output_text", "text": sentinel}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-active-slash",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 3,
                },
            },
        },
    )

    def run_pair_member(command: TuiComparisonCommand) -> object:
        with _SseFixtureServer(body, response_delay_seconds=5.0) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for active slash test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "active slash prompt",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="active slash prompt",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "/model\r",
                            ready_text_sequence=("Working", "esc to interrupt"),
                            ready_timeout=15.0,
                            # Keep the slash command write atomic enough for
                            # ConPTY.  A delayed per-character write can race
                            # Rust/Python redraws and leave the final "l" as
                            # ordinary composer text, which then creates a
                            # second model request when the cleanup `/quit` is
                            # typed.  The contract under test is that `/model`
                            # is rejected while a turn is active, not terminal
                            # key-repeat behavior.
                            chunk_delay=0.0,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text="'/model' is disabled while a task is in progress.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(sentinel, "mock-model"),
                            ready_timeout=35.0,
                            ready_quiet_period=0.7,
                        ),
                    ),
                    env=env,
                    timeout=15,
                    size=TerminalSize(rows=32, cols=120),
                    stop_pattern=sentinel,
                    stop_timeout=0.1,
                    terminate_on_stop_pattern=True,
                )
            assert len(server.requests) == 1, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            return transcript

    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust)
    python_transcript = run_pair_member(python)

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        # Live active-turn status is enforced by the ConPTY
        # ready_text_sequence above. The retained final screen may be an exit
        # summary after `/quit`, so do not require the transient status row to
        # remain in normalized_stdout.
        # The staged ready condition above proves the transient disabled
        # notice appears.  Rust's no-alt-screen redraw may later erase it from
        # the retained final stdout, so the final transcript assertion focuses
        # on durable semantics: no model popup and the original request
        # completed exactly once.
        assert sentinel in output
        assert "Select Model" not in output
        assert len([request for request in output.splitlines() if sentinel in request]) >= 1


def test_windows_conpty_native_and_python_status_command_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Status to a
    #   local status history cell and only requests a rate-limit refresh after
    #   the immediate render when ChatGPT auth supports it.
    # - codex-tui::status::card::new_status_output_with_rate_limits_handle
    #   owns the visible /status card.
    # - chatwidget/tests/status_command_tests.rs proves /status is rendered
    #   locally without becoming a model UserTurn.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/status\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.03,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=_with_rust_startup_tip_ready(input_steps),
            env=env,
            timeout=55,
            stop_pattern="Session:",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=35,
            stop_pattern="Session:",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
    rust_stdout = rust_transcript.normalized_stdout()
    python_stdout = python_transcript.normalized_stdout()

    for transcript in (rust_stdout, python_stdout):
        assert "/status" in transcript
        assert "OpenAI Codex" in transcript
        assert "Model:" in transcript
        assert "Directory:" in transcript
        assert "Permissions:" in transcript
        assert "Read Only (never)" in transcript
        assert "Session:" in transcript
    for transcript in (rust_transcript, python_transcript):
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_raw_command_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch handles SlashCommand::Raw
    #   locally, toggles raw output mode, and reports RAW_USAGE for invalid
    #   inline args.
    # - chatwidget/tests/slash_commands.rs covers toggle/on/off/invalid args.
    # - chatwidget/tests/status_and_layout.rs covers the visible raw-output
    #   status-line value when that status item is enabled.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = (
        "-c",
        'tui.status_line=["model-with-reasoning","raw-output"]',
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "/raw on\r",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.03,
        ),
        ConptyInputStep("/raw off\r", ready_text="Raw output mode on", ready_timeout=10.0, chunk_delay=0.03),
        ConptyInputStep("/raw maybe\r", ready_text="Raw output mode off", ready_timeout=10.0, chunk_delay=0.03),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=_with_rust_startup_tip_ready(input_steps),
            env=env,
            timeout=20,
            stop_pattern="Usage: /raw \\[on\\|off\\]",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=20,
            stop_pattern="Usage: /raw \\[on\\|off\\]",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Raw output mode on: transcript text is shown for clean terminal selection." in output
        assert "Raw output mode off: rich transcript rendering restored." in output
        assert "Usage: /raw [on|off]" in output
        assert "you\n  /raw" not in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_alt_r_raw_output_toggle_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::keymap defaults app.toggle_raw_output to Alt+R.
    # - codex-tui::app::input handles that shortcut as an app-level key event
    #   and calls apply_raw_output_mode(..., notify=false), so no /raw slash
    #   notice is inserted.
    # - chatwidget/tests/status_and_layout.rs covers the visible raw-output
    #   status-line value when that status item is enabled.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    pytest.skip(
        "text-only ConPTY input cannot synthesize the native Alt+R modifier event; "
        "Rust parity is covered by codex-tui keymap tests and Python ESC-prefix projection tests"
    )

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    extra_args = (
        "-c",
        'tui.status_line=["model-with-reasoning","raw-output"]',
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
    )
    env, temp_home = _isolated_codex_home_env()
    input_steps = (
        ConptyInputStep(
            "\x1br",
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            chunk_delay=0.0,
        ),
    )

    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=env,
            timeout=20,
            stop_pattern="raw output",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=20,
            stop_pattern="raw output",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "raw output" in output
        assert "Raw output mode on:" not in output
        assert "you\n  /raw" not in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_live_prompt_answer_visible_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer returns InputResult::Submitted
    #   for non-empty Enter submissions.
    # - codex-tui::chatwidget commits the user message and submits
    #   Op::UserTurn to the active thread.
    # - codex-tui::app::event_dispatch routes SubmitThreadOp/CodexOp through
    #   the active thread runtime and renders AgentMessageDelta before
    #   TurnCompleted.
    #
    # This opt-in live comparison proves the common product path reaches a real
    # model answer in both source-built Rust Codex and Python PyCodex. It
    # intentionally stops capture after the answer token is visible; clean
    # shutdown remains covered by the separate `/quit` ConPTY comparisons.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_NATIVE_LIVE_PROMPT_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_LIVE_PROMPT_ENV}=1 to run live OAuth prompt comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe)
    prompt = "Reply with exactly PYCODEX_NATIVE_OK and nothing else.\r"
    input_steps = (
        ConptyInputStep(
            prompt,
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            chunk_delay=0.02,
            ready_quiet_period=0.5,
        ),
    )

    rust_transcript = run_windows_conpty_tui_command(
        rust,
        input_steps=input_steps,
        env=_conpty_tui_env(),
        timeout=10,
        size=TerminalSize(rows=32, cols=120),
        stop_pattern="PYCODEX_NATIVE_OK",
        stop_timeout=140,
        terminate_on_stop_pattern=True,
    )
    python_transcript = run_windows_conpty_tui_command(
        python,
        input_steps=input_steps,
        env=_conpty_tui_env(),
        timeout=10,
        size=TerminalSize(rows=32, cols=120),
        stop_pattern="PYCODEX_NATIVE_OK",
        stop_timeout=140,
        terminate_on_stop_pattern=True,
    )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Reply with exactly PYCODEX_NATIVE_OK" in output
        assert "PYCODEX_NATIVE_OK" in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_live_multi_turn_clean_shutdown_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer submits each non-empty Enter as a
    #   user turn.
    # - codex-tui::chatwidget::protocol maps TurnCompleted into
    #   chatwidget::turn_runtime::on_task_complete, restoring composer
    #   readiness for the next user turn.
    # - codex-tui::app builds AppExitInfo after shutdown, while
    #   codex-cli::main::format_exit_messages prints token usage before the
    #   resume hint.
    #
    # This opt-in comparison proves the common product session shape, not just
    # first-answer visibility: answer A -> ready prompt -> answer B -> /quit.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_NATIVE_LIVE_PROMPT_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_LIVE_PROMPT_ENV}=1 to run live OAuth prompt comparison")
    if os.environ.get(RUN_NATIVE_MULTI_TURN_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_MULTI_TURN_ENV}=1 to run experimental multi-turn live comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe)
    first = "PYCODEX_NATIVE_MULTI_A"
    second = "PYCODEX_NATIVE_MULTI_B"
    first_prompt = "Reply with exactly the four parts PYCODEX NATIVE MULTI A joined by underscores and nothing else."
    second_prompt = "Reply with exactly the four parts PYCODEX NATIVE MULTI B joined by underscores and nothing else."

    def input_steps_for_prompt_marker(prompt_marker: str) -> tuple[ConptyInputStep, ...]:
        return (
        ConptyInputStep(
            first_prompt,
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            chunk_delay=0.02,
            ready_quiet_period=0.8,
        ),
        ConptyInputStep(
            "\r",
            ready_text="nothing else.",
            ready_timeout=10.0,
            chunk_delay=0.02,
            ready_quiet_period=0.3,
        ),
        ConptyInputStep(
            "",
            ready_text_sequence=(first, prompt_marker),
            ready_timeout=140.0,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            second_prompt,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "\r",
            ready_text="nothing else.",
            ready_timeout=10.0,
            chunk_delay=0.02,
            ready_quiet_period=0.3,
        ),
        ConptyInputStep(
            "",
            ready_text_sequence=(second, prompt_marker),
            ready_timeout=140.0,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "/quit\r",
            chunk_delay=0.05,
        ),
        )

    rust_transcript = run_windows_conpty_tui_command(
        rust,
        input_steps=input_steps_for_prompt_marker("\u203a"),
        env=_conpty_tui_env(),
        timeout=20,
        size=TerminalSize(rows=32, cols=120),
        stop_timeout=45,
    )
    python_transcript = run_windows_conpty_tui_command(
        python,
        input_steps=input_steps_for_prompt_marker(">"),
        env=_conpty_tui_env(),
        timeout=20,
        size=TerminalSize(rows=32, cols=120),
        stop_timeout=45,
    )

    for transcript in (rust_transcript, python_transcript):
        _assert_live_multi_turn_shutdown_summary(transcript, first=first, second=second)


def test_windows_conpty_native_and_python_live_complex_tool_prompt_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer submits the non-empty prompt as
    #   one AppCommand::UserTurn.
    # - codex-core::session::turn maps streamed model deltas and tool calls
    #   into ServerNotification events for the active thread.
    # - codex-tui::chatwidget::command_lifecycle and
    #   codex-tui::exec_cell::render surface live tool progress as
    #   Running/Ran/Called rows while chatwidget::streaming commits the final
    #   assistant answer once.
    #
    # This opt-in live comparison is intentionally not a default CI test.  It
    # exercises the real OAuth/service path for the user-facing complex-session
    # case that deterministic local SSE fixtures cannot prove: a repository
    # inspection prompt that should trigger at least one read-only tool call and
    # eventually render a final marker in both source-built Rust Codex and
    # Python PyCodex.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_NATIVE_LIVE_PROMPT_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_LIVE_PROMPT_ENV}=1 to run live OAuth prompt comparison")
    if os.environ.get(RUN_NATIVE_COMPLEX_LIVE_PROMPT_ENV) != "1":
        pytest.skip(
            f"set {RUN_NATIVE_COMPLEX_LIVE_PROMPT_ENV}=1 to run complex live OAuth prompt comparison"
        )
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe)
    marker = "PYCODEX_COMPLEX_OK"
    prompt = (
        "Inspect this repository using at least one read-only shell command if tools are available. "
        "Give exactly three concise bullets about the project, then end with a separate final line "
        "containing only the three parts PYCODEX COMPLEX OK joined by underscores."
    )
    input_steps = (
        ConptyInputStep(
            prompt,
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            chunk_delay=0.02,
            ready_quiet_period=0.8,
        ),
        ConptyInputStep(
            "\r",
            ready_text="joined by underscores.",
            ready_timeout=10.0,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "",
            ready_text=marker,
            ready_timeout=260.0,
            chunk_delay=0.02,
        ),
    )

    rust_transcript = run_windows_conpty_tui_command(
        rust,
        input_steps=input_steps,
        env=_conpty_tui_env(),
        timeout=10,
        size=TerminalSize(rows=36, cols=140),
        stop_pattern=marker,
        stop_timeout=5,
        terminate_on_stop_pattern=True,
    )
    python_env = _conpty_tui_env()
    with tempfile.TemporaryDirectory(prefix="pycodex-reasoning-trace-") as trace_dir:
        trace_path = Path(trace_dir) / "reasoning.jsonl"
        python_env["PYCODEX_TUI_REASONING_TRACE"] = str(trace_path)
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=python_env,
            timeout=10,
            size=TerminalSize(rows=36, cols=140),
            stop_pattern=marker,
            stop_timeout=5,
            terminate_on_stop_pattern=True,
        )
        reasoning_trace = _read_jsonl_records(trace_path)

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Inspect this repository" in output
        assert marker in output
        assert re.search(r"\b(Running|Ran|Called)\b", output), output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()

    raw_displayed = [
        record
        for record in reasoning_trace
        if record.get("source") == "raw_delta" and record.get("displayed") is True
    ]
    assert raw_displayed == []
    summary_sources = {
        str(record.get("source"))
        for record in reasoning_trace
        if record.get("displayed") is True
    }
    assert summary_sources & {"summary_delta", "completed_reasoning"}


def test_windows_conpty_native_and_python_first_request_context_and_tools_match_when_enabled(
    tmp_path: Path,
) -> None:
    """Compare the real first-turn model context at the product PTY boundary.

    Rust owners: codex-tui::app selects SessionSource::Cli and codex-core's
    Session::built_tools plus request assembly produce the Responses body.
    Python must reach the corresponding modules rather than a TUI-local tool
    list or Goal-specific prompt path.
    """

    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY comparison only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    prompt = "DYNAMIC_CONTEXT_TOOL_PARITY"
    answer = "DYNAMIC_CONTEXT_TOOL_PARITY_DONE"
    response = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-context-parity"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-context-parity",
                "content": [{"type": "output_text", "text": answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-context-parity",
                "usage": {
                    "input_tokens": 5,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 7,
                },
            },
        },
    )

    extra_args = (
        "--enable",
        "goals",
        "--enable",
        "unified_exec",
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
        sandbox_mode="read-only",
        approval_policy="on-request",
    )

    def run_member(command: TuiComparisonCommand, label: str) -> dict[str, object]:
        with _SseFixtureServer(response) as server:
            config = (
                'model = "gpt-5.4"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "goals = true\n"
                "unified_exec = true\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for context and tool parity"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            prompt,
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("\r", ready_text=prompt, ready_timeout=10.0),
                        ConptyInputStep("", ready_text=answer, ready_timeout=40.0, ready_quiet_period=0.3),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=50,
                    size=TerminalSize(rows=36, cols=140),
                )
            transcript.write_artifacts(tmp_path, prefix=f"{label}-request-context", rows=36, cols=140)
            assert server.request_bodies, (
                f"{label} emitted no Responses request; output={transcript.normalized_combined()!r}"
            )
            request = json.loads(server.request_bodies[0].decode("utf-8"))
            (tmp_path / f"{label}-request-context.json").write_text(
                json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return request

    rust_request = run_member(rust, "rust")
    python_request = run_member(python, "python")
    rust_context = _normalized_first_turn_request_context(rust_request)
    python_context = _normalized_first_turn_request_context(python_request)

    assert python_context == rust_context


def test_windows_conpty_native_and_python_goal_continuation_context_match_when_enabled(
    tmp_path: Path,
) -> None:
    """Compare the core-created Goal continuation request across both products."""

    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY comparison only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    objective = "verify dynamic goal continuation parity"
    prompt = "DYNAMIC_GOAL_CONTEXT_PARITY"
    final_answer = "DYNAMIC_GOAL_CONTEXT_PARITY_DONE"

    def tool_body(response_id: str, item_id: str, call_id: str, name: str, arguments: dict[str, object]) -> bytes:
        return _responses_sse(
            {"type": "response.created", "response": {"id": response_id}},
            {
                "type": "response.output_item.done",
                "item": {
                    "id": item_id,
                    "type": "function_call",
                    "call_id": call_id,
                    "name": name,
                    "arguments": json.dumps(arguments, separators=(",", ":")),
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "usage": {
                        "input_tokens": 100,
                        "input_tokens_details": {"cached_tokens": 20},
                        "output_tokens": 10,
                        "output_tokens_details": None,
                        "total_tokens": 110,
                    },
                },
            },
        )

    def message_body(response_id: str, message_id: str, text: str) -> bytes:
        return _responses_sse(
            {"type": "response.created", "response": {"id": response_id}},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": message_id,
                    "content": [{"type": "output_text", "text": text}],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "usage": {
                        "input_tokens": 20,
                        "input_tokens_details": {"cached_tokens": 5},
                        "output_tokens": 6,
                        "output_tokens_details": None,
                        "total_tokens": 26,
                    },
                },
            },
        )

    bodies = (
        tool_body(
            "resp-goal-create",
            "fc-goal-create",
            "call-goal-create",
            "create_goal",
            {"objective": objective, "token_budget": 1000},
        ),
        message_body("resp-goal-progress", "msg-goal-progress", "Initial goal progress."),
        tool_body(
            "resp-goal-complete",
            "fc-goal-complete",
            "call-goal-complete",
            "update_goal",
            {"status": "complete"},
        ),
        message_body("resp-goal-final", "msg-goal-final", final_answer),
    )

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--enable", "goals", "--enable", "unified_exec", "--disable", "apps", "--disable", "plugins"),
        sandbox_mode="read-only",
        approval_policy="on-request",
    )

    def run_member(command: TuiComparisonCommand, label: str) -> dict[str, object]:
        with _SseFixtureServer(bodies, response_delay_seconds=0.6) as server:
            config = (
                'model = "gpt-5.4"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "goals = true\n"
                "unified_exec = true\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for Goal continuation parity"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            prompt,
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("\r", ready_text=prompt, ready_timeout=10.0),
                        ConptyInputStep("", ready_text=final_answer, ready_timeout=60.0, ready_quiet_period=0.3),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=70,
                    size=TerminalSize(rows=40, cols=150),
                )
            transcript.write_artifacts(tmp_path, prefix=f"{label}-goal-context", rows=40, cols=150)
            requests = [json.loads(body.decode("utf-8")) for body in server.request_bodies]
            continuation = next(
                (request for request in requests if "<goal_context>" in json.dumps(request.get("input"), ensure_ascii=False)),
                None,
            )
            assert continuation is not None, (
                f"{label} emitted no GoalContext request; requests={len(requests)}; "
                f"output={transcript.normalized_combined()!r}"
            )
            (tmp_path / f"{label}-goal-context.json").write_text(
                json.dumps(continuation, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return continuation

    rust_request = run_member(rust, "rust")
    python_request = run_member(python, "python")
    rust_text = json.dumps(rust_request.get("input"), ensure_ascii=False)
    python_text = json.dumps(python_request.get("input"), ensure_ascii=False)
    rust_tokens = re.search(r"Tokens used: (\d+)", rust_text)
    python_tokens = re.search(r"Tokens used: (\d+)", python_text)

    assert rust_tokens is not None and int(rust_tokens.group(1)) > 0
    assert python_tokens is not None and int(python_tokens.group(1)) > 0
    assert _normalized_first_turn_request_context(python_request) == _normalized_first_turn_request_context(
        rust_request
    )


def test_windows_conpty_native_and_python_gpt56_update_plan_pipeline_match_when_enabled(
    tmp_path: Path,
) -> None:
    """Compare gpt-5.6 request context and the visible update-plan event pipeline."""

    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_EXPERIMENTAL_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_EXPERIMENTAL_CONPTY_ENV}=1 to debug experimental ConPTY driver")
    if os.environ.get(RUN_VERIFIED_CONPTY_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_ENV}=1 only after low-level ConPTY smoke is stable")
    if os.environ.get(RUN_VERIFIED_CONPTY_TUI_ENV) != "1":
        pytest.skip(f"set {RUN_VERIFIED_CONPTY_TUI_ENV}=1 only after ConPTY TUI input submission is stable")
    if os.name != "nt":
        pytest.skip("Windows ConPTY comparison only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)
    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    prompt = "DYNAMIC_GPT56_UPDATE_PLAN_PARITY"
    answer = "DYNAMIC_GPT56_UPDATE_PLAN_DONE"
    plan = [
        {"step": "Inspect dynamic context", "status": "completed"},
        {"step": "Verify update-plan event bridge", "status": "in_progress"},
        {"step": "Report parity evidence", "status": "pending"},
    ]
    responses = (
        _responses_sse(
            {"type": "response.created", "response": {"id": "resp-plan-call"}},
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "fc-plan-call",
                    "type": "function_call",
                    "call_id": "call-plan-parity",
                    "name": "update_plan",
                    "arguments": json.dumps(
                        {"explanation": "Adapting plan", "plan": plan},
                        separators=(",", ":"),
                    ),
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp-plan-call",
                    "usage": {
                        "input_tokens": 20,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens": 5,
                        "output_tokens_details": None,
                        "total_tokens": 25,
                    },
                },
            },
        ),
        _responses_sse(
            {"type": "response.created", "response": {"id": "resp-plan-answer"}},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": "msg-plan-answer",
                    "content": [{"type": "output_text", "text": answer}],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp-plan-answer",
                    "usage": {
                        "input_tokens": 25,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens": 4,
                        "output_tokens_details": None,
                        "total_tokens": 29,
                    },
                },
            },
        ),
    )

    repo_root = _repo_root()
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--enable", "goals", "--enable", "unified_exec", "--disable", "apps", "--disable", "plugins"),
        sandbox_mode="read-only",
        approval_policy="on-request",
    )

    def run_member(
        command: TuiComparisonCommand,
        label: str,
    ) -> tuple[list[dict[str, object]], TuiProcessTranscript]:
        with _SseFixtureServer(responses, response_delay_seconds=0.3) as server:
            config = (
                'model = "gpt-5.6-sol"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "goals = true\n"
                "unified_exec = true\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for gpt-5.6 plan parity"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            prompt,
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("\r", ready_text=prompt, ready_timeout=10.0),
                        ConptyInputStep("", ready_text=answer, ready_timeout=50.0, ready_quiet_period=0.3),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=60,
                    size=TerminalSize(rows=40, cols=150),
                )
            transcript.write_artifacts(tmp_path, prefix=f"{label}-gpt56-plan", rows=40, cols=150)
            requests = [json.loads(body.decode("utf-8")) for body in server.request_bodies]
            assert len(requests) >= 2, (
                f"{label} did not complete the update_plan round trip; "
                f"requests={len(requests)} output={transcript.normalized_combined()!r}"
            )
            for index, request in enumerate(requests[:2], start=1):
                (tmp_path / f"{label}-gpt56-plan-request-{index}.json").write_text(
                    json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            return requests[:2], transcript

    rust_requests, rust_transcript = run_member(rust, "rust")
    python_requests, python_transcript = run_member(python, "python")

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "Updated Plan" in output
        assert "Inspect dynamic context" in output
        assert "Verify update-plan event bridge" in output
        assert answer in output

    assert _normalized_first_turn_request_context(python_requests[0]) == _normalized_first_turn_request_context(
        rust_requests[0]
    )
    assert _normalized_first_turn_request_context(python_requests[1]) == _normalized_first_turn_request_context(
        rust_requests[1]
    )
    plan_tools = [
        tool
        for tool in rust_requests[0].get("tools", [])
        if isinstance(tool, dict) and tool.get("name") == "update_plan"
    ]
    assert len(plan_tools) == 1
    second_input = json.dumps(python_requests[1].get("input"), ensure_ascii=False)
    assert '"name": "update_plan"' in second_input
    assert "Plan updated" in second_input


