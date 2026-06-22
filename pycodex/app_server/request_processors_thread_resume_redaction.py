"""Thread resume redaction ported from ``app-server/src/request_processors/thread_resume_redaction.rs``."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from pycodex.app_server_protocol import Thread, ThreadItem, Turn

JsonValue = Any

REDACTED_PAYLOAD = "[redacted]"
CHATGPT_REMOTE_CLIENT_NAMES: tuple[str, ...] = (
    "codex_chatgpt_android_remote",
    "codex_chatgpt_ios_remote",
)


def should_redact_thread_resume_payloads(client_name: str | None) -> bool:
    """Return whether Rust redacts ``thread/resume`` payloads for this client."""

    return client_name in CHATGPT_REMOTE_CLIENT_NAMES


def redact_thread_resume_payloads(thread: Thread) -> Thread:
    """Return a copy of ``thread`` with large remote-client resume payloads redacted.

    Rust mutates ``&mut Thread`` in place. Python protocol ``Thread`` values are
    frozen dataclasses, so this function preserves the same behavior contract by
    returning a redacted copy and leaving persisted/history inputs untouched.
    """

    return replace(thread, turns=tuple(_redact_turn(turn) for turn in thread.turns))


def redacted_mcp_tool_call_result() -> dict[str, JsonValue]:
    return {
        "content": [
            {
                "type": "text",
                "text": REDACTED_PAYLOAD,
            }
        ],
        "structuredContent": None,
        "_meta": None,
    }


def _redact_turn(turn: Turn) -> Turn:
    items: list[ThreadItem] = []
    for item in turn.items:
        redacted = _redact_item(item)
        if redacted is not None:
            items.append(redacted)
    return replace(turn, items=tuple(items))


def _redact_item(item: ThreadItem) -> ThreadItem | None:
    if item.type == "imageGeneration":
        return None
    if item.type != "mcpToolCall":
        return item

    fields = copy.deepcopy(dict(item.fields or {}))
    fields["arguments"] = REDACTED_PAYLOAD
    if fields.get("result") is not None:
        fields["result"] = redacted_mcp_tool_call_result()
    error = fields.get("error")
    if error is not None:
        fields["error"] = _redacted_error(error)
    return ThreadItem("mcpToolCall", fields)


def _redacted_error(error: JsonValue) -> JsonValue:
    if isinstance(error, dict):
        redacted = dict(error)
        redacted["message"] = REDACTED_PAYLOAD
        return redacted
    if hasattr(error, "to_mapping"):
        redacted = dict(error.to_mapping())
        redacted["message"] = REDACTED_PAYLOAD
        return redacted
    return {"message": REDACTED_PAYLOAD}


__all__ = [
    "CHATGPT_REMOTE_CLIENT_NAMES",
    "REDACTED_PAYLOAD",
    "redact_thread_resume_payloads",
    "redacted_mcp_tool_call_result",
    "should_redact_thread_resume_payloads",
]
