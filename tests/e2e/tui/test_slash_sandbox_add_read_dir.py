"""End-to-end coverage for the ``/sandbox-add-read-dir`` slash command."""

from __future__ import annotations

import os
from pathlib import Path

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import *  # noqa: F401,F403
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_repeated_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_sandbox_add_read_dir_registry_contract() -> None:
    # Rust owners:
    # - slash_command.rs exposes this Windows-only inline command.
    # - chatwidget::slash_dispatch emits BeginWindowsSandboxGrantReadRoot.
    # - app::event_dispatch calls core::grant_read_root_non_elevated and
    #   renders the completed success/error event.
    route = terminal_slash_command_routes()[SlashCommand.SANDBOX_READ_ROOT]

    assert SlashCommand.SANDBOX_READ_ROOT.command() == "sandbox-add-read-dir"
    assert SlashCommand.SANDBOX_READ_ROOT.supports_inline_args() is True
    assert SlashCommand.SANDBOX_READ_ROOT.available_during_task() is False
    assert SlashCommand.SANDBOX_READ_ROOT.available_in_side_conversation() is False
    assert route.outcome == "effect"
    assert route.argument_form == "inline-or-bare"
    assert route.python_owner == (
        "pycodex.tui.chatwidget.slash_dispatch + "
        "pycodex.tui.app.event_dispatch"
    )


def test_windows_conpty_native_and_python_sandbox_add_read_dir_errors_are_local(
    tmp_path,
) -> None:
    # A missing absolute directory reaches the real core validation boundary
    # but cannot change ACLs or sandbox setup state. The preceding bare command
    # proves Rust's usage branch in the same isolated TUI.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    missing_root = Path(
        f"C:/pycodex-e2e-missing-read-root-{os.getpid()}"
    )
    assert not missing_root.exists()
    inline_command = f"/sandbox-add-read-dir {missing_root}"
    usage = "Usage: /sandbox-add-read-dir <absolute-directory-path>"
    error = "Error: path does not exist:"

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_repeated_local_slash_candidate(
            command,
            label=label,
            commands_and_effects=(
                ("/sandbox-add-read-dir", usage),
                (inline_command, error),
            ),
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 0, (
            f"{label} unexpectedly sent a model request\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert (usage,) in transcript.observed_ready_sequences
        assert error in output
        assert str(missing_root) in output
        assert "LOCAL_SLASH_COMMAND_MUST_NOT_REACH_THE_MODEL" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
