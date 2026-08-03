"""End-to-end coverage for the ``/vim`` slash command."""

import json
from pathlib import Path
import sys

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.support._native_tui import (
    ConptyInputStep,
    TerminalSize,
    run_windows_conpty_tui_command,
)
from tests.e2e.support.responses_fixture import (
    _SseFixtureServer,
    _completed_text_response,
)
from tests.e2e.tui._slash_command_common import (
    _isolated_codex_home_env_with_config,
    assert_local_slash_candidate,
    require_native_slash_comparison,
    slash_candidate_pair,
)
from tests.e2e.tui._common import (
    READY_COMPOSER_PATTERN,
    SESSION_CONFIGURED_COMPOSER_PATTERN,
)

pytestmark = pytest.mark.e2e

ROWS = 32
COLS = 120


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _vim_config(base_url: str, *, delayed_mcp: bool) -> str:
    repo_root = _repo_root()
    config = (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n\n'
        '[features]\napps = false\nplugins = false\n\n'
        '[model_providers.pycodex_mock]\n'
        'name = "Mock provider for Vim E2E"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
    )
    if delayed_mcp:
        config += (
            '[mcp_servers.delayed]\n'
            f'command = {json.dumps(sys.executable)}\n'
            'args = ["-m", "pycodex.rmcp_client.bin.rmcp_test_server"]\n\n'
        )
    return (
        config
        + f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        + 'trust_level = "trusted"\n'
    )


def _request_user_text(request: bytes) -> str:
    payload = json.loads(request.decode("utf-8"))
    for item in reversed(payload.get("input", [])):
        if item.get("role") != "user":
            continue
        content = item.get("content", [])
        if isinstance(content, str):
            return content
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in {"input_text", "text"}
        )
    return ""


def _cursor_contract(transcript: object, checkpoint: str, expected_text: str) -> tuple[int, str]:
    screen = transcript.checkpoint_cells(checkpoint, rows=ROWS, cols=COLS)
    row_text = "".join(cell.char for cell in screen.line(screen.cursor_row))
    assert expected_text in row_text, (
        f"checkpoint={checkpoint!r}; cursor=({screen.cursor_row}, {screen.cursor_col}); "
        f"screen=\n{screen.text()}"
    )
    start = row_text.index(expected_text)
    offset = screen.cursor_col - start
    cursor_char = row_text[screen.cursor_col] if screen.cursor_col < len(row_text) else ""
    return offset, cursor_char


def _cell_styles_for_text(screen: object, needle: str) -> tuple[object, ...]:
    for row in screen.rows:
        text = "".join(cell.char for cell in row)
        start = text.find(needle)
        if start >= 0:
            return tuple(cell.style for cell in row[start : start + len(needle)])
    raise AssertionError(f"missing {needle!r} in styled screen:\n{screen.text()}")


def test_vim_slash_command_routes_to_chatwidget_effect() -> None:
    route = terminal_slash_command_routes()[SlashCommand.VIM]

    assert route.outcome == "effect"
    assert route.python_owner == "pycodex.tui.chatwidget.protocol"
    assert SlashCommand.VIM.supports_inline_args() is False
    assert SlashCommand.VIM.available_during_task() is False
    assert SlashCommand.VIM.available_in_side_conversation() is False


def test_windows_conpty_native_and_python_vim_toggle_when_enabled(
    tmp_path: Path,
) -> None:
    # Rust: slash_dispatch calls toggle_vim_mode_and_notify. Repeating /vim in
    # the same TUI must expose both state transitions without a model UserTurn.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    results = []
    body = _completed_text_response("resp-vim-toggle", "msg-vim-toggle", "MUST-NOT-RUN")
    for label, command in (("rust", rust), ("python", python)):
        with _SseFixtureServer(body) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                _vim_config(server.base_url, delayed_mcp=False)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "/vim",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_screen_text="/vim", ready_timeout=10.0),
                        # Enabling Vim leaves the composer in Normal mode. Enter
                        # Insert before typing the second local slash command.
                        ConptyInputStep("i", ready_text="Vim mode enabled.", ready_timeout=10.0),
                        ConptyInputStep("/vim", ready_screen_text="Vim: Insert", ready_timeout=10.0),
                        ConptyInputStep("\r", ready_screen_text="/vim", ready_timeout=10.0),
                        ConptyInputStep("", ready_text="Vim mode disabled.", ready_timeout=10.0),
                    ),
                    env=env,
                    timeout=3,
                    stop_pattern="Vim mode disabled.",
                    stop_timeout=0.1,
                    terminate_on_stop_pattern=True,
                    size=TerminalSize(rows=ROWS, cols=COLS),
                )
            transcript.write_artifacts(
                tmp_path,
                prefix=f"{label}-vim-toggle",
                rows=ROWS,
                cols=COLS,
            )
            results.append((label, transcript, len(server.request_bodies)))

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "Vim mode enabled." in output
        assert "Vim mode disabled." in output


