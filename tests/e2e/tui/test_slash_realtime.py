"""End-to-end coverage for the Rust-owned ``/realtime`` slash command."""

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


def test_realtime_slash_command_uses_realtime_state_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.REALTIME]

    assert SlashCommand.REALTIME.supports_inline_args() is False
    assert SlashCommand.REALTIME.available_during_task() is True
    assert SlashCommand.REALTIME.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"


def test_windows_conpty_native_and_python_realtime_start_is_local(
    tmp_path: Path,
) -> None:
    # Rust slash_dispatch starts the shared realtime state machine and replaces
    # the passive footer with the `/realtime stop live voice` hint.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/realtime",
            stop_pattern=(
                r"(?:/realtime stop live voice|"
                r"Failed to start realtime WebRTC)"
            ),
            artifact_dir=tmp_path,
            feature_config_lines=("realtime_conversation = true",),
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert (
            "/realtime stop live voice" in output
            or "Failed to start realtime WebRTC" in output
        )
        assert "Traceback" not in output
