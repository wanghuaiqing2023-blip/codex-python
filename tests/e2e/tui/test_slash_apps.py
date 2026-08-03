"""End-to-end coverage for the Rust-owned ``/apps`` slash command."""

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


def test_apps_slash_command_uses_extension_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.APPS]

    assert SlashCommand.APPS.supports_inline_args() is False
    assert SlashCommand.APPS.available_during_task() is True
    assert SlashCommand.APPS.available_in_side_conversation() is False
    assert route.category == "extension"
    assert route.outcome == "effect"
    assert route.python_owner == "pycodex.tui.chatwidget.connectors"


def test_windows_conpty_native_and_python_apps_view_is_local(
    tmp_path: Path,
) -> None:
    # Rust source contract: with Apps enabled for a ChatGPT account,
    # chatwidget::connectors::add_connectors_output dispatches the connector
    # refresh locally and opens the loading view without submitting a model turn.
    # The isolated Apps backend can either remain pending or fail asynchronously,
    # so the stable contract boundary is the view rather than the backend result.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe, disable_apps=False)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/apps",
            stop_pattern=r"(?:Loading apps\.\.\.|app/list failed in TUI)",
            artifact_dir=tmp_path,
            apps_enabled=True,
            chatgpt_auth=True,
            provider_requires_openai_auth=True,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert (
            "Loading apps..." in output or "app/list failed in TUI" in output
        )
        assert "Traceback" not in output
