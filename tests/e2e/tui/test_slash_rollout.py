"""End-to-end coverage for the Rust-owned ``/rollout`` slash command."""

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


def test_rollout_slash_command_uses_core_local_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.ROLLOUT]

    assert SlashCommand.ROLLOUT.supports_inline_args() is False
    assert SlashCommand.ROLLOUT.available_during_task() is True
    assert SlashCommand.ROLLOUT.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"


def test_windows_conpty_native_and_python_rollout_output_is_local(
    tmp_path: Path,
) -> None:
    # Rust source/tests cover both a current path and the not-yet-available
    # branch. Startup timing decides which one a real isolated TUI observes.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    pattern = r"(?:Current rollout path:|Rollout path is not available yet\.)"

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/rollout",
            stop_pattern=pattern,
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert (
            "Current rollout path:" in output
            or "Rollout path is not available yet." in output
        )
        assert "Traceback" not in output
