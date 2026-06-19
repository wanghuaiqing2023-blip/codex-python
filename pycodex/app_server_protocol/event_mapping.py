"""Core event-to-app-server notification projections.

Ported from ``codex-rs/app-server-protocol/src/protocol/event_mapping.rs``.
The Rust module is intentionally stateless: it converts one supported core
``EventMsg`` into the corresponding v2 ``ServerNotification`` payload. Python
keeps the same boundary and accepts either typed protocol events or compatible
mapping/duck-typed payloads from neighboring modules.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .item import (
    AgentMessageDeltaNotification,
    CollabAgentState,
    CollabAgentTool,
    CollabAgentToolCallStatus,
    CommandExecutionOutputDeltaNotification,
    DynamicToolCallOutputContentItem,
    DynamicToolCallStatus,
    FileChangePatchUpdatedNotification,
    ItemCompletedNotification,
    ItemStartedNotification,
    PlanDeltaNotification,
    ReasoningSummaryPartAddedNotification,
    ReasoningSummaryTextDeltaNotification,
    ReasoningTextDeltaNotification,
    TerminalInteractionNotification,
    ThreadItem,
)
from .item_builders import (
    ServerNotification,
    build_command_execution_begin_item,
    build_command_execution_end_item,
    convert_patch_changes,
)

JsonValue = Any


def item_event_to_server_notification(msg: JsonValue, thread_id: str, turn_id: str) -> ServerNotification:
    """Build the v2 app-server notification for a single supported core event."""

    event_type, payload = _event_parts(msg)
    thread_id = str(thread_id)
    turn_id = str(turn_id)

    if event_type == "dynamic_tool_call_response":
        status = DynamicToolCallStatus.COMPLETED if _bool(_get(payload, "success")) else DynamicToolCallStatus.FAILED
        duration_ms = _duration_ms(_get(payload, "duration", default=None))
        item = ThreadItem(
            "dynamicToolCall",
            {
                "id": _str(_get(payload, "call_id", "callId"), "call_id"),
                "namespace": _optional_str(_get(payload, "namespace", default=None), "namespace"),
                "tool": _str(_get(payload, "tool"), "tool"),
                "arguments": _get(payload, "arguments", default=None),
                "status": status.value,
                "contentItems": [_dynamic_content_item(item).to_mapping() for item in _sequence(_get(payload, "content_items", "contentItems", default=()))],
                "success": _bool(_get(payload, "success")),
                "durationMs": duration_ms,
            },
        )
        notification = ItemCompletedNotification(
            thread_id=thread_id,
            turn_id=_optional_str(_get(payload, "turn_id", "turnId", default=None), "turn_id") or turn_id,
            item=item,
            completed_at_ms=_int(_get(payload, "completed_at_ms", "completedAtMs", default=0), "completed_at_ms"),
        )
        return ServerNotification("ItemCompleted", notification)

    if event_type == "collab_agent_spawn_begin":
        item = _collab_item(
            payload,
            tool=CollabAgentTool.SPAWN_AGENT,
            status=CollabAgentToolCallStatus.IN_PROGRESS,
            receiver_thread_ids=(),
            prompt=_optional_str(_get(payload, "prompt", default=None), "prompt"),
            model=_optional_str(_get(payload, "model", default=None), "model"),
            reasoning_effort=_enum_value(_get(payload, "reasoning_effort", "reasoningEffort", default=None)),
        )
        return ServerNotification("ItemStarted", _item_started(thread_id, turn_id, item, _started_at(payload)))

    if event_type == "collab_agent_spawn_end":
        receiver = _optional_thread_id(_get(payload, "new_thread_id", "newThreadId", default=None))
        agent_status = _agent_status(_get(payload, "status"))
        status = CollabAgentToolCallStatus.COMPLETED if receiver is not None and not _agent_failed(agent_status) else CollabAgentToolCallStatus.FAILED
        item = _collab_item(
            payload,
            tool=CollabAgentTool.SPAWN_AGENT,
            status=status,
            receiver_thread_ids=() if receiver is None else (receiver,),
            prompt=_optional_str(_get(payload, "prompt", default=None), "prompt"),
            model=_optional_str(_get(payload, "model", default=None), "model"),
            reasoning_effort=_enum_value(_get(payload, "reasoning_effort", "reasoningEffort", default=None)),
            agents_states={} if receiver is None else {receiver: _collab_state(agent_status)},
        )
        return ServerNotification("ItemCompleted", _item_completed(thread_id, turn_id, item, _completed_at(payload)))

    if event_type == "collab_agent_interaction_begin":
        receiver = _thread_id(_get(payload, "receiver_thread_id", "receiverThreadId"))
        item = _collab_item(
            payload,
            tool=CollabAgentTool.SEND_INPUT,
            status=CollabAgentToolCallStatus.IN_PROGRESS,
            receiver_thread_ids=(receiver,),
            prompt=_optional_str(_get(payload, "prompt", default=None), "prompt"),
        )
        return ServerNotification("ItemStarted", _item_started(thread_id, turn_id, item, _started_at(payload)))

    if event_type == "collab_agent_interaction_end":
        receiver = _thread_id(_get(payload, "receiver_thread_id", "receiverThreadId"))
        agent_status = _agent_status(_get(payload, "status"))
        item = _collab_item(
            payload,
            tool=CollabAgentTool.SEND_INPUT,
            status=_completed_or_failed(agent_status),
            receiver_thread_ids=(receiver,),
            prompt=_optional_str(_get(payload, "prompt", default=None), "prompt"),
            agents_states={receiver: _collab_state(agent_status)},
        )
        return ServerNotification("ItemCompleted", _item_completed(thread_id, turn_id, item, _completed_at(payload)))

    if event_type == "collab_waiting_begin":
        receiver_thread_ids = tuple(_thread_id(item) for item in _sequence(_get(payload, "receiver_thread_ids", "receiverThreadIds", default=())))
        item = _collab_item(payload, tool=CollabAgentTool.WAIT, status=CollabAgentToolCallStatus.IN_PROGRESS, receiver_thread_ids=receiver_thread_ids)
        return ServerNotification("ItemStarted", _item_started(thread_id, turn_id, item, _started_at(payload)))

    if event_type == "collab_waiting_end":
        statuses = _status_map(_get(payload, "statuses"))
        status = CollabAgentToolCallStatus.FAILED if any(_agent_failed(item) for item in statuses.values()) else CollabAgentToolCallStatus.COMPLETED
        item = _collab_item(
            payload,
            tool=CollabAgentTool.WAIT,
            status=status,
            receiver_thread_ids=tuple(statuses.keys()),
            agents_states={id_: _collab_state(agent_status) for id_, agent_status in statuses.items()},
        )
        return ServerNotification("ItemCompleted", _item_completed(thread_id, turn_id, item, _completed_at(payload)))

    if event_type == "collab_close_begin":
        receiver = _thread_id(_get(payload, "receiver_thread_id", "receiverThreadId"))
        item = _collab_item(payload, tool=CollabAgentTool.CLOSE_AGENT, status=CollabAgentToolCallStatus.IN_PROGRESS, receiver_thread_ids=(receiver,))
        return ServerNotification("ItemStarted", _item_started(thread_id, turn_id, item, _started_at(payload)))

    if event_type == "collab_close_end":
        receiver = _thread_id(_get(payload, "receiver_thread_id", "receiverThreadId"))
        agent_status = _agent_status(_get(payload, "status"))
        item = _collab_item(
            payload,
            tool=CollabAgentTool.CLOSE_AGENT,
            status=_completed_or_failed(agent_status),
            receiver_thread_ids=(receiver,),
            agents_states={receiver: _collab_state(agent_status)},
        )
        return ServerNotification("ItemCompleted", _item_completed(thread_id, turn_id, item, _completed_at(payload)))

    if event_type == "collab_resume_begin":
        receiver = _thread_id(_get(payload, "receiver_thread_id", "receiverThreadId"))
        item = _collab_item(payload, tool=CollabAgentTool.RESUME_AGENT, status=CollabAgentToolCallStatus.IN_PROGRESS, receiver_thread_ids=(receiver,))
        return ServerNotification("ItemStarted", _item_started(thread_id, turn_id, item, _started_at(payload)))

    if event_type == "collab_resume_end":
        receiver = _thread_id(_get(payload, "receiver_thread_id", "receiverThreadId"))
        agent_status = _agent_status(_get(payload, "status"))
        item = _collab_item(
            payload,
            tool=CollabAgentTool.RESUME_AGENT,
            status=_completed_or_failed(agent_status),
            receiver_thread_ids=(receiver,),
            agents_states={receiver: _collab_state(agent_status)},
        )
        return ServerNotification("ItemCompleted", _item_completed(thread_id, turn_id, item, _completed_at(payload)))

    if event_type == "agent_message_content_delta":
        return ServerNotification("AgentMessageDelta", AgentMessageDeltaNotification(thread_id, turn_id, _str(_get(payload, "item_id", "itemId"), "item_id"), _str(_get(payload, "delta"), "delta")))

    if event_type == "plan_delta":
        return ServerNotification("PlanDelta", PlanDeltaNotification(thread_id, turn_id, _str(_get(payload, "item_id", "itemId"), "item_id"), _str(_get(payload, "delta"), "delta")))

    if event_type == "reasoning_content_delta":
        return ServerNotification(
            "ReasoningSummaryTextDelta",
            ReasoningSummaryTextDeltaNotification(
                thread_id,
                turn_id,
                _str(_get(payload, "item_id", "itemId"), "item_id"),
                _str(_get(payload, "delta"), "delta"),
                _int(_get(payload, "summary_index", "summaryIndex", default=0), "summary_index"),
            ),
        )

    if event_type == "reasoning_raw_content_delta":
        return ServerNotification(
            "ReasoningTextDelta",
            ReasoningTextDeltaNotification(
                thread_id,
                turn_id,
                _str(_get(payload, "item_id", "itemId"), "item_id"),
                _str(_get(payload, "delta"), "delta"),
                _int(_get(payload, "content_index", "contentIndex", default=0), "content_index"),
            ),
        )

    if event_type == "agent_reasoning_section_break":
        return ServerNotification(
            "ReasoningSummaryPartAdded",
            ReasoningSummaryPartAddedNotification(
                thread_id,
                turn_id,
                _str(_get(payload, "item_id", "itemId", default=""), "item_id"),
                _int(_get(payload, "summary_index", "summaryIndex", default=0), "summary_index"),
            ),
        )

    if event_type == "item_started":
        return ServerNotification(
            "ItemStarted",
            _item_started(thread_id, turn_id, _thread_item(_get(payload, "item")), _started_at(payload)),
        )

    if event_type == "item_completed":
        return ServerNotification(
            "ItemCompleted",
            _item_completed(thread_id, turn_id, _thread_item(_get(payload, "item")), _completed_at(payload)),
        )

    if event_type == "patch_apply_updated":
        return ServerNotification(
            "FileChangePatchUpdated",
            FileChangePatchUpdatedNotification(
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=_str(_get(payload, "call_id", "callId"), "call_id"),
                changes=tuple(convert_patch_changes(_get(payload, "changes"))),
            ),
        )

    if event_type == "exec_command_begin":
        return ServerNotification(
            "ItemStarted",
            _item_started(thread_id, turn_id, build_command_execution_begin_item(payload), _started_at(payload)),
        )

    if event_type == "exec_command_output_delta":
        chunk = _get(payload, "chunk")
        return ServerNotification(
            "CommandExecutionOutputDelta",
            CommandExecutionOutputDeltaNotification(
                thread_id,
                turn_id,
                _str(_get(payload, "call_id", "callId"), "call_id"),
                _decode_lossy(chunk),
            ),
        )

    if event_type == "terminal_interaction":
        return ServerNotification(
            "TerminalInteraction",
            TerminalInteractionNotification(
                thread_id,
                turn_id,
                _str(_get(payload, "call_id", "callId"), "call_id"),
                _str(_get(payload, "process_id", "processId"), "process_id"),
                _str(_get(payload, "stdin"), "stdin"),
            ),
        )

    if event_type == "exec_command_end":
        return ServerNotification(
            "ItemCompleted",
            _item_completed(thread_id, turn_id, build_command_execution_end_item(payload), _completed_at(payload)),
        )

    raise ValueError(f"unsupported item event: {event_type}")


def _collab_item(
    payload: JsonValue,
    *,
    tool: CollabAgentTool,
    status: CollabAgentToolCallStatus,
    receiver_thread_ids: tuple[str, ...],
    prompt: str | None = None,
    model: str | None = None,
    reasoning_effort: JsonValue | None = None,
    agents_states: Mapping[str, CollabAgentState] | None = None,
) -> ThreadItem:
    return ThreadItem(
        "collabAgentToolCall",
        {
            "id": _str(_get(payload, "call_id", "callId"), "call_id"),
            "tool": tool.value,
            "status": status.value,
            "senderThreadId": _thread_id(_get(payload, "sender_thread_id", "senderThreadId")),
            "receiverThreadIds": list(receiver_thread_ids),
            "prompt": prompt,
            "model": model,
            "reasoningEffort": reasoning_effort,
            "agentsStates": {id_: state.to_mapping() for id_, state in (agents_states or {}).items()},
        },
    )


def _item_started(thread_id: str, turn_id: str, item: ThreadItem, started_at_ms: int) -> ItemStartedNotification:
    return ItemStartedNotification(item=item, thread_id=thread_id, turn_id=turn_id, started_at_ms=started_at_ms)


def _item_completed(thread_id: str, turn_id: str, item: ThreadItem, completed_at_ms: int) -> ItemCompletedNotification:
    return ItemCompletedNotification(item=item, thread_id=thread_id, turn_id=turn_id, completed_at_ms=completed_at_ms)


def _event_parts(msg: JsonValue) -> tuple[str, JsonValue]:
    if isinstance(msg, Mapping):
        event_type = msg.get("type")
        payload = msg.get("payload", None)
        if payload is None:
            payload = {key: value for key, value in msg.items() if key != "type"}
        return _str(event_type, "type"), payload
    event_type = getattr(msg, "type", None)
    if event_type is None:
        kind = getattr(msg, "kind", None)
        event_type = kind() if callable(kind) else kind
    return _str(event_type, "type"), getattr(msg, "payload", None)


def _thread_item(value: JsonValue) -> ThreadItem:
    if isinstance(value, ThreadItem):
        return value
    if isinstance(value, Mapping):
        return ThreadItem.from_mapping(value)
    mapping = _to_mapping(value)
    if isinstance(mapping, Mapping):
        return ThreadItem.from_mapping(mapping)
    raise TypeError("item must be a ThreadItem-compatible mapping")


def _dynamic_content_item(value: JsonValue) -> DynamicToolCallOutputContentItem:
    if isinstance(value, DynamicToolCallOutputContentItem):
        return value
    data = _to_mapping(value)
    if isinstance(data, Mapping):
        return DynamicToolCallOutputContentItem.from_mapping(data)
    raise TypeError("dynamic content item must be a tagged mapping")


def _status_map(value: JsonValue) -> dict[str, JsonValue]:
    data = _mapping(value, "statuses")
    return {_thread_id(key): _agent_status(status) for key, status in data.items()}


def _agent_status(value: JsonValue) -> JsonValue:
    if hasattr(value, "type"):
        return value
    if isinstance(value, Mapping):
        if "type" in value:
            return {"type": _str(value["type"], "status.type"), "message": value.get("message")}
        if len(value) == 1:
            status_type, message = next(iter(value.items()))
            return {"type": _snake_status(str(status_type)), "message": message if isinstance(message, str) else None}
    if isinstance(value, str):
        return {"type": _snake_status(value), "message": None}
    raise TypeError("agent status must be a status object, string, or mapping")


def _collab_state(value: JsonValue) -> CollabAgentState:
    status_type = _status_type(value)
    message = _status_message(value)
    return CollabAgentState(status=_camel_status(status_type), message=message)


def _completed_or_failed(value: JsonValue) -> CollabAgentToolCallStatus:
    return CollabAgentToolCallStatus.FAILED if _agent_failed(value) else CollabAgentToolCallStatus.COMPLETED


def _agent_failed(value: JsonValue) -> bool:
    return _status_type(value) in {"errored", "not_found"}


def _status_type(value: JsonValue) -> str:
    raw = getattr(value, "type", None)
    if raw is None and isinstance(value, Mapping):
        raw = value.get("type")
    if raw is None:
        raw = value
    return _snake_status(str(raw))


def _status_message(value: JsonValue) -> str | None:
    message = getattr(value, "message", None)
    if isinstance(value, Mapping):
        message = value.get("message", message)
    return message if isinstance(message, str) else None


def _snake_status(value: str) -> str:
    aliases = {
        "pendingInit": "pending_init",
        "notFound": "not_found",
        "pending_init": "pending_init",
        "not_found": "not_found",
    }
    return aliases.get(value, value)


def _camel_status(value: str) -> str:
    return {"pending_init": "pendingInit", "not_found": "notFound"}.get(_snake_status(value), _snake_status(value))


def _thread_id(value: JsonValue) -> str:
    return _str(_thread_id_raw(value), "thread_id")


def _optional_thread_id(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _thread_id(value)


def _thread_id_raw(value: JsonValue) -> JsonValue:
    to_json = getattr(value, "to_json", None)
    if callable(to_json):
        return to_json()
    return value


def _started_at(payload: JsonValue) -> int:
    return _int(_get(payload, "started_at_ms", "startedAtMs", default=0), "started_at_ms")


def _completed_at(payload: JsonValue) -> int:
    return _int(_get(payload, "completed_at_ms", "completedAtMs", default=0), "completed_at_ms")


def _duration_ms(value: JsonValue) -> int | None:
    if value is None:
        return None
    total = getattr(value, "total_seconds", None)
    if callable(total):
        return int(total() * 1000)
    if isinstance(value, Mapping):
        raw = _get(value, "duration_ms", "durationMs", "millis", default=None)
        return _int(raw, "duration_ms") if raw is not None else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return None


def _decode_lossy(value: JsonValue) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, bytearray):
        return bytes(value).decode("utf-8", errors="replace")
    return _str(value, "chunk")


def _get(value: JsonValue, *names: str, default: JsonValue = ...):
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if not isinstance(value, Mapping) and hasattr(value, name):
            return getattr(value, name)
    if default is not ...:
        return default
    label = " or ".join(names)
    raise KeyError(label)


def _mapping(value: JsonValue, label: str) -> Mapping[str, JsonValue]:
    data = _to_mapping(value)
    if not isinstance(data, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return data


def _sequence(value: JsonValue) -> tuple[JsonValue, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or isinstance(value, Mapping):
        raise TypeError("value must be a sequence")
    return tuple(value)


def _to_mapping(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return value
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        return to_mapping()
    if is_dataclass(value):
        return {name: getattr(value, name) for name in value.__dataclass_fields__}
    return value


def _enum_value(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    return value


def _optional_str(value: JsonValue, field: str) -> str | None:
    if value is None:
        return None
    return _str(value, field)


def _str(value: JsonValue, field: str) -> str:
    value = _enum_value(value)
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _int(value: JsonValue, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    return value


def _bool(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise TypeError("value must be a boolean")
    return value
