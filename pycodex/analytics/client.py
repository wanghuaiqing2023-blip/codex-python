"""Rust-aligned ``codex-analytics::client`` owner."""

from __future__ import annotations

import http.client
import json
from typing import Any
from urllib.parse import urlsplit

from . import now_unix_seconds
from .accepted_lines import *
from .events import *
from .facts import *
from .reducer import *

ANALYTICS_EVENT_DEDUPE_MAX_KEYS = 4096

ANALYTICS_EVENTS_TIMEOUT_SECONDS = 15

ANALYTICS_RELEVANT_CLIENT_REQUEST_KINDS = frozenset(("TurnStart", "TurnSteer"))

ANALYTICS_RELEVANT_CLIENT_RESPONSE_KINDS = frozenset(
    ("ThreadStart", "ThreadResume", "ThreadFork", "TurnStart", "TurnSteer")
)

ANALYTICS_RELEVANT_NOTIFICATION_KINDS = frozenset(
    (
        "TurnStarted",
        "TurnCompleted",
        "TurnDiffUpdated",
        "ItemStarted",
        "ItemCompleted",
        "ItemGuardianApprovalReviewStarted",
        "ItemGuardianApprovalReviewCompleted",
    )
)

def should_send_in_isolated_request(event: dict[str, Any] | Any) -> bool:
    return _event_type(event) == "codex_accepted_line_fingerprints"

def track_event_request_batches(events: list[dict[str, Any] | Any]) -> list[list[dict[str, Any] | Any]]:
    batches: list[list[dict[str, Any] | Any]] = []
    current_batch: list[dict[str, Any] | Any] = []
    for event in events:
        if should_send_in_isolated_request(event):
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            batches.append([event])
        else:
            current_batch.append(event)
    if current_batch:
        batches.append(current_batch)
    return batches

def send_track_events(auth: Any, base_url: str, events: list[dict[str, Any] | Any]) -> list[int]:
    if not events:
        return []
    resolved_auth = _resolve_auth(auth)
    if resolved_auth is None:
        return []
    if not _uses_codex_backend(resolved_auth):
        return []
    url = f"{base_url.rstrip('/')}/codex/analytics-events/events"
    statuses: list[int] = []
    for batch in track_event_request_batches(events):
        status = send_track_events_request(resolved_auth, url, batch)
        if status is not None:
            statuses.append(status)
    return statuses

def send_track_events_request(auth: Any, url: str, events: list[dict[str, Any] | Any]) -> int | None:
    if not events:
        return None
    body = json.dumps({"events": [_jsonable_event(event) for event in events]}, separators=(",", ":")).encode("utf-8")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid analytics endpoint: {url}")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    headers = _auth_headers(resolved_auth=auth)
    headers["Content-Type"] = "application/json"
    headers["Content-Length"] = str(len(body))
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.hostname, parsed.port, timeout=ANALYTICS_EVENTS_TIMEOUT_SECONDS)
    try:
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        response.read()
        return response.status
    finally:
        conn.close()

def analytics_relevant_client_request(kind: str) -> bool:
    return kind in ANALYTICS_RELEVANT_CLIENT_REQUEST_KINDS

def analytics_relevant_client_response(kind: str) -> bool:
    return kind in ANALYTICS_RELEVANT_CLIENT_RESPONSE_KINDS

def analytics_relevant_notification(kind: str) -> bool:
    return kind in ANALYTICS_RELEVANT_NOTIFICATION_KINDS

def _event_type(event: dict[str, Any] | Any) -> str | None:
    if isinstance(event, dict):
        value = event.get("event_type")
        return value if isinstance(value, str) else None
    value = getattr(event, "event_type", None)
    return value if isinstance(value, str) else None

