"""End-to-end coverage for canonical ``/subagents``."""

from __future__ import annotations

import re
from pathlib import Path

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


def test_subagents_registry_contract() -> None:
    # Rust SlashCommand::MultiAgents serializes only as `subagents`; the enum
    # variant's kebab-case spelling is not a user-facing command alias.
    route = terminal_slash_command_routes()[SlashCommand.MULTI_AGENTS]

    assert SlashCommand.MULTI_AGENTS.command() == "subagents"
    assert SlashCommand.parse("subagents") is SlashCommand.MULTI_AGENTS
    with pytest.raises(ValueError):
        SlashCommand.parse("multi-agents")
    assert SlashCommand.MULTI_AGENTS.supports_inline_args() is False
    assert SlashCommand.MULTI_AGENTS.available_during_task() is True
    assert SlashCommand.MULTI_AGENTS.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_subagents_opens_shared_picker_effect(
    tmp_path: Path,
) -> None:
    # Rust dispatch maps Agent | MultiAgents to AppEvent::OpenAgentPicker. With
    # multi-agent disabled, session_lifecycle deterministically opens this view.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "Enable subagents?"
    slash_text = "/subagents"

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=f"{label}-{slash_text.lstrip('/')}",
            slash_text=slash_text,
            stop_pattern=re.escape(expected),
            artifact_dir=tmp_path,
            feature_config_lines=("multi_agent = false",),
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        compact_output = re.sub(r"\s+", "", output)
        detail = (
            f"{label}/{slash_text}: stdout={output!r}; "
            f"stderr={transcript.normalized_stderr()!r}"
        )
        assert expected in output, detail
        assert "Yes, enable" in output, detail
        assert "Notnow" in compact_output, detail
        assert "Traceback" not in output, detail
