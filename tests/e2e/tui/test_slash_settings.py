"""End-to-end coverage for the Rust-owned ``/settings`` slash command."""

import re
from pathlib import Path

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_view_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_settings_slash_command_uses_realtime_audio_view_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.SETTINGS]

    assert SlashCommand.SETTINGS.supports_inline_args() is False
    assert SlashCommand.SETTINGS.available_during_task() is True
    assert SlashCommand.SETTINGS.available_in_side_conversation() is False
    assert route.category == "view"
    assert route.outcome == "view"
    assert route.python_owner == "pycodex.tui.chatwidget.settings_popups"


def test_windows_conpty_native_and_python_settings_view_opens_and_escapes(
    tmp_path: Path,
) -> None:
    # Rust source/snapshot contract: with realtime conversation enabled on a
    # non-Linux platform, /settings opens the audio device selection view.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = (
        "Settings",
        "Configure settings for Codex.",
        "Microphone",
        "Speaker",
        "System default",
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/settings",
            view_markers=markers,
            artifact_dir=tmp_path,
            feature_config_lines=("realtime_conversation = true",),
        )
        output = transcript.normalized_stdout()
        compact_output = re.sub(r"\s+", "", output)
        detail = (
            f"{label}: requests={request_count}; returncode={transcript.returncode}; "
            f"stdout={output!r}; stderr={transcript.normalized_stderr()!r}"
        )
        assert request_count == 0, detail
        assert transcript.returncode == 0, detail
        for marker in markers:
            assert re.sub(r"\s+", "", marker) in compact_output, detail
        assert "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output, detail
