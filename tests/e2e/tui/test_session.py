"""Tui Test Session scenarios extracted from the native comparison suite."""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


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
        ConptyInputStep("", ready_timeout=2.0),
        # Rust no-alt-screen startup can render an initial prompt before
        # session history metadata is installed.  Wait for the configured
        # model/directory header so this native oracle exercises persistent
        # history lookup instead of racing startup.
        # Once a match is visible, accept it with Enter before issuing /quit;
        # while reverse search is active Rust keeps routing printable keys to
        # the search footer instead of the normal composer.
        ConptyInputStep("\x12native", ready_timeout=0.2, chunk_delay=0.02),
        ConptyInputStep("", ready_text="newest native history", ready_timeout=10.0),
        ConptyInputStep("\r\x15/quit\r", ready_timeout=0.2, chunk_delay=0.02),
        ConptyInputStep("", ready_text="Shutting down", ready_timeout=10.0),
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
    python_transcript = run_member(python)

    assert rust_transcript.returncode == 0, rust_transcript.normalized_combined()
    assert python_transcript.returncode == 0, python_transcript.normalized_combined()
    for transcript in (rust_transcript, python_transcript):
        assert ("newest native history",) in transcript.observed_ready_sequences


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


def test_windows_conpty_python_healthy_mcp_turn_closes_without_pipe_errors_when_enabled() -> None:
    # Rust source/runtime contract:
    # - codex-core::session owns McpConnectionManager for the full session.
    # - codex-mcp::connection_manager keeps healthy stdio clients alive across
    #   turns and shuts them down before the session runtime is dropped.
    # This exercises the real terminal entrypoint, one model turn, and /quit so
    # Windows subprocess transport errors cannot hide behind unit-test doubles.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run local ConPTY E2E")
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
    answer = "PYCODEX_MCP_SESSION_OK"
    body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-mcp-session"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-mcp-session",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-mcp-session",
            "output_index": 0,
            "content_index": 0,
            "delta": answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-mcp-session",
                "content": [{"type": "output_text", "text": answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-mcp-session",
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

    with _SseFixtureServer(body) as server:
        config = (
            'model = "mock-model"\n'
            'model_provider = "pycodex_mock"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "read-only"\n'
            'suppress_unstable_features_warning = true\n'
            "\n"
            "[model_providers.pycodex_mock]\n"
            'name = "Mock provider for MCP session test"\n'
            f'base_url = "{server.base_url}"\n'
            'wire_api = "responses"\n'
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "supports_websockets = false\n"
            "\n"
            "[mcp_servers.healthy]\n"
            f"command = {json.dumps(sys.executable)}\n"
            'args = ["-B", "-m", "pycodex.rmcp_client.bin.rmcp_test_server"]\n'
            "\n"
            f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
            'trust_level = "trusted"\n'
        )
        env, temp_home = _isolated_codex_home_env_with_config(config)
        command = build_inline_tui_command(
            "python",
            repo_root=repo_root,
            python_executable=sys.executable,
            extra_args=("--disable", "apps", "--disable", "plugins"),
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "你好\r",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.2,
                    ),
                    ConptyInputStep(
                        "",
                        ready_text=answer,
                        ready_timeout=30.0,
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

    combined = transcript.normalized_combined()
    assert transcript.returncode == 0, combined
    assert answer in transcript.normalized_stdout(), combined
    assert len(server.requests) == 1, combined
    assert "MCP runtime is not implemented" not in combined
    assert "MCP startup incomplete" not in combined
    assert "ProactorBasePipeTransport" not in combined
    assert "BaseSubprocessTransport" not in combined
    assert "I/O operation on closed pipe" not in combined


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
                            atomic_write=True,
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
                            atomic_write=True,
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
                    ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                    ready_timeout=30.0,
                    ready_quiet_period=0.2,
                    atomic_write=True,
                ),
                ConptyInputStep(
                    "\r",
                    ready_text="overlay answer.",
                    ready_timeout=10.0,
                    ready_quiet_period=0.2,
                    chunk_delay=0.01,
                ),
                ConptyInputStep(
                    "",
                    ready_text="long overlay line 48",
                    ready_timeout=30.0,
                    ready_quiet_period=0.3,
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
                ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                atomic_write=True,
            ),
            ConptyInputStep(
                "\r",
                ready_text="navigation answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "",
                ready_text="screen nav line 48",
                ready_timeout=30.0,
                ready_quiet_period=0.3,
            ),
            ConptyInputStep(
                "\x14",
                ready_timeout=0.5,
                ready_quiet_period=0.2,
                chunk_delay=0.02,
            ),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("\x1b[H", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_pattern=r"(?<!\d)0%(?!\d)",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
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
        assert "OpenAI Codex" in screen or "Tip:" in screen, detail
        assert "screen nav line 48" not in screen, detail
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
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-ctrlb-page",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-ctrlb-page",
            "output_index": 0,
            "content_index": 0,
            "delta": long_reply,
        },
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

    def run_pair_member(
        command: TuiComparisonCommand,
        env: dict[str, str],
        prompt_marker: str,
    ) -> object:
        steps = [
            ConptyInputStep(
                "Send ctrlb probe answer.",
                ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
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
            ConptyInputStep(
                "\x14",
                ready_text_sequence=("ctrlb probe line 69", prompt_marker),
                ready_timeout=35.0,
                ready_quiet_period=0.5,
                chunk_delay=0.02,
            ),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("\x02", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_pattern=r"(?<!\d)(?:6\d|7\d|8\d|9[0-4])%(?!\d)",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
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
                run_pair_member(rust, env, "mock-model default"),
                run_pair_member(python, env, "mock-model"),
            ]

    for transcript in page_up_transcripts:
        screen = transcript.screen_stdout(rows=20, cols=100)
        output = transcript.normalized_stdout()
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={output}"
        assert "T R A N S C R I P T" in screen, detail
        percent_matches = [
            int(match.group(1))
            for match in re.finditer(r"(?<!\d)(\d{1,3})%", f"{screen}\n{output}")
        ]
        assert percent_matches, detail
        visible_indices = [
            int(match.group(1))
            for match in re.finditer(r"ctrlb probe line\s*(\d{2})", screen)
        ]
        assert visible_indices, detail
        assert min(visible_indices) < 60, detail
        assert max(visible_indices) < 69, detail
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
            ConptyInputStep(
                "\x14",
                ready_text="roundtrip probe line 69",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.02,
            ),
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
    # - keymap.rs::RuntimeKeymap builds `tui.keymap.pager.jump_top` from
    #   CLI/config overrides.
    # - Rust test: transcript_overlay_paging_is_continuous_and_round_trips
    #   proves PageDown from the top advances by the rendered page height.
    #
    # This native comparison deliberately remaps Home/jump_top to a plain
    # character, then uses the default Ctrl+F PageDown binding. That proves the
    # product behavior without depending on Windows ConPTY CSI delivery for
    # Home/PageDown.
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
                ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                atomic_write=True,
            ),
            ConptyInputStep(
                "\r",
                ready_text="top page-down probe answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "",
                ready_text="top page-down probe line 69",
                ready_timeout=30.0,
                ready_quiet_period=0.3,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("", ready_timeout=2.0),
            ConptyInputStep("g", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep("", ready_timeout=2.0),
            ConptyInputStep("\x06", ready_timeout=0.2, chunk_delay=0.02),
            ConptyInputStep("", ready_timeout=2.0),
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
        output = transcript.normalized_stdout()
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={output}"
        assert "T R A N S C R I P T" in screen, detail
        percent_matches = [
            int(match.group(1))
            for match in re.finditer(r"(?<!\d)(\d{1,3})%", screen)
        ]
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
                ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                atomic_write=True,
            ),
            ConptyInputStep(
                "\r",
                ready_text="end probe answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "",
                ready_text="end probe line 69",
                ready_timeout=30.0,
                ready_quiet_period=0.3,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("\x1b[H", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_screen_text="0%",
                ready_timeout=5.0,
                ready_quiet_period=0.3,
            ),
            ConptyInputStep("\x1b[F", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_screen_text="100%",
                ready_timeout=5.0,
                ready_quiet_period=0.3,
            ),
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
        assert re.search(r"(?<!\d)100%", screen) or re.search(
            r"(?<!\d)100%",
            transcript.normalized_stdout(),
        ), detail
        assert not re.search(r"(?<!\d)0%", screen), detail
        assert "[F" not in screen, detail


def test_windows_conpty_native_and_python_long_transcript_overlay_dual_remapped_jump_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::pager_overlay::PagerView::handle_key_event maps configured
    #   PagerKeymap.jump_top and jump_bottom bindings.
    #
    # This comparison exercises two configured plain-key actions end to end:
    # `g` moves to 0%, then `b` returns to 100%.
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
                ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                ready_timeout=30.0,
                ready_quiet_period=0.2,
                atomic_write=True,
            ),
            ConptyInputStep(
                "\r",
                ready_text="wheel key answer.",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.01,
            ),
            ConptyInputStep(
                "",
                ready_text="wheel key line 69",
                ready_timeout=30.0,
                ready_quiet_period=0.3,
            ),
            ConptyInputStep("\x14", ready_timeout=0.5, ready_quiet_period=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_text="T R A N S C R I P T",
                ready_timeout=10.0,
                ready_quiet_period=0.5,
            ),
            ConptyInputStep("g", ready_timeout=0.5, ready_quiet_period=0.5, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_screen_text="OpenAI Codex",
                ready_timeout=10.0,
            ),
            ConptyInputStep("", ready_timeout=2.0),
            ConptyInputStep("b", ready_timeout=0.2, chunk_delay=0.02),
            ConptyInputStep(
                "",
                ready_screen_text="100%",
                ready_timeout=10.0,
            ),
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
            "-c",
            'tui.keymap.pager.jump_top="g"',
            "-c",
            'tui.keymap.pager.jump_bottom="b"',
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
        output = transcript.normalized_stdout()
        detail = f"argv={transcript.argv!r}\nrequests={server.requests!r}\nscreen={screen}\nstdout={output}"
        assert "T R A N S C R I P T" in screen, detail
        assert ("OpenAI Codex",) in transcript.observed_ready_sequences, detail
        assert ("100%",) in transcript.observed_ready_sequences, detail


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
            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
            ready_timeout=30.0,
            ready_quiet_period=0.5,
            atomic_write=True,
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
        compact_output = re.sub(r"\s+", "", output)
        assert "OpenAI Codex" in output
        assert "ReplywithexactlyPYCODEX_NATIVE_OKandnothingelse." in compact_output
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
                "\x15/quit",
                chunk_delay=0.02,
            ),
            ConptyInputStep(
                "\r",
                ready_text="/quit",
                ready_timeout=10.0,
                ready_quiet_period=0.2,
                chunk_delay=0.02,
            ),
            ConptyInputStep(
                "",
                ready_text="Token usage:",
                ready_timeout=10.0,
            ),
        )

    rust_transcript = _run_live_conpty_with_capacity_retries(
        lambda: run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps_for_prompt_marker("\u203a"),
            env=_conpty_tui_env(),
            timeout=20,
            size=TerminalSize(rows=32, cols=120),
            stop_timeout=45,
        )
    )
    python_transcript = _run_live_conpty_with_capacity_retries(
        lambda: run_windows_conpty_tui_command(
            python,
            input_steps=input_steps_for_prompt_marker("\u203a"),
            env=_conpty_tui_env(),
            timeout=20,
            size=TerminalSize(rows=32, cols=120),
            stop_timeout=45,
        )
    )

    for transcript in (rust_transcript, python_transcript):
        _assert_live_multi_turn_shutdown_summary(transcript, first=first, second=second)
