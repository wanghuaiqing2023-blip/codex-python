"""End-to-end coverage for the Rust-owned ``/plugins`` slash command."""

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


def test_plugins_slash_command_uses_extension_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.PLUGINS]

    assert SlashCommand.PLUGINS.command() == "plugins"
    assert SlashCommand.PLUGINS.supports_inline_args() is False
    assert SlashCommand.PLUGINS.available_during_task() is True
    assert SlashCommand.PLUGINS.available_in_side_conversation() is False
    assert route.category == "extension"
    assert route.outcome == "effect"
    assert route.python_owner == "pycodex.tui.chatwidget.plugins"


def test_windows_conpty_native_and_python_plugins_view_is_local(
    tmp_path: Path,
) -> None:
    # Rust source/snapshot contract:
    # - chatwidget::plugins::add_plugins_output prefetches the plugin list;
    # - the loading SelectionView is opened before the marketplace result;
    # - the command never becomes a model turn.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe, disable_plugins=False)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/plugins",
            stop_pattern=r"(?:Loading plugins\.\.\.|plugin/list failed)",
            artifact_dir=tmp_path,
            plugins_enabled=True,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "Loading plugins..." in output or "plugin/list failed" in output
        assert "Traceback" not in output
