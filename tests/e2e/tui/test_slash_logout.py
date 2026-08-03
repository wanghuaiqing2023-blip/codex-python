"""End-to-end coverage for the Rust-owned ``/logout`` slash command."""

from pathlib import Path

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_clean_exit_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_logout_slash_command_uses_app_event_effect_route() -> None:
    # Rust chatwidget::slash_dispatch sends AppEvent::Logout; app::event_dispatch
    # logs out the account and then follows ShutdownFirst exit semantics.
    route = terminal_slash_command_routes()[SlashCommand.LOGOUT]

    assert SlashCommand.LOGOUT.supports_inline_args() is False
    assert SlashCommand.LOGOUT.available_during_task() is False
    assert SlashCommand.LOGOUT.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"


def test_windows_conpty_native_and_python_logout_is_local_clean_shutdown(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_clean_exit_slash_candidate(
            command,
            label=label,
            slash_text="/logout",
            artifact_dir=tmp_path,
        )
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
