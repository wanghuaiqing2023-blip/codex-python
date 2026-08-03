"""End-to-end coverage for the ``/skills`` slash command."""

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


def test_skills_registry_contract() -> None:
    # Rust owners:
    # - slash_dispatch delegates /skills to chatwidget::skills.
    # - chatwidget::skills builds the action menu and its AppEvents.
    # - selected management actions route through active BottomPaneView state.
    route = terminal_slash_command_routes()[SlashCommand.SKILLS]

    assert SlashCommand.SKILLS.command() == "skills"
    assert SlashCommand.SKILLS.supports_inline_args() is False
    assert SlashCommand.SKILLS.available_during_task() is True
    assert SlashCommand.SKILLS.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.chatwidget.skills"


def test_windows_conpty_native_and_python_skills_menu_is_local(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = (
        "Skills",
        "Choose an action",
        "List skills",
        "Tip: press $ to open this list directly.",
        "Enable/Disable Skills",
        "Enable or disable skills.",
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/skills",
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
        assert "extension area is not enabled" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
