"""End-to-end coverage for the ``/goal`` slash command."""

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


def test_goal_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch parses bare/objective/control forms.
    # - app::thread_goal_actions owns get/set/status/clear and goal views.
    route = terminal_slash_command_routes()[SlashCommand.GOAL]

    assert SlashCommand.GOAL.command() == "goal"
    assert SlashCommand.GOAL.supports_inline_args() is True
    assert SlashCommand.GOAL.available_during_task() is True
    assert SlashCommand.GOAL.available_in_side_conversation() is False
    assert route.outcome == "effect"
    assert route.argument_form == "inline-or-bare"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_goal_clear_without_goal_is_local(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "No goal to clear"

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/goal clear",
            stop_pattern=re.escape(expected),
            artifact_dir=tmp_path,
            feature_config_lines=("goals = true",),
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert expected in output
        assert "Usage: /goal <objective>" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
