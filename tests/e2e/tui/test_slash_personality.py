"""End-to-end coverage for the Rust-owned ``/personality`` slash command."""

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


def test_personality_slash_command_uses_settings_popup_view_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.PERSONALITY]

    assert SlashCommand.PERSONALITY.supports_inline_args() is False
    assert SlashCommand.PERSONALITY.available_during_task() is False
    assert SlashCommand.PERSONALITY.available_in_side_conversation() is False
    assert route.category == "view"
    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.chatwidget.settings_popups"


def test_windows_conpty_native_and_python_personality_model_guard_is_local(
    tmp_path: Path,
) -> None:
    # Rust settings_popups::open_personality_popup rejects a configured model
    # that lacks personality support before opening the selection view.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "doesn't support personalities. Try /model to pick a different model."

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/personality",
            stop_pattern=r"doesn't support personalities",
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert expected in output
        assert "Traceback" not in output
