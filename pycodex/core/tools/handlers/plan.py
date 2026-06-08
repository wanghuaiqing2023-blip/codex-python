"""Update-plan tool handler ported from Codex core."""

from __future__ import annotations

import json
import inspect
from dataclasses import dataclass
from typing import Any, Callable

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import EventMsg, ResponseInputItem, ToolName, UpdatePlanArgs

JsonValue = Any

PLAN_UPDATED_MESSAGE = "Plan updated"
UPDATE_PLAN_TOOL_NAME = "update_plan"

PlanUpdateCallback = Callable[[UpdatePlanArgs], None]


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


@dataclass(frozen=True)
class PlanToolOutput:
    def log_preview(self) -> str:
        return PLAN_UPDATED_MESSAGE

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        if not isinstance(call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return FunctionToolOutput.from_text(PLAN_UPDATED_MESSAGE, True).to_response_item(
            call_id,
            payload,
        )

    def code_mode_result(self, payload: ToolPayload) -> dict[str, JsonValue]:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return {}


class PlanHandler:
    def __init__(self, on_plan_update: PlanUpdateCallback | None = None) -> None:
        if on_plan_update is not None and not callable(on_plan_update):
            raise TypeError("on_plan_update must be callable or None")
        self._on_plan_update = on_plan_update

    def tool_name(self) -> ToolName:
        return ToolName.plain(UPDATE_PLAN_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_update_plan_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(
        self,
        invocation_or_payload: Any,
        *,
        collaboration_mode: Any = None,
    ) -> PlanToolOutput:
        turn = getattr(invocation_or_payload, "turn", None)
        if collaboration_mode is None and turn is not None:
            collaboration_mode = getattr(turn, "collaboration_mode", None)
        if _is_plan_mode(collaboration_mode):
            raise FunctionCallError.respond_to_model(
                "update_plan is a TODO/checklist tool and is not allowed in Plan mode"
            )

        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model(
                "update_plan handler received unsupported payload"
            )
        arguments = payload.arguments
        if arguments is None:
            raise FunctionCallError.respond_to_model(
                "update_plan handler received unsupported payload"
            )

        args = parse_update_plan_arguments(arguments)
        if self._on_plan_update is not None:
            self._on_plan_update(args)
        sender = getattr(getattr(invocation_or_payload, "session", None), "send_event", None)
        if callable(sender):
            result = sender(turn, EventMsg.with_payload("plan_update", args))
            if inspect.isawaitable(result):
                return _await_plan_update_event(result)
        return PlanToolOutput()


async def _await_plan_update_event(result: Any) -> PlanToolOutput:
    await result
    return PlanToolOutput()


def parse_update_plan_arguments(arguments: str) -> UpdatePlanArgs:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    try:
        decoded = json.loads(arguments)
        return UpdatePlanArgs.from_mapping(decoded)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise FunctionCallError.respond_to_model(
            f"failed to parse function arguments: {err}"
        ) from err


def _is_plan_mode(value: Any) -> bool:
    if value is None:
        return False
    if value == "plan":
        return True
    mode = getattr(value, "mode", value)
    raw = getattr(mode, "value", mode)
    return raw == "plan"


__all__ = [
    "PLAN_UPDATED_MESSAGE",
    "UPDATE_PLAN_TOOL_NAME",
    "PlanHandler",
    "PlanToolOutput",
    "PlanUpdateCallback",
    "create_update_plan_tool",
    "parse_update_plan_arguments",
]
