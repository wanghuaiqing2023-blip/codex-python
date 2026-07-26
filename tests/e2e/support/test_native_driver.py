"""Support Test Native Driver scenarios extracted from the native comparison suite."""

from tests.e2e.tui._common import *  # noqa: F401,F403
from tests.e2e.support._native_tui import (
    _NATIVE_E2E_STACK_RESERVE,
    _native_codex_with_e2e_stack,
    _windows_pe_stack_reserve,
)

pytestmark = pytest.mark.e2e_support


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


def test_native_debug_oracle_uses_cached_large_stack_copy(tmp_path: Path) -> None:
    executable = tmp_path / "codex.exe"
    image = bytearray(512)
    image[0x3C:0x40] = (0x80).to_bytes(4, "little")
    image[0x80:0x84] = b"PE\0\0"
    optional_header = 0x80 + 24
    image[optional_header : optional_header + 2] = (0x20B).to_bytes(2, "little")
    image[optional_header + 72 : optional_header + 80] = (8 * 1024 * 1024).to_bytes(8, "little")
    executable.write_bytes(image)

    prepared = _native_codex_with_e2e_stack(executable)

    assert prepared != executable
    assert _windows_pe_stack_reserve(executable) == 8 * 1024 * 1024
    assert _windows_pe_stack_reserve(prepared) == _NATIVE_E2E_STACK_RESERVE
    assert _native_codex_with_e2e_stack(executable) == prepared


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


def test_conpty_screen_wait_reconstructs_cells_preserved_by_diff_draw() -> None:
    # Rust's ratatui backend skips unchanged cells with cursor movement. The
    # second ``n`` is retained from ``Working`` rather than emitted again.
    raw = "\u2022 Working\x1b[1;3HRecon\x1b[1Cecting... 1/1"

    assert _wait_for_windows_conpty_screen_text(
        [raw.encode("utf-8")],
        "Reconnecting... 1/1",
        timeout=0.0,
        size=TerminalSize(rows=1, cols=40),
    )
    assert "Reconnecting... 1/1" not in normalize_tui_text(raw)


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
