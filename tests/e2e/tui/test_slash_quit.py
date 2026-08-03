"""End-to-end coverage for the ``/quit`` slash command."""

from pathlib import Path

import pytest

from pycodex.tui.chatwidget.slash_dispatch import (
    plan_terminal_local_command,
    terminal_slash_command_routes,
)
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_clean_exit_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_quit_slash_command_uses_local_exit_effect() -> None:
    # Rust: chatwidget::slash_dispatch handles Quit | Exit through
    # request_quit_without_confirmation.
    route = terminal_slash_command_routes()[SlashCommand.QUIT]

    assert route.outcome == "effect"
    assert plan_terminal_local_command("/quit").action == "exit"


def test_windows_conpty_native_and_python_quit_clean_shutdown_when_enabled(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    results = [
        (
            label,
            *run_clean_exit_slash_candidate(
                command,
                label=label,
                slash_text="/quit",
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        detail = (
            f"{label}: requests={request_count}; returncode={transcript.returncode}; "
            f"stdout={transcript.normalized_stdout()!r}; "
            f"stderr={transcript.normalized_stderr()!r}"
        )
        assert request_count == 0, detail
        assert transcript.returncode == 0, detail
        assert "OpenAI Codex" in transcript.normalized_stdout(), detail
        assert (
            "EXIT_SLASH_COMMAND_MUST_NOT_REACH_THE_MODEL"
            not in transcript.normalized_stdout()
        ), detail
