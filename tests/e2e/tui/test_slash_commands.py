"""Tui Test Slash Commands scenarios extracted from the native comparison suite."""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


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
        visible_lines = [line for line in screen.splitlines() if line.strip()]
        assert visible_lines[-1].lstrip().startswith("/mcp"), (
            "Rust ChatComposer ActivePopup rows replace the passive footer; "
            f"screen={screen}\nstdout={output}"
        )
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
            stop_pattern=r"Model changed to \S+ \S+",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )
        python_transcript = run_windows_conpty_tui_command(
            python,
            input_steps=input_steps,
            env=python_env,
            timeout=10,
            stop_pattern=r"Model changed to \S+ \S+",
            stop_timeout=10,
            terminate_on_stop_pattern=True,
            size=TerminalSize(rows=rows, cols=cols),
        )

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=rows, cols=cols)
        assert "OpenAI Codex" in output
        assert "Select Reasoning Level" in output
        match = re.search(r"Model changed to (\S+) (\S+)", output)
        assert match is not None, f"expected persisted selection notice; stdout={output!r}"
        selection = match.groups()
        assert re.search(rf"{re.escape(selection[0])}\s+{re.escape(selection[1])}", screen)
        assert selection[1] in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
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
            "/review",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
        ),
        ConptyInputStep("\r", ready_text="/review", ready_timeout=10.0),
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
        compact_output = re.sub(r"\s+", "", output)
        assert "OpenAI Codex" in output
        assert "Select a review preset" in output
        assert "Reviewagainstabasebranch" in compact_output
        assert "Reviewuncommittedchanges" in compact_output
        assert "Reviewacommit" in compact_output
        assert "Customreviewinstructions" in compact_output
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
        compact_output = re.sub(r"\s+", "", output)
        assert "OpenAI Codex" in output
        assert "Update Model Permissions" in output
        assert "ReadOnly" in compact_output
        assert "Default" in output
        assert "FullAccess" in compact_output
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
            chunk_delay=0.0,
            atomic_write=True,
        ),
        ConptyInputStep(
            "\r",
            ready_screen_text="/keymap debug",
            ready_timeout=10.0,
            ready_quiet_period=0.1,
            chunk_delay=0.0,
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
            "/keymap",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
        ),
        ConptyInputStep("\r", ready_text="/keymap", ready_timeout=10.0),
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
        ConptyInputStep("\r", ready_text="/status", ready_timeout=10.0),
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
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="CLR",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "/clear",
                            ready_text_sequence=(answer, prompt_marker),
                            ready_timeout=35.0,
                            ready_quiet_period=0.5,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="/clear",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            "",
                            ready_screen_text="OpenAI Codex",
                            ready_timeout=10.0,
                            ready_quiet_period=0.3,
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
        observed = "\n".join(
            "\n".join(sequence)
            for sequence in transcript.observed_ready_sequences
        )
        assert "/clear" in observed
        assert answer in observed
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
            "/copy",
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
        ),
        ConptyInputStep("\r", ready_text="/copy", ready_timeout=10.0),
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
        with _SseFixtureServer(body, response_delay_seconds=20.0) as server:
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
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="active slash prompt",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "/model",
                            ready_text_sequence=("Working", "esc to interrupt"),
                            ready_timeout=15.0,
                            chunk_delay=0.1,
                        ),
                        ConptyInputStep(
                            "\x1b\r\r",
                            ready_screen_text="/model",
                            ready_timeout=10.0,
                            chunk_delay=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text="'/model' is disabled while a task is in progress.",
                            ready_timeout=10.0,
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
        screen = transcript.screen_stdout(rows=32, cols=120)
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
        assert (sentinel, "mock-model") in transcript.observed_ready_sequences
        assert ("'/model' is disabled while a task is in progress.",) in (
            transcript.observed_ready_sequences
        )
        assert "Select Model" not in screen


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