def test_windows_conpty_native_and_python_vim_normal_indicator_color_when_enabled(
    tmp_path: Path,
) -> None:
    """Rust renders ``Vim: Normal`` in magenta; Python must preserve that style."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    body = _completed_text_response("resp-vim-color", "msg-vim-color", "MUST-NOT-RUN")
    styles: dict[str, tuple[object, ...]] = {}

    for label, command in (("rust", rust), ("python", python)):
        with _SseFixtureServer(body) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                _vim_config(server.base_url, delayed_mcp=False)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "/vim",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_screen_text="/vim", ready_timeout=10.0),
                        ConptyInputStep(
                            "",
                            ready_text="Vim mode enabled.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                            capture_name="vim-normal-color",
                        ),
                    ),
                    env=env,
                    timeout=3,
                    stop_pattern="Vim mode enabled.",
                    stop_timeout=0.1,
                    terminate_on_stop_pattern=True,
                    size=TerminalSize(rows=ROWS, cols=COLS),
                )
            transcript.write_artifacts(
                tmp_path,
                prefix=f"{label}-vim-normal-color",
                rows=ROWS,
                cols=COLS,
            )
            assert len(server.request_bodies) == 0, transcript.normalized_combined()
            screen = transcript.checkpoint_cells(
                "vim-normal-color",
                rows=ROWS,
                cols=COLS,
            )
            styles[label] = _cell_styles_for_text(screen, "Vim: Normal")

    assert styles["python"] == styles["rust"]
    assert len(set(styles["rust"])) == 1
    style = styles["rust"][0]
    assert (style.fg.kind, style.fg.value) == ("ansi", 5)
    assert style.bg is None
    assert not any(
        (style.bold, style.dim, style.italic, style.underline, style.reverse)
    )


def test_windows_conpty_native_and_python_vim_normal_slash_dispatch_when_enabled(
    tmp_path: Path,
) -> None:
    """A leading slash in Vim Normal mode enters Insert and dispatches locally."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    body = _completed_text_response("resp-vim-slash", "msg-vim-slash", "MUST-NOT-RUN")

    for label, command in (("rust", rust), ("python", python)):
        with _SseFixtureServer(body) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                _vim_config(server.base_url, delayed_mcp=False)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "/vim",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_screen_text="/vim", ready_timeout=10.0),
                        # Do not press `i`: the leading slash itself must open
                        # Insert mode and route through the command popup.
                        ConptyInputStep(
                            "/vim",
                            ready_screen_text="Vim: Normal",
                            ready_timeout=10.0,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="toggle Vim mode for the composer",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            capture_name="vim-normal-slash-draft",
                        ),
                        ConptyInputStep(
                            "",
                            ready_text="Vim mode disabled.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                        ),
                    ),
                    env=env,
                    timeout=3,
                    stop_pattern="Vim mode disabled.",
                    stop_timeout=0.1,
                    terminate_on_stop_pattern=True,
                    size=TerminalSize(rows=ROWS, cols=COLS),
                )
            transcript.write_artifacts(
                tmp_path,
                prefix=f"{label}-vim-normal-slash-dispatch",
                rows=ROWS,
                cols=COLS,
            )
            assert len(server.request_bodies) == 0, transcript.normalized_combined()
            draft = transcript.checkpoint_screen(
                "vim-normal-slash-draft",
                rows=ROWS,
                cols=COLS,
            )
            assert "/vim" in draft, f"{label}:\n{draft}"
            assert "toggle Vim mode for the composer" in draft, f"{label}:\n{draft}"
            assert "Vim mode disabled." in transcript.normalized_stdout()


