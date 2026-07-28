"""JSONL event processor for ``codex exec --json``.

Port of ``codex-exec/src/event_processor_with_jsonl_output.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import TextIO

from pycodex.protocol import SessionConfiguredEvent, TurnItem

from .event_processor import (
    CodexStatus,
    JsonValue,
    _EXEC_JSON_TURN_ITEM_TYPES,
    _field,
    _item_id,
    _message_with_details,
    _model_rerouted_message,
    _normalized_status,
    _notification_details,
    _session_configured_thread_id,
    _turn_error_message,
    _turn_item_from_value,
    _turn_items,
    _uses_raw_exec_notification_boundary,
    _warning_summary,
    exec_item_from_app_server_item,
    final_message_from_notification_items,
    handle_last_message,
    map_todo_items,
    notification_method,
    notification_params,
    usage_from_notification,
)
from .events import (
    ExecThreadItem,
    ThreadErrorEvent,
    ThreadEvent,
    Usage,
    error_item,
    exec_item_from_turn_item,
    final_message_from_turn_items,
    todo_list_item,
)

@dataclass(frozen=True)
class CollectedThreadEvents:
    events: tuple[ThreadEvent, ...]
    status: CodexStatus


@dataclass
class RunningTodoList:
    item_id: str
    items: tuple[tuple[str, bool], ...]


class EventProcessorWithJsonOutput:
    """Collect and emit upstream-shaped ``codex exec --json`` events."""

    def __init__(self, last_message_path: str | Path | None = None) -> None:
        self.last_message_path = Path(last_message_path) if last_message_path is not None else None
        self._next_item_number = 0
        self._raw_to_exec_item_id: dict[str, str] = {}
        self.last_critical_error: ThreadErrorEvent | None = None
        self.final_message: str | None = None
        self.emit_final_message_on_shutdown = False
        self.last_usage: Usage | None = None
        self.running_todo_list: RunningTodoList | None = None

    def next_item_id(self) -> str:
        item_id = f"item_{self._next_item_number}"
        self._next_item_number += 1
        return item_id

    def thread_started_event(self, thread_id: str) -> ThreadEvent:
        return ThreadEvent.thread_started(thread_id)

    def collect_config_summary(self, session_configured: SessionConfiguredEvent | JsonValue) -> CollectedThreadEvents:
        return CollectedThreadEvents(
            events=(self.thread_started_event(_session_configured_thread_id(session_configured)),),
            status=CodexStatus.RUNNING,
        )

    def print_config_summary(
        self,
        config: JsonValue,
        prompt: str,
        session_configured: SessionConfiguredEvent | JsonValue,
        *,
        output: TextIO | None = None,
    ) -> None:
        self.emit_json_lines(self.collect_config_summary(session_configured).events, output)

    def collect_warning(self, message: str) -> CollectedThreadEvents:
        return CollectedThreadEvents(
            events=(ThreadEvent.item_completed(error_item(self.next_item_id(), message)),),
            status=CodexStatus.RUNNING,
        )

    def collect_error(self, message: str) -> CollectedThreadEvents:
        error = ThreadErrorEvent(message)
        self.last_critical_error = error
        return CollectedThreadEvents(events=(ThreadEvent.error(error),), status=CodexStatus.RUNNING)

    def process_warning(self, message: str, *, output: TextIO | None = None) -> CodexStatus:
        collected = self.collect_warning(message)
        self.emit_json_lines(collected.events, output)
        return collected.status

    def collect_turn_started(self) -> CollectedThreadEvents:
        return CollectedThreadEvents(events=(ThreadEvent.turn_started(),), status=CodexStatus.RUNNING)

    def collect_item_started(self, item: TurnItem) -> CollectedThreadEvents:
        mapped = self._map_started_item(item)
        events = (ThreadEvent.item_started(mapped),) if mapped is not None else ()
        return CollectedThreadEvents(events=events, status=CodexStatus.RUNNING)

    def collect_item_completed(self, item: TurnItem) -> CollectedThreadEvents:
        mapped = self._map_completed_item(item)
        if mapped is not None and mapped.type == "agent_message":
            self.final_message = str(mapped.payload.get("text", ""))
        events = (ThreadEvent.item_completed(mapped),) if mapped is not None else ()
        return CollectedThreadEvents(events=events, status=CodexStatus.RUNNING)

    def collect_turn_completed(
        self,
        *,
        status: str,
        items: tuple[TurnItem, ...] | list[TurnItem] = (),
        error: str | None = None,
        usage: Usage | None = None,
    ) -> CollectedThreadEvents:
        events: list[ThreadEvent] = []
        if self.running_todo_list is not None:
            events.append(ThreadEvent.item_completed(todo_list_item(self.running_todo_list.item_id, self.running_todo_list.items)))
            self.running_todo_list = None
        events.extend(self._reconcile_unfinished_started_items(tuple(items)))
        normalized_status = _normalized_status(status)

        if normalized_status == "completed":
            final_message = final_message_from_turn_items(tuple(items))
            if final_message is not None:
                self.final_message = final_message
            self.emit_final_message_on_shutdown = True
            events.append(ThreadEvent.turn_completed(usage or self.last_usage or Usage()))
            return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

        if normalized_status == "failed":
            self.final_message = None
            self.emit_final_message_on_shutdown = False
            failure = ThreadErrorEvent(error or (self.last_critical_error.message if self.last_critical_error else "turn failed"))
            events.append(ThreadEvent.turn_failed(failure))
            return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

        if normalized_status == "interrupted":
            self.final_message = None
            self.emit_final_message_on_shutdown = False
            return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

        return CollectedThreadEvents(tuple(events), CodexStatus.RUNNING)

    def collect_thread_events(self, notification: JsonValue) -> CollectedThreadEvents:
        method = notification_method(notification)
        params = notification_params(notification)

        if method in {"configWarning", "warning"}:
            return self.collect_warning(_message_with_details(_warning_summary(params), _notification_details(params)))

        if method == "error":
            return self.collect_error(_turn_error_message(_field(params, "error") or params) or "")

        if method == "deprecationNotice":
            return self.collect_warning(_message_with_details(_warning_summary(params), _notification_details(params)))

        if method in {"hook/started", "hook/completed", "model/verification", "turn/diff/updated"}:
            return CollectedThreadEvents(events=(), status=CodexStatus.RUNNING)

        if method == "item/started":
            item = _field(params, "item")
            mapped = self._map_started_notification_item(item)
            events = (ThreadEvent.item_started(mapped),) if mapped is not None else ()
            return CollectedThreadEvents(events=events, status=CodexStatus.RUNNING)

        if method == "item/completed":
            item = _field(params, "item")
            mapped = self._map_completed_notification_item(item)
            if mapped is not None and mapped.type == "agent_message":
                self.final_message = str(mapped.payload.get("text", ""))
            events = (ThreadEvent.item_completed(mapped),) if mapped is not None else ()
            return CollectedThreadEvents(events=events, status=CodexStatus.RUNNING)

        if method == "model/rerouted":
            message = _model_rerouted_message(params, include_reason=True)
            return CollectedThreadEvents(
                events=(ThreadEvent.item_completed(error_item(self.next_item_id(), message)),),
                status=CodexStatus.RUNNING,
            )

        if method == "thread/tokenUsage/updated":
            self.last_usage = usage_from_notification(params)
            return CollectedThreadEvents(events=(), status=CodexStatus.RUNNING)

        if method == "turn/plan/updated":
            items = map_todo_items(_field(params, "plan") or ())
            if self.running_todo_list is not None:
                self.running_todo_list.items = items
                return CollectedThreadEvents(
                    events=(ThreadEvent.item_updated(todo_list_item(self.running_todo_list.item_id, items)),),
                    status=CodexStatus.RUNNING,
                )
            item_id = self.next_item_id()
            self.running_todo_list = RunningTodoList(item_id=item_id, items=items)
            return CollectedThreadEvents(
                events=(ThreadEvent.item_started(todo_list_item(item_id, items)),),
                status=CodexStatus.RUNNING,
            )

        if method == "turn/started":
            return self.collect_turn_started()

        if method == "turn/completed":
            turn = _field(params, "turn")
            items = _turn_items(turn)
            events: list[ThreadEvent] = []
            if self.running_todo_list is not None:
                events.append(ThreadEvent.item_completed(todo_list_item(self.running_todo_list.item_id, self.running_todo_list.items)))
                self.running_todo_list = None
            events.extend(self._reconcile_unfinished_notification_items(items))

            status = _normalized_status(_field(turn, "status"))
            if status == "completed":
                final_message = final_message_from_notification_items(items)
                if final_message is not None:
                    self.final_message = final_message
                self.emit_final_message_on_shutdown = True
                events.append(ThreadEvent.turn_completed(self.last_usage or Usage()))
                return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

            if status == "failed":
                self.final_message = None
                self.emit_final_message_on_shutdown = False
                failure_message = (
                    _turn_error_message(_field(turn, "error"))
                    or (self.last_critical_error.message if self.last_critical_error else None)
                    or "turn failed"
                )
                events.append(ThreadEvent.turn_failed(ThreadErrorEvent(failure_message)))
                return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

            if status == "interrupted":
                self.final_message = None
                self.emit_final_message_on_shutdown = False
                return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

            return CollectedThreadEvents(tuple(events), CodexStatus.RUNNING)

        return CollectedThreadEvents(events=(), status=CodexStatus.RUNNING)

    collect_server_notification = collect_thread_events

    def process_server_notification(self, notification: JsonValue, *, output: TextIO | None = None) -> CodexStatus:
        collected = self.collect_thread_events(notification)
        self.emit_json_lines(collected.events, output)
        return collected.status

    def print_final_output(self, *, stderr: TextIO | None = None) -> None:
        if self.emit_final_message_on_shutdown and self.last_message_path is not None:
            handle_last_message(self.final_message, self.last_message_path, stderr=stderr)

    def emit_json_lines(self, events: tuple[ThreadEvent, ...] | list[ThreadEvent], output: TextIO | None = None) -> None:
        out = sys.stdout if output is None else output
        for event in events:
            print(event.to_json_line(), file=out)

    def _started_item_id(self, raw_id: str) -> str:
        existing = self._raw_to_exec_item_id.get(raw_id)
        if existing is not None:
            return existing
        item_id = self.next_item_id()
        self._raw_to_exec_item_id[raw_id] = item_id
        return item_id

    def _completed_item_id(self, raw_id: str) -> str:
        return self._raw_to_exec_item_id.pop(raw_id, None) or self.next_item_id()

    def _map_started_item(self, item: TurnItem) -> ExecThreadItem | None:
        if item.type in {"AgentMessage", "Reasoning"}:
            return None
        if item.type not in _EXEC_JSON_TURN_ITEM_TYPES:
            return None
        return exec_item_from_turn_item(item, self._started_item_id(item.id()))

    def _map_completed_item(self, item: TurnItem) -> ExecThreadItem | None:
        if item.type == "Reasoning":
            text = "\n".join(getattr(item.item, "summary_text", ()))
            if text.strip() == "":
                return None
        if item.type in {"AgentMessage", "Reasoning"}:
            return exec_item_from_turn_item(item, self.next_item_id())
        if item.type not in _EXEC_JSON_TURN_ITEM_TYPES:
            return None
        return exec_item_from_turn_item(item, self._completed_item_id(item.id()))

    def _reconcile_unfinished_started_items(self, turn_items: tuple[TurnItem, ...]) -> tuple[ThreadEvent, ...]:
        events: list[ThreadEvent] = []
        for item in turn_items:
            raw_id = item.id()
            if raw_id not in self._raw_to_exec_item_id:
                continue
            mapped = self._map_completed_item(item)
            if mapped is not None:
                events.append(ThreadEvent.item_completed(mapped))
        return tuple(events)

    def _map_started_notification_item(self, item: JsonValue) -> ExecThreadItem | None:
        if _uses_raw_exec_notification_boundary(item):
            raw_id = _item_id(item)
            make_id = (lambda: self._started_item_id(raw_id)) if raw_id is not None else self.next_item_id
            return exec_item_from_app_server_item(item, make_id)
        turn_item = _turn_item_from_value(item)
        if turn_item is not None:
            return self._map_started_item(turn_item)
        raw_id = _item_id(item)
        make_id = (lambda: self._started_item_id(raw_id)) if raw_id is not None else self.next_item_id
        return exec_item_from_app_server_item(item, make_id)

    def _map_completed_notification_item(self, item: JsonValue) -> ExecThreadItem | None:
        if _uses_raw_exec_notification_boundary(item):
            raw_id = _item_id(item)
            make_id = (lambda: self._completed_item_id(raw_id)) if raw_id is not None else self.next_item_id
            return exec_item_from_app_server_item(item, make_id)
        turn_item = _turn_item_from_value(item)
        if turn_item is not None:
            return self._map_completed_item(turn_item)
        raw_id = _item_id(item)
        make_id = (lambda: self._completed_item_id(raw_id)) if raw_id is not None else self.next_item_id
        return exec_item_from_app_server_item(item, make_id)

    def _reconcile_unfinished_notification_items(self, items: tuple[JsonValue, ...]) -> tuple[ThreadEvent, ...]:
        events: list[ThreadEvent] = []
        for item in items:
            raw_id = _item_id(item)
            if raw_id is None or raw_id not in self._raw_to_exec_item_id:
                continue
            mapped = self._map_completed_notification_item(item)
            if mapped is not None:
                events.append(ThreadEvent.item_completed(mapped))
        return tuple(events)

__all__ = [
    "CollectedThreadEvents",
    "EventProcessorWithJsonOutput",
    "RunningTodoList",
]
