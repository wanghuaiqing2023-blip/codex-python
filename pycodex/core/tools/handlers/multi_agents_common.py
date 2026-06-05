"""Shared multi-agent helper logic ported from Codex core."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import (
    AgentStatus,
    CollabAgentRef,
    CollabAgentStatusEntry,
    ResponseInputItem,
    ThreadId,
    UserInput,
)

JsonValue = Any

MIN_WAIT_TIMEOUT_MS = 1_000
DEFAULT_WAIT_TIMEOUT_MS = 30_000
MAX_WAIT_TIMEOUT_MS = 600_000


def function_arguments(payload: ToolPayload) -> str:
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    if payload.type == "function":
        return payload.arguments or ""
    raise FunctionCallError.respond_to_model("collab handler received unsupported payload")


def tool_output_json_text(value: JsonValue, tool_name: str) -> str:
    if not isinstance(tool_name, str):
        raise TypeError("tool_name must be a string")
    try:
        return json.dumps(_to_json_value(value), separators=(",", ":"))
    except (TypeError, ValueError) as err:
        return json.dumps(f"failed to serialize {tool_name} result: {err}")


def tool_output_response_item(
    call_id: str,
    payload: ToolPayload,
    value: JsonValue,
    success: bool | None,
    tool_name: str,
) -> ResponseInputItem:
    if not isinstance(call_id, str):
        raise TypeError("call_id must be a string")
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    if success is not None and not isinstance(success, bool):
        raise TypeError("success must be a bool or None")
    return FunctionToolOutput.from_text(
        tool_output_json_text(value, tool_name),
        success,
    ).to_response_item(call_id, payload)


def tool_output_code_mode_result(value: JsonValue, tool_name: str) -> JsonValue:
    if not isinstance(tool_name, str):
        raise TypeError("tool_name must be a string")
    try:
        return _to_json_value(value)
    except (TypeError, ValueError) as err:
        return f"failed to serialize {tool_name} result: {err}"


def build_wait_agent_statuses(
    statuses: Mapping[ThreadId, AgentStatus],
    receiver_agents: Iterable[CollabAgentRef],
) -> tuple[CollabAgentStatusEntry, ...]:
    if not isinstance(statuses, Mapping):
        raise TypeError("statuses must be a mapping")
    receiver_tuple = _receiver_agents_tuple(receiver_agents)
    if not statuses:
        return ()

    entries: list[CollabAgentStatusEntry] = []
    seen: set[ThreadId] = set()
    for receiver_agent in receiver_tuple:
        seen.add(receiver_agent.thread_id)
        status = statuses.get(receiver_agent.thread_id)
        if status is not None:
            entries.append(
                CollabAgentStatusEntry(
                    thread_id=receiver_agent.thread_id,
                    agent_nickname=receiver_agent.agent_nickname,
                    agent_role=receiver_agent.agent_role,
                    status=_agent_status(status),
                )
            )

    extras = [
        CollabAgentStatusEntry(
            thread_id=_thread_id(thread_id),
            agent_nickname=None,
            agent_role=None,
            status=_agent_status(status),
        )
        for thread_id, status in statuses.items()
        if thread_id not in seen
    ]
    extras.sort(key=lambda entry: str(entry.thread_id))
    return tuple(entries + extras)


def parse_collab_input(
    message: str | None,
    items: Iterable[UserInput | Mapping[str, JsonValue]] | None,
) -> tuple[UserInput, ...]:
    if message is not None and not isinstance(message, str):
        raise TypeError("message must be a string or None")
    if message is not None and items is not None:
        raise FunctionCallError.respond_to_model("Provide either message or items, but not both")
    if message is None and items is None:
        raise FunctionCallError.respond_to_model("Provide one of: message or items")
    if message is not None:
        if message.strip() == "":
            raise FunctionCallError.respond_to_model("Empty message can't be sent to an agent")
        return (UserInput.text_input(message),)

    item_tuple = _user_input_tuple(items)
    if not item_tuple:
        raise FunctionCallError.respond_to_model("Items can't be empty")
    return item_tuple


def reject_full_fork_spawn_overrides(
    agent_type: str | None,
    model: str | None,
    reasoning_effort: str | None,
) -> None:
    if agent_type is not None and not isinstance(agent_type, str):
        raise TypeError("agent_type must be a string or None")
    if model is not None and not isinstance(model, str):
        raise TypeError("model must be a string or None")
    if reasoning_effort is not None and not isinstance(reasoning_effort, str):
        raise TypeError("reasoning_effort must be a string or None")
    if agent_type is not None or model is not None or reasoning_effort is not None:
        raise FunctionCallError.respond_to_model(
            "not supported: "
            "Full-history forked agents inherit the parent agent type, model, and reasoning effort; "
            "omit agent_type, model, and reasoning_effort, or spawn without a full-history fork."
        )


def _receiver_agents_tuple(values: Iterable[CollabAgentRef]) -> tuple[CollabAgentRef, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError("receiver_agents must be an iterable of CollabAgentRef values")
    result: list[CollabAgentRef] = []
    for value in values:
        if isinstance(value, CollabAgentRef):
            result.append(value)
        else:
            result.append(CollabAgentRef.from_mapping(value))
    return tuple(result)


def _user_input_tuple(
    values: Iterable[UserInput | Mapping[str, JsonValue]] | None,
) -> tuple[UserInput, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError("items must be an iterable of UserInput values")
    result: list[UserInput] = []
    for value in values:
        if isinstance(value, UserInput):
            result.append(value)
        else:
            result.append(UserInput.from_mapping(value))
    return tuple(result)


def _thread_id(value: ThreadId) -> ThreadId:
    if not isinstance(value, ThreadId):
        raise TypeError("statuses keys must be ThreadId")
    return value


def _agent_status(value: AgentStatus) -> AgentStatus:
    if isinstance(value, AgentStatus):
        return value
    return AgentStatus.from_mapping(value)


def _to_json_value(value: JsonValue) -> JsonValue:
    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return value.to_mapping()
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    return value
