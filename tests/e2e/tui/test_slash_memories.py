"""End-to-end coverage for the ``/memories`` slash command."""

from __future__ import annotations

import re

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_saved_view_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_memories_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch calls ChatWidget::open_memories_popup.
    # - chatwidget opens either the enable prompt or MemoriesSettingsView.
    # - bottom_pane::memories_settings_view owns toggle/save/reset behavior.
    # - app::config_persistence applies UpdateMemorySettings.
    route = terminal_slash_command_routes()[SlashCommand.MEMORIES]

    assert SlashCommand.MEMORIES.command() == "memories"
    assert SlashCommand.MEMORIES.supports_inline_args() is False
    assert SlashCommand.MEMORIES.available_during_task() is False
    assert SlashCommand.MEMORIES.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.python_owner == (
        "pycodex.tui.chatwidget + "
        "pycodex.tui.bottom_pane.memories_settings_view"
    )


def test_windows_conpty_native_and_python_memories_view_saves_locally(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    markers = (
        "Memories",
        "Choose how Codex uses and creates memories. Changes are saved to config.toml",
        "Use memories",
        "Generate memories",
        "Reset all memories",
        "Press Space to toggle; Enter to save or select",
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count, persisted_config = (
            run_saved_view_slash_candidate(
                command,
                label=label,
                slash_text="/memories",
                view_markers=markers,
                artifact_dir=tmp_path,
                feature_config_lines=("memories = true",),
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
            r"(?ms)^\[memories\]\s*$.*?"
            r"^use_memories\s*=\s*true\s*$.*?"
            r"^generate_memories\s*=\s*true\s*$",
            persisted_config,
        ), persisted_config
        assert "SAVED_VIEW_SLASH_MUST_NOT_REACH_THE_MODEL" not in output
        assert "product effect is not yet available" not in output
        assert "Traceback" not in output
        assert "Traceback" not in transcript.normalized_stderr()
