"""Windows Sandbox Test Conversation scenarios extracted from the native comparison suite."""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


def test_windows_conpty_native_and_python_conversation_session_uses_windows_sandbox_when_enabled(
    tmp_path: Path,
) -> None:
    # Rust source/test contract:
    # - codex-core maps Responses function_call items into turn tool execution.
    # - codex-tui::chatwidget::command_lifecycle projects command lifecycle
    #   events into exec_cell display items.
    # - codex-tui::exec_cell::render uses "Running" while active, "Ran" after
    #   completion, and preserves a bounded output preview in the transcript.
    #
    # This deterministic comparison runs the same local Responses SSE fixture
    # through native Rust Codex and Python PyCodex, proving the product path:
    # interactive conversation -> model tool call -> core exec -> native
    # Windows sandbox -> function_call_output -> final answer -> TUI.
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
    write_probe = tmp_path / "conversation-session-sandbox-write.txt"
    escaped_probe = str(write_probe).replace("'", "''")
    command = f"Set-Content -LiteralPath '{escaped_probe}' -Value 'sandbox write must fail'"
    control = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert control.returncode == 0, control.stderr
    assert write_probe.is_file()
    write_probe.unlink()

    final_answer = "PYCODEX_WINDOWS_SANDBOX_SESSION_DONE"
    approval_title = "Would you like to run the following command?"
    approval_option = "Yes, proceed"
    call_id = "call-pycodex-exec-native"
    item_id = "fc-pycodex-exec-native"

    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-exec-tool"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": item_id,
                "type": "function_call",
                "call_id": call_id,
                "name": "exec_command",
                "arguments": json.dumps({"cmd": command}, separators=(",", ":")),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-exec-tool",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )
    final_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-exec-final"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-exec-final",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-local-exec-final",
            "output_index": 0,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-exec-final",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-exec-final",
                "usage": {
                    "input_tokens": 2,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 4,
                },
            },
        },
    )

    def run_pair_member(
        command_spec: TuiComparisonCommand,
        prompt_marker: str,
    ) -> tuple[TuiProcessTranscript, list[dict[str, object]], bool]:
        # Delay both model responses so the active-turn status must remain
        # visible before and after command execution.
        with _SseFixtureServer((tool_body, final_body), response_delay_seconds=1.2) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[features]\n"
                "unified_exec = true\n"
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for local exec-command test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                "request_max_retries = 0\n"
                "stream_max_retries = 0\n"
                "supports_websockets = false\n\n"
                "[windows]\n"
                'sandbox = "unelevated"\n'
                "sandbox_private_desktop = false\n\n"
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            _seed_windows_sandbox_setup(Path(temp_home.name))
            if command_spec.kind == "python":
                env["PYCODEX_TUI_TIMING_LOG"] = str(tmp_path / "python.timing.jsonl")
            write_probe.unlink(missing_ok=True)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "run deterministic exec tool",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="exec tool",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "y",
                            ready_text_sequence=(approval_title, approval_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(
                                "Ran",
                                final_answer,
                                prompt_marker,
                            ),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep(
                            "/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                    ),
                    env=env,
                    timeout=50,
                    size=TerminalSize(rows=32, cols=120),
                )
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}\n"
                f"stdout={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            requests = [json.loads(body.decode("utf-8")) for body in server.request_bodies]
            write_created = write_probe.exists()
            write_probe.unlink(missing_ok=True)
            return transcript, requests, write_created

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
    rust_transcript, rust_requests, rust_write_created = run_pair_member(
        rust,
        "mock-model default",
    )
    python_transcript, python_requests, python_write_created = run_pair_member(
        python,
        "mock-model",
    )
    (tmp_path / "rust.requests.json").write_text(
        json.dumps(rust_requests, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (tmp_path / "python.requests.json").write_text(
        json.dumps(python_requests, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    rust_transcript.write_artifacts(tmp_path, prefix="rust", rows=32, cols=120)
    python_transcript.write_artifacts(tmp_path, prefix="python", rows=32, cols=120)

    readiness_failures: list[str] = []
    for label, transcript, requests, write_created, prompt_marker in (
        ("rust", rust_transcript, rust_requests, rust_write_created, "mock-model default"),
        ("python", python_transcript, python_requests, python_write_created, "mock-model"),
    ):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert len(requests) == 2
        second_input = requests[1].get("input")
        assert isinstance(second_input, list)
        function_outputs = [
            item
            for item in second_input
            if isinstance(item, dict)
            and item.get("type") == "function_call_output"
            and item.get("call_id") == call_id
        ]
        assert len(function_outputs) == 1
        function_output = json.dumps(function_outputs[0].get("output"), ensure_ascii=False)
        assert "blocked by policy" not in function_output.lower(), (
            f"{label} command never reached the approved execution path: {function_output}"
        )
        assert "process exited with code 1" in function_output.lower()
        assert not write_created, (
            f"{label} conversation session created {write_probe} despite the "
            "configured read-only Windows sandbox"
        )
        # Rust ratatui may redraw the retained screen again while /quit exits,
        # so completed rows and the final answer are asserted against the
        # ordered semantic checkpoint observed before shutdown.
        expected = (
            "Ran",
            final_answer,
            prompt_marker,
        )
        expected_approval = (approval_title, approval_option)
        if expected_approval not in transcript.observed_ready_sequences:
            readiness_failures.append(
                f"{label}: missing approval checkpoint {expected_approval!r}; "
                f"observed={transcript.observed_ready_sequences!r}"
            )
        if expected not in transcript.observed_ready_sequences:
            readiness_failures.append(
                f"{label}: expected={expected!r}; "
                f"observed={transcript.observed_ready_sequences!r}; "
                f"stderr={transcript.stderr!r}; "
                f"screen={transcript.screen_stdout(rows=32, cols=120)!r}; "
                f"normalized={output!r}; artifacts={str(tmp_path)!r}"
            )
    assert not readiness_failures, "\n".join(readiness_failures)
