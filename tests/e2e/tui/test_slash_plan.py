"""End-to-end coverage for the ``/plan`` slash command."""

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


def test_plan_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch applies the Plan collaboration mask.
    # - inline text is rebuilt as a prepared user message and submitted only
    #   after the mode change succeeds.
    route = terminal_slash_command_routes()[SlashCommand.PLAN]

    assert SlashCommand.PLAN.command() == "plan"
    assert SlashCommand.PLAN.supports_inline_args() is True
    assert SlashCommand.PLAN.available_during_task() is False
    assert SlashCommand.PLAN.available_in_side_conversation() is False
    assert route.outcome == "effect"
    assert route.argument_form == "inline-or-bare"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_bare_plan_switches_mode_locally(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "Plan mode."

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/plan",
            stop_pattern=re.escape(expected),
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert expected in output
        assert "Collaboration modes are disabled." not in output
        assert "Plan mode unavailable right now." not in output
