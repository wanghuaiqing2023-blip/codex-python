"""Tool specification for the Rust ``test_sync_spec`` module."""

from __future__ import annotations

from typing import Any

JsonValue = Any
TEST_SYNC_TOOL_NAME = "test_sync_tool"


def create_test_sync_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": TEST_SYNC_TOOL_NAME,
        "description": "Internal synchronization helper used by Codex integration tests.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "sleep_before_ms": {
                    "type": "number",
                    "description": "Optional delay in milliseconds before any other action",
                },
                "sleep_after_ms": {
                    "type": "number",
                    "description": "Optional delay in milliseconds after completing the barrier",
                },
                "barrier": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Identifier shared by concurrent calls that should rendezvous"},
                        "participants": {"type": "number", "description": "Number of tool calls that must arrive before the barrier opens"},
                        "timeout_ms": {"type": "number", "description": "Maximum time in milliseconds to wait at the barrier"},
                    },
                    "required": ["id", "participants"],
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    }


__all__ = ["TEST_SYNC_TOOL_NAME", "create_test_sync_tool"]
