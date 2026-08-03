"""End-to-end coverage for the ``/resume`` slash command."""

from __future__ import annotations

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_view_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_resume_registry_contract() -> None:
    # Rust owners:
    # - a bare command emits AppEvent::OpenResumePicker and opens
    #   resume_picker in ExistingSession mode;
    # - inline text resolves a saved thread by id/name through session
    #   lifecycle without creating a model turn.
    route = terminal_slash_command_routes()[SlashCommand.RESUME]

    assert SlashCommand.RESUME.command() == "resume"
    assert SlashCommand.RESUME.supports_inline_args() is True
    assert SlashCommand.RESUME.available_during_task() is False
    assert SlashCommand.RESUME.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.argument_form == "inline-or-bare"
    assert route.python_owner == (
        "pycodex.tui.resume_picker + pycodex.tui.chatwidget.slash_dispatch"
    )


def test_windows_conpty_native_and_python_resume_opens_picker(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = ("Resume a previous session",)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/resume",
            view_markers=markers,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 0
        assert markers in transcript.observed_ready_sequences
        assert "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output
        assert "Select a session from the resume picker." not in output
        assert "product effect is not yet available" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
