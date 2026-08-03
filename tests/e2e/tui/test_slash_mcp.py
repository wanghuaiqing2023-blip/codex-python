"""End-to-end coverage for the Rust-owned ``/mcp`` slash command."""

from pathlib import Path

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_repeated_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_mcp_slash_command_uses_extension_inventory_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.MCP]

    assert SlashCommand.MCP.supports_inline_args() is True
    assert SlashCommand.MCP.available_during_task() is True
    assert SlashCommand.MCP.available_in_side_conversation() is False
    assert route.category == "extension"
    assert route.outcome == "effect"
    assert route.argument_form == "inline-or-bare"


def test_windows_conpty_native_and_python_mcp_forms_are_local(
    tmp_path: Path,
) -> None:
    # Rust source/test contract:
    # - bare `/mcp` emits FetchMcpInventory(ToolsAndAuthOnly);
    # - `/mcp verbose` emits FetchMcpInventory(Full);
    # - any other inline argument renders the usage line;
    # - none of these paths submits a model turn.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    commands = (
        ("/mcp", "No MCP servers configured"),
        ("/mcp verbose", "No MCP servers configured"),
        ("/mcp full", r"Usage: /mcp \[verbose\]"),
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_repeated_local_slash_candidate(
            command,
            label=label,
            commands_and_effects=commands,
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "No MCP servers configured" in output
        assert "Usage: /mcp [verbose]" in output
        assert "Traceback" not in output
