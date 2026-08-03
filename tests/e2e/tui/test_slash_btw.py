"""End-to-end coverage for the Rust-owned ``/btw`` slash command."""

from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_side_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_btw_registry_contract() -> None:
    # Rust registers Btw as its own SlashCommand and dispatches it beside Side
    # through AppEvent::StartSide, preserving the submitted inline prompt.
    route = terminal_slash_command_routes()[SlashCommand.BTW]

    assert SlashCommand.BTW.command() == "btw"
    assert SlashCommand.BTW.supports_inline_args() is True
    assert SlashCommand.BTW.available_during_task() is True
    assert SlashCommand.BTW.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.argument_form == "inline-or-bare"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_btw_uses_side_effect(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    question = "Give a brief side observation."

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_bodies = run_side_slash_candidate(
            command,
            label=label,
            artifact_dir=tmp_path,
            inline_text=question,
            slash_command="btw",
        )
        output = transcript.normalized_stdout()
        detail = (
            f"{label}: requests={len(request_bodies)}; "
            f"stderr={transcript.normalized_stderr()!r}; output={output!r}"
        )
        assert len(request_bodies) == 2, detail
        child_request = request_bodies[-1].decode("utf-8")
        assert "Side conversation boundary." in child_request, detail
        assert question in child_request, detail
        assert "SIDE_REPLY_READY" in output, detail
        assert "Ctrl+Ctoreturn" in output.replace(" ", ""), detail
        assert "product effect is not yet available" not in output, detail
        assert "Traceback" not in output, detail