def test_windows_conpty_native_and_python_vim_normal_non_esc_clears_stale_backtrack_when_enabled(
    tmp_path: Path,
) -> None:
    """Typing after a priming Esc must prevent one later Esc opening transcript."""

    # Rust app::input clears backtrack.primed on every non-Esc key press. This
    # sequence deliberately primes before any user history exists, then enters
    # Vim Insert, submits a real turn, and presses Esc exactly once afterward.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    prompt = "VIM-STALE-BACKTRACK-PROBE"
    answer = "VIM-STALE-BACKTRACK-ACK"
    body = _completed_text_response(
        "resp-vim-stale-backtrack",
        "msg-vim-stale-backtrack",
        answer,
    )

    results: dict[str, tuple[object, bytes]] = {}
    for label, command in (("rust", rust), ("python", python)):
        with _SseFixtureServer(body) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                _vim_config(server.base_url, delayed_mcp=False)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "/vim",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_screen_text="/vim", ready_timeout=10.0),
                        # Prime global backtracking while there is no previous
                        # user message. The following `i` must cancel it.
                        ConptyInputStep(
                            "\x1b",
                            ready_text="Vim mode enabled.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("i", ready_screen_text="Vim: Normal", ready_timeout=10.0),
                        ConptyInputStep(
                            prompt,
                            ready_screen_text="Vim: Insert",
                            ready_timeout=10.0,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_screen_text=prompt, ready_timeout=10.0),
                        # Successful submission restores Vim Normal. This is a
                        # single Esc, so Rust only primes backtracking again.
                        ConptyInputStep(
                            "\x1b",
                            ready_text=answer,
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                        ),
                        ConptyInputStep(
                            "",
                            ready_timeout=0.6,
                            capture_name="after-single-esc",
                        ),
                    ),
                    env=env,
                    timeout=2,
                    size=TerminalSize(rows=ROWS, cols=COLS),
                )
            transcript.write_artifacts(
                tmp_path,
                prefix=f"{label}-vim-normal-stale-backtrack",
                rows=ROWS,
                cols=COLS,
            )
            assert len(server.request_bodies) == 1, transcript.normalized_combined()
            results[label] = (transcript, server.request_bodies[0])

    for label, (transcript, request) in results.items():
        screen = transcript.checkpoint_screen(
            "after-single-esc",
            rows=ROWS,
            cols=COLS,
        )
        assert _request_user_text(request) == prompt
        assert "T R A N S C R I P T" not in screen, f"{label}:\n{screen}"
        assert answer in transcript.normalized_stdout()


