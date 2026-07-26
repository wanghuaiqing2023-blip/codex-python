"""Tool specification for the Rust ``plan_spec`` module."""

from __future__ import annotations

from typing import Any

JsonValue = Any
UPDATE_PLAN_TOOL_NAME = "update_plan"


def create_update_plan_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": UPDATE_PLAN_TOOL_NAME,
        "description": (
            "Updates the task plan.\n"
            "Provide an optional explanation and a list of plan items, each with a step and status.\n"
            "At most one step can be in_progress at a time.\n"
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "explanation": {"type": "string"},
                "plan": {
                    "type": "array",
                    "description": "The list of steps",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string"},
                            "status": {
                                "type": "string",
                                "description": "One of: pending, in_progress, completed",
                            },
                        },
                        "required": ["step", "status"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["plan"],
            "additionalProperties": False,
        },
    }


__all__ = ["UPDATE_PLAN_TOOL_NAME", "create_update_plan_tool"]
