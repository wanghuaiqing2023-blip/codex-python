"""Tui Test Startup scenarios extracted from the native comparison suite."""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


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
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
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

    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        output = transcript.normalized_stdout()
        detail = f"{label}:\n{transcript.normalized_combined()}"
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

    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        output = transcript.normalized_stdout()
        detail = f"{label}:\n{transcript.normalized_combined()}"
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
            input_steps=(
                ConptyInputStep(
                    "",
                    ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                    ready_timeout=12,
                    ready_quiet_period=0.5,
                ),
            ),
            env=env,
            timeout=0.5,
            size=TerminalSize(rows=rows, cols=cols),
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
        assert (SESSION_CONFIGURED_COMPOSER_PATTERN,) in transcript.observed_ready_sequences, detail
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
        try:
            _assert_startup_yolo_current_screen_surface(transcript, rows=rows, cols=cols)
        except AssertionError:
            raise AssertionError(detail) from None


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
    startup_complete = "MCP startup incomplete (failed: pycodex_fail)"
    with temp_home:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_text="/quit\r",
            env=env,
            timeout=45,
            input_delay=35.0,
            input_chunk_delay=0.2,
            input_ready_pattern=re.escape(startup_complete),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_text="/quit\r",
            env=env,
            timeout=30,
            input_delay=20.0,
            input_chunk_delay=0.2,
            input_ready_pattern=re.escape(startup_complete),
        )

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        output = transcript.normalized_stdout()
        detail = f"{label}:\n{transcript.normalized_combined()}"
        assert "OpenAI Codex" in output
        assert "pycodex_fail" in output, detail
        assert "MCP client for `pycodex_fail` failed to start" in output, detail
        assert "MCP startup incomplete (failed: pycodex_fail)" in output, detail
        # The zero return code above proves /quit completed. Rust does not
        # guarantee that its transient shutdown placeholder remains captured.
