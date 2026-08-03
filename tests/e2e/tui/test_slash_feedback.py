"""End-to-end coverage for the Rust-owned ``/feedback`` slash command."""

import re
from pathlib import Path

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_view_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_feedback_slash_command_uses_feedback_selection_view_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.FEEDBACK]

    assert SlashCommand.FEEDBACK.supports_inline_args() is False
    assert SlashCommand.FEEDBACK.available_during_task() is True
    assert SlashCommand.FEEDBACK.available_in_side_conversation() is False
    assert route.category == "view"
    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.bottom_pane.feedback_view"


def test_windows_conpty_native_and_python_feedback_view_opens_and_escapes(
    tmp_path: Path,
) -> None:
    # Rust source contract: dispatch opens feedback_selection_params; Esc is
    # consumed by the active ListSelectionView and returns to the composer.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = ("How was this?", "bad result", "good result", "other")

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/feedback",
            view_markers=markers,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        detail = (
            f"{label}: requests={request_count}; returncode={transcript.returncode}; "
            f"stdout={output!r}; stderr={transcript.normalized_stderr()!r}"
        )
        assert request_count == 0, detail
        assert transcript.returncode == 0, detail
        compact_output = re.sub(r"\s+", "", output)
        for marker in markers:
            assert re.sub(r"\s+", "", marker) in compact_output, detail
        assert "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output, detail
        assert "product effect is not yet available" not in output, detail
