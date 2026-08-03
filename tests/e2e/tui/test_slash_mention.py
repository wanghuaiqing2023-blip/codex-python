"""End-to-end coverage for the ``/mention`` slash command."""

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


def test_mention_slash_command_uses_local_effect_route() -> None:
    assert terminal_slash_command_routes()[SlashCommand.MENTION].outcome == "effect"


def test_windows_conpty_native_and_python_mention_seeds_composer_when_enabled(
    tmp_path: Path,
) -> None:
    # Rust source contract: chatwidget::slash_dispatch::SlashCommand::Mention
    # calls ChatWidget::insert_str("@") and must not submit `/mention` as a
    # model UserTurn.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    composer_pattern = r"(?m)^.*@$"

    results = [
        (
            label,
            *run_local_slash_candidate(
                command,
                label=label,
                slash_text="/mention",
                stop_pattern=r"(?s)/mention.*?@",
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        screen = transcript.screen_stdout(rows=32, cols=120)
        assert re.search(composer_pattern, screen), (
            f"{label}: composer was not seeded with @; screen={screen!r}"
        )
        assert "Working" not in screen
