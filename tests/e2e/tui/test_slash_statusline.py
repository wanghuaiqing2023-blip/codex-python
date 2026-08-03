"""E2E coverage for the Rust-owned ``/statusline`` command contract."""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


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
    warning = 'Ignored invalid status line item: "bogus_item".'
    try:
        rust_transcript = run_windows_conpty_tui_command(
            rust,
            input_text="/quit\r",
            env=env,
            timeout=35,
            input_delay=25.0,
            input_chunk_delay=0.2,
            input_ready_pattern=re.escape(warning),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_text="/quit\r",
            env=env,
            timeout=25,
            input_delay=15.0,
            input_chunk_delay=0.2,
            input_ready_pattern=re.escape(warning),
        )
    finally:
        temp_home.cleanup()

    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        output = transcript.normalized_stdout()
        detail = f"{label}:\n{transcript.normalized_combined()}"
        assert transcript.returncode == 0, detail
        # ConPTY captures terminal repaint bytes, so the same single history
        # cell may occur more than once in cumulative output. The Rust-derived
        # module test proves one-time insertion; E2E proves it is visible.
        assert warning in output, detail
        assert "Context 0% used" in output, detail


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

    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        screen = transcript.screen_stdout(rows=rows, cols=cols)
        detail = (
            f"{label}: argv={transcript.argv!r}\n"
            f"stderr={transcript.normalized_stderr()}\n"
            f"screen={screen}\n"
            f"stdout={transcript.normalized_stdout()}"
        )
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr(), detail
        assert "OpenAI Codex" in screen, detail
        assert "Context 0% used" in screen, detail
        assert "Ignored invalid status line" not in screen, detail
        assert "Shutting down" not in screen, detail


