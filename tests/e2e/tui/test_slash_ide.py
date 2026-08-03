"""End-to-end coverage for the ``/ide`` slash command."""

from pathlib import Path
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


def test_ide_slash_command_routes_to_chatwidget_ide_context() -> None:
    route = terminal_slash_command_routes()[SlashCommand.IDE]

    assert route.outcome == "effect"
    assert route.python_owner == "pycodex.tui.chatwidget.ide_context"
    assert SlashCommand.IDE.supports_inline_args() is True
    assert SlashCommand.IDE.available_during_task() is True
    assert SlashCommand.IDE.available_in_side_conversation() is True


@pytest.mark.parametrize(
    ("slash_text", "expected_effect"),
    (
        ("/ide off", "IDE context is off."),
        ("/ide invalid", "Usage: /ide [on|off|status]"),
        ("/ide", "IDE context could not be enabled."),
    ),
)
def test_windows_conpty_native_and_python_ide_command_when_enabled(
    slash_text: str,
    expected_effect: str,
    tmp_path: Path,
) -> None:
    # Rust owners:
    # - slash_command marks /ide inline-capable and available during tasks and
    #   side conversations.
    # - chatwidget::slash_dispatch delegates bare and prepared args to
    #   chatwidget::ide_context.
    # - chatwidget::ide_context owns off, usage, and unavailable-provider
    #   messages without creating a model UserTurn.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    results = [
        (
            label,
            *run_local_slash_candidate(
                command,
                label=label,
                slash_text=slash_text,
                stop_pattern=re.escape(expected_effect),
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        assert expected_effect in transcript.normalized_stdout()
