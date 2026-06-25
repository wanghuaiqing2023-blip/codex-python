"""Runtime composition for Rust ``codex-tui::app``.

Rust source: ``codex/codex-rs/tui/src/app.rs``.

This module owns the Python product-path equivalent of Rust's dynamic graph:
``AppCommand::UserTurn`` is routed through the active thread, the active thread
emits app-server notifications, and ``chatwidget::protocol`` consumes those
notifications to update turn, streaming, status, and redraw state.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Callable, Mapping, Protocol

from pycodex.exec.local_runtime import (
    final_text_from_local_http_exec_result,
    prewarm_exec_core_websocket_session,
    run_exec_user_turn_core_sampling_websocket_preferred,
)
from pycodex.exec.run import ExecRunPlan, InitialOperation
from pycodex.protocol import TurnItem, UserInput

from ..app_command import AppCommand
from ..chatwidget.protocol import ChatWidgetProtocolRuntime, ServerNotification
from .thread_routing import ThreadRoutingPlan, ThreadRoutingState, submit_active_thread_op_plan

RUST_MODULE_CRATE = "codex-tui"
RUST_MODULE = "app"
RUST_SOURCE = "codex/codex-rs/tui/src/app.rs"


class ActiveThreadEventStream(Protocol):
    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        ...


class ActiveThreadRuntime(Protocol):
    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        ...


_EOF = object()


def _timing_trace(event: str, **fields: Any) -> None:
    path = os.environ.get("PYCODEX_TUI_TIMING_LOG")
    if not path:
        return
    record = {"t": time.monotonic(), "event": event, **fields}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        return


@dataclass
class QueueActiveThreadEventStream:
    queue: Queue[Any]
    closed: bool = False

    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        try:
            value = self.queue.get(timeout=timeout)
        except Empty:
            return None
        if value is _EOF:
            self.closed = True
            return None
        return value


@dataclass
class ExecFunctionActiveThreadRuntime:
    """Adapt the current exec implementation to Rust-style notifications.

    The wrapped callable is intentionally below the TUI runtime boundary.  The
    TUI submits an ``AppCommand`` and observes server notifications; it no
    longer synchronously waits for the callable's final return value.
    """

    execute_prompt: Callable[[str], int | tuple[int, str]]

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        queue: Queue[Any] = Queue()
        turn_id = "terminal-turn"
        prompt = user_turn_prompt(op)

        def worker() -> None:
            queue.put(ServerNotification("TurnStarted", {"turn": {"id": turn_id, "thread_id": thread_id}}))
            try:
                result = self.execute_prompt(prompt)
                if isinstance(result, tuple):
                    code, output = result
                else:
                    code, output = result, ""
                if output:
                    queue.put(ServerNotification("AgentMessageDelta", {"delta": str(output), "thread_id": thread_id}))
                if code == 0:
                    queue.put(
                        ServerNotification(
                            "TurnCompleted",
                            {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Completed", "duration_ms": None}},
                        )
                    )
                else:
                    queue.put(
                        ServerNotification(
                            "TurnCompleted",
                            {
                                "turn": {
                                    "id": turn_id,
                                    "thread_id": thread_id,
                                    "status": "Failed",
                                    "error": {
                                        "message": str(output or f"exec exited with status {code}"),
                                        "codex_error_info": None,
                                        "exit_code": code,
                                    },
                                }
                            },
                        )
                    )
            except BaseException as exc:
                queue.put(
                    ServerNotification(
                        "TurnCompleted",
                        {
                            "turn": {
                                "id": turn_id,
                                "thread_id": thread_id,
                                "status": "Failed",
                                "error": {"message": str(exc), "codex_error_info": None, "exit_code": 1},
                            }
                        },
                    )
                )
            finally:
                queue.put(_EOF)

        Thread(target=worker, name="pycodex-tui-active-thread", daemon=True).start()
        return QueueActiveThreadEventStream(queue)


@dataclass
class CoreExecActiveThreadRuntime:
    """Run ``AppCommand::UserTurn`` through the core in-memory turn runtime.

    Rust ``codex-tui::app`` submits user turns to the active thread and observes
    app-server notifications.  This keeps the product TUI path on that shape:
    terminal input becomes an ``AppCommand`` and core sampling/session events
    become the notifications consumed by ``chatwidget::protocol``.
    """

    session_config: Any
    model_client: Any
    provider: Any
    model_info: Any
    auth: Any = None
    codex_home: Path | str | None = None
    auth_manager: Any = None
    endpoint: str | None = None
    timeout: float | None = None
    opener: Any = None
    built_tools: Any = None
    max_tool_followups: int | None = None
    startup_prewarm_enabled: bool = False
    prewarmed_model_session: Any = None
    _startup_prewarm_ready: Event = field(default_factory=Event, init=False, repr=False)
    _startup_prewarm_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _startup_prewarm_session: Any = field(default=None, init=False, repr=False)
    _startup_prewarm_consumed: bool = field(default=False, init=False, repr=False)
    _startup_prewarm_started_at: float | None = field(default=None, init=False, repr=False)
    _startup_prewarm_timeout: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.prewarmed_model_session is not None:
            self._startup_prewarm_session = self.prewarmed_model_session
            self._startup_prewarm_ready.set()
            return
        if self.startup_prewarm_enabled:
            self._schedule_startup_prewarm()

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        queue: Queue[Any] = Queue()
        turn_id = "terminal-turn"

        def worker() -> None:
            queue.put(_turn_started_notification(thread_id, turn_id))
            observed_delta = False
            observed_error_message: str | None = None
            pending_commands: dict[str, dict[str, Any]] = {}
            completed_commands: set[str] = set()
            observed_live_kinds: set[str] = set()

            def observe_session_event(event: Any) -> None:
                nonlocal observed_delta, observed_error_message
                error_message = _session_event_error_message(event)
                if error_message:
                    observed_error_message = error_message
                notifications = _server_notifications_from_session_event(
                    event,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    pending_commands=pending_commands,
                    completed_commands=completed_commands,
                )
                _timing_trace(
                    "tui_session_event",
                    type=getattr(event, "type", None),
                    notifications=tuple(notification.kind for notification in notifications),
                    items=tuple(
                        {
                            "kind": (
                                notification.payload.get("item", {}).get("kind")
                                if isinstance(notification.payload, dict)
                                and isinstance(notification.payload.get("item"), dict)
                                else None
                            ),
                            "command": (
                                notification.payload.get("item", {}).get("command")
                                if isinstance(notification.payload, dict)
                                and isinstance(notification.payload.get("item"), dict)
                                else None
                            ),
                        }
                        for notification in notifications
                    ),
                )
                for notification in notifications:
                    if notification.kind == "AgentMessageDelta":
                        observed_delta = True
                    observed_live_kinds.add(notification.kind)
                    queue.put(notification)

            try:
                model_session = self._take_startup_prewarm_session()
                result = asyncio.run(
                    self._run_op(
                        op,
                        session_event_observer=observe_session_event,
                        model_session=model_session,
                    )
                )
                emitted_delta = observed_delta
                for event in _server_notifications_from_session_events(
                    result,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    pending_commands=pending_commands,
                    completed_commands=completed_commands,
                ):
                    if event.kind in observed_live_kinds:
                        continue
                    if event.kind == "AgentMessageDelta":
                        emitted_delta = True
                    queue.put(event)
                for notification in _command_completion_notifications_from_result(
                    result,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    pending_commands=pending_commands,
                    completed_commands=completed_commands,
                ):
                    queue.put(notification)
                final_text = final_text_from_local_http_exec_result(result)
                if final_text and not emitted_delta:
                    queue.put(ServerNotification("AgentMessageDelta", {"delta": final_text, "thread_id": thread_id, "turn_id": turn_id}))
                    emitted_delta = True
                if observed_error_message and not emitted_delta:
                    queue.put(_turn_failed_notification(thread_id, turn_id, observed_error_message, exit_code=1))
                else:
                    queue.put(_turn_completed_notification(thread_id, turn_id, result))
            except BaseException as exc:
                queue.put(_turn_failed_notification(thread_id, turn_id, str(exc), exit_code=1))
            finally:
                queue.put(_EOF)

        Thread(target=worker, name="pycodex-tui-core-active-thread", daemon=True).start()
        return QueueActiveThreadEventStream(queue)

    def _schedule_startup_prewarm(self) -> None:
        new_session = getattr(self.model_client, "new_session", None)
        model = str(getattr(self.model_info, "slug", "") or "")
        if not callable(new_session) or not model:
            self._startup_prewarm_ready.set()
            return
        self._startup_prewarm_started_at = time.monotonic()
        self._startup_prewarm_timeout = self._startup_prewarm_timeout_seconds()
        _timing_trace("startup_prewarm_scheduled", timeout=self._startup_prewarm_timeout)

        def worker() -> None:
            try:
                session = new_session()
                _timing_trace("startup_prewarm_worker_started")
                session = asyncio.run(
                    prewarm_exec_core_websocket_session(
                        self.session_config,
                        self.model_client,
                        self.provider,
                        self.model_info,
                        auth=self.auth,
                        endpoint=self.endpoint,
                        timeout=self.timeout,
                        built_tools=self.built_tools,
                        auth_manager=self.auth_manager,
                        codex_home=self.codex_home,
                        model_session=session,
                    )
                )
                with self._startup_prewarm_lock:
                    if session is not None and not self._startup_prewarm_consumed:
                        self._startup_prewarm_session = session
                        _timing_trace("startup_prewarm_ready")
                    elif session is not None:
                        _timing_trace("startup_prewarm_ready_after_consumed")
                    else:
                        _timing_trace("startup_prewarm_unavailable")
            except BaseException as exc:
                fallback = getattr(self.model_client, "force_http_fallback", None)
                activated = False
                if callable(fallback):
                    try:
                        activated = bool(fallback())
                    except Exception:
                        activated = False
                _timing_trace("startup_prewarm_failed", error=str(exc), http_fallback=activated)
                pass
            finally:
                self._startup_prewarm_ready.set()

        Thread(target=worker, name="pycodex-tui-startup-prewarm", daemon=True).start()

    def _take_startup_prewarm_session(self) -> Any:
        with self._startup_prewarm_lock:
            if self._startup_prewarm_consumed:
                return None
        if self.startup_prewarm_enabled or self.prewarmed_model_session is not None:
            remaining = self._startup_prewarm_remaining_seconds()
            _timing_trace("startup_prewarm_resolve_wait", remaining=remaining)
            self._startup_prewarm_ready.wait(remaining)
        with self._startup_prewarm_lock:
            if self._startup_prewarm_consumed:
                return None
            self._startup_prewarm_consumed = True
            session = self._startup_prewarm_session
            self._startup_prewarm_session = None
            _timing_trace("startup_prewarm_resolved", ready=session is not None)
            return session

    def _startup_prewarm_remaining_seconds(self) -> float:
        if self.prewarmed_model_session is not None:
            return 0.0
        started_at = self._startup_prewarm_started_at
        if started_at is None:
            return 0.0
        age = max(time.monotonic() - started_at, 0.0)
        return max(self._startup_prewarm_timeout - age, 0.0)

    def _startup_prewarm_timeout_seconds(self) -> float:
        info_method = getattr(self.provider, "info", None)
        provider_info = info_method() if callable(info_method) else self.provider
        timeout_method = getattr(provider_info, "websocket_connect_timeout", None)
        if callable(timeout_method):
            try:
                return max(float(timeout_method()) / 1000.0, 0.0)
            except (TypeError, ValueError):
                return 0.0
        timeout_ms = getattr(provider_info, "websocket_connect_timeout_ms", None)
        try:
            return max(float(timeout_ms) / 1000.0, 0.0) if timeout_ms is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    async def _run_op(
        self,
        op: AppCommand,
        *,
        session_event_observer: Any = None,
        model_session: Any = None,
    ) -> Any:
        _timing_trace("core_run_op_started", has_model_session=model_session is not None)
        return await run_exec_user_turn_core_sampling_websocket_preferred(
            self.session_config,
            exec_run_plan_for_app_command(op),
            self.model_client,
            self.provider,
            self.model_info,
            auth=self.auth,
            endpoint=self.endpoint,
            timeout=self.timeout,
            opener=self.opener,
            built_tools=self.built_tools,
            max_tool_followups=self.max_tool_followups,
            auth_manager=self.auth_manager,
            codex_home=self.codex_home,
            session_event_observer=session_event_observer,
            model_session=model_session,
        )


@dataclass
class TuiAppRuntime:
    active_thread_runtime: ActiveThreadRuntime
    thread_id: str = "primary"
    cwd: Path = field(default_factory=Path.cwd)
    chat_widget: ChatWidgetProtocolRuntime = field(default_factory=ChatWidgetProtocolRuntime)
    routing_state: ThreadRoutingState = field(default_factory=lambda: ThreadRoutingState(active_thread_id="primary", primary_thread_id="primary"))
    submitted_ops: list[AppCommand] = field(default_factory=list)
    routing_plans: list[ThreadRoutingPlan] = field(default_factory=list)

    def submit_user_turn(self, prompt: str) -> ActiveThreadEventStream:
        op = app_command_for_prompt(prompt, cwd=self.cwd)
        plan = submit_active_thread_op_plan(self.routing_state, op)
        self.routing_plans.append(plan)
        if plan.action != "submit_thread_op" or plan.thread_id is None:
            raise RuntimeError(plan.error_message or "failed to submit active thread op")
        self.submitted_ops.append(op)
        return self.active_thread_runtime.submit_thread_op(plan.thread_id, op)

    def handle_notification(self, notification: ServerNotification) -> None:
        self.chat_widget.handle(notification)


def app_command_for_prompt(prompt: str, *, cwd: Path | str) -> AppCommand:
    return AppCommand.user_turn(
        [{"kind": "Text", "text": prompt}],
        cwd=cwd,
        approval_policy=None,
        active_permission_profile=None,
        model="",
        effort=None,
        summary=None,
        service_tier=None,
        final_output_json_schema=None,
        collaboration_mode=None,
        personality=None,
    )


def user_turn_prompt(op: AppCommand) -> str:
    if op.kind != "UserTurn":
        return ""
    items = op.payload.get("items") or []
    texts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("text")
        else:
            text = getattr(item, "text", None)
        if text is not None:
            texts.append(str(text))
    return "\n".join(texts)


def exec_run_plan_for_app_command(op: AppCommand) -> ExecRunPlan:
    if op.kind != "UserTurn":
        raise ValueError("active thread runtime supports only AppCommand::UserTurn")
    return ExecRunPlan(
        InitialOperation.user_turn(user_inputs_for_app_command(op), op.payload.get("final_output_json_schema")),
        user_turn_prompt(op),
    )


def user_inputs_for_app_command(op: AppCommand) -> tuple[UserInput, ...]:
    if op.kind != "UserTurn":
        return ()
    user_inputs: list[UserInput] = []
    for item in op.payload.get("items") or ():
        raw_kind = _field(item, "kind")
        kind = str(raw_kind or "").lower()
        if kind == "text":
            user_inputs.append(UserInput.text_input(str(_field(item, "text") or "")))
        elif kind in {"localimage", "local_image"}:
            path = _field(item, "path")
            if path is not None:
                user_inputs.append(UserInput.local_image(Path(str(path))))
    if not user_inputs:
        prompt = user_turn_prompt(op)
        if prompt:
            user_inputs.append(UserInput.text_input(prompt))
    return tuple(user_inputs)


def _server_notifications_from_session_events(
    result: Any,
    *,
    thread_id: str,
    turn_id: str,
    pending_commands: dict[str, dict[str, Any]] | None = None,
    completed_commands: set[str] | None = None,
) -> tuple[ServerNotification, ...]:
    notifications: list[ServerNotification] = []
    for event in tuple(getattr(result, "session_events", ()) or ()):
        notifications.extend(
            _server_notifications_from_session_event(
                event,
                thread_id=thread_id,
                turn_id=turn_id,
                pending_commands=pending_commands,
                completed_commands=completed_commands,
            )
        )
    return tuple(notifications)


def _server_notifications_from_session_event(
    event: Any,
    *,
    thread_id: str,
    turn_id: str,
    pending_commands: dict[str, dict[str, Any]] | None = None,
    completed_commands: set[str] | None = None,
) -> tuple[ServerNotification, ...]:
    event_type = getattr(event, "type", None)
    payload = getattr(event, "payload", None)
    if event_type == "agent_message_content_delta":
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("AgentMessageDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "reasoning_summary_delta":
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("ReasoningSummaryTextDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "reasoning_summary_part_added":
        return (ServerNotification("ReasoningSummaryPartAdded", {"thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "reasoning_content_delta":
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("ReasoningTextDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "response_created":
        return (ServerNotification("ResponseStarted", {"thread_id": thread_id, "turn_id": turn_id}),)
    if event_type in {"item_started", "item_completed"}:
        item = _chatwidget_item_from_turn_item(getattr(payload, "item", None))
        if item is None:
            return ()
        item_id = item.get("id")
        if item.get("kind") == "CommandExecution" and isinstance(item_id, str):
            if event_type == "item_started" and pending_commands is not None:
                pending_commands[item_id] = dict(item)
            if event_type == "item_completed" and completed_commands is not None:
                completed_commands.add(item_id)
        notification_kind = "ItemStarted" if event_type == "item_started" else "ItemCompleted"
        timestamp_name = "started_at_ms" if event_type == "item_started" else "completed_at_ms"
        timestamp_value = getattr(payload, timestamp_name, None)
        if not isinstance(timestamp_value, int):
            timestamp_value = int(time.time() * 1000)
        return (
            ServerNotification(
                notification_kind,
                {
                    "thread_id": _thread_id_value(getattr(payload, "thread_id", thread_id)),
                    "turn_id": getattr(payload, "turn_id", turn_id),
                    timestamp_name: timestamp_value,
                    "item": item,
                },
            ),
        )
    if event_type == "response_output_item_done":
        item = _field(payload, "item")
        command_item = _command_execution_item_from_response_item(item, status="InProgress")
        if command_item is not None:
            call_id = command_item["id"]
            if pending_commands is not None:
                pending_commands[call_id] = dict(command_item)
            return (
                ServerNotification(
                    "ItemStarted",
                    {
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "started_at_ms": int(time.time() * 1000),
                        "item": command_item,
                    },
                ),
            )
    return ()


def _chatwidget_item_from_turn_item(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    if isinstance(item, Mapping):
        raw_kind = item.get("kind") or item.get("type")
        if raw_kind is None:
            return None
        kind = _turn_item_kind(str(raw_kind))
        if kind == "CommandExecution":
            return _chatwidget_command_execution_item(item)
        result = dict(item)
        result.pop("type", None)
        result["kind"] = kind
        return result
    if isinstance(item, TurnItem):
        if item.type == "CommandExecution":
            return _chatwidget_command_execution_item(item.item)
        result = item.to_mapping()
        result.pop("type", None)
        result["kind"] = item.type
        return result
    raw_type = getattr(item, "type", None)
    raw_inner = getattr(item, "item", None)
    if isinstance(raw_type, str):
        if raw_type == "CommandExecution":
            return _chatwidget_command_execution_item(raw_inner)
        to_mapping = getattr(item, "to_mapping", None)
        result = to_mapping() if callable(to_mapping) else dict(getattr(item, "__dict__", {}))
        result.pop("type", None)
        result.pop("item", None)
        result["kind"] = raw_type
        return result
    return None


def _chatwidget_command_execution_item(value: Any) -> dict[str, Any]:
    status = _command_execution_status_name(_field(value, "status", "inProgress"))
    return {
        "kind": "CommandExecution",
        "id": str(_field(value, "id", "")),
        "command": str(_field(value, "command", "")),
        "cwd": _field(value, "cwd"),
        "process_id": _field(value, "process_id", _field(value, "processId")),
        "source": _command_execution_source_name(_field(value, "source", "agent")),
        "status": status,
        "command_actions": _field(value, "command_actions", _field(value, "commandActions", ())) or (),
        "aggregated_output": _field(value, "aggregated_output", _field(value, "aggregatedOutput")),
        "exit_code": _field(value, "exit_code", _field(value, "exitCode")),
        "duration_ms": _field(value, "duration_ms", _field(value, "durationMs")),
    }


def _turn_item_kind(value: str) -> str:
    return {
        "agentMessage": "AgentMessage",
        "commandExecution": "CommandExecution",
        "contextCompaction": "ContextCompaction",
        "dynamicToolCall": "DynamicToolCall",
        "enteredReviewMode": "EnteredReviewMode",
        "exitedReviewMode": "ExitedReviewMode",
        "fileChange": "FileChange",
        "hookPrompt": "HookPrompt",
        "imageGeneration": "ImageGeneration",
        "imageView": "ImageView",
        "mcpToolCall": "McpToolCall",
        "plan": "Plan",
        "reasoning": "Reasoning",
        "userMessage": "UserMessage",
        "webSearch": "WebSearch",
    }.get(value, value)


def _command_execution_status_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    return {
        "inProgress": "InProgress",
        "completed": "Completed",
        "failed": "Failed",
        "declined": "Declined",
    }.get(str(raw), str(raw))


def _command_execution_source_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    return {
        "agent": "agent",
        "userShell": "user_shell",
        "unifiedExecStartup": "unified_exec_startup",
        "unifiedExecInteraction": "unified_exec_interaction",
    }.get(str(raw), str(raw))


def _thread_id_value(value: Any) -> str:
    raw = getattr(value, "id", value)
    return str(raw)


def _command_completion_notifications_from_result(
    result: Any,
    *,
    thread_id: str,
    turn_id: str,
    pending_commands: dict[str, dict[str, Any]],
    completed_commands: set[str],
) -> tuple[ServerNotification, ...]:
    notifications: list[ServerNotification] = []
    for item in tuple(getattr(result, "tool_response_items", ()) or ()):
        call_id = _field(item, "call_id")
        if not isinstance(call_id, str) or call_id in completed_commands:
            continue
        started = pending_commands.get(call_id)
        if started is None:
            continue
        completed = dict(started)
        completed["status"] = "Completed" if _tool_output_success(item) is not False else "Failed"
        completed["aggregated_output"] = _tool_output_text(item)
        completed["exit_code"] = 0 if completed["status"] == "Completed" else 1
        completed["duration_ms"] = None
        completed_commands.add(call_id)
        notifications.append(
            ServerNotification(
                "ItemCompleted",
                {
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "completed_at_ms": int(time.time() * 1000),
                    "item": completed,
                },
            )
        )
    return tuple(notifications)


def _command_execution_item_from_response_item(item: Any, *, status: str) -> dict[str, Any] | None:
    item_type = _field(item, "type")
    name = _field(item, "name")
    if item_type not in {"function_call", "local_shell_call"}:
        return None
    if item_type == "function_call" and name not in {"exec_command", "local_shell", "shell"}:
        return None
    call_id = _field(item, "call_id") or _field(item, "id")
    if not isinstance(call_id, str) or not call_id:
        return None
    command, cwd = _command_and_cwd_from_tool_item(item)
    if not command:
        return None
    return {
        "kind": "CommandExecution",
        "id": call_id,
        "command": command,
        "cwd": cwd,
        "process_id": None,
        "source": "Agent",
        "status": status,
        "command_actions": [{"type": "unknown", "cmd": command}],
        "aggregated_output": None,
        "exit_code": None,
        "duration_ms": None,
    }


def _command_and_cwd_from_tool_item(item: Any) -> tuple[str, str | None]:
    if _field(item, "type") == "local_shell_call":
        action = _field(item, "action")
        command = _field(action, "command")
        return (str(command), _field(action, "workdir")) if command is not None else ("", None)
    arguments = _field(item, "arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return arguments, None
    if isinstance(arguments, Mapping):
        command = arguments.get("cmd", arguments.get("command"))
        cwd = arguments.get("workdir", arguments.get("cwd"))
        return (str(command), str(cwd) if cwd is not None else None) if command is not None else ("", None)
    return "", None


def _tool_output_text(item: Any) -> str | None:
    output = _field(item, "output")
    if output is None:
        return None
    to_text = getattr(output, "to_text", None)
    if callable(to_text):
        value = to_text()
        return None if value is None else str(value)
    if isinstance(output, Mapping):
        text = output.get("text")
        if isinstance(text, str):
            return text
    return str(output)


def _tool_output_success(item: Any) -> bool | None:
    output = _field(item, "output")
    success = _field(output, "success") if output is not None else None
    return success if isinstance(success, bool) else None


def _session_event_error_message(event: Any) -> str | None:
    event_type = getattr(event, "type", None)
    if event_type not in {"stream_error", "error"}:
        return None
    payload = getattr(event, "payload", None)
    message = getattr(payload, "message", None)
    if isinstance(message, str) and message:
        details = getattr(payload, "additional_details", None)
        if isinstance(details, str) and details and details != message:
            return f"{message}: {details}"
        return message
    return None


def _turn_started_notification(thread_id: str, turn_id: str) -> ServerNotification:
    return ServerNotification("TurnStarted", {"turn": {"id": turn_id, "thread_id": thread_id}})


def _turn_completed_notification(thread_id: str, turn_id: str, result: Any) -> ServerNotification:
    status = str(getattr(result, "turn_status", "completed") or "completed")
    if status == "completed":
        return ServerNotification("TurnCompleted", {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Completed", "duration_ms": None}})
    return _turn_failed_notification(thread_id, turn_id, status, exit_code=1)


def _turn_failed_notification(thread_id: str, turn_id: str, message: str, *, exit_code: int) -> ServerNotification:
    return ServerNotification(
        "TurnCompleted",
        {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Failed", "error": {"message": message, "codex_error_info": None, "exit_code": exit_code}}},
    )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "ActiveThreadEventStream",
    "ActiveThreadRuntime",
    "CoreExecActiveThreadRuntime",
    "ExecFunctionActiveThreadRuntime",
    "QueueActiveThreadEventStream",
    "RUST_MODULE",
    "RUST_MODULE_CRATE",
    "RUST_SOURCE",
    "TuiAppRuntime",
    "app_command_for_prompt",
    "exec_run_plan_for_app_command",
    "user_inputs_for_app_command",
    "user_turn_prompt",
]
