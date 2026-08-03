"""End-to-end coverage for the Rust-owned ``/ps`` slash command."""

from pathlib import Path

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


def test_ps_slash_command_uses_unified_exec_history_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.PS]

    assert SlashCommand.PS.supports_inline_args() is False
    assert SlashCommand.PS.available_during_task() is True
    assert SlashCommand.PS.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"


def test_windows_conpty_native_and_python_ps_empty_state_is_local(
    tmp_path: Path,
) -> None:
    # Rust chatwidget::add_ps_output always inserts the UnifiedExecProcesses
    # history cell; a fresh isolated session has the stable empty state.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/ps",
            stop_pattern="No background terminals running.",
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "Background terminals" in output
        assert "No background terminals running." in output
        assert "Traceback" not in output
