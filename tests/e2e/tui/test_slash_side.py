"""End-to-end coverage for the ``/side`` slash command."""

from __future__ import annotations

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_side_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_side_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch emits AppEvent::StartSide.
    # - app::side forks, injects the side boundary, switches threads, and
    #   submits inline text only after the child is active.
    route = terminal_slash_command_routes()[SlashCommand.SIDE]

    assert SlashCommand.SIDE.command() == "side"
    assert SlashCommand.SIDE.supports_inline_args() is True
    assert SlashCommand.SIDE.available_during_task() is True
    assert SlashCommand.SIDE.available_in_side_conversation() is False
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.argument_form == "inline-or-bare"


def test_windows_conpty_native_and_python_bare_side_forks_and_returns(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_bodies = run_side_slash_candidate(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        detail = (
            f"{label}: requests={len(request_bodies)}; "
            f"stderr={transcript.normalized_stderr()!r}; output={output!r}"
        )
        assert len(request_bodies) == 1, detail
        assert "MAIN_SESSION_READY" in output, detail
        assert "Ctrl+Ctoreturn" in output.replace(" ", ""), detail
        assert "Session:" in output, detail
        assert "Failed to start side conversation" not in output, detail
        assert "product effect is not yet available" not in output, detail
        assert "Traceback" not in output, detail


def test_windows_conpty_native_and_python_ctrl_c_returns_to_main_thread(
    tmp_path,
) -> None:
    """Ctrl+C must restore the parent runtime, not merely leave a usable composer."""

    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_bodies = run_side_slash_candidate(
            command,
            label=label,
            artifact_dir=tmp_path,
            return_shortcut="\x03",
            verify_main_return=True,
        )
        output = transcript.normalized_stdout()
        detail = (
            f"{label}: requests={len(request_bodies)}; "
            f"stderr={transcript.normalized_stderr()!r}; output={output!r}"
        )
        assert len(request_bodies) == 2, detail
        return_request = request_bodies[-1].decode("utf-8")
        assert "RETURN_TO_MAIN_PROBE" in return_request, detail
        assert "Side conversation boundary." not in return_request, detail
        assert "MAIN_RETURN_READY" in output, detail
        assert "Traceback" not in output, detail


def test_windows_conpty_native_and_python_inline_side_submits_in_child(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    question = "What is the active thread for?"

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_bodies = run_side_slash_candidate(
            command,
            label=label,
            artifact_dir=tmp_path,
            inline_text=question,
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
