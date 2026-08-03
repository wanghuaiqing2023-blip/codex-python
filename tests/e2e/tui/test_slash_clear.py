"""End-to-end coverage for the ``/clear`` slash command."""

from __future__ import annotations

from pycodex.tui.chatwidget.slash_dispatch import (
    plan_terminal_local_command,
    terminal_slash_command_routes,
)
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import (
    SESSION_CONFIGURED_COMPOSER_PATTERN,
    ConptyInputStep,
    TerminalSize,
    TuiComparisonCommand,
    _isolated_codex_home_env_with_config,
    _repo_root,
    _responses_sse,
    _SseFixtureServer,
    run_windows_conpty_tui_command,
)
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    slash_candidate_pair,
)

import pytest

pytestmark = pytest.mark.e2e


def test_clear_slash_command_uses_local_clear_effect() -> None:
    # Rust: chatwidget::slash_dispatch maps SlashCommand::Clear to
    # AppEvent::ClearUi while idle.
    route = terminal_slash_command_routes()[SlashCommand.CLEAR]

    assert route.outcome == "effect"
    assert plan_terminal_local_command("/clear").action == "clear"


def test_windows_conpty_native_and_python_clear_slash_transcript_screen_when_enabled() -> None:
    # Rust source/test contract:
    # - chatwidget/tests/slash_commands.rs::slash_clear_requests_ui_clear_when_idle
    #   proves the chatwidget dispatch boundary.
    # - codex-tui::app::history_ui::clear_terminal_ui owns the fresh header
    #   replay and stale transcript/status removal after /clear.
    #
    # Create a deterministic assistant transcript through local Responses SSE,
    # submit /clear through the real composer, and verify the current screen no
    # longer contains the previous answer.
    native_exe = require_native_slash_comparison()
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

    rust, python = slash_candidate_pair(native_exe)
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
