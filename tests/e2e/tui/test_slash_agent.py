"""End-to-end coverage for the ``/agent`` slash command."""

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


def test_agent_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch emits AppEvent::OpenAgentPicker.
    # - app::session_lifecycle opens the enable prompt when Collab is disabled,
    #   otherwise it opens the tracked-agent selection view.
    route = terminal_slash_command_routes()[SlashCommand.AGENT]

    assert SlashCommand.AGENT.command() == "agent"
    assert SlashCommand.AGENT.supports_inline_args() is False
    assert SlashCommand.AGENT.available_during_task() is True
    assert SlashCommand.AGENT.available_in_side_conversation() is False
    assert route.outcome == "effect"
    assert route.argument_form == "bare"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_agent_opens_enable_prompt(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "Enable subagents?"

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/agent",
            stop_pattern=re.escape(expected),
            artifact_dir=tmp_path,
            feature_config_lines=("multi_agent = false",),
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert expected in output
        assert "Yes, enable" in output
        assert "Not now" in output
        assert "Traceback" not in output
