"""End-to-end coverage for ``/stop`` and its ``/clean`` alias."""

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


def test_stop_slash_command_and_clean_alias_use_cleanup_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.STOP]

    assert SlashCommand.STOP.command() == "stop"
    assert SlashCommand.parse("clean") is SlashCommand.STOP
    assert SlashCommand.STOP.supports_inline_args() is False
    assert SlashCommand.STOP.available_during_task() is True
    assert SlashCommand.STOP.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"


@pytest.mark.parametrize("slash_text", ["/stop", "/clean"])
def test_windows_conpty_native_and_python_stop_forms_are_local(
    tmp_path: Path,
    slash_text: str,
) -> None:
    # Rust chatwidget::clean_background_terminals submits the cleanup op,
    # clears the tracked processes/footer, and emits this confirmation.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text=slash_text,
            stop_pattern="Stopping all background terminals.",
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "Stopping all background terminals." in output
        assert "Traceback" not in output
