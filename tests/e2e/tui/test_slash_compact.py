"""End-to-end coverage for the ``/compact`` slash command."""

from __future__ import annotations

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_compact_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_compact_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch marks the task running and emits
    #   AppCommand::Compact.
    # - app::thread_routing invokes thread/compact/start.
    # - core::compact owns the standalone manual compaction turn.
    route = terminal_slash_command_routes()[SlashCommand.COMPACT]

    assert SlashCommand.COMPACT.command() == "compact"
    assert SlashCommand.COMPACT.supports_inline_args() is False
    assert SlashCommand.COMPACT.available_during_task() is False
    assert SlashCommand.COMPACT.available_in_side_conversation() is False
    assert route.outcome == "effect"
    assert route.argument_form == "bare"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_compact_uses_dedicated_turn(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_compact_slash_candidate(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 1, (
            f"{label} expected one compaction request, got {request_count}\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert "/compact" in output
        assert "/status" in output
        assert "Session:" in output
        assert "Compacted conversation summary." not in output
        assert "product effect is not yet available" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
        assert (
            "ConPTY command terminated after stop pattern"
            in transcript.normalized_stderr()
        )
