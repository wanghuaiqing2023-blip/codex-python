"""Tui Test Reconnect scenarios extracted from the native comparison suite."""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


def test_windows_conpty_native_and_python_stream_retry_state_match_when_enabled(
    tmp_path: Path,
) -> None:
    """Compare retry events, request identity, recovery, and visible status.

    Rust owners/tests:
    - codex-core::responses_retry::handle_retryable_response_stream_error
    - status_and_layout.rs::stream_error_updates_status_indicator
    - app_server.rs::live_app_server_stream_recovery_restores_previous_status_header
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
    # Keep the probe below Rust's paste-burst threshold so ConPTY input is
    # treated as ordinary typing before the retry state machine is exercised.
    prompt = "Retry now"
    answer = "DYNAMIC_STREAM_RETRY_RECOVERED"
    incomplete = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-incomplete"}},
    )
    completed = _completed_text_response("resp-recovered", "msg-recovered", answer)
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
        sandbox_mode="read-only",
        approval_policy="never",
    )

    def run_member(command: TuiComparisonCommand, label: str) -> tuple[TuiProcessTranscript, list[dict[str, object]]]:
        with _SseFixtureServer(
            (incomplete, completed),
            response_delay_seconds=0.25,
        ) as server:
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
                'name = "Mock provider for stream retry parity"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 1\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            timing_log = tmp_path / f"{label}-stream-retry-timing.jsonl"
            env["PYCODEX_TUI_TIMING_LOG"] = str(timing_log)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(prompt, ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=30.0),
                        ConptyInputStep("\r", ready_timeout=0.2),
                        ConptyInputStep(
                            "",
                            ready_screen_text="Reconnecting... 1/1",
                            ready_timeout=20.0,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text=answer,
                            ready_timeout=30.0,
                            ready_quiet_period=0.5,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                        ConptyInputStep("", ready_text="Shutting down", ready_timeout=10.0),
                    ),
                    env=env,
                    timeout=45,
                    size=TerminalSize(rows=32, cols=120),
                )
            requests = [json.loads(body.decode("utf-8")) for body in server.request_bodies]
        transcript.write_artifacts(tmp_path, prefix=f"{label}-stream-retry", rows=32, cols=120)
        (tmp_path / f"{label}-stream-retry-requests.json").write_text(
            json.dumps(requests, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return transcript, requests

    rust_transcript, rust_requests = run_member(rust, "rust")
    python_transcript, python_requests = run_member(python, "python")

    for label, transcript, requests in (
        ("rust", rust_transcript, rust_requests),
        ("python", python_transcript, python_requests),
    ):
        output = transcript.normalized_stdout()
        assert transcript.returncode == 0, f"{label}: {transcript.stderr}"
        assert ("Reconnecting... 1/1",) in transcript.observed_ready_sequences, label
        assert prompt in output, label
        assert answer in output, label
        assert len(requests) == 2, label
        assert requests[0] == requests[1], label
        request_input = json.dumps(requests[0].get("input"), ensure_ascii=False)
        assert request_input.count(prompt) == 1, label

    assert _normalized_first_turn_request_context(python_requests[0]) == (
        _normalized_first_turn_request_context(rust_requests[0])
    )


def test_windows_conpty_native_and_python_stream_retry_exhaustion_clears_working_when_enabled(
    tmp_path: Path,
) -> None:
    """A permanently broken response stream must end the turn after retries.

    Rust owners/tests:
    - codex-core::responses_retry::handle_retryable_response_stream_error
    - codex-core::tasks::SessionTask::run terminal TurnComplete publication
    - codex-tui::chatwidget::turn_runtime::on_error/finalize_turn
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
    # Keep the probe short so neither product routes it through paste-burst or
    # cyber-risk input handling before the mocked network request starts.
    prompt = "Say hello"
    final_error = "stream disconnected before completion: stream closed before response.completed"
    incomplete = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-incomplete"}},
    )
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
        sandbox_mode="read-only",
        approval_policy="never",
    )

    def run_member(command: TuiComparisonCommand, label: str) -> tuple[TuiProcessTranscript, int]:
        with _SseFixtureServer(incomplete) as server:
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
                'name = "Mock provider for stream retry exhaustion parity"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 1\n"
                "supports_websockets = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(prompt, ready_pattern=READY_COMPOSER_PATTERN, ready_timeout=30.0),
                        ConptyInputStep("\r", ready_timeout=0.2),
                        ConptyInputStep("", ready_screen_text="Reconnecting... 1/1", ready_timeout=20.0),
                        ConptyInputStep(
                            "",
                            ready_screen_text=final_error,
                            ready_timeout=20.0,
                            ready_quiet_period=0.3,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2),
                    ),
                    env=env,
                    timeout=45,
                    size=TerminalSize(rows=32, cols=120),
                )
            request_count = len(server.request_bodies)
        transcript.write_artifacts(tmp_path, prefix=f"{label}-stream-retry-exhaustion", rows=32, cols=120)
        return transcript, request_count

    python_transcript, python_request_count = run_member(python, "python")
    rust_transcript, rust_request_count = run_member(rust, "rust")

    for label, transcript, request_count in (
        ("rust", rust_transcript, rust_request_count),
        ("python", python_transcript, python_request_count),
    ):
        screen = transcript.screen_stdout(rows=32, cols=120)
        assert transcript.returncode == 0, f"{label}: {transcript.normalized_combined()}"
        assert ("Reconnecting... 1/1",) in transcript.observed_ready_sequences, label
        assert (final_error,) in transcript.observed_ready_sequences, label
        assert request_count == 2, label
        assert "Working (" not in screen, f"{label}: {screen!r}"
