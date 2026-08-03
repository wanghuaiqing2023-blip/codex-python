"""End-to-end coverage for Rust's debug-only ``/test-approval`` command."""

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


def test_test_approval_slash_command_uses_core_approval_effect() -> None:
    route = terminal_slash_command_routes()[SlashCommand.TEST_APPROVAL]

    assert SlashCommand.TEST_APPROVAL.is_visible() is True
    assert SlashCommand.TEST_APPROVAL.supports_inline_args() is False
    assert SlashCommand.TEST_APPROVAL.available_during_task() is True
    assert SlashCommand.TEST_APPROVAL.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_test_approval_opens_and_escapes(
    tmp_path: Path,
) -> None:
    # Rust chatwidget::slash_dispatch builds a deterministic two-file
    # ApplyPatchApprovalRequestEvent and routes it through approval_overlay.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = (
        "Would you like to make the following edits?",
        "Yes, proceed",
        "Yes, and don't ask again for these files",
        "No, and tell Codex what to do differently",
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/test-approval",
            view_markers=markers,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        compact_output = re.sub(r"\s+", "", output)
        detail = (
            f"{label}: requests={request_count}; returncode={transcript.returncode}; "
            f"stdout={output!r}; stderr={transcript.normalized_stderr()!r}"
        )
        assert request_count == 0, detail
        assert transcript.returncode == 0, detail
        for marker in markers:
            assert re.sub(r"\s+", "", marker) in compact_output, detail
        assert "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output, detail
