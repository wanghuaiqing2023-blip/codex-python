"""End-to-end coverage for the ``/setup-default-sandbox`` slash command."""

from __future__ import annotations

import re

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import *  # noqa: F401,F403
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_seeded_windows_sandbox_setup_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_setup_default_sandbox_registry_contract() -> None:
    # Rust owners:
    # - slash_command.rs registers the Windows-only canonical spelling.
    # - bottom_pane::slash_commands gates it on RestrictedToken mode.
    # - chatwidget::slash_dispatch emits BeginWindowsSandboxElevatedSetup.
    route = terminal_slash_command_routes()[SlashCommand.ELEVATE_SANDBOX]

    assert SlashCommand.ELEVATE_SANDBOX.command() == "setup-default-sandbox"
    assert SlashCommand.ELEVATE_SANDBOX.supports_inline_args() is False
    assert SlashCommand.ELEVATE_SANDBOX.available_during_task() is False
    assert SlashCommand.ELEVATE_SANDBOX.available_in_side_conversation() is False
    assert route.outcome == "effect"
    assert route.python_owner == (
        "pycodex.tui.chatwidget.slash_dispatch + "
        "pycodex.tui.app.event_dispatch"
    )


def test_windows_conpty_native_and_python_setup_default_sandbox_when_enabled(
    tmp_path,
) -> None:
    # The host sandbox identities are copied into an isolated CODEX_HOME, so
    # both products take Rust's "setup already complete" branch: no UAC is
    # opened, but slash recognition, AppEvent dispatch, config persistence,
    # success rendering, and the no-UserTurn invariant are all exercised.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    results = [
        (
            label,
            *run_seeded_windows_sandbox_setup_candidate(
                command,
                label=label,
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count, persisted_config in results:
        output = transcript.normalized_stdout()
        screen = transcript.screen_stdout(rows=32, cols=120)
        assert request_count == 0, (
            f"{label} unexpectedly sent a model request\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert "Sandbox ready" in output or "Sandbox ready" in screen
        assert re.search(
            r"(?ms)^\[windows\]\s*$.*?^sandbox\s*=\s*[\"']elevated[\"']\s*$",
            persisted_config,
        ), persisted_config
        assert "SETUP_DEFAULT_SANDBOX_MUST_NOT_REACH_THE_MODEL" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