def test_windows_conpty_native_and_python_vim_normal_single_esc_after_existing_turn_when_enabled(
    tmp_path: Path,
) -> None:
    """One Esc after enabling Vim mid-session must not open transcript."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    first_prompt = "VIM-PREEXISTING-TURN"
    second_prompt = "VIM-NORMAL-SINGLE-ESC"
    answer = "VIM-SINGLE-ESC-ACK"
    body = _completed_text_response("resp-vim-single-esc", "msg-vim-single-esc", answer)

    results: dict[str, tuple[object, list[bytes]]] = {}
    for label, command in (("rust", rust), ("python", python)):
        with _SseFixtureServer(body) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                _vim_config(server.base_url, delayed_mcp=False)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            first_prompt,
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_screen_text=first_prompt, ready_timeout=10.0),
                        ConptyInputStep("/vim", ready_text=answer, ready_timeout=30.0, atomic_write=True),
                        ConptyInputStep("\r", ready_screen_text="/vim", ready_timeout=10.0),
                        ConptyInputStep("i", ready_text="Vim mode enabled.", ready_timeout=10.0),
                        ConptyInputStep(
                            second_prompt,
                            ready_screen_text="Vim: Insert",
                            ready_timeout=10.0,
                            atomic_write=True,
                        ),
                        # Mirror manual Vim use: Esc to Normal, then Enter to submit.
                        ConptyInputStep("\x1b", ready_screen_text=second_prompt, ready_timeout=10.0),
                        ConptyInputStep("\r", ready_screen_text="Vim: Normal", ready_timeout=10.0),
                        ConptyInputStep(
                            "\x1b",
                            ready_text=answer,
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                        ),
                        ConptyInputStep("", ready_timeout=0.6, capture_name="after-single-esc"),
                    ),
                    env=env,
                    timeout=2,
                    size=TerminalSize(rows=ROWS, cols=COLS),
                )
            transcript.write_artifacts(
                tmp_path,
                prefix=f"{label}-vim-normal-existing-turn-single-esc",
                rows=ROWS,
                cols=COLS,
            )
            assert len(server.request_bodies) == 2, transcript.normalized_combined()
            results[label] = (transcript, list(server.request_bodies))

    for label, (transcript, requests) in results.items():
        cells = transcript.checkpoint_cells("after-single-esc", rows=ROWS, cols=COLS)
        screen = cells.text()
        assert [_request_user_text(request) for request in requests] == [
            first_prompt,
            second_prompt,
        ]
        assert "T R A N S C R I P T" not in screen, f"{label}:\n{screen}"
        assert first_prompt in screen, f"{label}:\n{screen}"
        assert second_prompt in screen, f"{label}:\n{screen}"
        assert answer in screen, f"{label}:\n{screen}"

        # Rust footer::FooterMode::EscHint replaces the ordinary Vim/status
        # footer after the first Esc. The composer remains focused and empty,
        # with a dim suggested prompt beginning under the cursor.
        hint = "esc again to edit previous message"
        assert hint in screen, f"{label}:\n{screen}"
        assert "Vim: Normal" not in screen, f"{label}:\n{screen}"
        cursor_line = "".join(cell.char for cell in cells.line(cells.cursor_row))
        assert cursor_line.startswith("\u203a "), f"{label}:\n{screen}"
        assert cells.cursor_col == 2, f"{label}: cursor={cells.cursor_col}\n{screen}"
        placeholder = cursor_line[2:].rstrip()
        assert placeholder, f"{label}: missing suggested prompt\n{screen}"
        placeholder_styles = tuple(
            cell.style
            for cell in cells.line(cells.cursor_row)[2 : 2 + len(placeholder)]
        )
        assert placeholder_styles and all(style.dim for style in placeholder_styles)

        hint_styles = _cell_styles_for_text(cells, hint)
        assert len(set(hint_styles)) == 1
        hint_style = hint_styles[0]
        assert hint_style.dim is True
        assert hint_style.fg is None
        assert hint_style.bg is None
        assert not any(
            (
                hint_style.bold,
                hint_style.italic,
                hint_style.underline,
                hint_style.crossed_out,
                hint_style.reverse,
            )
        )


def test_windows_conpty_native_and_python_vim_after_delayed_mcp_edits_and_submits_when_enabled(
    tmp_path: Path,
) -> None:
    """A settled MCP startup must release `/vim` into the real textarea."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    answer = "VIM-E2E-ACK"
    request_text = "alpha beta gamma"
    edited_text = "alpha eta gamma"
    body = _completed_text_response(
        "resp-vim-editor",
        "msg-vim-editor",
        answer,
    )

    results: dict[str, tuple[object, bytes]] = {}
    for label, command in (("rust", rust), ("python", python)):
        with _SseFixtureServer(body) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                _vim_config(server.base_url, delayed_mcp=True)
            )
            env["PYCODEX_TEST_MCP_INITIALIZE_DELAY_MS"] = "1200"
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                        ),
                        # The server answers initialize after this interval. The
                        # product must continue polling app-server events while
                        # the composer is otherwise idle.
                        # The configured 1.2s delay begins inside the MCP
                        # child, after process spawn and initialize transport
                        # setup. Leave enough wall-clock time for both native
                        # implementations on a loaded Windows CI host.
                        ConptyInputStep("", ready_timeout=5.0),
                        ConptyInputStep("/vim", ready_timeout=0.1, atomic_write=True),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="/vim",
                            ready_timeout=10.0,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "i",
                            ready_text="Vim mode enabled.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            capture_name="vim-normal",
                        ),
                        ConptyInputStep(
                            request_text,
                            ready_screen_text="Vim: Insert",
                            ready_timeout=10.0,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\x1b",
                            ready_screen_text=request_text,
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "0",
                            ready_screen_text="Vim: Normal",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("w", ready_timeout=0.2),
                        ConptyInputStep("x", ready_timeout=0.2),
                        ConptyInputStep(
                            "",
                            ready_screen_text=edited_text,
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            capture_name="edited-normal",
                        ),
                        ConptyInputStep("\r", ready_timeout=0.1),
                        ConptyInputStep(
                            "",
                            ready_text=answer,
                            ready_timeout=30.0,
                            ready_quiet_period=0.3,
                            capture_name="answered",
                        ),
                    ),
                    env=env,
                    timeout=3,
                    stop_pattern=answer,
                    stop_timeout=0.1,
                    terminate_on_stop_pattern=True,
                    size=TerminalSize(rows=ROWS, cols=COLS),
                )
            transcript.write_artifacts(
                tmp_path,
                prefix=f"{label}-vim-delayed-mcp-editor",
                rows=ROWS,
                cols=COLS,
            )
            assert len(server.request_bodies) == 1, transcript.normalized_combined()
            results[label] = (transcript, server.request_bodies[0])

    contracts: dict[str, tuple[int, str]] = {}
    for label, (transcript, request) in results.items():
        normal = transcript.checkpoint_screen("vim-normal", rows=ROWS, cols=COLS)
        edited = transcript.checkpoint_screen("edited-normal", rows=ROWS, cols=COLS)
        assert "Vim: Normal" in normal, f"{label}:\n{normal}"
        assert edited_text in edited, f"{label}:\n{edited}"
        assert "Vim: Normal" in edited, f"{label}:\n{edited}"
        assert "disabled while a task is in progress" not in transcript.normalized_stdout()
        assert _request_user_text(request) == edited_text
        contracts[label] = _cursor_contract(
            transcript,
            "edited-normal",
            edited_text,
        )

    # After `w` then `x`, Normal mode stays on the first surviving `e`.
    assert contracts == {
        "rust": (6, "e"),
        "python": (6, "e"),
    }


