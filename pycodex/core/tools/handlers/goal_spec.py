"""Tool specifications for the Rust ``goal_spec`` module."""

from __future__ import annotations

from typing import Any

JsonValue = Any

GET_GOAL_TOOL_NAME = "get_goal"
CREATE_GOAL_TOOL_NAME = "create_goal"
UPDATE_GOAL_TOOL_NAME = "update_goal"


def create_get_goal_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": GET_GOAL_TOOL_NAME,
        "description": "Get the current goal for this thread, including status, budgets, token and elapsed-time usage, and remaining token budget.",
        "strict": False,
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    }


def create_create_goal_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": CREATE_GOAL_TOOL_NAME,
        "description": (
            "Create a goal only when explicitly requested by the user or system/developer instructions; do not infer goals from ordinary tasks.\n"
            f"Set token_budget only when an explicit token budget is requested. Fails if a goal exists; use {UPDATE_GOAL_TOOL_NAME} only for status."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "Required. The concrete objective to start pursuing. This starts a new active goal only when no goal is currently defined; if a goal already exists, this tool fails.",
                },
                "token_budget": {
                    "type": "integer",
                    "description": "Optional positive token budget for the new active goal.",
                },
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
    }


def create_update_goal_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": UPDATE_GOAL_TOOL_NAME,
        "description": (
            "Update the existing goal.\nUse this tool only to mark the goal achieved or genuinely blocked.\n"
            "Set status to `complete` only when the objective has actually been achieved and no required work remains.\n"
            "Set status to `blocked` only when the same blocking condition has repeated for at least three consecutive goal turns, counting the original/user-triggered turn and any automatic continuations, and the agent cannot make meaningful progress without user input or an external-state change.\n"
            "If the user resumes a goal that was previously marked `blocked`, treat the resumed run as a fresh blocked audit. If the same blocking condition then repeats for at least three consecutive resumed goal turns, set status to `blocked` again.\n"
            "Once the blocked threshold is satisfied, do not keep reporting that you are still blocked while leaving the goal active; set status to `blocked`.\n"
            "Do not use `blocked` merely because the work is hard, slow, uncertain, incomplete, or would benefit from clarification.\n"
            "Do not mark a goal complete merely because its budget is nearly exhausted or because you are stopping work.\n"
            "You cannot use this tool to pause, resume, budget-limit, or usage-limit a goal; those status changes are controlled by the user or system.\n"
            "When marking a budgeted goal achieved with status `complete`, report the final token usage from the tool result to the user."
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["complete", "blocked"],
                    "description": "Required. Set to `complete` only when the objective is achieved and no required work remains. Set to `blocked` only after the same blocking condition has recurred for at least three consecutive goal turns and the agent is at an impasse. After a previously blocked goal is resumed, the resumed run starts a fresh blocked audit.",
                }
            },
            "required": ["status"],
            "additionalProperties": False,
        },
    }


__all__ = [
    "CREATE_GOAL_TOOL_NAME",
    "GET_GOAL_TOOL_NAME",
    "UPDATE_GOAL_TOOL_NAME",
    "create_create_goal_tool",
    "create_get_goal_tool",
    "create_update_goal_tool",
]
