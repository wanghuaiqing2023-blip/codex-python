"""Tui Test Tools scenarios extracted from the native comparison suite."""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


def test_windows_conpty_native_and_python_hosted_web_search_lifecycle(tmp_path: Path) -> None:
    """Compare Rust/Python WebSearch start, completion, and final-answer UI.

    Rust owners:
    - ``codex-core::stream_events_utils`` maps hosted ``web_search_call``
      response items into item-started and item-completed notifications;
    - ``codex-tui::chatwidget::protocol`` routes those notifications to
      ``on_web_search_begin`` and replay completion;
    - ``codex-tui::chatwidget::tool_lifecycle`` owns the active/completed
      ``Searching the web`` / ``Searched`` transcript cells.
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
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    query = "pycodex deterministic web search marker"
    final_answer = "PYCODEX_WEB_SEARCH_DONE"
    response_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-web-search"}},
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": "ws-pycodex-e2e",
                "type": "web_search_call",
                "status": "in_progress",
            },
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": "ws-pycodex-e2e",
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "type": "search",
                    "query": query,
                    "queries": [query],
                },
            },
        },
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "item": {
                "id": "msg-web-search-final",
                "type": "message",
                "role": "assistant",
                "content": [],
            },
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-web-search-final",
            "output_index": 1,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "output_index": 1,
            "item": {
                "id": "msg-web-search-final",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-web-search",
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

    def run_pair_member(command_spec: TuiComparisonCommand, label: str) -> tuple[object, tuple[dict[str, object], ...]]:
        with _SseFixtureServer(response_body) as server:
            config = (
                'model = "gpt-5.5"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'web_search = "live"\n'
                'suppress_unstable_features_warning = true\n\n'
                '[features]\napps = false\nplugins = false\n\n'
                '[model_providers.pycodex_mock]\n'
                'name = "Mock provider for hosted web-search test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                'requires_openai_auth = false\n'
                'request_max_retries = 0\n'
                'stream_max_retries = 0\n'
                'supports_websockets = false\n\n'
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "use hosted web search",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="hosted web search",
                            ready_timeout=10.0,
                        ),
                        ConptyInputStep(
                            "",
                            ready_pattern=(
                                f"{re.escape(final_answer)}|"
                                r"replay target does not implement on_web_search_begin\(\)"
                            ),
                            ready_timeout=40.0,
                            ready_quiet_period=0.3,
                            capture_name="web-search-complete-or-error",
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2),
                    ),
                    env=env,
                    timeout=50,
                    size=TerminalSize(rows=32, cols=130),
                )
            requests = tuple(json.loads(body) for body in server.request_bodies)
        transcript.write_artifacts(tmp_path, prefix=f"{label}-web-search", rows=32, cols=130)
        return transcript, requests

    rust_command, python_command = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    results = {
        "rust": run_pair_member(rust_command, "rust"),
        "python": run_pair_member(python_command, "python"),
    }

    for label, (transcript, requests) in results.items():
        assert len(requests) == 1, f"{label}: requests={requests!r}"
        assert any(
            isinstance(tool, dict) and str(tool.get("type", "")).startswith("web_search")
            for tool in requests[0].get("tools", [])
        ), f"{label}: hosted web-search tool missing from model request"
        screen = transcript.checkpoint_screen(
            "web-search-complete-or-error",
            rows=32,
            cols=130,
        )
        assert f"Searched {query}" in screen, f"{label}: {screen}"
        assert final_answer in screen, f"{label}: {screen}"
        assert "Conversation interrupted" not in screen, f"{label}: {screen}"
        assert "replay target does not implement on_web_search_begin()" not in screen, (
            f"{label}: {screen}"
        )


def test_windows_conpty_native_and_python_hosted_image_generation_lifecycle(
    tmp_path: Path,
) -> None:
    """Compare Rust/Python image generation completion and artifact UI.

    Rust owners:
    - ``codex-core::stream_events_utils`` saves completed hosted image output
      and emits the ImageGeneration item lifecycle;
    - ``codex-tui::chatwidget::replay`` routes the completed item to
      ``on_image_generation_end``;
    - ``codex-tui::chatwidget::tool_lifecycle`` commits the generated-image
      history cell and saved artifact path.
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
        pytest.skip("Windows ConPTY smoke only runs on Windows")

    capability = interactive_tui_comparison_capability()
    if not capability.available:
        pytest.skip(capability.reason)

    native_exe = native_codex_exe_from_env()
    if not native_exe.exists():
        pytest.skip(f"native codex executable not found: {native_exe}")

    repo_root = _repo_root()
    revised_prompt = "A deterministic tiny orange cat icon"
    tiny_png_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    image_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-image-generation"}},
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": "ig-pycodex-e2e",
                "type": "image_generation_call",
                "status": "completed",
                "revised_prompt": revised_prompt,
                "result": tiny_png_base64,
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-image-generation",
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

    def run_pair_member(
        command_spec: TuiComparisonCommand,
        label: str,
    ) -> tuple[object, tuple[dict[str, object], ...]]:
        with _SseFixtureServer(image_body) as server:
            config = (
                'model = "gpt-5.5"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                '[features]\n'
                'image_generation = true\n'
                'apps = false\n'
                'plugins = false\n\n'
                '[model_providers.pycodex_mock]\n'
                'name = "Mock provider for hosted image-generation test"\n'
                f'base_url = "{server.base_url}"\n'
                'wire_api = "responses"\n'
                'requires_openai_auth = false\n'
                'request_max_retries = 0\n'
                'stream_max_retries = 0\n'
                'supports_websockets = false\n\n'
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "generate a deterministic cat image",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="deterministic cat image",
                            ready_timeout=10.0,
                        ),
                        ConptyInputStep(
                            "",
                            ready_pattern=(
                                r"Generated Image:|"
                                r"replay target does not implement "
                                r"on_image_generation_(?:begin|end)\(\)"
                            ),
                            ready_timeout=40.0,
                            ready_quiet_period=0.3,
                            capture_name="image-generation-complete-or-error",
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2),
                    ),
                    env=env,
                    timeout=50,
                    size=TerminalSize(rows=32, cols=130),
                )
            requests = tuple(json.loads(body) for body in server.request_bodies)
        transcript.write_artifacts(
            tmp_path,
            prefix=f"{label}-image-generation",
            rows=32,
            cols=130,
        )
        return transcript, requests

    rust_command, python_command = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=("--disable", "apps", "--disable", "plugins"),
    )
    results = {
        "rust": run_pair_member(rust_command, "rust"),
        "python": run_pair_member(python_command, "python"),
    }

    for label, (transcript, requests) in results.items():
        assert requests, f"{label}: no model request received"
        screen = transcript.checkpoint_screen(
            "image-generation-complete-or-error",
            rows=32,
            cols=130,
        )
        assert "Generated Image:" in screen, f"{label}: {screen}"
        assert revised_prompt in screen, f"{label}: {screen}"
        assert "Saved to:" in screen, f"{label}: {screen}"
        assert len(requests) == 1, f"{label}: requests={requests!r}"
        assert "Conversation interrupted" not in screen, f"{label}: {screen}"
        assert "replay target does not implement on_image_generation_" not in screen, (
            f"{label}: {screen}"
        )