def test_windows_conpty_native_and_python_vim_is_disabled_only_during_real_turn_when_enabled(
    tmp_path: Path,
) -> None:
    """A genuine delayed model turn keeps `/vim` behind the Rust guard."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    answer = "VIM-BUSY-E2E-DONE"
    disabled = "'/vim' is disabled while a task is in progress."
    body = _completed_text_response("resp-vim-busy", "msg-vim-busy", answer)

    for label, command in (("rust", rust), ("python", python)):
        with _SseFixtureServer(body, response_delay_seconds=4.0) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                _vim_config(server.base_url, delayed_mcp=False)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "busy vim prompt",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="busy vim prompt",
                            ready_timeout=10.0,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "/vim",
                            ready_text_sequence=("Working", "esc to interrupt"),
                            ready_timeout=15.0,
                            chunk_delay=0.05,
                        ),
                        ConptyInputStep(
                            "\x1b\r\r",
                            ready_screen_text="/vim",
                            ready_timeout=10.0,
                            chunk_delay=0.05,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text=disabled,
                            ready_timeout=10.0,
                            capture_name="busy-disabled",
                        ),
                        ConptyInputStep(
                            "",
                            ready_text=answer,
                            ready_timeout=20.0,
                            ready_quiet_period=0.3,
                        ),
                    ),
                    env=env,
                    timeout=3,
                    stop_pattern=answer,
                    stop_timeout=0.1,
                    terminate_on_stop_pattern=True,
                    size=TerminalSize(rows=ROWS, cols=COLS),
                )
            transcript.write_artifacts(
                tmp_path,
                prefix=f"{label}-vim-real-turn-guard",
                rows=ROWS,
                cols=COLS,
            )
            assert len(server.request_bodies) == 1, transcript.normalized_combined()
            assert (disabled,) in transcript.observed_ready_sequences
            assert "Vim mode enabled." not in transcript.normalized_stdout()
            assert "Vim: Normal" not in transcript.checkpoint_screen(
                "busy-disabled",
                rows=ROWS,
                cols=COLS,
            )
