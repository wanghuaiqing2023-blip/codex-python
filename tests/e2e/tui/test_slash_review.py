"""End-to-end coverage for the ``/review`` slash command."""

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


def test_review_registry_contract() -> None:
    # Rust owners:
    # - slash_dispatch opens chatwidget::review_popups for a bare command.
    # - inline text becomes a custom review target.
    # - review_popups owns preset/branch/commit/custom child views.
    route = terminal_slash_command_routes()[SlashCommand.REVIEW]

    assert SlashCommand.REVIEW.command() == "review"
    assert SlashCommand.REVIEW.supports_inline_args() is True
    assert SlashCommand.REVIEW.available_during_task() is False
    assert SlashCommand.REVIEW.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.argument_form == "inline-or-bare"
    assert route.python_owner == "pycodex.tui.chatwidget.review_popups"


def test_windows_conpty_native_and_python_review_popup_is_local(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = (
        "Select a review preset",
        "Review against a base branch",
        "Review uncommitted changes",
        "Review a commit",
        "Custom review instructions",
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/review",
            view_markers=markers,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 0, (
            f"{label} unexpectedly sent a model request\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert markers in transcript.observed_ready_sequences
        assert "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output
        assert "product effect is not yet available" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
