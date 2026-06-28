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
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

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
    build_inline_tui_command,
    build_rust_python_inline_pair,
    interactive_tui_comparison_capability,
    native_codex_exe_from_env,
    native_comparison_enabled,
    normalize_tui_text,
    run_piped_tui_command,
    run_windows_conpty_tui_command,
    _semantic_conpty_text,
    _wait_for_windows_conpty_ordered_semantic_text,
    _wait_for_windows_conpty_semantic_text,
    _wait_for_windows_conpty_quiet,
    _wait_for_windows_conpty_output_pattern,
)

RUN_NATIVE_LIVE_PROMPT_ENV = "PYCODEX_RUN_NATIVE_TUI_LIVE_PROMPT"
RUN_NATIVE_MULTI_TURN_ENV = "PYCODEX_RUN_NATIVE_TUI_MULTI_TURN"
READY_COMPOSER_PATTERN = "(?m)>\\s*$|^\\s*\\u203a\\s+.+$"


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
        self._lock = threading.Lock()
        self._body_index = 0

    def __enter__(self) -> "_SseFixtureServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
                with outer._lock:
                    outer.requests.append(("POST", self.path))
                    index = min(outer._body_index, len(outer._bodies) - 1)
                    body = outer._bodies[index]
                    outer._body_index += 1
                length = int(self.headers.get("content-length") or "0")
                if length:
                    self.rfile.read(length)
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
    assert "Shutting down" in output
    assert any("gpt-" in line and "codex-python" in line for line in output.splitlines())
    assert any(placeholder in output for placeholder in CHAT_PLACEHOLDERS)


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
                    ready_pattern=r"Tip:",
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
    extra_args = ("--disable", "apps", "--disable", "plugins")
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
        ConptyInputStep("", ready_text="Tip:", ready_timeout=30.0, ready_quiet_period=0.5),
        ConptyInputStep("\x14", ready_timeout=0.1, chunk_delay=0.02),
        ConptyInputStep("q", ready_text="T R A N S C R I P T", ready_timeout=10.0, chunk_delay=0.02),
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
        assert "T R A N S C R I P T" in output


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
                            ready_pattern=r"Tip:",
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
                            "/quit\r",
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


def test_windows_conpty_python_local_sse_codepage_chinese_submission_when_enabled() -> None:
    # Rust source contract:
    # - codex-tui::tui enables Windows VT/raw terminal input before running the
    #   app.
    # - codex-tui::tui::event_stream consumes crossterm KeyEvents, so IME text
    #   and Enter reach bottom_pane::chat_composer as decoded input events.
    #
    # Python's Textual Windows VT driver reads bytes from ConPTY. Windows
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
                        ready_pattern=r"Tip:",
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
                    ready_pattern=r"Tip:",
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
        ConptyInputStep("", ready_text="Tip:", ready_timeout=30.0, ready_quiet_period=0.5),
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
        ConptyInputStep("", ready_text="Tip:", ready_timeout=30.0, ready_quiet_period=0.5),
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
            ready_text="Tip:",
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

    def run_pair_member(command: TuiComparisonCommand, prompt_marker: str) -> object:
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
                            ready_pattern=r"Tip:",
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
                            ready_text="Working",
                            ready_timeout=15.0,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text="'/model' is disabled while a task is in progress.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(sentinel, prompt_marker),
                            ready_timeout=35.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                    ),
                    env=env,
                    timeout=35,
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
    rust_transcript = run_pair_member(rust, "\u203a")
    python_transcript = run_pair_member(python, ">")

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "• Working" in output or "◦ Working" in output
        assert "esc to interrupt" in output
        assert "'/model' is disabled while a task is in progress." in output
        assert sentinel in output
        assert "Select Model" not in output
        assert "Token usage:" in output
        assert transcript.returncode == 0, transcript.normalized_combined()


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
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe)
    rust_transcript = run_windows_conpty_tui_command(
        rust,
        input_text="/status\r/quit\r",
        env=_conpty_tui_env(),
        timeout=55,
        input_delay=8.0,
        input_chunk_delay=0.2,
        input_ready_pattern=READY_COMPOSER_PATTERN,
    )
    python_transcript = run_windows_conpty_tui_command(
        python,
        input_text="/status\r/quit\r",
        env=_conpty_tui_env(),
        timeout=35,
        input_delay=8.0,
        input_chunk_delay=0.2,
        input_ready_pattern=READY_COMPOSER_PATTERN,
    )
    rust_stdout = rust_transcript.normalized_stdout()
    python_stdout = python_transcript.normalized_stdout()

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for transcript in (rust_stdout, python_stdout):
        assert "/status" in transcript
        assert "OpenAI Codex" in transcript
        assert "Model:" in transcript
        assert "Directory:" in transcript
        assert "Permissions:" in transcript
        assert "Read Only (never)" in transcript
        assert "Session:" in transcript
        assert "Shutting down" in transcript


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
            ready_text="Tip:",
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
            input_steps=input_steps,
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
            ready_text="Tip:",
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
            ready_pattern=r"Tip:",
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
        _assert_interrupt_affordance_visible(transcript)
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
            ready_pattern=r"Tip:",
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

