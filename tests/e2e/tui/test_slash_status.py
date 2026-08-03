"""End-to-end coverage for the ``/status`` slash command."""

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


def test_status_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch inserts the immediate status history cell.
    # - status::card owns visible model, directory, permissions, session, and
    #   optional rate-limit fields.
    route = terminal_slash_command_routes()[SlashCommand.STATUS]

    assert SlashCommand.STATUS.command() == "status"
    assert SlashCommand.STATUS.supports_inline_args() is False
    assert SlashCommand.STATUS.available_during_task() is True
    assert SlashCommand.STATUS.available_in_side_conversation() is True
    assert route.category == "local"
    assert route.outcome == "effect"
    assert route.argument_form == "bare"


def test_windows_conpty_native_and_python_status_card_is_local(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/status",
            stop_pattern="Session:",
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "/status" in output
        assert "OpenAI Codex" in output
        assert "Model:" in output
        assert "Directory:" in output
        assert "Permissions:" in output
        assert "Read Only (never)" in output
        assert "Session:" in output
        assert "Traceback" not in output
