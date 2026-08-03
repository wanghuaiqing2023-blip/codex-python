"""End-to-end coverage for the ``/rename`` slash command."""

from __future__ import annotations

import re

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
    run_view_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_rename_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::interaction opens CustomPromptView for a bare command.
    # - chatwidget::slash_dispatch normalizes inline text and emits
    #   AppCommand::SetThreadName without creating a model turn.
    route = terminal_slash_command_routes()[SlashCommand.RENAME]

    assert SlashCommand.RENAME.command() == "rename"
    assert SlashCommand.RENAME.supports_inline_args() is True
    assert SlashCommand.RENAME.available_during_task() is True
    assert SlashCommand.RENAME.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.argument_form == "inline-or-bare"
    assert route.python_owner == "pycodex.tui.chatwidget.interaction"


def test_windows_conpty_native_and_python_bare_rename_opens_prompt(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = ("Name thread", "Type a name and press Enter")

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/rename",
            view_markers=markers,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 0
        assert markers in transcript.observed_ready_sequences
        assert "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output
        assert "Usage: /rename <name>" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()


def test_windows_conpty_native_and_python_inline_rename_is_local(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    slash_text = "/rename E2E rename title"
    expected = "Thread renamed to E2E rename title"

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text=slash_text,
            stop_pattern=re.escape(expected),
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        assert expected in transcript.normalized_stdout()
