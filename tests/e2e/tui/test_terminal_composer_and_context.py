"""Cross-command composer, keybinding, and request-context E2E scenarios.

Canonical slash-command coverage lives in ``test_slash_<command>.py`` files.
This suite retains interactions that intentionally span command discovery,
keyboard handling, session restart, and model-request context.
"""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


def _last_live_composer_row(screen: str) -> str:
    rows = [line.strip() for line in screen.splitlines() if line.lstrip().startswith("›")]
    return rows[-1] if rows else ""


def test_windows_conpty_python_ctrl_c_clears_multiline_draft_then_empty_ctrl_c_exits(
    tmp_path: Path,
) -> None:
    """Ctrl+C clears and records a whole draft before it is allowed to exit.

    Rust owners/tests:
    - ``bottom_pane::BottomPane::on_ctrl_c`` gives a non-empty composer first
      refusal and only leaves an empty composer unhandled for the quit path;
    - ``bottom_pane::ChatComposer::clear_for_ctrl_c`` clears the complete
      draft, resets navigation, and records the cleared draft in local history;
    - ``clear_for_ctrl_c_records_cleared_draft`` proves Up can recall it.

    Bracketed paste creates one real multiline draft without submitting a
    model turn.  The first Ctrl+C must leave the process alive with an empty
    composer, Up must restore both lines, and only a later Ctrl+C on the empty
    composer may exit.
    """

    if os.name != "nt":
        pytest.skip("Windows ConPTY regression only runs on Windows")
    capability = interactive_tui_comparison_capability(conpty_driver_available=True)
    if not capability.available:
        pytest.skip(capability.reason)

    repo_root = _repo_root()
    first_line = "PYCODEX_CTRL_C_MULTILINE_FIRST"
    second_line = "PYCODEX_CTRL_C_MULTILINE_SECOND"
    multiline_draft = f"{first_line}\n{second_line}"
    python = build_inline_tui_command(
        "python",
        repo_root=repo_root,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    env, temp_home = _isolated_codex_home_env()

    with temp_home:
        transcript = run_windows_conpty_tui_command(
            python,
            input_steps=(
                ConptyInputStep(
                    f"\x1b[200~{multiline_draft}\x1b[201~",
                    ready_pattern=READY_COMPOSER_PATTERN,
                    ready_timeout=30.0,
                    ready_quiet_period=0.2,
                    atomic_write=True,
                ),
                ConptyInputStep(
                    "",
                    ready_screen_text=second_line,
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                    capture_name="multiline-before-ctrl-c",
                ),
                ConptyInputStep("\x03", ready_timeout=0.1, atomic_write=True),
                ConptyInputStep(
                    "",
                    ready_timeout=0.5,
                    capture_name="after-first-ctrl-c",
                ),
                ConptyInputStep("\x1b[A", ready_timeout=0.1, atomic_write=True),
                ConptyInputStep(
                    "",
                    ready_timeout=0.5,
                    capture_name="recalled-cleared-draft",
                ),
                # Clear the recalled draft, then press Ctrl+C on the now-empty
                # composer to exercise the Rust-owned exit boundary.
                ConptyInputStep("\x03", ready_timeout=0.1, atomic_write=True),
                ConptyInputStep("\x03", ready_timeout=0.2, atomic_write=True),
            ),
            env=env,
            timeout=20,
            size=TerminalSize(rows=32, cols=120),
        )

    transcript.write_artifacts(tmp_path, prefix="python-ctrl-c-multiline", rows=32, cols=120)
    before_clear = transcript.checkpoint_screen(
        "multiline-before-ctrl-c",
        rows=32,
        cols=120,
    )
    after_clear = transcript.checkpoint_screen(
        "after-first-ctrl-c",
        rows=32,
        cols=120,
    )
    recalled = transcript.checkpoint_screen(
        "recalled-cleared-draft",
        rows=32,
        cols=120,
    )

    assert first_line in before_clear and second_line in before_clear, before_clear
    assert first_line not in after_clear and second_line not in after_clear, after_clear
    assert _last_live_composer_row(after_clear) == "› Ask Codex to do anything", after_clear
    assert first_line in recalled and second_line in recalled, recalled
    assert transcript.returncode == 0, transcript.normalized_combined()
    assert "Traceback" not in transcript.normalized_combined()


def test_windows_conpty_python_up_continues_past_recalled_slash_command(
    tmp_path: Path,
) -> None:
    """A recalled slash command must not reopen the popup and consume Up.

    Rust owner: ``ChatComposer::sync_popups`` checks
    ``history.should_handle_navigation`` and suppresses all popups while the
    composer contains a recalled history entry.
    """

    if os.name != "nt":
        pytest.skip("Windows ConPTY regression only runs on Windows")
    capability = interactive_tui_comparison_capability(conpty_driver_available=True)
    if not capability.available:
        pytest.skip(capability.reason)

    repo_root = _repo_root()
    python = build_inline_tui_command(
        "python",
        repo_root=repo_root,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    env, temp_home = _isolated_codex_home_env()

    with temp_home:
        transcript = run_windows_conpty_tui_command(
            python,
            input_steps=(
                ConptyInputStep(
                    "/status\r",
                    ready_pattern=READY_COMPOSER_PATTERN,
                    ready_timeout=30.0,
                    ready_quiet_period=0.2,
                    atomic_write=True,
                ),
                ConptyInputStep("/ps\r", ready_timeout=0.3, atomic_write=True),
                ConptyInputStep("\x1b[A", ready_timeout=0.2, atomic_write=True),
                ConptyInputStep(
                    "",
                    ready_screen_text="› /ps",
                    ready_timeout=5.0,
                    ready_quiet_period=0.2,
                    capture_name="recalled-latest-slash",
                ),
                ConptyInputStep("\x1b[A", ready_timeout=0.2, atomic_write=True),
                ConptyInputStep(
                    "",
                    ready_timeout=0.5,
                    capture_name="recalled-older-slash",
                ),
                ConptyInputStep("\x03", ready_timeout=0.1, atomic_write=True),
                ConptyInputStep("\x03", ready_timeout=0.2, atomic_write=True),
            ),
            env=env,
            timeout=20,
            size=TerminalSize(rows=32, cols=120),
        )

    transcript.write_artifacts(tmp_path, prefix="python-slash-history-up", rows=32, cols=120)
    latest = transcript.checkpoint_screen("recalled-latest-slash", rows=32, cols=120)
    older = transcript.checkpoint_screen("recalled-older-slash", rows=32, cols=120)

    assert _last_live_composer_row(latest) == "› /ps", latest
    assert _last_live_composer_row(older) == "› /status", older
    assert transcript.returncode == 0, transcript.normalized_combined()
    assert "Traceback" not in transcript.normalized_combined()


def test_windows_conpty_python_history_retains_multiple_modal_slash_commands(
    tmp_path: Path,
) -> None:
    """Modal slash commands must remain available to repeated Up navigation.

    Rust ``chatwidget::slash_dispatch`` records the command staged by
    ``ChatComposer`` after dispatch, including commands such as ``/model`` and
    ``/permissions`` that open a bottom-pane view.  Cancelling those views does
    not remove their composer-history entries.
    """

    if os.name != "nt":
        pytest.skip("Windows ConPTY regression only runs on Windows")
    capability = interactive_tui_comparison_capability(conpty_driver_available=True)
    if not capability.available:
        pytest.skip(capability.reason)

    repo_root = _repo_root()
    python = build_inline_tui_command(
        "python",
        repo_root=repo_root,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    env, temp_home = _isolated_codex_home_env()

    with temp_home:
        transcript = run_windows_conpty_tui_command(
            python,
            input_steps=(
                ConptyInputStep(
                    "/model\r",
                    ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                    ready_timeout=30.0,
                    ready_quiet_period=0.4,
                    atomic_write=True,
                ),
                ConptyInputStep(
                    "",
                    ready_screen_text="Select Model",
                    ready_timeout=10.0,
                    ready_quiet_period=0.3,
                ),
                # Give the Windows escape decoder an isolated byte and enough
                # time to cancel the view before starting the next command.
                ConptyInputStep("\x1b", ready_timeout=1.0, atomic_write=True),
                ConptyInputStep("/permissions\r", ready_timeout=0.2, atomic_write=True),
                ConptyInputStep(
                    "",
                    ready_screen_text="Update Model Permissions",
                    ready_timeout=10.0,
                    ready_quiet_period=0.3,
                ),
                ConptyInputStep("\x1b", ready_timeout=1.0, atomic_write=True),
                ConptyInputStep("/status\r", ready_timeout=0.2, atomic_write=True),
                ConptyInputStep(
                    "",
                    ready_screen_text="Token usage:",
                    ready_timeout=10.0,
                    ready_quiet_period=0.3,
                ),
                ConptyInputStep("\x1b[A", ready_timeout=0.2, atomic_write=True),
                ConptyInputStep("", ready_timeout=0.5, capture_name="modal-history-up-1"),
                ConptyInputStep("\x1b[A", ready_timeout=0.2, atomic_write=True),
                ConptyInputStep("", ready_timeout=0.5, capture_name="modal-history-up-2"),
                ConptyInputStep("\x1b[A", ready_timeout=0.2, atomic_write=True),
                ConptyInputStep("", ready_timeout=0.5, capture_name="modal-history-up-3"),
                ConptyInputStep("\x03", ready_timeout=0.1, atomic_write=True),
                ConptyInputStep("\x03", ready_timeout=0.2, atomic_write=True),
            ),
            env=env,
            timeout=35,
            size=TerminalSize(rows=32, cols=120),
        )

    transcript.write_artifacts(tmp_path, prefix="python-modal-slash-history", rows=32, cols=120)
    recalled = [
        _last_live_composer_row(
            transcript.checkpoint_screen(
                f"modal-history-up-{index}",
                rows=32,
                cols=120,
            )
        )
        for index in range(1, 4)
    ]

    assert recalled == ["› /status", "› /permissions", "› /model"]
    assert transcript.returncode == 0, transcript.normalized_combined()
    assert "Traceback" not in transcript.normalized_combined()


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
        compact_output = re.sub(r"\s+", "", output)
        assert "OpenAI Codex" in output
        assert "/ for commands" in output
        assert "! for shell commands" in output
        assert "ctrl + t to view transcript" in output
        assert "customizeshortcutswith/keymap" in compact_output


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
        ConptyInputStep("literal", ready_timeout=0.1, chunk_delay=0.02),
        ConptyInputStep("?", ready_screen_text="literal", ready_timeout=10.0, chunk_delay=0.02),
        ConptyInputStep("\x15", ready_screen_text="literal?", ready_timeout=10.0, chunk_delay=0.02),
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
        assert any("literal?" in observed for observed in transcript.observed_ready_sequences)
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
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
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
        # A zero return code proves /quit completed. The native TUI does not
        # retain the transient shutdown placeholder on this backtrack path.




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
        visible_lines = [line for line in screen.splitlines() if line.strip()]
        assert visible_lines[-1].lstrip().startswith("/mcp"), (
            "Rust ChatComposer ActivePopup rows replace the passive footer; "
            f"screen={screen}\nstdout={output}"
        )
        assert "/plugins" not in screen
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
            "/agent",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
        ),
        ConptyInputStep("\r", ready_text="/agent", ready_timeout=10.0),
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
        compact_output = re.sub(r"\s+", "", output)
        assert "OpenAI Codex" in output
        assert "Enable subagents?" in output
        assert "Yes, enable" in output
        assert "Notnow" in compact_output
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
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
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
            "/status",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
        ),
        ConptyInputStep(
            "\r",
            ready_screen_text="› /status",
            ready_timeout=10.0,
            ready_quiet_period=0.3,
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
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
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
            "-c",
            'tui.keymap.global.open_external_editor="f12"',
            "-c",
            'tui.keymap.global.copy="ctrl-x"',
            "--disable",
            "apps",
            "--disable",
            "plugins",
        ),
    )
    env, temp_home = _isolated_codex_home_env_with_config(config_text)
    input_steps = (
        ConptyInputStep(
            "\x18",
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
        "-c",
        'tui.keymap.global.open_external_editor="f12"',
        "-c",
        'tui.keymap.global.toggle_raw_output="ctrl-x"',
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
            "\x18",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
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
            stop_pattern="raw",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=env,
            timeout=20,
            stop_pattern="raw",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=32, cols=120),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        compact_output = re.sub(r"\s+", "", output)
        assert "OpenAI Codex" in output
        assert "rawoutput" in compact_output
        assert "Raw output mode on:" not in output
        assert "you\n  /raw" not in output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()


@pytest.mark.parametrize(
    ("implementation_choice", "continuation_kind"),
    (("1", "same_context"), ("2", "clear_context"), ("3", "stay_plan")),
    ids=("implement", "clear-context-implement", "stay-plan"),
)
def test_windows_conpty_native_and_python_plan_slash_context_and_completion_match_when_enabled(
    tmp_path: Path,
    implementation_choice: str,
    continuation_kind: str,
) -> None:
    """Compare /plan from slash dispatch through proposed-plan completion.

    Rust owners:
    - codex-tui::chatwidget::slash_dispatch::apply_plan_slash_command
    - codex-core::session::turn::built_tools and request assembly
    - codex-core proposed-plan stream item mapping
    - codex-tui::chatwidget::plan_implementation
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
    prompt = "DYNAMIC_PLAN_SLASH_CONTEXT_PARITY"
    command_text = f"/plan {prompt}"
    visible_answer = "DYNAMIC_PLAN_SLASH_DONE"
    implementation_answer = "DYNAMIC_PLAN_IMPLEMENTATION_DONE"
    stay_prompt = "DYNAMIC_STAY_PLAN_CHECK"
    stay_answer = "DYNAMIC_STAY_PLAN_CONFIRMED"
    plan_markdown = "- Inspect the parser\n- Propose the implementation"
    full_answer = (
        f"{visible_answer}\n<proposed_plan>\n{plan_markdown}\n</proposed_plan>\n"
    )
    rejected_update_plan_response = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-plan-rejected-update"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-plan-rejected-update",
                "type": "function_call",
                "call_id": "call-plan-rejected-update",
                "name": "update_plan",
                "arguments": json.dumps(
                    {"plan": [{"step": "Do not use update_plan in Plan mode", "status": "in_progress"}]},
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-plan-rejected-update",
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 4,
                    "output_tokens_details": None,
                    "total_tokens": 14,
                },
            },
        },
    )
    request_user_input_response = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-plan-question"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-plan-question",
                "type": "function_call",
                "call_id": "call-plan-question",
                "name": "request_user_input",
                "arguments": json.dumps(
                    {
                        "questions": [
                            {
                                "header": "Approach",
                                "id": "approach",
                                "question": "Which implementation approach?",
                                "options": [
                                    {
                                        "label": "Direct implementation",
                                        "description": "Implement the smallest Rust-aligned change.",
                                    },
                                    {
                                        "label": "Defer implementation",
                                        "description": "Keep planning without changing code.",
                                    },
                                ],
                            }
                        ]
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-plan-question",
                "usage": {
                    "input_tokens": 12,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 5,
                    "output_tokens_details": None,
                    "total_tokens": 17,
                },
            },
        },
    )
    plan_response = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-plan-slash"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-plan-slash",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-plan-slash",
            "output_index": 0,
            "content_index": 0,
            "delta": full_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-plan-slash",
                "content": [{"type": "output_text", "text": full_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-plan-slash",
                "usage": {
                    "input_tokens": 12,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 8,
                    "output_tokens_details": None,
                    "total_tokens": 20,
                },
            },
        },
    )
    implementation_response = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-plan-implementation"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-plan-implementation",
                "content": [{"type": "output_text", "text": implementation_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-plan-implementation",
                "usage": {
                    "input_tokens": 16,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 4,
                    "output_tokens_details": None,
                    "total_tokens": 20,
                },
            },
        },
    )
    stay_response = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-plan-stay"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-plan-stay",
                "content": [{"type": "output_text", "text": stay_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-plan-stay",
                "usage": {
                    "input_tokens": 16,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 4,
                    "output_tokens_details": None,
                    "total_tokens": 20,
                },
            },
        },
    )
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

    def run_member(command: TuiComparisonCommand, label: str) -> tuple[list[dict[str, object]], TuiProcessTranscript]:
        final_response = stay_response if continuation_kind == "stay_plan" else implementation_response
        with _SseFixtureServer(
            (
                rejected_update_plan_response,
                request_user_input_response,
                plan_response,
                final_response,
            ),
            response_delay_seconds=0.2,
        ) as server:
            config = (
                'model = "gpt-5.6-sol"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "unified_exec = true\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for plan slash parity"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            if label == "python":
                env["PYCODEX_TUI_TIMING_LOG"] = str(
                    tmp_path / f"python-plan-slash-{continuation_kind}-timing.jsonl"
                )
            final_steps = (
                (
                    ConptyInputStep(
                        "",
                        ready_text=implementation_answer,
                        ready_timeout=45.0,
                        ready_quiet_period=0.3,
                    ),
                )
                if continuation_kind != "stay_plan"
                else (
                    ConptyInputStep(
                        stay_prompt,
                        ready_timeout=1.0,
                        chunk_delay=0.02,
                    ),
                    ConptyInputStep("\r", ready_timeout=0.5, chunk_delay=0.02),
                    ConptyInputStep(
                        "",
                        ready_text=stay_answer,
                        ready_timeout=45.0,
                        ready_quiet_period=0.3,
                    ),
                )
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "/plan",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_timeout=1.0, chunk_delay=0.02),
                        ConptyInputStep(
                            "",
                            ready_text="Plan mode.",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            command_text,
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            chunk_delay=0.02,
                            ready_quiet_period=0.2,
                        ),
                        # Slash-popup redraws split the visible draft across VT frames,
                        # so synchronize Enter with the input event stream rather than
                        # requiring the transcript to contain one contiguous command.
                        ConptyInputStep("\r", ready_timeout=2.0, chunk_delay=0.02),
                        ConptyInputStep(
                            "",
                            ready_text="Which implementation approach?",
                            ready_timeout=45.0,
                            ready_quiet_period=0.3,
                        ),
                        # Rust request_user_input accepts numbered options in
                        # the digit key event itself. A trailing Enter can race
                        # with the plan-implementation view and accept its
                        # default row instead of the requested scenario.
                        ConptyInputStep("1", ready_text="Direct implementation", ready_timeout=5.0),
                        ConptyInputStep(
                            "",
                            ready_text=PLAN_IMPLEMENTATION_TITLE,
                            ready_timeout=45.0,
                            ready_quiet_period=0.3,
                        ),
                        ConptyInputStep(
                            implementation_choice,
                            ready_text=PLAN_IMPLEMENTATION_TITLE,
                            ready_timeout=5.0,
                        ),
                        *final_steps,
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=65,
                    size=TerminalSize(rows=40, cols=150),
                )
            transcript.write_artifacts(
                tmp_path,
                prefix=f"{label}-plan-slash-{continuation_kind}",
                rows=40,
                cols=150,
            )
            assert server.request_bodies, (
                f"{label} emitted no Plan request; output={transcript.normalized_combined()!r}"
            )
            requests = [json.loads(body.decode("utf-8")) for body in server.request_bodies]
            (tmp_path / f"{label}-plan-slash-{continuation_kind}-request.json").write_text(
                json.dumps(requests, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return requests, transcript

    rust_requests, rust_transcript = run_member(rust, "rust")
    python_requests, python_transcript = run_member(python, "python")

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert visible_answer in output
        assert "Inspect the parser" in output
        assert "Propose the implementation" in output
        assert "<proposed_plan>" not in output
        assert "</proposed_plan>" not in output
        assert "\u2022 Proposed Plan" in output
        assert PLAN_IMPLEMENTATION_TITLE in output
    python_output = python_transcript.normalized_stdout()
    assert (stay_answer if continuation_kind == "stay_plan" else implementation_answer) in python_output

    assert len(python_requests) == 4
    assert len(rust_requests) >= 3
    (
        rust_request,
        rust_after_rejection_request,
        rust_after_user_input_request,
    ) = rust_requests[:3]
    (
        python_request,
        python_after_rejection_request,
        python_after_user_input_request,
        python_continuation_request,
    ) = python_requests
    rust_context = _normalized_first_turn_request_context(rust_request)
    python_context = _normalized_first_turn_request_context(python_request)
    assert python_context == rust_context
    assert prompt in json.dumps(python_request.get("input"), ensure_ascii=False)
    assert command_text not in json.dumps(python_request.get("input"), ensure_ascii=False)
    assert "function:update_plan" in python_context["tool_names"]
    assert "function:request_user_input" in python_context["tool_names"]
    assert _normalized_first_turn_request_context(python_after_rejection_request) == (
        _normalized_first_turn_request_context(rust_after_rejection_request)
    )
    rejection_input = json.dumps(python_after_rejection_request.get("input"), ensure_ascii=False)
    assert "update_plan is a TODO/checklist tool and is not allowed in Plan mode" in rejection_input
    assert _normalized_first_turn_request_context(python_after_user_input_request) == (
        _normalized_first_turn_request_context(rust_after_user_input_request)
    )
    user_input_result = json.dumps(python_after_user_input_request.get("input"), ensure_ascii=False)
    assert "Direct implementation" in user_input_result
    continuation_input = json.dumps(python_continuation_request.get("input"), ensure_ascii=False)
    if continuation_kind == "same_context":
        assert "Implement the plan." in continuation_input
    elif continuation_kind == "clear_context":
        assert PLAN_IMPLEMENTATION_CLEAR_CONTEXT_PREFIX in continuation_input
        assert "Inspect the parser" in continuation_input
        assert "Propose the implementation" in continuation_input
        assert prompt not in continuation_input
    else:
        assert stay_prompt in continuation_input
        assert "<collaboration_mode># Plan Mode" in continuation_input

    assert len(rust_requests) == 4
    rust_continuation_request = rust_requests[3]
    assert _normalized_first_turn_request_context(python_continuation_request) == (
        _normalized_first_turn_request_context(rust_continuation_request)
    )
    rust_output = rust_transcript.normalized_stdout()
    assert (stay_answer if continuation_kind == "stay_plan" else implementation_answer) in rust_output


def test_windows_conpty_native_and_python_plan_mode_resume_context_match_when_enabled(
    tmp_path: Path,
) -> None:
    """Compare historical Plan context across a real ``resume --last`` restart.

    Rust owners/tests:
    - codex-tui::app_server_session::thread_session_state_from_thread_resume_response
    - chatwidget::session_flow::handle_thread_session

    A cold process restart retains Plan in model history but starts the current
    collaboration mode in Default. In-process thread snapshot replay is covered
    separately and does restore the saved Plan input state.
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
    seed_prompt = "DYNAMIC_PLAN_RESUME_SEED"
    resumed_prompt = "DYNAMIC_PLAN_RESUME_CONTINUATION"
    seed_answer = "DYNAMIC_PLAN_RESUME_SEEDED"
    resumed_answer = "DYNAMIC_PLAN_RESUME_CONFIRMED"

    def message_response(response_id: str, message_id: str, text: str) -> bytes:
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
                        "input_tokens": 8,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens": 3,
                        "output_tokens_details": None,
                        "total_tokens": 11,
                    },
                },
            },
        )

    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
        sandbox_mode="read-only",
        approval_policy="on-request",
    )

    def run_member(command: TuiComparisonCommand, label: str) -> tuple[list[dict[str, object]], tuple[TuiProcessTranscript, TuiProcessTranscript]]:
        with _SseFixtureServer(
            (
                message_response("resp-plan-resume-seed", "msg-plan-resume-seed", seed_answer),
                message_response("resp-plan-resume-next", "msg-plan-resume-next", resumed_answer),
            ),
            response_delay_seconds=0.2,
        ) as server:
            config = (
                'model = "gpt-5.6-sol"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "apps = false\n"
                "plugins = false\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for Plan resume parity"\n'
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
                timing_log = Path(temp_home.name) / f"{label}-plan-resume-timing.jsonl"
                env["PYCODEX_TUI_TIMING_LOG"] = str(timing_log)
                first = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep("/plan", ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=30.0),
                        ConptyInputStep("\r", ready_timeout=1.0),
                        ConptyInputStep("", ready_text="Plan mode.", ready_timeout=10.0),
                        ConptyInputStep(seed_prompt, ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=30.0),
                        ConptyInputStep("\r", ready_timeout=0.5),
                        ConptyInputStep("", ready_text=seed_answer, ready_timeout=40.0),
                        ConptyInputStep("/quit\r", ready_timeout=0.2),
                    ),
                    env=env,
                    timeout=55,
                    size=TerminalSize(rows=36, cols=140),
                )
                resumed_command = TuiComparisonCommand(
                    kind=command.kind,
                    argv=(*command.argv, "resume", "--last"),
                    cwd=command.cwd,
                )
                second = run_windows_conpty_tui_command(
                    resumed_command,
                    input_steps=(
                        ConptyInputStep(resumed_prompt, ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=35.0),
                        ConptyInputStep("\r", ready_timeout=0.5),
                        ConptyInputStep("", ready_text=resumed_answer, ready_timeout=40.0),
                        ConptyInputStep("/quit\r", ready_timeout=0.2),
                    ),
                    env=env,
                    timeout=55,
                    size=TerminalSize(rows=36, cols=140),
                )
                for index, rollout in enumerate(
                    sorted(Path(temp_home.name).rglob("rollout-*.jsonl"))
                ):
                    (tmp_path / f"{label}-plan-resume-rollout-{index}.jsonl").write_bytes(
                        rollout.read_bytes()
                    )
                if timing_log.is_file():
                    (tmp_path / timing_log.name).write_bytes(timing_log.read_bytes())
            first.write_artifacts(tmp_path, prefix=f"{label}-plan-resume-seed", rows=36, cols=140)
            second.write_artifacts(tmp_path, prefix=f"{label}-plan-resume-next", rows=36, cols=140)
            requests = [json.loads(body.decode("utf-8")) for body in server.request_bodies]
            (tmp_path / f"{label}-plan-resume-request.json").write_text(
                json.dumps(requests, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return requests, (first, second)

    rust_requests, rust_transcripts = run_member(rust, "rust")
    python_requests, python_transcripts = run_member(python, "python")

    def rollout_mode_sequence(label: str) -> list[str | None]:
        rollouts = sorted(tmp_path.glob(f"{label}-plan-resume-rollout-*.jsonl"))
        assert len(rollouts) == 1
        modes: list[str | None] = []
        for raw_line in rollouts[0].read_text(encoding="utf-8").splitlines():
            record = json.loads(raw_line)
            if record.get("type") != "turn_context":
                continue
            collaboration = record.get("payload", {}).get("collaboration_mode")
            modes.append(collaboration.get("mode") if isinstance(collaboration, dict) else None)
        return modes

    assert len(rust_requests) == len(python_requests) == 2
    for requests, transcripts in ((rust_requests, rust_transcripts), (python_requests, python_transcripts)):
        assert seed_answer in transcripts[0].normalized_stdout()
        assert resumed_answer in transcripts[1].normalized_stdout()
        assert seed_prompt in json.dumps(requests[0].get("input"), ensure_ascii=False)
        assert resumed_prompt in json.dumps(requests[1].get("input"), ensure_ascii=False)
        assert "<collaboration_mode># Plan Mode" in json.dumps(requests[1].get("input"), ensure_ascii=False)

    assert rollout_mode_sequence("rust") == ["plan", "default"]
    assert rollout_mode_sequence("python") == ["plan", "default"]

    assert _normalized_first_turn_request_context(python_requests[0]) == (
        _normalized_first_turn_request_context(rust_requests[0])
    )
    assert _normalized_first_turn_request_context(python_requests[1]) == (
        _normalized_first_turn_request_context(rust_requests[1])
    )


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
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
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
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
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
