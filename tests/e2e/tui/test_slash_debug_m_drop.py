"""End-to-end coverage for Rust's ``/debug-m-drop`` slash command."""

from pathlib import Path

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


def test_debug_m_drop_registry_and_effect_contract() -> None:
    # Rust slash_commands::slash_memory_drop_reports_stubbed_feature fixes both
    # the local error text and the requirement that no memory operation is sent.
    route = terminal_slash_command_routes()[SlashCommand.MEMORY_DROP]

    assert SlashCommand.MEMORY_DROP.command() == "debug-m-drop"
    assert SlashCommand.MEMORY_DROP.supports_inline_args() is False
    assert SlashCommand.MEMORY_DROP.available_during_task() is False
    assert SlashCommand.MEMORY_DROP.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_debug_m_drop_reports_tui_stub(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "Memory maintenance: Not available in TUI yet."

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/debug-m-drop",
            stop_pattern=expected,
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        detail = (
            f"{label}: stdout={output!r}; "
            f"stderr={transcript.normalized_stderr()!r}"
        )
        assert expected in output, detail
        assert "Traceback" not in output, detail
