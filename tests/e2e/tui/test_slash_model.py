"""End-to-end coverage for the ``/model`` slash command."""

from pycodex.tui.chatwidget.slash_dispatch import (
    plan_terminal_local_command,
    terminal_slash_command_routes,
)
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


def test_model_slash_command_routes_to_owned_selection_view() -> None:
    # Rust: chatwidget::slash_dispatch opens chatwidget::model_popups and the
    # command is unavailable during tasks and side conversations.
    route = terminal_slash_command_routes()[SlashCommand.MODEL]

    assert route.outcome == "view"
    assert plan_terminal_local_command("/model").action == "none"
    assert SlashCommand.MODEL.supports_inline_args() is False
    assert SlashCommand.MODEL.available_during_task() is False
    assert SlashCommand.MODEL.available_in_side_conversation() is False


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
