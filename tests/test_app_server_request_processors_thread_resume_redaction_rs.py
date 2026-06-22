from __future__ import annotations

from pathlib import Path

from pycodex.app_server.request_processors_thread_resume_redaction import (
    REDACTED_PAYLOAD,
    redact_thread_resume_payloads,
    redacted_mcp_tool_call_result,
    should_redact_thread_resume_payloads,
)
from pycodex.app_server_protocol import Thread, ThreadItem, Turn


def test_should_redact_thread_resume_payloads_matches_remote_client_names() -> None:
    # Rust source: should_redact_thread_resume_payloads.
    assert should_redact_thread_resume_payloads("codex_chatgpt_android_remote")
    assert should_redact_thread_resume_payloads("codex_chatgpt_ios_remote")
    assert not should_redact_thread_resume_payloads("codex_desktop")
    assert not should_redact_thread_resume_payloads(None)


def test_redacts_mcp_success_result_and_removes_image_generation() -> None:
    # Rust source: redacts_mcp_success_result_and_removes_image_generation.
    thread = _test_thread(
        [
            ThreadItem.agent_message("agent-1", "kept"),
            ThreadItem(
                "mcpToolCall",
                {
                    "id": "mcp-1",
                    "server": "docs",
                    "tool": "lookup",
                    "status": "completed",
                    "arguments": {"secret": "argument"},
                    "mcpAppResourceUri": "ui://widget/lookup.html",
                    "pluginId": "sample@test",
                    "result": {
                        "content": [{"type": "text", "text": "secret result"}],
                        "structuredContent": {"secret": "structured"},
                        "_meta": {"secret": "meta"},
                    },
                    "error": None,
                    "durationMs": 8,
                },
            ),
            ThreadItem(
                "imageGeneration",
                {
                    "id": "ig-1",
                    "status": "completed",
                    "revisedPrompt": "revised",
                    "result": "base64-result",
                    "savedPath": "ig-1.png",
                },
            ),
        ]
    )

    redacted = redact_thread_resume_payloads(thread)

    assert len(redacted.turns[0].items) == 2
    assert redacted.turns[0].items[0] == ThreadItem.agent_message("agent-1", "kept")
    assert redacted.turns[0].items[1] == ThreadItem(
        "mcpToolCall",
        {
            "id": "mcp-1",
            "server": "docs",
            "tool": "lookup",
            "status": "completed",
            "arguments": REDACTED_PAYLOAD,
            "mcpAppResourceUri": "ui://widget/lookup.html",
            "pluginId": "sample@test",
            "result": redacted_mcp_tool_call_result(),
            "error": None,
            "durationMs": 8,
        },
    )
    assert len(thread.turns[0].items) == 3


def test_redacts_mcp_error_message() -> None:
    # Rust source: redacts_mcp_error_message.
    thread = _test_thread(
        [
            ThreadItem(
                "mcpToolCall",
                {
                    "id": "mcp-1",
                    "server": "docs",
                    "tool": "lookup",
                    "status": "failed",
                    "arguments": {"secret": "argument"},
                    "mcpAppResourceUri": None,
                    "pluginId": None,
                    "result": None,
                    "error": {"message": "secret error"},
                    "durationMs": 8,
                },
            )
        ]
    )

    redacted = redact_thread_resume_payloads(thread)

    assert redacted.turns[0].items[0] == ThreadItem(
        "mcpToolCall",
        {
            "id": "mcp-1",
            "server": "docs",
            "tool": "lookup",
            "status": "failed",
            "arguments": REDACTED_PAYLOAD,
            "mcpAppResourceUri": None,
            "pluginId": None,
            "result": None,
            "error": {"message": REDACTED_PAYLOAD},
            "durationMs": 8,
        },
    )


def _test_thread(items) -> Thread:
    return Thread(
        id="thread-1",
        session_id="session-1",
        forked_from_id=None,
        preview="preview",
        ephemeral=False,
        model_provider="mock_provider",
        created_at=0,
        updated_at=0,
        status={"type": "idle"},
        path=None,
        cwd=Path("."),
        cli_version="0.0.0",
        source="cli",
        turns=(
            Turn(
                id="turn-1",
                items=tuple(items),
                status="completed",
            ),
        ),
    )
