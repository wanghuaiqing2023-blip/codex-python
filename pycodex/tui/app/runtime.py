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
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Protocol

from pycodex.core.config.edit import ConfigEditsBuilder
from pycodex.core.event_mapping import parse_turn_item
from pycodex.exec.local_runtime import (
    final_text_from_local_http_exec_result,
    persist_core_exec_rollout,
    prewarm_exec_core_websocket_session,
    run_exec_user_turn_core_sampling_websocket_preferred,
)
from pycodex.exec.run import ExecRunPlan, InitialOperation
from pycodex.protocol import ResponseItem, ReviewRequest, ReviewTarget, TurnItem, UserInput

from ..app_command import AppCommand
from ..app_event import AppEvent, RateLimitRefreshOrigin
from ..chatwidget.input_submission import UserMessage, UserMessageHistoryRecord, submit_user_message_with_history_record
from ..chatwidget.protocol import ChatWidgetProtocolRuntime, ServerNotification
from ..config_update import build_model_selection_edits, write_config_batch
from ..status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay, rate_limit_snapshot_display_for_limit
from .agent_navigation import AgentNavigationDirection, AgentNavigationState
from .app_server_events import (
    AppServerEventPlan,
    plan_app_server_event,
    refresh_mcp_startup_expected_servers_from_config,
)
from .event_dispatch import EventDispatchPlan, EventDispatchState, dispatch_event_plan
from .thread_routing import ThreadRoutingPlan, ThreadRoutingState, active_thread_event_plan, submit_active_thread_op_plan

RUST_MODULE_CRATE = "codex-tui"
RUST_MODULE = "app"
RUST_SOURCE = "codex/codex-rs/tui/src/app.rs"


class ActiveThreadEventStream(Protocol):
    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        ...


class ActiveThreadRuntime(Protocol):
    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        ...

    def shutdown_thread(self, thread_id: str) -> ActiveThreadEventStream:
        ...


_EOF = object()


def _first_runtime_config_source(*candidates: Any) -> Any | None:
    config_fields = {
        "hide_agent_reasoning",
        "show_raw_agent_reasoning",
        "model_reasoning_effort",
        "reasoning_effort",
        "model_reasoning_summary",
    }
    for candidate in candidates:
        if candidate is not None and any(hasattr(candidate, name) for name in config_fields):
            return candidate
    return None


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


