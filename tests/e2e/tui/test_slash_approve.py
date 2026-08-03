"""End-to-end coverage for the canonical ``/approve`` slash command."""

from __future__ import annotations

import re

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


def test_approve_registry_contract() -> None:
    # Rust owners:
    # - slash_command.rs maps AutoReview to the canonical name "approve".
    # - chatwidget::slash_dispatch opens the recent-denials view.
    # - chatwidget::permission_popups owns the empty state, selection rows,
    #   and ApproveRecentAutoReviewDenial event.
    route = terminal_slash_command_routes()[SlashCommand.AUTO_REVIEW]

    assert SlashCommand.AUTO_REVIEW.command() == "approve"
    assert SlashCommand.parse("approve") is SlashCommand.AUTO_REVIEW
    assert SlashCommand.AUTO_REVIEW.supports_inline_args() is False
    assert SlashCommand.AUTO_REVIEW.available_during_task() is True
    assert SlashCommand.AUTO_REVIEW.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.chatwidget.permission_popups"


def test_windows_conpty_native_and_python_approve_empty_state_is_local(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "No recent auto-review denials in this thread."

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/approve",
            stop_pattern=re.escape(expected),
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert expected in output
        assert "Denials are recorded after auto-review rejects an action." in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
