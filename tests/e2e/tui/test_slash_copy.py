"""End-to-end coverage for the ``/copy`` slash command."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from pycodex.tui.chatwidget.protocol import ChatWidgetProtocolRuntime, ServerNotification
from pycodex.tui.chatwidget.slash_dispatch import (
    TerminalSlashCommandEffectDispatcher,
    terminal_slash_command_routes,
)
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_copy_after_response_candidate,
    run_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e

COPY_SOURCE_MARKDOWN = "**COPY-SLASH-20260801** `raw-markdown`"


class _CopyLifecycleApp:
    def __init__(self, widget: ChatWidgetProtocolRuntime) -> None:
        self.chat_widget = widget
        self.info_messages: list[tuple[str, str | None]] = []
        self.error_messages: list[str] = []

    def insert_info_history_message(self, message: str, hint: str | None) -> None:
        self.info_messages.append((message, hint))

    def insert_history_cell(self, cell: object) -> None:
        message = getattr(cell, "message", None)
        if message is None and isinstance(cell, dict):
            message = cell.get("message")
        self.error_messages.append(str(message or cell))


def test_copy_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch maps Copy to
    #   ChatWidget::copy_last_agent_markdown.
    # - chatwidget::interaction owns response lookup, clipboard lease
    #   replacement, and visible success/error messages.
    route = terminal_slash_command_routes()[SlashCommand.COPY]

    assert SlashCommand.COPY.command() == "copy"
    assert SlashCommand.COPY.supports_inline_args() is False
    assert SlashCommand.COPY.available_during_task() is True
    assert SlashCommand.COPY.available_in_side_conversation() is True
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.argument_form == "bare"


def test_copy_after_completed_agent_response_reaches_clipboard(monkeypatch) -> None:
    """Cover Rust streaming -> transcript -> slash_dispatch -> clipboard."""

    widget = ChatWidgetProtocolRuntime()
    app = _CopyLifecycleApp(widget)
    copied: list[str] = []
    monkeypatch.setattr(
        "pycodex.tui.clipboard_copy.copy_to_clipboard",
        lambda markdown: copied.append(markdown) or SimpleNamespace(owner="probe"),
    )

    widget.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-copy"}}))
    widget.handle(
        ServerNotification(
            "ItemCompleted",
            {
                "turn_id": "turn-copy",
                "item": {
                    "kind": "AgentMessage",
                    "id": "message-copy",
                    "phase": "FinalAnswer",
                    "text": COPY_SOURCE_MARKDOWN,
                },
            },
        )
    )
    widget.handle(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-copy", "status": "Completed"}},
        )
    )

    result = TerminalSlashCommandEffectDispatcher(app).dispatch(SlashCommand.COPY)

    assert result.action == "handled"
    assert copied == [COPY_SOURCE_MARKDOWN], (
        "the completed response was rendered but /copy did not receive its raw markdown; "
        f"copy errors: {app.error_messages}"
    )
    assert app.info_messages == [("Copied last message to clipboard", None)]
    assert app.error_messages == []


def test_windows_conpty_native_and_python_copy_without_response_is_local(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    expected = "No agent response to copy"

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text="/copy",
            stop_pattern=re.escape(expected),
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert expected in output
        assert "Copied last message to clipboard" not in output
        assert "Traceback" not in output


def test_windows_conpty_native_and_python_copy_completed_response(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_copy_after_response_candidate(
            command,
            label=label,
            response_markdown=COPY_SOURCE_MARKDOWN,
            response_ready_text="COPY-SLASH-20260801",
            artifact_dir=tmp_path,
        )
        output = transcript.normalized_stdout()
        assert request_count == 1, (
            f"{label} should make one request for the user prompt and no request for /copy"
        )
        assert "COPY-SLASH-20260801 raw-markdown" in output, (
            f"{label} did not render the completed assistant response"
        )
        assert "Copied last message to clipboard" in output, (
            f"{label} did not copy the completed assistant response"
        )
        assert "No agent response to copy" not in output, (
            f"{label} rendered the response but did not retain it as the /copy source"
        )
        assert "Copy failed:" not in output, f"{label} clipboard backend failed"
        assert "Traceback" not in output, f"{label} raised an unexpected exception"