def _run_coro_blocking(coro: Any) -> Any:
    """Run an async Rust-shaped helper from the sync terminal runtime."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised below
            box["error"] = exc

    thread = Thread(target=worker, name="pycodex-tui-config-write", daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _close_model_session(session: Any) -> None:
    if session is None:
        return
    reset = getattr(session, "reset_websocket_session", None)
    if callable(reset):
        reset()
    close = getattr(session, "close", None)
    if callable(close):
        close()


def _request_handle_from_runtime(runtime: Any) -> Any:
    for name in ("request_handle", "get_request_handle"):
        candidate = getattr(runtime, name, None)
        if callable(candidate):
            return candidate()
        if candidate is not None:
            return candidate
    for container_name in ("app_server", "app_server_session", "server"):
        container = getattr(runtime, container_name, None)
        if container is None:
            continue
        candidate = getattr(container, "request_handle", None)
        if callable(candidate):
            return candidate()
        if candidate is not None:
            return candidate
    return None


def _config_from_runtime(runtime: Any) -> Any:
    for name in ("session_config", "config"):
        value = getattr(runtime, name, None)
        if value is not None:
            return value
    return None


def _effort_config_value(effort: Any) -> str | None:
    if effort is None:
        return None
    if isinstance(effort, Enum):
        value = effort.value
    else:
        value = effort
    text = str(value)
    if "." in text and text.rsplit(".", 1)[-1] in {"Minimal", "Low", "Medium", "High", "XHigh", "None"}:
        text = text.rsplit(".", 1)[-1]
    normalized = text.strip().replace("-", "_").lower()
    aliases = {
        "none": None,
        "none_": None,
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "x_high": "xhigh",
        "extra_high": "xhigh",
        "extra high": "xhigh",
    }
    return aliases.get(normalized, normalized or None)


def _reasoning_label_for(model: str, effort: Any) -> str | None:
    if model.startswith("codex-auto-"):
        return None
    return _effort_config_value(effort) or "default"


def _rate_limit_origin_kind(origin: Any) -> str | None:
    if origin is None:
        return None
    if isinstance(origin, Mapping):
        return origin.get("kind") or origin.get("type") or origin.get("variant")
    return getattr(origin, "kind", None)


def _rate_limit_origin_request_id(origin: Any) -> int | None:
    if origin is None:
        return None
    if isinstance(origin, Mapping):
        value = origin.get("request_id") or origin.get("requestId")
    else:
        value = getattr(origin, "request_id", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rate_limit_result_snapshots(result: Any) -> list[Any] | None:
    if result is None or isinstance(result, BaseException):
        return None
    if isinstance(result, Mapping) and ("error" in result or "err" in result):
        return None
    by_id = _mapping_or_attr(result, "rate_limits_by_limit_id", "rateLimitsByLimitId")
    if by_id:
        if isinstance(by_id, Mapping):
            return list(by_id.values())
        try:
            return list(by_id)
        except TypeError:
            return [by_id]
    primary = _mapping_or_attr(result, "rate_limits", "rateLimits")
    if primary is not None:
        return [primary]
    if isinstance(result, Mapping) and _looks_like_rate_limit_snapshot(result):
        return [result]
    if isinstance(result, (RateLimitSnapshotDisplay, RateLimitWindowDisplay)):
        return [result]
    try:
        return list(result)
    except TypeError:
        return [result]


def _rate_limit_snapshot_display(snapshot: Any) -> RateLimitSnapshotDisplay:
    if isinstance(snapshot, RateLimitSnapshotDisplay):
        return snapshot
    if isinstance(snapshot, RateLimitWindowDisplay):
        return RateLimitSnapshotDisplay("codex", datetime.now().astimezone(), primary=snapshot)
    limit_name = _mapping_or_attr(snapshot, "limit_name", "limitName", "limit_id", "limitId") or "codex"
    return rate_limit_snapshot_display_for_limit(snapshot, str(limit_name), datetime.now().astimezone())


def _store_runtime_rate_limit_snapshot(runtime: Any, snapshot: RateLimitSnapshotDisplay) -> None:
    for target in (runtime, getattr(runtime, "session_config", None), getattr(runtime, "model_client", None)):
        if target is None:
            continue
        current = getattr(target, "rate_limit_snapshots_by_limit_id", None)
        if current is None:
            current = {}
            try:
                setattr(target, "rate_limit_snapshots_by_limit_id", current)
            except Exception:
                continue
        if isinstance(current, dict):
            current[snapshot.limit_name] = snapshot
        try:
            setattr(target, "latest_rate_limits", snapshot)
        except Exception:
            pass


def _mapping_or_attr(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, Mapping):
            if name in value:
                return value[name]
        else:
            candidate = getattr(value, name, None)
            if candidate is not None:
                return candidate() if callable(candidate) else candidate
    return None


def _looks_like_rate_limit_snapshot(value: Mapping[str, Any]) -> bool:
    return bool(set(value.keys()) & {"primary", "secondary", "credits", "limit_id", "limitId", "limit_name", "limitName"})


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


def _closed_event_stream() -> QueueActiveThreadEventStream:
    queue: Queue[Any] = Queue()
    queue.put(_EOF)
    return QueueActiveThreadEventStream(queue)


def _clean_background_terminals_for_runtime(runtime: Any) -> None:
    """Mirror Rust core ``session::handlers::clean_background_terminals``.

    Product TUI active-thread runtimes can be backed by a full session object,
    a session config carrying services, or a lightweight test/runtime object.
    Rust ultimately calls ``Session::close_unified_exec_processes``; Python
    follows that hook first and then falls back to the ported unified-exec
    manager when it is exposed through services.
    """

    for source in (
        runtime,
        getattr(runtime, "session", None),
        getattr(runtime, "session_config", None),
    ):
        cleaner = getattr(source, "close_unified_exec_processes", None)
        if callable(cleaner):
            result = cleaner()
            if hasattr(result, "__await__"):
                _run_coro_blocking(result)
            return

    for source in (
        runtime,
        getattr(runtime, "session", None),
        getattr(runtime, "session_config", None),
        getattr(getattr(runtime, "session_config", None), "services", None),
        getattr(getattr(runtime, "session", None), "services", None),
    ):
        manager = getattr(source, "unified_exec_manager", None)
        terminator = getattr(manager, "terminate_all_processes", None)
        if callable(terminator):
            terminator()
            return


@dataclass
class _ActiveCoreTurn:
    thread_id: str
    turn_id: str
    queue: Queue[Any]
    lock: Lock = field(default_factory=Lock)
    cancel_event: Event = field(default_factory=Event)
    terminal_sent: bool = False
    cancellation_requested: bool = False

    def put(self, notification: ServerNotification) -> bool:
        with self.lock:
            if self.terminal_sent:
                return False
            self.queue.put(notification)
            return True

    def finish(self, notification: ServerNotification) -> bool:
        with self.lock:
            if self.terminal_sent:
                return False
            self.terminal_sent = True
            self.queue.put(notification)
            self.queue.put(_EOF)
            return True

    def interrupt(self) -> bool:
        with self.lock:
            self.cancellation_requested = True
            self.cancel_event.set()
            if self.terminal_sent:
                return False
            self.terminal_sent = True
            self.queue.put(_turn_interrupted_notification(self.thread_id, self.turn_id))
            self.queue.put(_EOF)
            return True

    def is_terminal_sent(self) -> bool:
        with self.lock:
            return self.terminal_sent

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    async def cancelled(self) -> None:
        if self.cancel_event.is_set():
            return
        await asyncio.to_thread(self.cancel_event.wait)


@dataclass
class ExecFunctionActiveThreadRuntime:
    """Adapt the current exec implementation to Rust-style notifications.

    The wrapped callable is intentionally below the TUI runtime boundary.  The
    TUI submits an ``AppCommand`` and observes server notifications; it no
    longer synchronously waits for the callable's final return value.
    """

    execute_prompt: Callable[[str], int | tuple[int, str]]

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        if op.kind == "Interrupt":
            return _closed_event_stream()
        if op.kind == "CleanBackgroundTerminals":
            _clean_background_terminals_for_runtime(self)
            return _closed_event_stream()
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

    def shutdown_thread(self, thread_id: str) -> ActiveThreadEventStream:
        queue: Queue[Any] = Queue()
        queue.put(ServerNotification("ThreadClosed", {"thread_id": thread_id}))
        queue.put(_EOF)
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
    _active_turn_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _active_turn: _ActiveCoreTurn | None = field(default=None, init=False, repr=False)
    _rollout_path_ready: Event = field(default_factory=Event, init=False, repr=False)
    _last_worker_error: BaseException | None = field(default=None, init=False, repr=False)
    _startup_app_server_events: Queue[Any] = field(default_factory=Queue, init=False, repr=False)
    rollout_path: Path | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._seed_configured_mcp_startup_events()
        if self.prewarmed_model_session is not None:
            self._startup_prewarm_session = self.prewarmed_model_session
            self._startup_prewarm_ready.set()
            return
        if self.startup_prewarm_enabled:
            self._schedule_startup_prewarm()

    @property
    def thread_id(self) -> str | None:
        return _model_client_state_value(self.model_client, "thread_id")

    @property
    def conversation_id(self) -> str | None:
        return self.thread_id

    @property
    def session_id(self) -> str | None:
        return _model_client_state_value(self.model_client, "session_id")

    def next_app_server_event(self, timeout: float | None = 0) -> object | None:
        try:
            wait = 0.0 if timeout is None else max(float(timeout), 0.0)
            return self._startup_app_server_events.get(timeout=wait)
        except Empty:
            return None

    def _seed_configured_mcp_startup_events(self) -> None:
        names = refresh_mcp_startup_expected_servers_from_config(self.session_config)
        for name in names:
            self._startup_app_server_events.put(
                {
                    "kind": "ServerNotification",
                    "notification": ServerNotification(
                        "McpServerStatusUpdated",
                        {"name": name, "status": "Starting"},
                    ),
                }
            )
            self._startup_app_server_events.put(
                {
                    "kind": "ServerNotification",
                    "notification": ServerNotification(
                        "McpServerStatusUpdated",
                        {
                            "name": name,
                            "status": "Failed",
                            "error": (
                                f"MCP client for `{name}` failed to start: "
                                "MCP runtime is not implemented in the PyCodex TUI"
                            ),
                        },
                    ),
                }
            )

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        if op.kind == "Interrupt":
            with self._active_turn_lock:
                active_turn = self._active_turn
            if active_turn is not None:
                active_turn.interrupt()
            return _closed_event_stream()
        if op.kind == "CleanBackgroundTerminals":
            _clean_background_terminals_for_runtime(self)
            return _closed_event_stream()
        queue: Queue[Any] = Queue()
        turn_id = "terminal-turn"
        active_turn = _ActiveCoreTurn(thread_id=thread_id, turn_id=turn_id, queue=queue)
        queue.put(_turn_started_notification(thread_id, turn_id))
        self._rollout_path_ready.clear()
        self._last_worker_error = None
        with self._active_turn_lock:
            self._active_turn = active_turn

        def worker() -> None:
            observed_delta = False
            observed_error_message: str | None = None
            pending_commands: dict[str, dict[str, Any]] = {}
            completed_commands: set[str] = set()
            observed_live_kinds: set[str] = set()

            def observe_session_event(event: Any) -> None:
                nonlocal observed_delta, observed_error_message
                event_type = _field(event, "type")
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
                    type=event_type,
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
                    if notification.kind == "TurnCompleted":
                        active_turn.finish(notification)
                    else:
                        active_turn.put(notification)

            try:
                model_session = self._take_startup_prewarm_session()
                result = asyncio.run(
                    self._run_op(
                        op,
                        session_event_observer=observe_session_event,
                        model_session=model_session,
                        cancellation_token=active_turn,
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
                    active_turn.put(event)
                for notification in _command_completion_notifications_from_result(
                    result,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    pending_commands=pending_commands,
                    completed_commands=completed_commands,
                ):
                    active_turn.put(notification)
                final_text = final_text_from_local_http_exec_result(result)
                if final_text and not emitted_delta:
                    active_turn.put(ServerNotification("AgentMessageDelta", {"delta": final_text, "thread_id": thread_id, "turn_id": turn_id}))
                    emitted_delta = True
                if observed_error_message and not emitted_delta:
                    active_turn.finish(_turn_failed_notification(thread_id, turn_id, observed_error_message, exit_code=1))
                else:
                    active_turn.finish(_turn_completed_notification(thread_id, turn_id, result))
            except BaseException as exc:
                self._last_worker_error = exc
                _timing_trace("core_active_thread_worker_failed", error=str(exc))
                active_turn.finish(_turn_failed_notification(thread_id, turn_id, str(exc), exit_code=1))
            finally:
                if not active_turn.is_terminal_sent():
                    active_turn.finish(_turn_failed_notification(thread_id, turn_id, "active thread event stream closed before turn completed", exit_code=1))
                with self._active_turn_lock:
                    if self._active_turn is active_turn:
                        self._active_turn = None

        Thread(target=worker, name="pycodex-tui-core-active-thread", daemon=True).start()
        return QueueActiveThreadEventStream(queue)

    def shutdown_thread(self, thread_id: str) -> ActiveThreadEventStream:
        with self._active_turn_lock:
            active_turn = self._active_turn
        if active_turn is not None:
            active_turn.interrupt()
        queue: Queue[Any] = Queue()
        queue.put(ServerNotification("ThreadClosed", {"thread_id": thread_id}))
        queue.put(_EOF)
        return QueueActiveThreadEventStream(queue)

    def close(self) -> None:
        """Release transport resources owned by the terminal active runtime.

        Rust ``codex-tui::app`` exits by dropping the app/session runtime, which
        releases websocket tasks and their receive loops.  Python keeps these
        objects behind explicit session caches, so the product TUI shutdown path
        must close them instead of relying on interpreter teardown.
        """

        with self._active_turn_lock:
            active_turn = self._active_turn
        if active_turn is not None:
            active_turn.interrupt()

        with self._startup_prewarm_lock:
            startup_session = self._startup_prewarm_session
            self._startup_prewarm_session = None
            self._startup_prewarm_consumed = True
        _close_model_session(startup_session)

        if self.prewarmed_model_session is not startup_session:
            _close_model_session(self.prewarmed_model_session)

        close_cached = getattr(self.model_client, "close_cached_websocket_session", None)
        if callable(close_cached):
            close_cached()

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
                        session = None
                    elif session is not None:
                        _timing_trace("startup_prewarm_ready_after_consumed")
                    else:
                        _timing_trace("startup_prewarm_unavailable")
                _close_model_session(session)
            except BaseException as exc:
                _timing_trace("startup_prewarm_failed", error=str(exc))
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
        cancellation_token: Any = None,
    ) -> Any:
        _timing_trace("core_run_op_started", has_model_session=model_session is not None)
        plan = exec_run_plan_for_app_command(op)
        result = await run_exec_user_turn_core_sampling_websocket_preferred(
            self.session_config,
            plan,
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
            cancellation_token=cancellation_token,
        )
        self._persist_rollout(plan, result)
        return result

    def _persist_rollout(self, plan: ExecRunPlan, result: Any) -> None:
        try:
            if self.codex_home is None:
                return
            operation = getattr(plan, "initial_operation", None)
            input_items = getattr(operation, "items", ()) if getattr(operation, "kind", None) == "user_turn" else ()
            path = persist_core_exec_rollout(
                Path(self.codex_home),
                self.session_config,
                result,
                self.model_client,
                input_items=input_items,
                cli_version="pycodex",
            )
            self.rollout_path = Path(path) if path is not None else None
        finally:
            self._rollout_path_ready.set()

    def wait_for_rollout_path(self, timeout_seconds: float | None = None) -> Path | None:
        """Wait for the post-turn rollout path used by Rust-style exit summaries."""

        self._rollout_path_ready.wait(timeout_seconds)
        return self.rollout_path


@dataclass
class TuiAppRuntime:
    active_thread_runtime: ActiveThreadRuntime
    thread_id: str = "primary"
    rollout_path: Path | None = None
    cwd: Path = field(default_factory=Path.cwd)
    chat_widget: ChatWidgetProtocolRuntime = field(default_factory=ChatWidgetProtocolRuntime)
    routing_state: ThreadRoutingState = field(default_factory=lambda: ThreadRoutingState(active_thread_id="primary", primary_thread_id="primary"))
    agent_navigation: AgentNavigationState = field(default_factory=AgentNavigationState)
    submitted_ops: list[AppCommand] = field(default_factory=list)
    routing_plans: list[ThreadRoutingPlan] = field(default_factory=list)
    event_dispatch_plans: list[EventDispatchPlan] = field(default_factory=list)
    app_server_event_plans: list[AppServerEventPlan] = field(default_factory=list)
    _status_rate_limit_request_id: int = 0

    def __post_init__(self) -> None:
        self.sync_chat_widget_config_from_runtime()

    def sync_chat_widget_config_from_runtime(self) -> None:
        """Project Rust ``Config`` fields needed by ``chatwidget``.

        Rust keeps these values on the loaded core ``Config`` and
        ``codex-tui::chatwidget`` reads them directly.  The Python active
        thread runtime carries the same subset on ``session_config``; mirror it
        into the chatwidget config so Textual rendering follows the configured
        reasoning visibility instead of local UI defaults.
        """

        source = _first_runtime_config_source(
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.active_thread_runtime, "config", None),
            getattr(self.active_thread_runtime, "model_client", None),
        )
        if source is None:
            return
        target = getattr(self.chat_widget, "config", None)
        if target is None:
            target = SimpleNamespace()
            self.chat_widget.config = target
        for name in (
            "hide_agent_reasoning",
            "show_raw_agent_reasoning",
            "model_reasoning_effort",
            "reasoning_effort",
            "model_reasoning_summary",
        ):
            if hasattr(source, name):
                setattr(target, name, getattr(source, name))

    def submit_user_turn(self, prompt: str) -> ActiveThreadEventStream:
        op = app_command_for_prompt(prompt, cwd=self.cwd)
        return self.submit_op(op)

    def submit_op(self, op: AppCommand) -> ActiveThreadEventStream:
        plan = submit_active_thread_op_plan(self.routing_state, op)
        self.routing_plans.append(plan)
        if plan.action != "submit_thread_op" or plan.thread_id is None:
            raise RuntimeError(plan.error_message or "failed to submit active thread op")
        self.submitted_ops.append(op)
        return self.active_thread_runtime.submit_thread_op(plan.thread_id, op)

    def handle_app_event(self, event: AppEvent | dict[str, Any] | Any) -> EventDispatchPlan:
        """Apply the app-level side effects owned by Rust ``app::event_dispatch``.

        Most Rust ``AppEvent`` variants delegate to neighboring modules.  The
        product terminal path only executes the side effects it can faithfully
        own; unsupported variants still return a dispatch plan for tests and
        future composition work.
        """

        plan = dispatch_event_plan(
            EventDispatchState(
                active_thread_id=self.routing_state.active_thread_id,
                chat_widget_thread_id=self.current_displayed_thread_id(),
                pending_shutdown_exit_thread_id=self.routing_state.pending_shutdown_exit_thread_id,
            ),
            event,
        )
        self.event_dispatch_plans.append(plan)
        if plan.action == "update_model":
            model = plan.updates[0][1] if plan.updates else None
            self.update_model(model)
        elif plan.action == "update_reasoning_effort":
            effort = plan.updates[0][1] if plan.updates else None
            self.update_reasoning_effort(effort)
        elif plan.action == "persist_model_selection":
            payload = plan.updates[0][1] if plan.updates else {}
            model = payload.get("model") if isinstance(payload, Mapping) else None
            effort = payload.get("effort") if isinstance(payload, Mapping) else None
            self.persist_model_selection(model, effort)
        elif plan.action == "refresh_rate_limits":
            origin = plan.updates[0][1] if plan.updates else None
            self.refresh_rate_limits(origin)
        elif plan.action == "rate_limits_loaded":
            payload = plan.updates[0][1] if plan.updates else {}
            if isinstance(payload, Mapping):
                self.on_rate_limits_loaded(payload.get("origin"), payload.get("result"))
        elif plan.action == "apply_raw_output_mode":
            payload = plan.updates[0][1] if plan.updates else {}
            enabled = payload.get("enabled") if isinstance(payload, Mapping) else payload
            self.apply_raw_output_mode(enabled)
        elif plan.action == "diff_result":
            text = plan.updates[0][1] if plan.updates else ""
            self.chat_widget.on_diff_complete(text)
        return plan

    def handle_app_server_event(self, event: Any) -> AppServerEventPlan:
        """Apply Rust ``app::app_server_events`` pre-chatwidget routing.

        Rust refreshes the expected MCP startup server set before forwarding
        startup-status notifications and before settling lagged startup rounds.
        Keeping that app-owned step here lets ``chatwidget::mcp_startup`` stay
        focused on its own state machine while the product runtime preserves
        the Rust event ordering.
        """

        plan = plan_app_server_event(
            event,
            primary_thread_id=self.routing_state.primary_thread_id,
        )
        self.app_server_event_plans.append(plan)
        self._apply_app_server_event_plan(plan)
        if (
            plan.notification is not None
            and "refresh_mcp_expected_servers" in plan.actions
            and "handle_global_server_notification" not in plan.actions
        ):
            self.handle_notification(_coerce_server_notification(plan.notification))
        return plan

    def next_status_rate_limit_request_id(self) -> int:
        request_id = self._status_rate_limit_request_id
        self._status_rate_limit_request_id += 1
        return request_id

    def register_status_rate_limit_handle(self, request_id: int, handle: Any) -> None:
        add = getattr(self.chat_widget, "add_refreshing_status_output", None)
        if callable(add):
            add(request_id, handle)

    def refresh_rate_limits(self, origin: Any) -> None:
        """Start the Rust-shaped rate-limit refresh boundary when available.

        Rust spawns an app-server RPC and routes completion as
        ``RateLimitsLoaded``.  The dependency-light runtime records the dispatch
        and supports injected/fake active runtimes that can provide a result
        immediately for tests; real product paths can wire a background request
        source behind the same method without changing TUI projection code.
        """

        fetcher = getattr(self.active_thread_runtime, "fetch_account_rate_limits", None)
        if fetcher is None:
            fetcher = getattr(self.active_thread_runtime, "get_account_rate_limits", None)
        if not callable(fetcher):
            return
        try:
            result = fetcher()
            if hasattr(result, "__await__"):
                result = _run_coro_blocking(result)
        except BaseException as exc:
            result = exc
        self.handle_app_event(AppEvent.rate_limits_loaded(origin, result))

    def on_rate_limits_loaded(self, origin: Any, result: Any) -> None:
        snapshots = _rate_limit_result_snapshots(result)
        if snapshots is not None:
            for snapshot in snapshots:
                display = _rate_limit_snapshot_display(snapshot)
                self.chat_widget.on_rate_limit_snapshot(display)
                _store_runtime_rate_limit_snapshot(self.active_thread_runtime, display)
        if _rate_limit_origin_kind(origin) == RateLimitRefreshOrigin.STATUS_COMMAND:
            request_id = _rate_limit_origin_request_id(origin)
            if request_id is not None:
                self.chat_widget.finish_status_rate_limit_refresh(request_id)

    def refresh_mcp_startup_expected_servers(self) -> list[str]:
        expected: list[str] = []
        for config in (
            getattr(self.chat_widget, "config", None),
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.active_thread_runtime, "config", None),
        ):
            expected = refresh_mcp_startup_expected_servers_from_config(config)
            if expected:
                break
        setter = getattr(self.chat_widget.mcp_startup, "set_mcp_startup_expected_servers", None)
        if callable(setter):
            setter(expected)
        return expected

    def finish_mcp_startup_after_lag(self) -> None:
        finish = getattr(self.chat_widget.mcp_startup, "finish_mcp_startup_after_lag", None)
        if callable(finish):
            previous_warning_count = len(getattr(self.chat_widget.mcp_startup, "warnings", []) or [])
            finish()
        else:
            previous_warning_count = 0
        self.chat_widget.turn.mcp_startup_status = self.chat_widget.mcp_startup.startup_status
        self.chat_widget.turn.update_task_running_state()
        warnings = list(getattr(self.chat_widget.mcp_startup, "warnings", []) or [])
        for warning in warnings[previous_warning_count:]:
            self.chat_widget.turn.on_warning(warning)
        self.chat_widget.request_redraw()

    def apply_raw_output_mode(self, enabled: Any) -> None:
        setter = getattr(self.chat_widget, "set_raw_output_mode", None)
        if callable(setter):
            setter(bool(enabled))
        else:
            setattr(self.chat_widget, "raw_mode", bool(enabled))
        self.chat_widget.request_redraw()

    def update_model(self, model: Any) -> None:
        model_text = "" if model is None else str(model).strip()
        if not model_text:
            return
        setter = getattr(self.chat_widget, "set_model", None)
        if callable(setter):
            setter(model_text)
        _set_runtime_model_value(self.active_thread_runtime, model_text)
        session_config = getattr(self.active_thread_runtime, "session_config", None)
        _set_runtime_model_value(session_config, model_text)
        model_client = getattr(self.active_thread_runtime, "model_client", None)
        _set_runtime_model_value(model_client, model_text)

    def update_reasoning_effort(self, effort: Any = None) -> None:
        effort_text = _effort_config_value(effort)
        setter = getattr(self.chat_widget, "set_reasoning_effort", None)
        if callable(setter):
            setter(effort_text)
        else:
            setattr(self.chat_widget.config, "model_reasoning_effort", effort_text)
        for target in (
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.active_thread_runtime, "model_client", None),
        ):
            if target is not None:
                setattr(target, "model_reasoning_effort", effort_text)
                setattr(target, "reasoning_effort", effort_text)

    def persist_model_selection(self, model: Any, effort: Any = None) -> bool:
        """Persist a model selection using Rust ``config_update`` semantics."""

        model_text = "" if model is None else str(model).strip()
        if not model_text:
            return False
        effort_text = _effort_config_value(effort)
        try:
            request_handle = _request_handle_from_runtime(self.active_thread_runtime)
            if request_handle is not None:
                _run_coro_blocking(write_config_batch(request_handle, build_model_selection_edits(model_text, effort_text)))
            else:
                config = _config_from_runtime(self.active_thread_runtime)
                if config is None:
                    raise RuntimeError("missing request handle or config")
                ConfigEditsBuilder.for_config(config).set_model(model_text, effort_text).apply_blocking()
        except BaseException as exc:
            self.chat_widget.add_error_message(f"Failed to save default model: {exc}")
            return False

        message = f"Model changed to {model_text}"
        label = _reasoning_label_for(model_text, effort_text)
        if label is not None:
            message = f"{message} {label}"
        self.chat_widget.add_info_message(message, None)
        return True

    def shutdown_current_thread(self, *, timeout_seconds: float = 2.0) -> bool:
        thread_id = self.routing_state.active_thread_id or self.thread_id
        self.routing_state.pending_shutdown_exit_thread_id = thread_id
        self.routing_plans.append(
            ThreadRoutingPlan(
                action="shutdown_current_thread",
                thread_id=thread_id,
                app_server_call=("thread_shutdown", thread_id),
            )
        )
        shutdown_thread = getattr(self.active_thread_runtime, "shutdown_thread", None)
        if not callable(shutdown_thread):
            self.routing_state.pending_shutdown_exit_thread_id = None
            return False
        try:
            stream = shutdown_thread(thread_id)
            deadline = time.monotonic() + max(0.0, timeout_seconds)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                event = stream.next_event(timeout=min(0.05, remaining))
                if event is None:
                    if getattr(stream, "closed", False):
                        return True
                    continue
                self.handle_notification(event)
                if event.kind == "ThreadClosed":
                    return True
        except BaseException:
            return False
        finally:
            self.routing_state.pending_shutdown_exit_thread_id = None

    def close(self) -> None:
        closer = getattr(self.active_thread_runtime, "close", None)
        if callable(closer):
            closer()

    def current_displayed_thread_id(self) -> str | None:
        if self.routing_state.active_thread_id:
            return self.routing_state.active_thread_id
        thread_id = getattr(self.chat_widget, "thread_id", None)
        thread_id = thread_id() if callable(thread_id) else thread_id
        if thread_id is None:
            return None
        text = str(thread_id).strip()
        return text or None

    def upsert_agent_picker_thread(
        self,
        thread_id: str,
        *,
        agent_nickname: str | None = None,
        agent_role: str | None = None,
        is_closed: bool = False,
    ) -> str | None:
        try:
            self.agent_navigation.upsert(
                thread_id,
                agent_nickname=agent_nickname,
                agent_role=agent_role,
                is_closed=is_closed,
            )
        except (TypeError, ValueError, AttributeError):
            return self.sync_active_agent_label()
        return self.sync_active_agent_label()

    def mark_agent_picker_thread_closed(self, thread_id: str) -> str | None:
        try:
            self.agent_navigation.mark_closed(thread_id)
        except (TypeError, ValueError, AttributeError):
            return self.sync_active_agent_label()
        return self.sync_active_agent_label()

    def sync_active_agent_label(self) -> str | None:
        try:
            label = self.agent_navigation.active_agent_label(
                self.current_displayed_thread_id(),
                self.routing_state.primary_thread_id,
            )
        except (TypeError, ValueError, AttributeError):
            label = None
        self.chat_widget.set_active_agent_label(label)
        return label

    def select_agent_thread(self, thread_id: str) -> ThreadRoutingPlan:
        target_thread_id = str(thread_id).strip()
        entry = self.agent_navigation.get(target_thread_id)
        if entry is None:
            error_message = f"Agent thread {target_thread_id} is no longer available."
            self.chat_widget.add_error_message(error_message)
            plan = ThreadRoutingPlan(
                action="select_agent_thread_unavailable",
                thread_id=target_thread_id,
                error_message=error_message,
            )
            self.routing_plans.append(plan)
            return plan

        if self.routing_state.active_thread_id == target_thread_id:
            label = self.sync_active_agent_label()
            plan = ThreadRoutingPlan(
                action="select_agent_thread_current",
                thread_id=target_thread_id,
                updates=(("active_agent_label", label),),
            )
            self.routing_plans.append(plan)
            return plan

        self.routing_state.active_thread_id = target_thread_id
        label = self.sync_active_agent_label()
        plan = ThreadRoutingPlan(
            action="select_agent_thread",
            thread_id=target_thread_id,
            updates=(("active_thread_id", target_thread_id), ("active_agent_label", label)),
        )
        self.routing_plans.append(plan)
        return plan

    def select_adjacent_agent_thread(self, direction: AgentNavigationDirection) -> ThreadRoutingPlan:
        target_thread_id = self.agent_navigation.adjacent_thread_id(
            self.current_displayed_thread_id(),
            direction,
        )
        if target_thread_id is None:
            plan = ThreadRoutingPlan(action="select_adjacent_agent_thread_skipped")
            self.routing_plans.append(plan)
            return plan
        return self.select_agent_thread(target_thread_id)

    def handle_notification(self, notification: ServerNotification) -> None:
        if notification.kind == "McpServerStatusUpdated":
            self.refresh_mcp_startup_expected_servers()
        if notification.kind == "ThreadClosed":
            plan = active_thread_event_plan(self.routing_state, {"notification": notification})
            self.routing_plans.append(plan)
            if plan.action == "failover_to_primary_thread" and plan.target_thread_id is not None:
                self.routing_state.active_thread_id = plan.target_thread_id
                self.mark_agent_picker_thread_closed(plan.thread_id or "")
                if plan.info_message:
                    self.chat_widget.add_info_message(plan.info_message, None)
                return
        self.chat_widget.handle(notification)

    def _apply_app_server_event_plan(self, plan: AppServerEventPlan) -> None:
        if "refresh_mcp_expected_servers" in plan.actions:
            self.refresh_mcp_startup_expected_servers()
        if "finish_mcp_startup_after_lag" in plan.actions:
            self.finish_mcp_startup_after_lag()
        if "handle_global_server_notification" in plan.actions and plan.notification is not None:
            self.handle_notification(_coerce_server_notification(plan.notification))
        if "add_error_message" in plan.actions and plan.message:
            self.chat_widget.add_error_message(plan.message)


def app_command_for_prompt(prompt: str, *, cwd: Path | str) -> AppCommand:
    widget = _TerminalInputSubmissionWidget(cwd=Path(cwd))
    accepted = submit_user_message_with_history_record(
        widget,
        UserMessage(prompt),
        UserMessageHistoryRecord.user_message_text(),
    )
    if not accepted or not widget.ops:
        raise ValueError("terminal user input was not accepted for submission")
    return widget.ops[-1]


def user_turn_prompt(op: AppCommand) -> str:
    if op.kind != "UserTurn":
        return ""
    items = op.payload.get("items") or []
    texts: list[str] = []
    for item in items:
        text = _item_text(item)
        if text is not None:
            texts.append(str(text))
    return "\n".join(texts)


def _model_client_state_value(model_client: Any, name: str) -> str | None:
    state = getattr(model_client, "state", None)
    value = getattr(state, name, None)
    value = value() if callable(value) else value
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _set_runtime_model_value(target: Any, model: str) -> None:
    if target is None:
        return
    if isinstance(target, dict):
        target["model"] = model
        return
    for name in ("model", "model_slug", "requested_model"):
        if hasattr(target, name):
            try:
                setattr(target, name, model)
            except (AttributeError, TypeError):
                pass
            return
    try:
        setattr(target, "model", model)
    except (AttributeError, TypeError):
        return


def exec_run_plan_for_app_command(op: AppCommand) -> ExecRunPlan:
    if op.kind == "Review":
        target = _review_target_for_protocol(op.payload.get("target"))
        return ExecRunPlan(InitialOperation.review(ReviewRequest(target=target)), _review_prompt_summary(target))
    if op.kind != "UserTurn":
        raise ValueError("active thread runtime supports only AppCommand::UserTurn or AppCommand::Review")
    return ExecRunPlan(
        InitialOperation.user_turn(user_inputs_for_app_command(op), op.payload.get("final_output_json_schema")),
        user_turn_prompt(op),
    )


def _review_target_for_protocol(value: Any) -> ReviewTarget:
    if isinstance(value, ReviewTarget):
        return value
    target_type = _field(value, "type")
    if target_type == "uncommittedChanges":
        return ReviewTarget.uncommitted_changes()
    if target_type == "baseBranch":
        return ReviewTarget.base_branch(str(_field(value, "branch") or ""))
    if target_type == "commit":
        title = _field(value, "title")
        return ReviewTarget.commit(str(_field(value, "sha") or ""), None if title is None else str(title))
    if target_type == "custom":
        return ReviewTarget.custom(str(_field(value, "instructions") or ""))
    if isinstance(value, Mapping):
        return ReviewTarget.from_mapping(dict(value))
    raise ValueError(f"unknown review target: {value!r}")


def _review_prompt_summary(target: ReviewTarget) -> str:
    if target.type == "custom":
        return str(target.instructions or "").strip()
    if target.type == "baseBranch":
        return f"Review changes against {target.branch}"
    if target.type == "commit":
        title = f": {target.title}" if target.title else ""
        return f"Review commit {target.sha}{title}"
    return "Review current changes"


def user_inputs_for_app_command(op: AppCommand) -> tuple[UserInput, ...]:
    if op.kind != "UserTurn":
        return ()
    user_inputs: list[UserInput] = []
    for item in op.payload.get("items") or ():
        raw_kind = _field(item, "kind")
        kind = str(raw_kind or "").lower()
        if kind == "text":
            user_inputs.append(UserInput.text_input(str(_item_text(item) or "")))
        elif kind in {"localimage", "local_image"}:
            path = _item_payload_field(item, "path")
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
    event_type = _field(event, "type")
    payload = _field(event, "payload", event)
    if event_type == "agent_message_content_delta":
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("AgentMessageDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type in {"reasoning_summary_delta", "reasoning_content_delta"}:
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("ReasoningSummaryTextDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type in {"reasoning_summary_part_added", "agent_reasoning_section_break"}:
        return (ServerNotification("ReasoningSummaryPartAdded", {"thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "reasoning_raw_content_delta":
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("ReasoningTextDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "response_created":
        return (ServerNotification("ResponseStarted", {"thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "token_count":
        token_usage = _thread_token_usage_from_token_count_event(payload)
        if token_usage is not None:
            return (
                ServerNotification(
                    "ThreadTokenUsageUpdated",
                    {
                        "thread_id": thread_id,
                        "token_usage": token_usage,
                    },
                ),
            )
    if event_type in {"task_complete", "turn_complete"}:
        return (_turn_completed_notification(thread_id, turn_id, SimpleNamespace(turn_status="completed")),)
    if event_type in {"task_aborted", "turn_aborted"}:
        return (_turn_interrupted_notification(thread_id, turn_id),)
    if event_type in {"item_started", "item_completed"}:
        item = _chatwidget_item_from_turn_item(_field(payload, "item"))
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
        timestamp_value = _field(payload, timestamp_name)
        if not isinstance(timestamp_value, int):
            timestamp_value = int(time.time() * 1000)
        return (
            ServerNotification(
                notification_kind,
                {
                    "thread_id": _thread_id_value(_field(payload, "thread_id", thread_id)),
                    "turn_id": _field(payload, "turn_id", turn_id),
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
        turn_item = _turn_item_from_response_item(item)
        chat_item = _chatwidget_item_from_turn_item(turn_item)
        if chat_item is not None:
            return (
                ServerNotification(
                    "ItemCompleted",
                    {
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "completed_at_ms": int(time.time() * 1000),
                        "item": chat_item,
                    },
                ),
            )
    return ()


def _thread_token_usage_from_token_count_event(payload: Any) -> dict[str, Any] | None:
    """Project Rust ``TokenCountEvent.info`` into app-server token usage shape."""

    info = _field(payload, "info", payload)
    if info is None:
        return None
    total = _field(info, "total_token_usage", None)
    last = _field(info, "last_token_usage", None)
    if total is None and last is None:
        return None
    return {
        "total": _token_usage_mapping(total),
        "last": _token_usage_mapping(last),
        "model_context_window": _field(info, "model_context_window", None),
    }


def _token_usage_mapping(value: Any) -> dict[str, int]:
    return {
        "total_tokens": int(_field(value, "total_tokens", 0) or 0),
        "input_tokens": int(_field(value, "input_tokens", 0) or 0),
        "cached_input_tokens": int(_field(value, "cached_input_tokens", 0) or 0),
        "output_tokens": int(_field(value, "output_tokens", 0) or 0),
        "reasoning_output_tokens": int(_field(value, "reasoning_output_tokens", 0) or 0),
    }


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


def _turn_item_from_response_item(item: Any) -> TurnItem | None:
    if item is None:
        return None
    response_item: ResponseItem | None
    if isinstance(item, ResponseItem):
        response_item = item
    elif isinstance(item, Mapping):
        try:
            response_item = ResponseItem.from_mapping(item)
        except (KeyError, TypeError, ValueError):
            return None
    else:
        to_mapping = getattr(item, "to_mapping", None)
        if callable(to_mapping):
            try:
                response_item = ResponseItem.from_mapping(to_mapping())
            except (KeyError, TypeError, ValueError):
                return None
        else:
            response_item = None
    return parse_turn_item(response_item) if response_item is not None else None


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
    if status.lower() == "interrupted":
        return _turn_interrupted_notification(thread_id, turn_id)
    return _turn_failed_notification(thread_id, turn_id, status, exit_code=1)


def _turn_interrupted_notification(thread_id: str, turn_id: str) -> ServerNotification:
    return ServerNotification(
        "TurnCompleted",
        {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Interrupted", "duration_ms": None}},
    )


def _turn_failed_notification(thread_id: str, turn_id: str, message: str, *, exit_code: int) -> ServerNotification:
    return ServerNotification(
        "TurnCompleted",
        {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Failed", "error": {"message": message, "codex_error_info": None, "exit_code": exit_code}}},
    )


def _coerce_server_notification(notification: Any) -> ServerNotification:
    if isinstance(notification, ServerNotification):
        return notification
    kind = _field(notification, "kind", _field(notification, "type", None))
    if kind is None:
        raise ValueError("app-server notification is missing kind/type")
    payload = _field(notification, "payload", None)
    return ServerNotification(str(kind), notification if payload is None else payload)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _item_payload_field(value: Any, name: str, default: Any = None) -> Any:
    direct = _field(value, name, None)
    if direct is not None:
        return direct
    payload = _field(value, "payload", None)
    if isinstance(payload, Mapping):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _item_text(value: Any) -> Any:
    return _item_payload_field(value, "text")


@dataclass
class _TerminalMode:
    model_name: str = "terminal"

    def model(self) -> str:
        return self.model_name

    def reasoning_effort(self) -> Any:
        return None


@dataclass
class _TerminalPermissions:
    approval_policy: Any = None

    def active_permission_profile(self) -> Any:
        return None


@dataclass
class _TerminalFeatures:
    def enabled(self, _name: str) -> bool:
        return False


@dataclass
class _TerminalBottomPane:
    def take_recent_submission_images_with_placeholders(self) -> tuple[Any, ...]:
        return ()

    def take_recent_submission_mention_bindings(self) -> tuple[Any, ...]:
        return ()

    def skills(self) -> None:
        return None


@dataclass
class _TerminalInputQueue:
    queued_user_messages: Any = field(default_factory=list)
    queued_user_message_history_records: Any = field(default_factory=list)
    user_turn_pending_start: bool = False
    pending_steers: Any = field(default_factory=list)


@dataclass
class _TerminalInputSubmissionWidget:
    cwd: Path
    ops: list[AppCommand] = field(default_factory=list)
    bottom_pane: _TerminalBottomPane = field(default_factory=_TerminalBottomPane)
    input_queue: _TerminalInputQueue = field(default_factory=_TerminalInputQueue)

    def __post_init__(self) -> None:
        from types import SimpleNamespace

        self.turn_lifecycle = SimpleNamespace(agent_turn_running=False)
        self.transcript = SimpleNamespace(needs_final_message_separator=True, saw_plan_item_this_turn=False)
        self.config = SimpleNamespace(
            cwd=self.cwd,
            permissions=_TerminalPermissions(),
            features=_TerminalFeatures(),
            personality=None,
        )

    def take_remote_image_urls(self) -> tuple[str, ...]:
        return ()

    def is_session_configured(self) -> bool:
        return True

    def current_model_supports_images(self) -> bool:
        return True

    def effective_collaboration_mode(self) -> _TerminalMode:
        return _TerminalMode()

    def collaboration_modes_enabled(self) -> bool:
        return False

    def current_model_supports_personality(self) -> bool:
        return False

    def service_tier_update_for_core(self) -> Any:
        return None

    def maybe_apply_ide_context(self, _items: Any) -> None:
        return None

    def plugins_for_mentions(self) -> None:
        return None

    def connectors_for_mentions(self) -> None:
        return None

    def submit_op(self, op: AppCommand) -> bool:
        self.ops.append(op)
        return True

    def append_message_history_entry(self, _text: str) -> None:
        return None

    def on_user_message_display(self, _display: Any) -> None:
        return None


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
