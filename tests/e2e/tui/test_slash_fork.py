"""End-to-end coverage for the ``/fork`` slash command."""

from __future__ import annotations

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_session_transition_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_fork_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch emits AppEvent::ForkCurrentSession.
    # - app::session_lifecycle forks the active thread, preserves its history,
    #   and installs the new thread as the active session.
    route = terminal_slash_command_routes()[SlashCommand.FORK]

    assert SlashCommand.FORK.command() == "fork"
    assert SlashCommand.FORK.supports_inline_args() is False
    assert SlashCommand.FORK.available_during_task() is False
    assert SlashCommand.FORK.available_in_side_conversation() is False
    assert route.outcome == "effect"
    assert route.argument_form == "bare"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_fork_installs_live_session(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_session_transition_slash_candidate(
            command,
            label=label,
            slash_text="/fork",
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 0, (
            f"{label} unexpectedly sent a model request\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert "/fork" in output
        assert "/status" in output
        assert "Model:" in output
        assert "Directory:" in output
        assert "Session:" in output
        assert "SESSION_SLASH_MUST_NOT_REACH_THE_MODEL" not in output
        assert "product effect is not yet available" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
        assert (
            "ConPTY command terminated after stop pattern"
            in transcript.normalized_stderr()
        )
