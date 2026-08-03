"""End-to-end coverage for the ``/debug-config`` slash command."""

from __future__ import annotations

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_debug_config_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch calls add_debug_config_output.
    # - debug_config renders every config layer (including disabled layers),
    #   requirement sources, and optional session proxy state.
    route = terminal_slash_command_routes()[SlashCommand.DEBUG_CONFIG]

    assert SlashCommand.DEBUG_CONFIG.command() == "debug-config"
    assert SlashCommand.DEBUG_CONFIG.supports_inline_args() is False
    assert SlashCommand.DEBUG_CONFIG.available_during_task() is True
    assert SlashCommand.DEBUG_CONFIG.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.argument_form == "bare"


def test_windows_conpty_native_and_python_debug_config_is_local(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/debug-config",
            stop_pattern="Requirements:",
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "/debug-config" in output
        assert "Config layer stack (lowest precedence first):" in output
        assert "Requirements:" in output
        assert "product effect is not yet available" not in output
        assert "Traceback" not in output
