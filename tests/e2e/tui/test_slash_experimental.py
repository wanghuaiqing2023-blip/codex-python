"""End-to-end coverage for the ``/experimental`` slash command."""

from __future__ import annotations

import re

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import *  # noqa: F401,F403
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_saved_view_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_experimental_registry_contract() -> None:
    # Rust owners:
    # - settings_popups builds only Stage::Experimental entries.
    # - experimental_features_view owns toggle/navigation/save behavior.
    # - AppEvent::UpdateFeatureFlags persists accepted values.
    route = terminal_slash_command_routes()[SlashCommand.EXPERIMENTAL]

    assert SlashCommand.EXPERIMENTAL.command() == "experimental"
    assert SlashCommand.EXPERIMENTAL.supports_inline_args() is False
    assert SlashCommand.EXPERIMENTAL.available_during_task() is False
    assert SlashCommand.EXPERIMENTAL.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.python_owner == (
        "pycodex.tui.chatwidget.settings_popups + "
        "pycodex.tui.bottom_pane.experimental_features_view"
    )


def test_windows_conpty_native_and_python_experimental_view_saves_locally(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = (
        "Experimental features",
        "Toggle experimental features. Changes are saved to config.toml.",
        "Terminal resize reflow",
        "Press Space to select or Enter to save for next conversation",
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count, persisted_config = (
            run_saved_view_slash_candidate(
                command,
                label=label,
                slash_text="/experimental",
                view_markers=markers,
                artifact_dir=tmp_path,
            )
        )
        output = transcript.normalized_stdout()
        assert request_count == 0, (
            f"{label} unexpectedly sent a model request\n"
            f"stdout={output}\n"
            f"stderr={transcript.normalized_stderr()}"
        )
        assert markers in transcript.observed_ready_sequences
        assert re.search(
            r"(?ms)^\[features\]\s*$.*?"
            r"^terminal_resize_reflow\s*=\s*true\s*$",
            persisted_config,
        ), persisted_config
        assert "SAVED_VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