def _jsonable_event(event: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    to_json_dict = getattr(event, "to_json_dict", None)
    if callable(to_json_dict):
        value = to_json_dict()
        if isinstance(value, dict):
            return value
    if hasattr(event, "__dict__"):
        return dict(vars(event))
    raise TypeError(f"analytics event is not JSON serializable: {event!r}")

def _resolve_auth(auth: Any) -> Any | None:
    if auth is None:
        return None
    auth_method = getattr(auth, "auth", None)
    if callable(auth_method):
        return auth_method()
    return auth

def _uses_codex_backend(auth: Any) -> bool:
    uses_codex_backend = getattr(auth, "uses_codex_backend", None)
    if callable(uses_codex_backend):
        return bool(uses_codex_backend())
    if isinstance(auth, dict) and "uses_codex_backend" in auth:
        return bool(auth["uses_codex_backend"])
    return bool(getattr(auth, "codex_backend", False))

def _auth_headers(resolved_auth: Any) -> dict[str, str]:
    for name in ("to_auth_headers", "auth_headers", "headers"):
        value = getattr(resolved_auth, name, None)
        if callable(value):
            return {str(key): str(header_value) for key, header_value in value().items()}
        if isinstance(value, dict):
            return {str(key): str(header_value) for key, header_value in value.items()}
    if isinstance(resolved_auth, dict):
        headers = resolved_auth.get("headers")
        if isinstance(headers, dict):
            return {str(key): str(value) for key, value in headers.items()}
        token = resolved_auth.get("token") or resolved_auth.get("access_token")
        if token is not None:
            return {"Authorization": f"Bearer {token}"}
    token = getattr(resolved_auth, "token", None) or getattr(resolved_auth, "access_token", None)
    if token is not None:
        return {"Authorization": f"Bearer {token}"}
    return {}

class AnalyticsEventsClient:
    def __init__(
        self,
        auth_manager: Any = None,
        base_url: str = "",
        analytics_enabled: bool | None = None,
        *,
        enabled: bool | None = None,
    ) -> None:
        self.auth_manager = auth_manager
        self.base_url = str(base_url).rstrip("/")
        self.enabled = (
            bool(enabled)
            if enabled is not None
            else analytics_enabled is not False
        )
        self.recorded_facts: list[dict[str, Any]] = []

    @classmethod
    def disabled(cls) -> "AnalyticsEventsClient":
        return cls(analytics_enabled=False)

    async def record_events(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def record_fact(self, fact: dict[str, Any]) -> None:
        if self.enabled:
            self.recorded_facts.append(fact)

    def track_request(self, connection_id: int, request_id: Any, request_kind: str) -> None:
        normalized_kind = getattr(request_kind, "type", request_kind)
        if analytics_relevant_client_request(normalized_kind):
            self.record_fact(
                {
                    "type": "ClientRequest",
                    "connection_id": connection_id,
                    "request_id": request_id,
                    "request_kind": normalized_kind,
                }
            )

    def track_initialize(
        self,
        connection_id: int,
        params: Any,
        product_client_id: str,
        rpc_transport: Any,
    ) -> None:
        self.record_fact(
            {
                "type": "Initialize",
                "connection_id": connection_id,
                "params": params,
                "product_client_id": product_client_id,
                "rpc_transport": rpc_transport,
            }
        )

    def track_response(self, connection_id: int, request_id: Any, response_kind: str) -> None:
        if analytics_relevant_client_response(response_kind):
            self.record_fact(
                {
                    "type": "ClientResponse",
                    "connection_id": connection_id,
                    "request_id": request_id,
                    "response_kind": response_kind,
                }
            )

    def track_notification(self, notification_kind: str) -> None:
        if analytics_relevant_notification(notification_kind):
            self.record_fact({"type": "Notification", "notification_kind": notification_kind})

class AnalyticsEventsQueue:
    def __init__(self) -> None:
        self.app_used_emitted_keys: set[tuple[str, str]] = set()
        self.plugin_used_emitted_keys: set[tuple[str, str]] = set()

    def should_enqueue_app_used(self, tracking: TrackEventsContext, app: AppInvocation) -> bool:
        if app.connector_id is None:
            return True
        if len(self.app_used_emitted_keys) >= ANALYTICS_EVENT_DEDUPE_MAX_KEYS:
            self.app_used_emitted_keys.clear()
        key = (tracking.turn_id, app.connector_id)
        if key in self.app_used_emitted_keys:
            return False
        self.app_used_emitted_keys.add(key)
        return True

    def should_enqueue_plugin_used(self, tracking: TrackEventsContext, plugin: PluginTelemetryMetadata) -> bool:
        if len(self.plugin_used_emitted_keys) >= ANALYTICS_EVENT_DEDUPE_MAX_KEYS:
            self.plugin_used_emitted_keys.clear()
        key = (tracking.turn_id, plugin.plugin_id.as_key())
        if key in self.plugin_used_emitted_keys:
            return False
        self.plugin_used_emitted_keys.add(key)
        return True


__all__ = [name for name in globals() if not name.startswith("_")]