def test_windows_conpty_native_and_python_local_sse_exec_command_output_when_enabled(tmp_path: Path) -> None:
    # Rust source/test contract:
    # - codex-core maps Responses function_call items into turn tool execution.
    # - codex-core::exec::exec_windows_sandbox selects Windows sandbox capture.
    # - codex-windows-sandbox::run_windows_sandbox_capture_with_filesystem_overrides
    #   owns restricted-token process execution and filesystem policy.
    # - codex-tui::chatwidget::command_lifecycle projects command lifecycle
    #   events into exec_cell display items.
    # - codex-tui::exec_cell::render uses "Running" while active, "Ran" after
    #   completion, and preserves a bounded output preview in the transcript.
    #
    # This deterministic comparison runs the same local Responses SSE fixture
    # through native Rust Codex and Python PyCodex, proving the product path:
    # model tool call -> core exec -> TUI command display -> final answer.
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
    command = "echo PYCODEX_EXEC_NATIVE"
    final_answer = "PYCODEX_EXEC_DONE"
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

    def run_pair_member(command_spec: TuiComparisonCommand, prompt_marker: str) -> object:
        # Delay both model responses so the active-turn status must remain
        # visible before and after command execution.
        with _SseFixtureServer((tool_body, final_body), response_delay_seconds=1.2) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
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
                f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
                'trust_level = "trusted"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(config)
            if command_spec.kind == "python":
                env["PYCODEX_TUI_TIMING_LOG"] = str(tmp_path / "python.timing.jsonl")
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "run deterministic exec tool",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="exec tool",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(
                                "Working",
                                "esc to interrupt",
                            ),
                            ready_timeout=20.0,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(
                                "Ran",
                                "PYCODEX_EXEC_NATIVE",
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
            return transcript

    extra_args = (
        "--enable",
        "unified_exec",
        "--disable",
        "apps",
        "--disable",
        "plugins",
    )
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe, extra_args=extra_args)
    rust_transcript = run_pair_member(rust, "mock-model default")
    python_transcript = run_pair_member(python, "mock-model")
    rust_transcript.write_artifacts(tmp_path, prefix="rust", rows=32, cols=120)
    python_transcript.write_artifacts(tmp_path, prefix="python", rows=32, cols=120)

    readiness_failures: list[str] = []
    for label, transcript, prompt_marker in (
        ("rust", rust_transcript, "mock-model default"),
        ("python", python_transcript, "mock-model"),
    ):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        # Rust ratatui may redraw the retained screen again while /quit exits,
        # so completed rows and the final answer are asserted against the
        # ordered semantic checkpoint observed before shutdown.
        running_expected = (
            "Working",
            "esc to interrupt",
        )
        completed_expected = (
            "Ran",
            "PYCODEX_EXEC_NATIVE",
            final_answer,
            prompt_marker,
        )
        if (
            running_expected not in transcript.observed_ready_sequences
            or completed_expected not in transcript.observed_ready_sequences
        ):
            readiness_failures.append(
                f"{label}: expected_running={running_expected!r}; "
                f"expected_completed={completed_expected!r}; "
                f"observed={transcript.observed_ready_sequences!r}; "
                f"stderr={transcript.stderr!r}; "
                f"screen={transcript.screen_stdout(rows=32, cols=120)!r}; "
                f"normalized={output!r}; artifacts={str(tmp_path)!r}"
            )
    assert not readiness_failures, "\n".join(readiness_failures)


