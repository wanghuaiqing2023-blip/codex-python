"""End-to-end coverage for the ``/hooks`` slash command."""

from __future__ import annotations

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_view_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_hooks_registry_contract() -> None:
    # Rust owners:
    # - slash_dispatch calls chatwidget::hooks::add_hooks_output.
    # - hooks_rpc loads the current cwd's hook entry.
    # - bottom_pane::hooks_browser_view renders and navigates lifecycle events.
    route = terminal_slash_command_routes()[SlashCommand.HOOKS]

    assert SlashCommand.HOOKS.command() == "hooks"
    assert SlashCommand.HOOKS.supports_inline_args() is False
    assert SlashCommand.HOOKS.available_during_task() is True
    assert SlashCommand.HOOKS.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.python_owner == (
        "pycodex.tui.chatwidget.hooks + "
        "pycodex.tui.bottom_pane.hooks_browser_view"
    )


def test_windows_conpty_native_and_python_hooks_browser_is_local(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = (
        "Hooks",
        "Lifecycle hooks from config and enabled plugins.",
        "Press Enter to view hooks; Esc to close",
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_view_slash_candidate(
            command,
            label=label,
            slash_text="/hooks",
            view_markers=markers,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 0, (
            f"{label} unexpectedly sent a model request\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert markers in transcript.observed_ready_sequences
        assert "VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output
        assert "extension area is not enabled" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
