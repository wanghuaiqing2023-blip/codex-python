"""Thread-history reconstruction from persisted rollout items.

Ported from ``codex-rs/app-server-protocol/src/protocol/thread_history.rs``.
The module owns replaying core rollout/event entries into app-server v2
``Turn`` values. Python keeps the same reducer-shaped public surface while
accepting typed protocol events, mappings, and compatible duck-typed payloads.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from .event_mapping import item_event_to_server_notification
from .item import ThreadItem
from .item_builders import (
    build_command_execution_begin_item,
    build_command_execution_end_item,
    build_file_change_approval_request_item,
    build_file_change_begin_item,
    build_file_change_end_item,
    build_item_from_guardian_event,
)
from .thread_data import Turn, TurnError, TurnItemsView
from .turn import TurnStatus, UserInput

JsonValue = Any

_ITEM_EVENT_TYPES = {
    "collab_agent_spawn_begin",
    "collab_agent_spawn_end",
    "collab_agent_interaction_begin",
    "collab_agent_interaction_end",
    "collab_waiting_begin",
    "collab_waiting_end",
    "collab_close_begin",
    "collab_close_end",
    "collab_resume_begin",
    "collab_resume_end",
    "dynamic_tool_call_response",
}


def build_turns_from_rollout_items(items: Sequence[JsonValue]) -> list[Turn]:
    builder = ThreadHistoryBuilder()
    for item in items:
        builder.handle_rollout_item(item)
    return builder.finish()


@dataclass
class _PendingTurn:
    id: str
    items: list[ThreadItem] = field(default_factory=list)
    error: TurnError | None = None
    status: TurnStatus = TurnStatus.COMPLETED
    started_at: int | None = None
    completed_at: int | None = None
    duration_ms: int | None = None
    opened_explicitly: bool = False
    saw_compaction: bool = False
    rollout_start_index: int = 0

    def snapshot(self) -> Turn:
        return Turn(
            id=self.id,
            items=tuple(self.items),
            items_view=TurnItemsView.FULL,
            error=self.error,
            status=self.status.value,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_ms=self.duration_ms,
        )


class ThreadHistoryBuilder:
    def __init__(self) -> None:
        self.turns: list[Turn] = []
        self.current_turn: _PendingTurn | None = None
        self.next_item_index = 1
        self.current_rollout_index = 0
        self.next_rollout_index = 0

    def reset(self) -> None:
        self.__init__()

    def finish(self) -> list[Turn]:
        self.finish_current_turn()
        return list(self.turns)

    def active_turn_snapshot(self) -> Turn | None:
        if self.current_turn is not None:
            return self.current_turn.snapshot()
        return self.turns[-1] if self.turns else None

    def active_turn_position(self) -> int | None:
        if self.current_turn is not None:
            return len(self.turns)
        if not self.turns:
            return None
        return len(self.turns) - 1

    def has_active_turn(self) -> bool:
        return self.current_turn is not None

    def active_turn_id_if_explicit(self) -> str | None:
        if self.current_turn is not None and self.current_turn.opened_explicitly:
            return self.current_turn.id
        return None

    def active_turn_start_index(self) -> int | None:
        return self.current_turn.rollout_start_index if self.current_turn is not None else None

    def handle_rollout_item(self, item: JsonValue) -> None:
        self.current_rollout_index = self.next_rollout_index
        self.next_rollout_index += 1
        kind, payload = _rollout_parts(item)
        if kind in {"event_msg", "eventMsg", "EventMsg", "event"}:
            self.handle_event(payload)
        elif kind in {"compacted", "Compacted"}:
            self.handle_compacted(payload)
        elif kind in {"response_item", "responseItem", "ResponseItem"}:
            self.handle_response_item(payload)

    def handle_event(self, event: JsonValue) -> None:
        event_type, payload = _event_parts(event)
        if event_type == "user_message":
            self.handle_user_message(payload)
        elif event_type == "agent_message":
            self.handle_agent_message(_str(_get(payload, "message"), "message"), _get(payload, "phase", default=None), _get(payload, "memory_citation", "memoryCitation", default=None))
        elif event_type == "agent_reasoning":
            self.handle_agent_reasoning(payload)
        elif event_type == "agent_reasoning_raw_content":
            self.handle_agent_reasoning_raw_content(payload)
        elif event_type in {"web_search_begin", "web_search_end", "view_image_tool_call", "image_generation_begin", "image_generation_end"}:
            self._handle_simple_tool_event(event_type, payload)
        elif event_type == "exec_command_begin":
            self._upsert_by_payload_turn(payload, build_command_execution_begin_item(payload))
        elif event_type == "exec_command_end":
            self._upsert_by_payload_turn(payload, build_command_execution_end_item(payload))
        elif event_type == "guardian_assessment":
            self.handle_guardian_assessment(payload)
        elif event_type == "apply_patch_approval_request":
            self._upsert_by_payload_turn(payload, build_file_change_approval_request_item(payload))
        elif event_type == "patch_apply_begin":
            self._upsert_by_payload_turn(payload, build_file_change_begin_item(payload))
        elif event_type == "patch_apply_end":
            self._upsert_by_payload_turn(payload, build_file_change_end_item(payload))
        elif event_type == "dynamic_tool_call_request":
            self.handle_dynamic_tool_call_request(payload)
        elif event_type in _ITEM_EVENT_TYPES:
            self.handle_item_projection(event)
        elif event_type in {"mcp_tool_call_begin", "mcp_tool_call_end"}:
            self.handle_mcp_tool_call(event_type, payload)
        elif event_type in {"context_compacted"}:
            self.handle_context_compacted(payload)
        elif event_type == "entered_review_mode":
            self._append_generated_item("enteredReviewMode", {"review": _optional_str(_get(payload, "user_facing_hint", "userFacingHint", default=None), "review") or "Review requested."})
        elif event_type == "exited_review_mode":
            text = _review_output_text(_get(payload, "review_output", "reviewOutput", default=None))
            self._append_generated_item("exitedReviewMode", {"review": text})
        elif event_type == "item_started":
            self.handle_item_lifecycle(payload, started=True)
        elif event_type == "item_completed":
            self.handle_item_lifecycle(payload, started=False)
        elif event_type == "error":
            self.handle_error(payload)
        elif event_type == "thread_rolled_back":
            self.handle_thread_rollback(payload)
        elif event_type == "turn_aborted":
            self.handle_turn_aborted(payload)
        elif event_type == "turn_started":
            self.handle_turn_started(payload)
        elif event_type in {"turn_complete", "task_complete"}:
            self.handle_turn_complete(payload)

    def handle_response_item(self, item: JsonValue) -> None:
        data = _to_mapping(item)
        if not isinstance(data, Mapping) or data.get("role") != "user":
            return
        hook = _parse_hook_prompt_message(data)
        if hook is not None:
            self.ensure_turn().items.append(hook)

    def handle_user_message(self, payload: JsonValue) -> None:
        if self.current_turn is not None and not self.current_turn.opened_explicitly and not (self.current_turn.saw_compaction and not self.current_turn.items):
            self.finish_current_turn()
        turn = self.current_turn or self.new_turn(None)
        self.current_turn = None
        turn.items.append(ThreadItem.user_message(self.next_item_id(), self.build_user_inputs(payload)))
        self.current_turn = turn

    def handle_agent_message(self, text: str, phase: JsonValue | None = None, memory_citation: JsonValue | None = None) -> None:
        if not text:
            return
        self.ensure_turn().items.append(ThreadItem.agent_message(self.next_item_id(), text, phase=phase, memory_citation=memory_citation))

    def handle_agent_reasoning(self, payload: JsonValue) -> None:
        text = _str(_get(payload, "text"), "text")
        if not text:
            return
        turn = self.ensure_turn()
        if turn.items and turn.items[-1].type == "reasoning":
            fields = dict(turn.items[-1].fields or {})
            fields["summary"] = [*fields.get("summary", []), text]
            turn.items[-1] = ThreadItem("reasoning", fields)
        else:
            turn.items.append(ThreadItem.reasoning(self.next_item_id(), summary=(text,)))

    def handle_agent_reasoning_raw_content(self, payload: JsonValue) -> None:
        text = _str(_get(payload, "text"), "text")
        if not text:
            return
        turn = self.ensure_turn()
        if turn.items and turn.items[-1].type == "reasoning":
            fields = dict(turn.items[-1].fields or {})
            fields["content"] = [*fields.get("content", []), text]
            turn.items[-1] = ThreadItem("reasoning", fields)
        else:
            turn.items.append(ThreadItem.reasoning(self.next_item_id(), content=(text,)))

    def handle_item_lifecycle(self, payload: JsonValue, *, started: bool) -> None:
        item = _thread_item(_get(payload, "item"))
        if item.type != "plan":
            return
        if not (item.fields or {}).get("text"):
            return
        self.upsert_item_in_turn_id(_str(_get(payload, "turn_id", "turnId"), "turn_id"), item)

    def handle_item_projection(self, event: JsonValue) -> None:
        event_type, payload = _event_parts(event)
        turn_id = _optional_str(_get(payload, "turn_id", "turnId", default=None), "turn_id") or ""
        notification = item_event_to_server_notification(event, "", turn_id)
        item = getattr(notification.payload, "item", None)
        if not isinstance(item, ThreadItem):
            return
        if turn_id:
            self.upsert_item_in_turn_id(turn_id, item)
        else:
            self.upsert_item_in_current_turn(item)

    def handle_dynamic_tool_call_request(self, payload: JsonValue) -> None:
        item = ThreadItem(
            "dynamicToolCall",
            {
                "id": _str(_get(payload, "call_id", "callId"), "call_id"),
                "namespace": _get(payload, "namespace", default=None),
                "tool": _str(_get(payload, "tool"), "tool"),
                "arguments": _get(payload, "arguments", default=None),
                "status": "inProgress",
                "contentItems": None,
                "success": None,
                "durationMs": None,
            },
        )
        self._upsert_by_payload_turn(payload, item)

    def handle_mcp_tool_call(self, event_type: str, payload: JsonValue) -> None:
        invocation = _get(payload, "invocation", default={})
        result = _get(payload, "result", default=None)
        success = event_type == "mcp_tool_call_begin" or _is_success_result(payload)
        item = ThreadItem(
            "mcpToolCall",
            {
                "id": _str(_get(payload, "call_id", "callId"), "call_id"),
                "server": _str(_get(invocation, "server", default=_get(payload, "server", default="")), "server"),
                "tool": _str(_get(invocation, "tool", default=_get(payload, "tool", default="")), "tool"),
                "status": "inProgress" if event_type.endswith("_begin") else ("completed" if success else "failed"),
                "arguments": _get(invocation, "arguments", default=None),
                "mcpAppResourceUri": _get(payload, "mcp_app_resource_uri", "mcpAppResourceUri", default=None),
                "pluginId": _get(payload, "plugin_id", "pluginId", default=None),
                "result": result if success and event_type.endswith("_end") else None,
                "error": None if success else {"message": str(result)},
                "durationMs": _duration_ms(_get(payload, "duration", default=None)),
            },
        )
        self.upsert_item_in_current_turn(item)

    def handle_guardian_assessment(self, payload: JsonValue) -> None:
        status = _variant_type(_get(payload, "status", default=""))
        command_status = {
            "inProgress": "inProgress",
            "in_progress": "inProgress",
            "denied": "declined",
            "aborted": "declined",
            "timedOut": "failed",
            "timed_out": "failed",
        }.get(status)
        if command_status is None:
            return
        item = build_item_from_guardian_event(payload, command_status)
        if item is not None:
            self._upsert_by_payload_turn(payload, item)

    def handle_context_compacted(self, _payload: JsonValue) -> None:
        self.ensure_turn().items.append(ThreadItem.context_compaction(self.next_item_id()))

    def handle_error(self, payload: JsonValue) -> None:
        if not _affects_turn_status(payload):
            return
        if self.current_turn is None:
            return
        self.current_turn.status = TurnStatus.FAILED
        self.current_turn.error = TurnError(
            message=_str(_get(payload, "message"), "message"),
            codex_error_info=_get(payload, "codex_error_info", "codexErrorInfo", default=None),
            additional_details=None,
        )

    def handle_turn_aborted(self, payload: JsonValue) -> None:
        turn_id = _optional_str(_get(payload, "turn_id", "turnId", default=None), "turn_id")

        def apply(turn: _PendingTurn | Turn) -> None:
            if isinstance(turn, _PendingTurn):
                turn.status = TurnStatus.INTERRUPTED
                turn.completed_at = _optional_int(_get(payload, "completed_at", "completedAt", default=None), "completed_at")
                turn.duration_ms = _optional_int(_get(payload, "duration_ms", "durationMs", default=None), "duration_ms")

        if turn_id and self.current_turn is not None and self.current_turn.id == turn_id:
            apply(self.current_turn)
            return
        if turn_id:
            self._replace_finished_turn_status(turn_id, TurnStatus.INTERRUPTED, payload)
            return
        if self.current_turn is not None:
            apply(self.current_turn)

    def handle_turn_started(self, payload: JsonValue) -> None:
        self.finish_current_turn()
        self.current_turn = self.new_turn(_str(_get(payload, "turn_id", "turnId"), "turn_id"))
        self.current_turn.status = TurnStatus.IN_PROGRESS
        self.current_turn.started_at = _optional_int(_get(payload, "started_at", "startedAt", default=None), "started_at")
        self.current_turn.opened_explicitly = True

    def handle_turn_complete(self, payload: JsonValue) -> None:
        turn_id = _str(_get(payload, "turn_id", "turnId"), "turn_id")
        if self.current_turn is not None and self.current_turn.id == turn_id:
            self._mark_pending_complete(self.current_turn, payload)
            self.finish_current_turn()
            return
        if self._replace_finished_turn_status(turn_id, TurnStatus.COMPLETED, payload, only_if_non_failed=True):
            return
        if self.current_turn is not None:
            self._mark_pending_complete(self.current_turn, payload)
            self.finish_current_turn()

    def handle_compacted(self, _payload: JsonValue) -> None:
        self.ensure_turn().saw_compaction = True

    def handle_thread_rollback(self, payload: JsonValue) -> None:
        self.finish_current_turn()
        count = _int(_get(payload, "num_turns", "numTurns"), "num_turns")
        if count >= len(self.turns):
            self.turns.clear()
        else:
            del self.turns[len(self.turns) - count :]
        self.next_item_index = sum(len(turn.items) for turn in self.turns) + 1

    def finish_current_turn(self) -> None:
        if self.current_turn is None:
            return
        turn = self.current_turn
        self.current_turn = None
        if not turn.items and not turn.opened_explicitly and not turn.saw_compaction:
            return
        self.turns.append(turn.snapshot())

    def new_turn(self, id: str | None) -> _PendingTurn:
        if id is None:
            id = str(uuid4()) if self.next_rollout_index == 0 else f"rollout-{self.current_rollout_index}"
        return _PendingTurn(id=id, rollout_start_index=self.current_rollout_index)

    def ensure_turn(self) -> _PendingTurn:
        if self.current_turn is None:
            self.current_turn = self.new_turn(None)
        return self.current_turn

    def upsert_item_in_turn_id(self, turn_id: str, item: ThreadItem) -> None:
        if self.current_turn is not None and self.current_turn.id == turn_id:
            _upsert_turn_item(self.current_turn.items, item)
            return
        for idx, turn in enumerate(self.turns):
            if turn.id == turn_id:
                items = list(turn.items)
                _upsert_turn_item(items, item)
                self.turns[idx] = _turn_with(turn, items=tuple(items))
                return

    def upsert_item_in_current_turn(self, item: ThreadItem) -> None:
        _upsert_turn_item(self.ensure_turn().items, item)

    def next_item_id(self) -> str:
        id_ = f"item-{self.next_item_index}"
        self.next_item_index += 1
        return id_

    def build_user_inputs(self, payload: JsonValue) -> list[UserInput]:
        content: list[UserInput] = []
        message = _optional_str(_get(payload, "message", default=None), "message")
        if message is not None and message.strip():
            content.append(UserInput.text(message, _sequence(_get(payload, "text_elements", "textElements", default=()))))
        images = _get(payload, "images", default=None)
        details = tuple(_sequence(_get(payload, "image_details", "imageDetails", default=())))
        if images is not None:
            for idx, image in enumerate(_sequence(images)):
                content.append(UserInput.image(_str(image, "image"), details[idx] if idx < len(details) else None))
        local_images = _sequence(_get(payload, "local_images", "localImages", default=()))
        local_details = tuple(_sequence(_get(payload, "local_image_details", "localImageDetails", default=())))
        for idx, path in enumerate(local_images):
            content.append(UserInput.local_image(path, local_details[idx] if idx < len(local_details) else None))
        return content

    def _handle_simple_tool_event(self, event_type: str, payload: JsonValue) -> None:
        if event_type == "web_search_begin":
            item = ThreadItem("webSearch", {"id": _str(_get(payload, "call_id", "callId"), "call_id"), "query": "", "action": None})
        elif event_type == "web_search_end":
            item = ThreadItem("webSearch", {"id": _str(_get(payload, "call_id", "callId"), "call_id"), "query": _get(payload, "query", default=""), "action": _get(payload, "action", default=None)})
        elif event_type == "view_image_tool_call":
            item = ThreadItem("imageView", {"id": _str(_get(payload, "call_id", "callId"), "call_id"), "path": str(_get(payload, "path"))})
        elif event_type == "image_generation_begin":
            item = ThreadItem("imageGeneration", {"id": _str(_get(payload, "call_id", "callId"), "call_id"), "status": "", "revisedPrompt": None, "result": "", "savedPath": None})
        else:
            item = ThreadItem(
                "imageGeneration",
                {
                    "id": _str(_get(payload, "call_id", "callId"), "call_id"),
                    "status": _str(_get(payload, "status"), "status"),
                    "revisedPrompt": _get(payload, "revised_prompt", "revisedPrompt", default=None),
                    "result": _str(_get(payload, "result", default=""), "result"),
                    "savedPath": _get(payload, "saved_path", "savedPath", default=None),
                },
            )
        self.upsert_item_in_current_turn(item)

    def _append_generated_item(self, type_: str, fields: Mapping[str, JsonValue]) -> None:
        self.ensure_turn().items.append(ThreadItem(type_, {"id": self.next_item_id(), **dict(fields)}))

    def _upsert_by_payload_turn(self, payload: JsonValue, item: ThreadItem) -> None:
        turn_id = _optional_str(_get(payload, "turn_id", "turnId", default=None), "turn_id") or ""
        if turn_id:
            self.upsert_item_in_turn_id(turn_id, item)
        else:
            self.upsert_item_in_current_turn(item)

    def _mark_pending_complete(self, turn: _PendingTurn, payload: JsonValue) -> None:
        if turn.status in {TurnStatus.COMPLETED, TurnStatus.IN_PROGRESS}:
            turn.status = TurnStatus.COMPLETED
        turn.completed_at = _optional_int(_get(payload, "completed_at", "completedAt", default=None), "completed_at")
        turn.duration_ms = _optional_int(_get(payload, "duration_ms", "durationMs", default=None), "duration_ms")

    def _replace_finished_turn_status(self, turn_id: str, status: TurnStatus, payload: JsonValue, *, only_if_non_failed: bool = False) -> bool:
        for idx, turn in enumerate(self.turns):
            if turn.id != turn_id:
                continue
            next_status = turn.status
            if not only_if_non_failed or turn.status in {"completed", "inProgress", TurnStatus.COMPLETED, TurnStatus.IN_PROGRESS}:
                next_status = status.value
            self.turns[idx] = _turn_with(
                turn,
                status=next_status,
                completed_at=_optional_int(_get(payload, "completed_at", "completedAt", default=None), "completed_at"),
                duration_ms=_optional_int(_get(payload, "duration_ms", "durationMs", default=None), "duration_ms"),
            )
            return True
        return False


def _upsert_turn_item(items: list[ThreadItem], item: ThreadItem) -> None:
    item_id = item.id()
    for idx, existing in enumerate(items):
        if existing.id() == item_id:
            items[idx] = item
            return
    items.append(item)


def _turn_with(turn: Turn, **updates: JsonValue) -> Turn:
    data = {
        "id": turn.id,
        "items": turn.items,
        "status": turn.status,
        "items_view": turn.items_view,
        "error": turn.error,
        "started_at": turn.started_at,
        "completed_at": turn.completed_at,
        "duration_ms": turn.duration_ms,
    }
    data.update(updates)
    return Turn(**data)


def _rollout_parts(item: JsonValue) -> tuple[str, JsonValue]:
    data = _to_mapping(item)
    if isinstance(data, Mapping):
        type_ = data.get("type") or data.get("kind") or data.get("variant")
        if type_ is not None:
            payload = data.get("payload", data.get("item", data.get("msg", {key: value for key, value in data.items() if key not in {"type", "kind", "variant"}})))
            return _str(type_, "type"), payload
    if hasattr(item, "msg"):
        return "event_msg", getattr(item, "msg")
    return "event_msg", item


def _event_parts(event: JsonValue) -> tuple[str, JsonValue]:
    data = _to_mapping(event)
    if isinstance(data, Mapping):
        type_ = data.get("type")
        payload = data.get("payload")
        if payload is None:
            payload = {key: value for key, value in data.items() if key != "type"}
        return _str(type_, "type"), payload
    kind = getattr(event, "kind", None)
    type_ = getattr(event, "type", None) or (kind() if callable(kind) else kind)
    return _str(type_, "type"), getattr(event, "payload", None)


def _thread_item(value: JsonValue) -> ThreadItem:
    if isinstance(value, ThreadItem):
        return value
    data = _to_mapping(value)
    if isinstance(data, Mapping):
        return ThreadItem.from_mapping(data)
    raise TypeError("item must be ThreadItem-compatible")


def _parse_hook_prompt_message(data: Mapping[str, JsonValue]) -> ThreadItem | None:
    content = data.get("content")
    if not isinstance(content, Iterable) or isinstance(content, (str, bytes, Mapping)):
        return None
    fragments: list[dict[str, str]] = []
    for item in content:
        item_data = _to_mapping(item)
        if not isinstance(item_data, Mapping):
            continue
        text = item_data.get("text")
        hook_run_id = item_data.get("hook_run_id") or item_data.get("hookRunId")
        if isinstance(text, str) and isinstance(hook_run_id, str):
            fragments.append({"text": text, "hookRunId": hook_run_id})
    if not fragments:
        return None
    return ThreadItem("hookPrompt", {"id": _optional_str(data.get("id"), "id") or str(uuid4()), "fragments": fragments})


def _review_output_text(value: JsonValue) -> str:
    if value is None:
        return "Reviewer failed to output a response."
    text = _optional_str(_get(value, "overall_explanation", "overallExplanation", default=None), "overall_explanation")
    return text.strip() if text and text.strip() else "Reviewer failed to output a response."


def _affects_turn_status(payload: JsonValue) -> bool:
    affects = getattr(payload, "affects_turn_status", None)
    if callable(affects):
        return bool(affects())
    info = _get(payload, "codex_error_info", "codexErrorInfo", default=None)
    text = str(info)
    return "ThreadRollbackFailed" not in text and "thread_rollback_failed" not in text


def _is_success_result(payload: JsonValue) -> bool:
    is_success = getattr(payload, "is_success", None)
    if callable(is_success):
        return bool(is_success())
    result = _get(payload, "result", default=None)
    if isinstance(result, Mapping):
        return "Ok" in result or "ok" in result or result.get("success") is True
    return not isinstance(result, str)


def _duration_ms(value: JsonValue) -> int | None:
    if value is None:
        return None
    total = getattr(value, "total_seconds", None)
    if callable(total):
        return int(total() * 1000)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return None


def _get(value: JsonValue, *names: str, default: JsonValue = ...):
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if not isinstance(value, Mapping) and hasattr(value, name):
            return getattr(value, name)
    if default is not ...:
        return default
    raise KeyError(" or ".join(names))


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


def _variant_type(value: JsonValue) -> str:
    value = _to_mapping(value)
    if isinstance(value, Mapping):
        type_ = value.get("type")
        if type_ is not None:
            return str(type_)
        if len(value) == 1:
            return str(next(iter(value)))
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _optional_str(value: JsonValue, field: str) -> str | None:
    if value is None:
        return None
    return _str(value, field)


def _str(value: JsonValue, field: str) -> str:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _optional_int(value: JsonValue, field: str) -> int | None:
    if value is None:
        return None
    return _int(value, field)


def _int(value: JsonValue, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    return value


__all__ = ["ThreadHistoryBuilder", "build_turns_from_rollout_items"]