def test_windows_conpty_native_and_python_statusline_setup_open_when_enabled(
    tmp_path: Path,
) -> None:
    # Fixed Rust baseline 1c7832f source/test contract:
    # - codex-tui::chatwidget::slash_dispatch maps SlashCommand::Statusline to
    #   ChatWidget::open_status_line_setup().
    # - codex-tui::bottom_pane::status_line_setup owns StatusLineSetupView and
    #   renders the "Configure Status Line" multi-select picker.
    # - codex-tui::chatwidget::tests::status_surface_previews proves the view is
    #   local and previews status-line items without creating a model turn.
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
        sandbox_mode="read-only",
        approval_policy="never",
    )
    fixture_body = _completed_text_response(
        "resp-statusline-must-not-run",
        "msg-statusline-must-not-run",
        "STATUSLINE_MUST_REMAIN_LOCAL",
    )

    def run_member(
        command: TuiComparisonCommand,
        label: str,
    ) -> tuple[TuiProcessTranscript, int]:
        with _SseFixtureServer(fixture_body) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider that /statusline must not call"\n'
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
                            "/statusline\r",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.5,
                            chunk_delay=0.02,
                        ),
                    ),
                    env=env,
                    timeout=2,
                    stop_pattern="Press space to toggle",
                    stop_timeout=8,
                    terminate_on_stop_pattern=True,
                    size=TerminalSize(rows=32, cols=120),
                )
            request_count = len(server.request_bodies)
        transcript.write_artifacts(
            tmp_path,
            prefix=f"{label}-statusline-setup",
            rows=32,
            cols=120,
        )
        return transcript, request_count

    rust_transcript, rust_request_count = run_member(rust, "rust")
    python_transcript, python_request_count = run_member(python, "python")

    failures: list[str] = []
    for label, transcript, request_count in (
        ("rust", rust_transcript, rust_request_count),
        ("python", python_transcript, python_request_count),
    ):
        output = transcript.normalized_stdout()
        expected = (
            "Configure Status Line",
            "Select which items to display in the status line.",
            "Type to search",
            "Use theme colors",
            "Press space to toggle",
        )
        missing = [text for text in expected if text not in output]
        if missing:
            failures.append(
                f"{label}: missing status-line setup content {missing!r}; "
                f"requests={request_count}; stderr={transcript.normalized_stderr()!r}; "
                f"screen={transcript.screen_stdout(rows=32, cols=120)!r}; "
                f"artifacts={str(tmp_path)!r}"
            )
        if request_count != 0:
            failures.append(
                f"{label}: /statusline became a model turn; "
                f"request_count={request_count}; artifacts={str(tmp_path)!r}"
            )
        if "product effect is not yet available" in output:
            failures.append(
                f"{label}: /statusline remained a compatibility shim; "
                f"artifacts={str(tmp_path)!r}"
            )
        screen = transcript.screen_stdout(rows=32, cols=120)
        if "branch-changes" in screen:
            failures.append(
                f"{label}: status-line setup rendered rows beyond Rust's "
                f"bounded initial viewport; screen={screen!r}; "
                f"artifacts={str(tmp_path)!r}"
            )
        if re.search(
            r"Press space to toggle[^\r\n]*[\r\n]+"
            r"mock-model[^\r\n]*\u00b7[^\r\n]*codex-python",
            screen,
        ):
            failures.append(
                f"{label}: active StatusLineSetupView was incorrectly composed "
                f"with the ambient model/directory footer; screen={screen!r}; "
                f"artifacts={str(tmp_path)!r}"
            )
        expected_initial_items = (
            "Use theme colors",
            "model-with-reasoning",
            "current-dir",
            "model",
            "project-name",
            "git-branch",
            "pull-request-number",
        )
        item_matches = [
            re.search(
                rf"(?m)^[^\r\n]*\[[ x]\]\s+{re.escape(item)}(?=\s{{2,}}|$)",
                screen,
            )
            for item in expected_initial_items
        ]
        item_positions = [
            match.start() if match is not None else -1 for match in item_matches
        ]
        if any(position < 0 for position in item_positions):
            failures.append(
                f"{label}: status-line setup did not render Rust's initial "
                f"visible item window; positions={item_positions!r}; "
                f"screen={screen!r}; artifacts={str(tmp_path)!r}"
            )
        elif item_positions != sorted(item_positions):
            failures.append(
                f"{label}: status-line setup initial items are out of Rust "
                f"order; positions={item_positions!r}; screen={screen!r}; "
                f"artifacts={str(tmp_path)!r}"
            )
        checkbox_rows = re.findall(r"\[[ x]\]\s+", screen)
        if len(checkbox_rows) != len(expected_initial_items):
            failures.append(
                f"{label}: expected {len(expected_initial_items)} checkbox "
                f"rows in Rust's eight-row viewport (including its separator), "
                f"observed {len(checkbox_rows)}; screen={screen!r}; "
                f"artifacts={str(tmp_path)!r}"
            )
        for footer_fragment in (
            "Press space to toggle",
            "to move",
            "enter to confirm and close",
            "esc to close",
        ):
            if footer_fragment not in screen:
                failures.append(
                    f"{label}: status-line setup footer is missing "
                    f"{footer_fragment!r}; screen={screen!r}; "
                    f"artifacts={str(tmp_path)!r}"
                )
        if "ConPTY command terminated after stop pattern" not in transcript.normalized_stderr():
            failures.append(
                f"{label}: setup view stop pattern was never observed; "
                f"stderr={transcript.normalized_stderr()!r}; artifacts={str(tmp_path)!r}"
            )

    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_statusline_escape_closes_when_enabled(
    tmp_path: Path,
) -> None:
    # Fixed Rust baseline 1c7832f dynamic contract:
    # - bottom_pane::multi_select_picker maps Esc to close().
    # - StatusLineSetupView forwards the key event and emits
    #   AppEvent::StatusLineSetupCancelled.
    # - bottom_pane consumes Esc while the active view is closing, so the key
    #   cannot fall through to the main composer/backtrack handling.
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
        sandbox_mode="read-only",
        approval_policy="never",
    )
    fixture_body = _completed_text_response(
        "resp-statusline-escape-must-not-run",
        "msg-statusline-escape-must-not-run",
        "STATUSLINE_ESCAPE_MUST_REMAIN_LOCAL",
    )
    composer_probe = "ESC_STATUSLINE_CLOSED"

    def run_member(
        command: TuiComparisonCommand,
        label: str,
    ) -> tuple[TuiProcessTranscript, int]:
        with _SseFixtureServer(fixture_body) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider that /statusline must not call"\n'
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
                            "/statusline\r",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.5,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            "\x1b",
                            ready_text="Press space to toggle",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            composer_probe,
                            ready_timeout=0.5,
                            atomic_write=True,
                        ),
                    ),
                    env=env,
                    timeout=2,
                    stop_pattern=re.escape(composer_probe),
                    stop_timeout=8,
                    terminate_on_stop_pattern=True,
                    size=TerminalSize(rows=32, cols=120),
                )
            request_count = len(server.request_bodies)
        transcript.write_artifacts(
            tmp_path,
            prefix=f"{label}-statusline-escape",
            rows=32,
            cols=120,
        )
        return transcript, request_count

    rust_result = run_member(rust, "rust")
    python_result = run_member(python, "python")

    failures: list[str] = []
    for label, (transcript, request_count) in (
        ("rust", rust_result),
        ("python", python_result),
    ):
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=32, cols=120)
        if composer_probe not in screen:
            failures.append(
                f"{label}: text entered after Esc did not reach the composer; "
                f"screen={screen!r}; artifacts={str(tmp_path)!r}"
            )
        if "Configure Status Line" in screen:
            failures.append(
                f"{label}: Esc did not close StatusLineSetupView; "
                f"screen={screen!r}; artifacts={str(tmp_path)!r}"
            )
        if "No previous message to edit." in output:
            failures.append(
                f"{label}: Esc leaked past the active bottom-pane view into "
                f"the global previous-message action; artifacts={str(tmp_path)!r}"
            )
        if request_count != 0:
            failures.append(
                f"{label}: local status-line cancellation created a model "
                f"request; count={request_count}; artifacts={str(tmp_path)!r}"
            )
        if "ConPTY command terminated after stop pattern" not in transcript.normalized_stderr():
            failures.append(
                f"{label}: composer probe was not observed after Esc; "
                f"stderr={transcript.normalized_stderr()!r}; "
                f"artifacts={str(tmp_path)!r}"
            )

    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_statusline_toggle_persists_when_enabled(
    tmp_path: Path,
) -> None:
    # Fixed Rust baseline 1c7832f dynamic contract:
    # - multi_select_picker maps Char(' ') to toggle_selected().
    # - StatusLineSetupView emits AppEvent::StatusLineSetup on Enter.
    # - app::event_dispatch persists status_line/status_line_use_colors and
    #   refreshes ChatWidget before the setup view is opened again.
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
        sandbox_mode="read-only",
        approval_policy="never",
    )
    fixture_body = _completed_text_response(
        "resp-statusline-toggle-must-not-run",
        "msg-statusline-toggle-must-not-run",
        "STATUSLINE_TOGGLE_MUST_REMAIN_LOCAL",
    )

    def run_member(
        command: TuiComparisonCommand,
        label: str,
    ) -> tuple[TuiProcessTranscript, dict[str, object], int]:
        with _SseFixtureServer(fixture_body) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[tui]\n"
                'status_line = ["model-with-reasoning", "current-dir"]\n'
                "status_line_use_colors = true\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider that /statusline must not call"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            config_path = Path(env["CODEX_HOME"]) / "config.toml"
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "/statusline\r",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.5,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            " \r",
                            ready_text="Press space to toggle",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\x15/statusline",
                            ready_timeout=1.0,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="/statusline",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                        ),
                        ConptyInputStep(
                            "",
                            ready_pattern=r"\[ \]\s+Use theme colors",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
                        ),
                    ),
                    env=env,
                    timeout=2,
                    stop_pattern=r"\[ \]\s+Use theme colors",
                    stop_timeout=8,
                    terminate_on_stop_pattern=True,
                    size=TerminalSize(rows=32, cols=120),
                )
                persisted = read_toml_mapping(config_path)
            request_count = len(server.request_bodies)
        transcript.write_artifacts(
            tmp_path,
            prefix=f"{label}-statusline-toggle",
            rows=32,
            cols=120,
        )
        return transcript, persisted, request_count

    rust_result = run_member(rust, "rust")
    python_result = run_member(python, "python")

    failures: list[str] = []
    for label, (transcript, persisted, request_count) in (
        ("rust", rust_result),
        ("python", python_result),
    ):
        tui_config = persisted.get("tui", {})
        if not isinstance(tui_config, dict):
            tui_config = {}
        if tui_config.get("status_line_use_colors") is not False:
            failures.append(
                f"{label}: Space+Enter did not persist disabled theme colors; "
                f"tui={tui_config!r}; artifacts={str(tmp_path)!r}"
            )
        if tui_config.get("status_line") != [
            "model-with-reasoning",
            "current-dir",
        ]:
            failures.append(
                f"{label}: unchanged selected status items were not preserved; "
                f"tui={tui_config!r}; artifacts={str(tmp_path)!r}"
            )
        output = transcript.normalized_stdout()
        if not re.search(r"\[ \]\s+Use theme colors", output):
            failures.append(
                f"{label}: reopening /statusline did not show the persisted "
                f"unchecked option; output={output!r}; artifacts={str(tmp_path)!r}"
            )
        if request_count != 0:
            failures.append(
                f"{label}: local status-line interaction created a model "
                f"request; count={request_count}; artifacts={str(tmp_path)!r}"
            )
        if "ConPTY command terminated after stop pattern" not in transcript.normalized_stderr():
            failures.append(
                f"{label}: persisted unchecked state was not observed; "
                f"stderr={transcript.normalized_stderr()!r}; artifacts={str(tmp_path)!r}"
            )

    assert not failures, "\n".join(failures)
