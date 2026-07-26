"""Tui Test Approvals scenarios extracted from the native comparison suite."""

from tests.e2e.tui._common import *  # noqa: F401,F403

pytestmark = pytest.mark.e2e


def test_windows_conpty_native_and_python_exec_approval_roundtrip_when_enabled(tmp_path: Path) -> None:
    """Compare the fixed-Rust and Python interactive approval product path.

    Fixed Rust commit 1c7832f owners:
    ``core::session::request_command_approval`` ->
    ``tui::chatwidget::approval_requests`` ->
    ``bottom_pane::approval_overlay`` -> ``Op::ExecApproval``.
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
    # Fixed-Rust ``unified exec on request escalated requires approval`` uses
    # read-only plus an explicitly escalated Python command. Use the Windows
    # executable spelling while preserving that exact policy shape.
    command = 'python -c "print(\'PYCODEX_APPROVAL_EXECUTED\')"'
    final_answer = "PYCODEX_APPROVAL_DONE"
    approval_title = "Would you like to run the following command?"
    approval_option = "Yes, proceed"
    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-approval-tool"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-pycodex-approval",
                "type": "function_call",
                "call_id": "call-pycodex-approval",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": command,
                        "sandbox_permissions": "require_escalated",
                        "justification": "deterministic approval parity fixture",
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-approval-tool",
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
        {"type": "response.created", "response": {"id": "resp-approval-final"}},
        {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-approval-final",
                "content": [],
            },
            "output_index": 0,
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg-approval-final",
            "output_index": 0,
            "content_index": 0,
            "delta": final_answer,
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-approval-final",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-approval-final",
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

    def run_pair_member(command_spec: TuiComparisonCommand, prompt_marker: str, prefix: str) -> TuiProcessTranscript:
        with _SseFixtureServer((tool_body, final_body)) as server:
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
                'name = "Mock provider for approval comparison"\n'
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
                            "run deterministic approval tool",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="approval tool",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "y",
                            ready_text_sequence=(approval_title, approval_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=("Ran", "PYCODEX_APPROVAL_EXECUTED", final_answer, prompt_marker),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=55,
                    size=TerminalSize(rows=36, cols=120),
                )
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}\n"
                f"normalized={transcript.normalized_stdout()}\n"
                f"stderr={transcript.normalized_stderr()}"
            )
            transcript.write_artifacts(tmp_path, prefix=prefix, rows=36, cols=120)
            return transcript

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
    rust_transcript = run_pair_member(rust, "mock-model default", "rust-approval")
    python_transcript = run_pair_member(python, "mock-model", "python-approval")

    failures: list[str] = []
    for label, transcript, prompt_marker in (
        ("rust", rust_transcript, "mock-model default"),
        ("python", python_transcript, "mock-model"),
    ):
        expected_approval = (approval_title, approval_option)
        expected_completion = ("Ran", "PYCODEX_APPROVAL_EXECUTED", final_answer, prompt_marker)
        if expected_approval not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing approval checkpoint: {transcript.observed_ready_sequences!r}")
        if expected_completion not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing completion checkpoint: {transcript.observed_ready_sequences!r}")
        normalized = transcript.normalized_stdout()
        if approval_title not in normalized or final_answer not in normalized:
            failures.append(f"{label} normalized transcript incomplete: {normalized!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_exec_approval_cancel_resize_and_recovery_when_enabled(
    tmp_path: Path,
) -> None:
    """Exercise cancel, modal resize, title cleanup, and next-turn IME recovery.

    Fixed Rust commit 1c7832f owners:
    ``bottom_pane::approval_overlay::exec_options`` maps Esc to
    ``CommandExecutionApprovalDecision::Cancel``; ``chatwidget`` owns the
    action-required title lifecycle; ``custom_terminal`` and
    ``app::resize_reflow`` preserve the active modal across resize.
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
    chinese_answer = "PYCODEX_CHINESE_RECOVERED"
    approval_title = "Would you like to run the following command?"
    cancel_option = "No, and tell Codex what to do differently"

    def final_body(response_id: str, message_id: str, text: str) -> bytes:
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
        prefix: str,
    ) -> TuiProcessTranscript:
        side_effect_path = tmp_path / f"{prefix}-cancelled-command.txt"
        side_effect_path.unlink(missing_ok=True)
        command = (
            'python -c "from pathlib import Path; '
            f"Path(r'{side_effect_path}').write_text('ran', encoding='utf-8')\""
        )
        tool_body = _responses_sse(
            {"type": "response.created", "response": {"id": "resp-cancel-tool"}},
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "fc-pycodex-cancel",
                    "type": "function_call",
                    "call_id": "call-pycodex-cancel",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {
                            "cmd": command,
                            "sandbox_permissions": "require_escalated",
                            "justification": "deterministic cancel and resize parity fixture",
                        },
                        separators=(",", ":"),
                    ),
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp-cancel-tool",
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
        with _SseFixtureServer(
            (
                tool_body,
                final_body("resp-chinese-final", "msg-chinese-final", chinese_answer),
            )
        ) as server:
            config = (
                'model = "mock-model"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "unified_exec = true\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for cancel and resize comparison"\n'
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
                            "run deterministic cancelled approval tool",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            resize=TerminalSize(rows=22, cols=80),
                            ready_text="cancelled approval tool",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            resize=TerminalSize(rows=36, cols=120),
                            ready_text_sequence=(approval_title, cancel_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "\x1b",
                            ready_text_sequence=(approval_title, cancel_option),
                            ready_timeout=20.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=("Conversation interrupted", prompt_marker),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep(
                            "你好",
                            ready_timeout=0.2,
                            chunk_delay=0.05,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="你好",
                            ready_timeout=10.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(chinese_answer, prompt_marker),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=65,
                    size=TerminalSize(rows=36, cols=120),
                )
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}; checkpoints={transcript.observed_ready_sequences!r}; "
                f"normalized={transcript.normalized_stdout()!r}; artifacts={str(tmp_path)!r}"
            )
            assert not side_effect_path.exists(), (
                f"{prefix} executed the cancelled command; normalized={transcript.normalized_stdout()!r}"
            )
            transcript.write_artifacts(tmp_path, prefix=prefix, rows=36, cols=120)
            return transcript

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
    rust_transcript = run_pair_member(rust, "mock-model default", "rust-approval-cancel-resize")
    python_transcript = run_pair_member(python, "mock-model", "python-approval-cancel-resize")

    failures: list[str] = []
    for label, transcript, prompt_marker in (
        ("rust", rust_transcript, "mock-model default"),
        ("python", python_transcript, "mock-model"),
    ):
        expected_modal = (approval_title, cancel_option)
        expected_cancel = ("Conversation interrupted", prompt_marker)
        expected_chinese = (chinese_answer, prompt_marker)
        observed = transcript.observed_ready_sequences
        if observed.count(expected_modal) != 2:
            failures.append(f"{label} did not preserve the modal across both resize checkpoints: {observed!r}")
        if expected_cancel not in observed or expected_chinese not in observed:
            failures.append(f"{label} did not recover both post-cancel turns: {observed!r}")
        normalized = transcript.normalized_stdout()
        if "canceled the request to run" not in normalized:
            failures.append(f"{label} missing typed cancel history: {normalized!r}")
        if "你好" not in normalized or chinese_answer not in normalized:
            failures.append(f"{label} lost post-modal Chinese input or response: {normalized!r}")
        titles = re.findall(r"\x1b\]0;([^\x07]*)\x07", transcript.stdout)
        action_index = next((index for index, title in enumerate(titles) if "Action Required" in title), None)
        if action_index is None or not any("Action Required" not in title for title in titles[action_index + 1 :]):
            failures.append(f"{label} did not restore the terminal title after cancellation: {titles!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_patch_approval_roundtrip_when_enabled(tmp_path: Path) -> None:
    """Compare fixed-Rust and Python apply-patch approval product paths.

    Fixed Rust commit 1c7832f owners:
    ``core::tools::runtimes::apply_patch`` ->
    ``tui::chatwidget::approval_requests`` ->
    ``bottom_pane::approval_overlay`` -> ``Op::PatchApproval``.
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
    final_answer = "PYCODEX_PATCH_APPROVAL_DONE"
    approval_title = "Would you like to make the following edits?"
    approval_option = "Yes, proceed"

    def run_pair_member(command_spec: TuiComparisonCommand, prompt_marker: str, prefix: str) -> TuiProcessTranscript:
        relative_path = Path(".tmp") / f"conpty-{prefix}-patch-approval.txt"
        target = repo_root / relative_path
        target.unlink(missing_ok=True)
        patch_text = (
            "*** Begin Patch\n"
            f"*** Add File: {relative_path.as_posix()}\n"
            f"+created by {prefix} approval fixture\n"
            "*** End Patch\n"
        )
        tool_body = _responses_sse(
            {"type": "response.created", "response": {"id": f"resp-{prefix}-patch-tool"}},
            {
                "type": "response.output_item.added",
                "item": {
                    "id": f"ctc-{prefix}-patch",
                    "type": "custom_tool_call",
                    "call_id": f"call-{prefix}-patch",
                    "name": "apply_patch",
                    "input": "",
                },
                "output_index": 0,
            },
            {
                "type": "response.custom_tool_call_input.delta",
                "item_id": f"ctc-{prefix}-patch",
                "call_id": f"call-{prefix}-patch",
                "output_index": 0,
                "delta": patch_text,
            },
            {
                "type": "response.output_item.done",
                "item": {
                    "id": f"ctc-{prefix}-patch",
                    "type": "custom_tool_call",
                    "call_id": f"call-{prefix}-patch",
                    "name": "apply_patch",
                    "input": patch_text,
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": f"resp-{prefix}-patch-tool",
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
            {"type": "response.created", "response": {"id": f"resp-{prefix}-patch-final"}},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": f"msg-{prefix}-patch-final",
                    "content": [{"type": "output_text", "text": final_answer}],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": f"resp-{prefix}-patch-final",
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
        try:
            with _SseFixtureServer((tool_body, final_body)) as server:
                config = (
                    'model = "gpt-5.4"\n'
                    'model_provider = "pycodex_mock"\n'
                    'approval_policy = "on-request"\n'
                    'sandbox_mode = "read-only"\n'
                    'suppress_unstable_features_warning = true\n\n'
                    "[model_providers.pycodex_mock]\n"
                    'name = "Mock provider for patch approval comparison"\n'
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
                                "apply deterministic patch",
                                ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                                ready_timeout=30.0,
                                ready_quiet_period=0.2,
                                atomic_write=True,
                            ),
                            ConptyInputStep("\r", ready_text="deterministic patch", ready_timeout=10.0),
                            ConptyInputStep(
                                "y",
                                ready_text_sequence=(approval_title, approval_option),
                                ready_timeout=40.0,
                                ready_quiet_period=0.1,
                            ),
                            ConptyInputStep(
                                "",
                                ready_text_sequence=(final_answer, prompt_marker),
                                ready_timeout=40.0,
                            ),
                            ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                        ),
                        env=env,
                        timeout=55,
                        size=TerminalSize(rows=36, cols=120),
                    )
                transcript.write_artifacts(tmp_path, prefix=f"{prefix}-patch-approval", rows=36, cols=120)
                assert len(server.requests) >= 2, transcript.normalized_stdout()
                assert target.exists(), (
                    f"{prefix} did not apply approved patch; "
                    f"checkpoints={transcript.observed_ready_sequences!r}; "
                    f"normalized={transcript.normalized_stdout()!r}; artifacts={str(tmp_path)!r}"
                )
                assert target.read_text(encoding="utf-8").strip() == f"created by {prefix} approval fixture"
                return transcript
        finally:
            target.unlink(missing_ok=True)

    extra_args = ("--disable", "apps", "--disable", "plugins")
    rust, python = build_rust_python_inline_pair(
        repo_root=repo_root,
        native_exe=native_exe,
        extra_args=extra_args,
        sandbox_mode="read-only",
        approval_policy="on-request",
    )
    rust_transcript = run_pair_member(rust, "gpt-5.4", "rust")
    python_transcript = run_pair_member(python, "gpt-5.4", "python")

    failures: list[str] = []
    for label, transcript, prompt_marker in (
        ("rust", rust_transcript, "gpt-5.4"),
        ("python", python_transcript, "gpt-5.4"),
    ):
        expected_approval = (approval_title, approval_option)
        expected_completion = (final_answer, prompt_marker)
        if expected_approval not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing patch approval checkpoint: {transcript.observed_ready_sequences!r}")
        if expected_completion not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing patch completion checkpoint: {transcript.observed_ready_sequences!r}")
        normalized = transcript.normalized_stdout()
        if "Added" not in normalized or f"conpty-{label}-patch-approval.txt" not in normalized:
            failures.append(f"{label} missing typed patch history: {normalized!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_permissions_approval_roundtrip_when_enabled(tmp_path: Path) -> None:
    """Compare fixed-Rust and Python request-permissions approval paths.

    Fixed Rust commit 1c7832f owners:
    ``core::session::request_permissions`` ->
    ``tui::chatwidget::protocol_requests`` ->
    ``bottom_pane::approval_overlay`` -> ``Op::RequestPermissionsResponse``.
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
    final_answer = "PYCODEX_PERMISSIONS_APPROVAL_DONE"
    approval_title = "Would you like to grant these permissions?"
    approval_option = "Yes, grant these permissions for this turn"
    tool_body = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-permissions-tool"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-pycodex-permissions",
                "type": "function_call",
                "call_id": "call-pycodex-permissions",
                "name": "request_permissions",
                "arguments": json.dumps(
                    {
                        "reason": "deterministic network permission fixture",
                        "permissions": {"network": {"enabled": True}},
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-permissions-tool",
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
        {"type": "response.created", "response": {"id": "resp-permissions-final"}},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg-permissions-final",
                "content": [{"type": "output_text", "text": final_answer}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-permissions-final",
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

    def run_pair_member(command_spec: TuiComparisonCommand, prefix: str) -> TuiProcessTranscript:
        with _SseFixtureServer((tool_body, final_body)) as server:
            config = (
                'model = "gpt-5.4"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "request_permissions_tool = true\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for permissions approval comparison"\n'
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
                            "request deterministic permissions",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_text="deterministic permissions", ready_timeout=10.0),
                        ConptyInputStep(
                            "y",
                            ready_text_sequence=(approval_title, approval_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text_sequence=(final_answer, "gpt-5.4"),
                            ready_timeout=40.0,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=55,
                    size=TerminalSize(rows=36, cols=120),
                )
            transcript.write_artifacts(tmp_path, prefix=f"{prefix}-permissions-approval", rows=36, cols=120)
            assert len(server.requests) >= 2, (
                f"requests={server.requests!r}; checkpoints={transcript.observed_ready_sequences!r}; "
                f"normalized={transcript.normalized_stdout()!r}; artifacts={str(tmp_path)!r}"
            )
            return transcript

    extra_args = (
        "--enable",
        "request_permissions_tool",
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
    rust_transcript = run_pair_member(rust, "rust")
    python_transcript = run_pair_member(python, "python")

    failures: list[str] = []
    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        if (approval_title, approval_option) not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing permissions approval checkpoint: {transcript.observed_ready_sequences!r}")
        if (final_answer, "gpt-5.4") not in transcript.observed_ready_sequences:
            failures.append(f"{label} missing permissions completion checkpoint: {transcript.observed_ready_sequences!r}")
        normalized = transcript.normalized_stdout()
        if "You granted additional permissions" not in normalized:
            failures.append(f"{label} missing permissions audit history: {normalized!r}")
    assert not failures, "\n".join(failures)


def test_windows_conpty_native_and_python_permissions_session_grant_reused_next_turn_when_enabled(
    tmp_path: Path,
) -> None:
    """Prove a session-scoped permission grant reaches a later turn's tool plan.

    Fixed Rust commit 1c7832f owners:
    ``core::session::record_granted_request_permissions_for_turn`` records a
    session grant in ``SessionState``; ``tools::handlers::apply_granted_turn_permissions``
    marks an identical later permission profile preapproved. The second turn
    must therefore execute without opening another approval overlay.
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
    first_answer = "PYCODEX_SESSION_PERMISSION_GRANTED"
    command_output = "PYCODEX_SESSION_PERMISSION_REUSED"
    second_answer = "PYCODEX_SESSION_PERMISSION_SECOND_TURN_DONE"
    approval_title = "Would you like to grant these permissions?"
    session_option = "Yes, grant these permissions for this session"
    different_approval_title = "Would you like to run the following command?"
    different_side_effect = repo_root / ".tmp" / "permission-profile-different.txt"

    def completed_message(response_id: str, message_id: str, text: str) -> bytes:
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
                        "input_tokens": 2,
                        "input_tokens_details": None,
                        "output_tokens": 2,
                        "output_tokens_details": None,
                        "total_tokens": 4,
                    },
                },
            },
        )

    permissions_tool = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-session-permissions-tool"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-session-permissions",
                "type": "function_call",
                "call_id": "call-session-permissions",
                "name": "request_permissions",
                "arguments": json.dumps(
                    {
                        "reason": "reuse deterministic network permission in the next turn",
                        "permissions": {"network": {"enabled": True}},
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-session-permissions-tool",
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
    exec_tool = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-session-permissions-exec"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-session-permissions-exec",
                "type": "function_call",
                "call_id": "call-session-permissions-exec",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": f"echo {command_output}",
                        "sandbox_permissions": "use_default",
                        "additional_permissions": {"network": {"enabled": True}},
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-session-permissions-exec",
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
    different_exec_tool = _responses_sse(
        {"type": "response.created", "response": {"id": "resp-session-permissions-different-exec"}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "fc-session-permissions-different-exec",
                "type": "function_call",
                "call_id": "call-session-permissions-different-exec",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": (
                            "Set-Content -LiteralPath "
                            f"'{different_side_effect}' -Value 'PYCODEX_DIFFERENT_PERMISSION_EXECUTED'"
                        ),
                        "sandbox_permissions": "with_additional_permissions",
                        "additional_permissions": {
                            "file_system": {"write": [str(different_side_effect.parent)]}
                        },
                    },
                    separators=(",", ":"),
                ),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-session-permissions-different-exec",
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

    def run_pair_member(command_spec: TuiComparisonCommand, prefix: str) -> TuiProcessTranscript:
        bodies = (
            permissions_tool,
            completed_message("resp-session-permissions-first-final", "msg-session-permissions-first", first_answer),
            exec_tool,
            completed_message("resp-session-permissions-second-final", "msg-session-permissions-second", second_answer),
            different_exec_tool,
        )
        with _SseFixtureServer(bodies) as server:
            config = (
                'model = "gpt-5.4"\n'
                'model_provider = "pycodex_mock"\n'
                'approval_policy = "on-request"\n'
                'sandbox_mode = "read-only"\n'
                'suppress_unstable_features_warning = true\n\n'
                "[features]\n"
                "exec_permission_approvals = true\n"
                "request_permissions_tool = true\n"
                "unified_exec = true\n\n"
                "[model_providers.pycodex_mock]\n"
                'name = "Mock provider for session permission reuse comparison"\n'
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
                            "grant deterministic network permission for this session",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=30.0,
                            ready_quiet_period=0.2,
                            atomic_write=True,
                        ),
                        ConptyInputStep("\r", ready_text="network permission", ready_timeout=10.0),
                        ConptyInputStep(
                            "a",
                            ready_text_sequence=(approval_title, session_option),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_pattern=(
                                rf"(?ms){re.escape(first_answer)}.*?"
                                r"(?:^>\s*$|^\s*\u203a(?:\s+.+)?$)"
                            ),
                            ready_timeout=40.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep(
                            "reuse the same network permission now",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep("\r", ready_text="reuse the same network permission now", ready_timeout=10.0),
                        ConptyInputStep(
                            "",
                            ready_text=second_answer,
                            ready_timeout=45.0,
                            ready_quiet_period=0.5,
                        ),
                        ConptyInputStep(
                            "request a materially different file write permission now",
                            ready_timeout=0.2,
                            chunk_delay=0.02,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_text="request a materially different file write permission now",
                            ready_timeout=10.0,
                        ),
                        ConptyInputStep(
                            "\x1b",
                            ready_text_sequence=(different_approval_title, "Permission rule:"),
                            ready_timeout=40.0,
                            ready_quiet_period=0.1,
                        ),
                        ConptyInputStep(
                            "",
                            ready_text="Conversation interrupted",
                            ready_timeout=40.0,
                            ready_quiet_period=0.2,
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2, chunk_delay=0.02),
                    ),
                    env=env,
                    timeout=70,
                    size=TerminalSize(rows=36, cols=120),
                )
            transcript.write_artifacts(tmp_path, prefix=f"{prefix}-permissions-session-reuse", rows=36, cols=120)
            assert len(server.requests) >= 5, (
                f"requests={server.requests!r}; checkpoints={transcript.observed_ready_sequences!r}; "
                f"normalized={transcript.normalized_stdout()!r}; artifacts={str(tmp_path)!r}"
            )
            assert not different_side_effect.exists(), (
                f"{prefix} executed a materially different permission profile before approval"
            )
            first_request = json.loads(server.request_bodies[0].decode("utf-8"))
            exec_command = next(tool for tool in first_request["tools"] if tool.get("name") == "exec_command")
            exec_properties = exec_command["parameters"]["properties"]
            assert "additional_permissions" in exec_properties
            assert "with_additional_permissions" in exec_properties["sandbox_permissions"]["description"]
            return transcript

    extra_args = (
        "--enable",
        "request_permissions_tool",
        "--enable",
        "exec_permission_approvals",
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
    rust_transcript = run_pair_member(rust, "rust")
    python_transcript = run_pair_member(python, "python")

    failures: list[str] = []
    for label, transcript in (("rust", rust_transcript), ("python", python_transcript)):
        observed = transcript.observed_ready_sequences
        if observed.count((approval_title, session_option)) != 1:
            failures.append(f"{label} did not expose exactly one session grant checkpoint: {observed!r}")
        if (different_approval_title, "Permission rule:") not in observed:
            failures.append(f"{label} did not prompt for a materially different permission profile: {observed!r}")
        normalized = transcript.normalized_stdout()
        if second_answer not in normalized:
            failures.append(f"{label} did not reuse the session grant in the next turn: {normalized!r}")
        if "You granted additional permissions for this session" not in normalized:
            failures.append(f"{label} did not record the session grant decision: {normalized!r}")
    assert not failures, "\n".join(failures)