def test_windows_conpty_native_and_python_local_sse_parallel_exec_commands_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-core tool executors can advertise supports_parallel_tool_calls.
    # - codex-core preserves grouped function_call items before their matching
    #   tool outputs in the follow-up model request.
    # - codex-tui::chatwidget::command_lifecycle keeps multiple in-flight
    #   command rows visible until command completion, then exec_cell renders
    #   them as completed `Ran` rows with bounded output previews.
    #
    # This native comparison feeds two exec_command calls in the same Responses
    # turn to source-built Rust Codex and Python PyCodex. It proves the product
    # shell can surface more than one tool result before the final answer.
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
    command_a = "echo PYCODEX_PARALLEL_A"
    command_b = "echo PYCODEX_PARALLEL_B"
    final_answer = "PYCODEX_PARALLEL_DONE"

    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-parallel-tools"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-pycodex-parallel-a",
                "type": "function_call",
                "call_id": "call-pycodex-parallel-a",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": command_a}, separators=(",", ":")),
            },
        },
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-pycodex-parallel-b",
                "type": "function_call",
                "call_id": "call-pycodex-parallel-b",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": command_b}, separators=(",", ":")),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-parallel-tools",
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
    final_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-local-parallel-final"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-parallel-final",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-local-parallel-final",
            "output_index": 0,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-local-parallel-final",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-local-parallel-final",
                "usage": {
                    "input_tokens": 3,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 5,
                },
            },
        },
    )

    def run_pair_member(command_spec: TuiComparisonCommand, prompt_marker: str) -> object:
        with _SseFixtureServer((tool_body, final_body)) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "never"\n'
                'sandbox_mode = "read-only"\n'
                "experimental_use_unified_exec_tool = true\n"
                'suppress_unstable_features_warning = true\n'
                "\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for local parallel exec-command test"\n'
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
                    command_spec,
                    input_steps=(
                        ConptyInputStep(
                            "run deterministic parallel exec tools",
                            ready_pattern=READY_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="parallel exec tools",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                            chunk_delay=0.01,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(
                                "Ran",
                                "PYCODEX_PARALLEL_A",
                                "PYCODEX_PARALLEL_B",
                                final_answer,
                                prompt_marker,
                            ),
                            ready_timeout=45.0,
                        ),
                        ConptyInputStep(
                            "/quit\r",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                    ),
                    env=env,
                    timeout=55,
                    size=TerminalSize(rows=34, cols=120),
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
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert final_answer in output


def test_windows_conpty_native_and_python_live_complex_tool_prompt_when_enabled() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer submits the non-empty prompt as
    #   one AppCommand::UserTurn.
    # - codex-core::session::turn maps streamed model deltas and tool calls
    #   into ServerNotification events for the active thread.
    # - codex-tui::chatwidget::command_lifecycle and
    #   codex-tui::exec_cell::render surface live tool progress as
    #   Running/Ran/Called rows while chatwidget::streaming commits the final
    #   assistant answer once.
    #
    # This opt-in live comparison is intentionally not a default CI test.  It
    # exercises the real OAuth/service path for the user-facing complex-session
    # case that deterministic local SSE fixtures cannot prove: a repository
    # inspection prompt that should trigger at least one read-only tool call and
    # eventually render a final marker in both source-built Rust Codex and
    # Python PyCodex.
    if os.environ.get(RUN_NATIVE_COMPARISON_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_COMPARISON_ENV}=1 to run native ConPTY comparison")
    if os.environ.get(RUN_NATIVE_LIVE_PROMPT_ENV) != "1":
        pytest.skip(f"set {RUN_NATIVE_LIVE_PROMPT_ENV}=1 to run live OAuth prompt comparison")
    if os.environ.get(RUN_NATIVE_COMPLEX_LIVE_PROMPT_ENV) != "1":
        pytest.skip(
            f"set {RUN_NATIVE_COMPLEX_LIVE_PROMPT_ENV}=1 to run complex live OAuth prompt comparison"
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
    rust, python = build_rust_python_inline_pair(repo_root=repo_root, native_exe=native_exe)
    marker = "PYCODEX_COMPLEX_OK"
    prompt = (
        "Inspect this repository using at least one read-only shell command if tools are available. "
        "Give exactly three concise bullets about the project, then end with a separate final line "
        "containing only the three parts PYCODEX COMPLEX OK joined by underscores."
    )
    input_steps = (
        ConptyInputStep(
            prompt,
            ready_pattern=READY_COMPOSER_PATTERN,
            ready_timeout=30.0,
            chunk_delay=0.02,
            ready_quiet_period=0.8,
        ),
        ConptyInputStep(
            "\r",
            ready_text="joined by underscores.",
            ready_timeout=10.0,
            chunk_delay=0.02,
        ),
        ConptyInputStep(
            "",
            ready_text=marker,
            ready_timeout=260.0,
            chunk_delay=0.02,
        ),
    )

    rust_transcript = _run_live_conpty_with_capacity_retries(
        lambda: run_windows_conpty_tui_command(
            rust,
            input_steps=input_steps,
            env=_conpty_tui_env(),
            timeout=10,
            size=TerminalSize(rows=36, cols=140),
            stop_pattern=marker,
            stop_timeout=5,
            terminate_on_stop_pattern=True,
        )
    )
    python_env = _conpty_tui_env()
    with tempfile.TemporaryDirectory(prefix="pycodex-reasoning-trace-") as trace_dir:
        trace_path = Path(trace_dir) / "reasoning.jsonl"
        python_env["PYCODEX_TUI_REASONING_TRACE"] = str(trace_path)
        python_transcript = _run_live_conpty_with_capacity_retries(
            lambda: run_windows_conpty_tui_command(
                python,
                input_steps=input_steps,
                env=python_env,
                timeout=10,
                size=TerminalSize(rows=36, cols=140),
                stop_pattern=marker,
                stop_timeout=5,
                terminate_on_stop_pattern=True,
            )
        )
        reasoning_trace = _read_jsonl_records(trace_path)

    for transcript in (rust_transcript, python_transcript):
        output = transcript.normalized_stdout()
        assert "OpenAI Codex" in output
        assert "Inspect this repository" in output
        assert marker in output
        assert re.search(r"\b(Running|Ran|Called)\b", output), output
        assert "ConPTY command terminated after stop pattern" in transcript.normalized_stderr()

    raw_displayed = [
        record
        for record in reasoning_trace
        if record.get("source") == "raw_delta" and record.get("displayed") is True
    ]
    assert raw_displayed == []
    summary_sources = {
        str(record.get("source"))
        for record in reasoning_trace
        if record.get("displayed") is True
    }
    assert summary_sources <= {"summary_delta", "completed_reasoning"}


def test_windows_conpty_native_and_python_first_request_context_and_tools_match_when_enabled(
    tmp_path: Path,
) -> None:
    """Compare the real first-turn model context at the product PTY boundary.

    Rust owners: codex-tui::app selects SessionSource::Cli and codex-core's
    Session::built_tools plus request assembly produce the Responses body.
    Python must reach the corresponding modules rather than a TUI-local tool
    list or Goal-specific prompt path.
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
    prompt = "DYNAMIC_CONTEXT_TOOL_PARITY"
    answer = "DYNAMIC_CONTEXT_TOOL_PARITY_DONE"
    response = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-context-parity"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-context-parity",
                "content": [{"type": "output_text", "text": answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-context-parity",
                "usage": {
                    "input_tokens": 5,
                    "input_tokens_details": None,
                    "output_tokens": 2,
                    "output_tokens_details": None,
                    "total_tokens": 7,
                },
            },
        },
    )

    extra_args = (
        "--enable",
        "goals",
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

    def run_member(command: TuiComparisonCommand, label: str) -> dict[str, object]:
        with _SseFixtureServer(response) as server:
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
                'name = "Mock provider for context and tool parity"\n'
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
                                ready_pattern=READY_COMPOSER_PATTERN,
                                ready_timeout=30.0,
                                ready_quiet_period=0.2,
                                atomic_write=True,
                            ),
                        ConptyInputStep("\r", ready_text=prompt, ready_timeout=10.0),
                        ConptyInputStep("", ready_text=answer, ready_timeout=40.0, ready_quiet_period=0.3),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=50,
                    size=TerminalSize(rows=36, cols=140),
                )
            transcript.write_artifacts(tmp_path, prefix=f"{label}-request-context", rows=36, cols=140)
            assert server.request_bodies, (
                f"{label} emitted no Responses request; output={transcript.normalized_combined()!r}"
            )
            request = json.loads(server.request_bodies[0].decode("utf-8"))
            (tmp_path / f"{label}-request-context.json").write_text(
                json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return request

    rust_request = run_member(rust, "rust")
    python_request = run_member(python, "python")
    rust_context = _normalized_first_turn_request_context(rust_request)
    python_context = _normalized_first_turn_request_context(python_request)

    assert python_context == rust_context
