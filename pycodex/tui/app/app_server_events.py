"""App-server event stream handling for the TUI app.

Upstream source: ``codex/codex-rs/tui/src/app/app_server_events.rs``.

Rust implements this as methods on ``App``.  The Python port exposes pure
semantic planning helpers so callers can apply the same routing decisions
without depending on the full TUI runtime object graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::app_server_events",
    source="codex/codex-rs/tui/src/app/app_server_events.rs",
    status="complete",
)


@dataclass(frozen=True)
class AppServerEventPlan:
    actions: Tuple[str, ...]
    thread_id: Optional[str] = None
    message: Optional[str] = None
    notification: Any = None
    request: Any = None
    rejection: Any = None


@dataclass
class PendingRequests:
    unsupported: Any = None
    resolved: Dict[str, Any] = field(default_factory=dict)
    noted: List[Any] = field(default_factory=list)

    def note_server_request(self, request: Any) -> Any:
        self.noted.append(request)
        return self.unsupported

    def resolve_notification(self, request_id: str) -> Any:
        return self.resolved.pop(request_id, None)


def refresh_mcp_startup_expected_servers_from_config(config: Any) -> List[str]:
    servers = _get(_get(config, "mcp_servers", {}), "get", None)
    if callable(servers):
        servers = servers()
    if servers is None:
        servers = _get(config, "mcp_servers", {})
    items = servers.items() if hasattr(servers, "items") else []
    return [name for name, server in items if bool(_get(server, "enabled", True))]


def plan_app_server_event(
    event: Any,
    *,
    primary_thread_id: Optional[str] = None,
    pending_requests: Any = None,
) -> AppServerEventPlan:
    kind = _variant(event)
    if kind == "Lagged":
        return AppServerEventPlan(("warn_lagged", "refresh_mcp_expected_servers", "finish_mcp_startup_after_lag"))
    if kind == "ServerNotification":
        return plan_server_notification_event(
            _payload(event, "notification"),
            primary_thread_id=primary_thread_id,
            pending_requests=pending_requests,
        )
    if kind == "ServerRequest":
        return plan_server_request_event(
            _payload(event, "request"),
            primary_thread_id=primary_thread_id,
            pending_requests=pending_requests,
        )
    if kind == "Disconnected":
        message = str(_payload(event, "message") or "")
        return AppServerEventPlan(("warn_disconnected", "add_error_message", "fatal_exit_request"), message=message)
    return AppServerEventPlan(("ignore_unknown_event",), message=kind)


def plan_server_notification_event(
    notification: Any,
    *,
    primary_thread_id: Optional[str] = None,
    pending_requests: Any = None,
) -> AppServerEventPlan:
    kind = _variant(notification)
    if kind == "ServerRequestResolved":
        request_id = _get(_payload(notification, "notification", notification), "request_id", None)
        resolved = _resolve_pending(pending_requests, request_id)
        actions = ("resolve_pending_request", "dismiss_app_server_request") if resolved is not None else ("resolve_pending_request",)
        return AppServerEventPlan(actions, notification=notification, request=resolved)
    if kind == "McpServerStatusUpdated":
        return AppServerEventPlan(("refresh_mcp_expected_servers",), notification=notification)
    if kind == "AccountRateLimitsUpdated":
        return AppServerEventPlan(("update_rate_limit_snapshot",), notification=notification)
    if kind == "AccountUpdated":
        return AppServerEventPlan(("update_account_state",), notification=notification)
    if kind == "ExternalAgentConfigImportCompleted":
        return AppServerEventPlan(
            (
                "refresh_in_memory_config_from_disk",
                "refresh_plugin_mentions",
                "reload_user_config",
                "fetch_plugins_list",
            ),
            notification=notification,
        )
    if kind == "AppListUpdated":
        return AppServerEventPlan(("on_connectors_loaded",), notification=notification)

    target = _notification_thread_target(notification)
    if target.kind == "Thread":
        actions = ("enqueue_primary_thread_notification",) if primary_thread_id in {None, target.thread_id} else ("enqueue_thread_notification",)
        return AppServerEventPlan(actions, thread_id=target.thread_id, notification=notification)
    if target.kind == "InvalidThreadId":
        return AppServerEventPlan(("warn_invalid_thread_id",), thread_id=target.thread_id, notification=notification)
    return AppServerEventPlan(("handle_global_server_notification",), notification=notification)


def plan_server_request_event(
    request: Any,
    *,
    primary_thread_id: Optional[str] = None,
    pending_requests: Any = None,
) -> AppServerEventPlan:
    unsupported = _note_pending_request(pending_requests, request)
    if unsupported is not None:
        return AppServerEventPlan(
            ("warn_unsupported_request", "add_error_message", "reject_app_server_request"),
            request=request,
            rejection=unsupported,
            message=str(_get(unsupported, "message", "")),
        )

    thread_id = _request_thread_id(request)
    if thread_id is None:
        return AppServerEventPlan(("warn_threadless_request",), request=request)
    actions = ("enqueue_primary_thread_request",) if primary_thread_id in {None, thread_id} else ("enqueue_thread_request",)
    return AppServerEventPlan(actions, thread_id=thread_id, request=request)


@dataclass(frozen=True)
class _ThreadTarget:
    kind: str
    thread_id: Optional[str] = None


def _notification_thread_target(notification: Any) -> _ThreadTarget:
    thread_id = _get(notification, "thread_id", None)
    payload = _payload(notification, "notification", notification)
    thread_id = _get(payload, "thread_id", thread_id)
    if thread_id is None:
        return _ThreadTarget("Global")
    thread_id = str(thread_id)
    if not thread_id:
        return _ThreadTarget("InvalidThreadId", thread_id)
    return _ThreadTarget("Thread", thread_id)


def _request_thread_id(request: Any) -> Optional[str]:
    thread_id = _get(request, "thread_id", None)
    payload = _payload(request, "request", request)
    thread_id = _get(payload, "thread_id", thread_id)
    return None if thread_id is None or str(thread_id) == "" else str(thread_id)


def _note_pending_request(pending_requests: Any, request: Any) -> Any:
    if pending_requests is None:
        return None
    note = getattr(pending_requests, "note_server_request", None)
    return note(request) if callable(note) else None


def _resolve_pending(pending_requests: Any, request_id: Any) -> Any:
    if pending_requests is None or request_id is None:
        return None
    resolve = getattr(pending_requests, "resolve_notification", None)
    return resolve(str(request_id)) if callable(resolve) else None


def _variant(value: Any) -> str:
    for attr in ("kind", "type", "variant"):
        found = _get(value, attr, None)
        if found is not None:
            return str(found)
    name = getattr(value, "name", None)
    if name is not None:
        return str(name)
    return type(value).__name__


def _payload(value: Any, field: str, default: Any = None) -> Any:
    payload = _get(value, field, None)
    if payload is not None:
        return payload
    payload = _get(value, "payload", None)
    return default if payload is None else payload


def _get(value: Any, field: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(field, default)
    return getattr(value, field, default)


__all__ = [
    "AppServerEventPlan",
    "PendingRequests",
    "RUST_MODULE",
    "plan_app_server_event",
    "plan_server_notification_event",
    "plan_server_request_event",
    "refresh_mcp_startup_expected_servers_from_config",
]
