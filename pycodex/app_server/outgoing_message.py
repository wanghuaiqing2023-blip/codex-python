"""Outgoing message coordination ported from ``app-server/src/outgoing_message.rs``."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

from pycodex.app_server.error_code import internal_error
from pycodex.app_server.server_request_error import TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    RequestId,
    ServerNotification,
    ServerRequest,
)

ClientRequestResult = Any


class OutgoingMessageKind(Enum):
    REQUEST = "Request"
    RESPONSE = "Response"
    ERROR = "Error"
    APP_SERVER_NOTIFICATION = "AppServerNotification"


@dataclass(frozen=True)
class ConnectionRequestId:
    connection_id: Any
    request_id: RequestId | str | int

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", RequestId.from_value(self.request_id))


@dataclass(frozen=True)
class RequestContext:
    request_id: ConnectionRequestId
    span: Any = None
    parent_trace: Any = None
    turn_id: str | None = None

    @classmethod
    def new(
        cls,
        request_id: ConnectionRequestId,
        span: Any = None,
        parent_trace: Any = None,
    ) -> "RequestContext":
        return cls(request_id=request_id, span=span, parent_trace=parent_trace)

    def request_trace(self) -> Any:
        span_trace = getattr(self.span, "trace_context", None)
        if callable(span_trace):
            span_trace = span_trace()
        return span_trace if span_trace is not None else self.parent_trace

    def record_turn_id(self, turn_id: str) -> "RequestContext":
        recorder = getattr(self.span, "record", None)
        if callable(recorder):
            recorder("turn.id", turn_id)
        return replace(self, turn_id=turn_id)


@dataclass(frozen=True)
class OutgoingResponse:
    id: RequestId
    result: Any

    def to_mapping(self) -> dict[str, Any]:
        return {"id": self.id.to_json(), "result": _to_json(self.result)}


@dataclass(frozen=True)
class OutgoingError:
    id: RequestId
    error: JSONRPCErrorError

    def to_mapping(self) -> dict[str, Any]:
        return {"id": self.id.to_json(), "error": self.error.to_mapping()}


@dataclass(frozen=True)
class OutgoingMessage:
    kind: OutgoingMessageKind
    payload: Any

    @classmethod
    def request(cls, request: ServerRequest) -> "OutgoingMessage":
        return cls(OutgoingMessageKind.REQUEST, request)

    @classmethod
    def response(cls, response: OutgoingResponse) -> "OutgoingMessage":
        return cls(OutgoingMessageKind.RESPONSE, response)

    @classmethod
    def error(cls, error: OutgoingError) -> "OutgoingMessage":
        return cls(OutgoingMessageKind.ERROR, error)

    @classmethod
    def app_server_notification(cls, notification: ServerNotification) -> "OutgoingMessage":
        return cls(OutgoingMessageKind.APP_SERVER_NOTIFICATION, notification)

    def to_mapping(self) -> dict[str, Any]:
        if hasattr(self.payload, "to_mapping"):
            payload = self.payload.to_mapping()
        else:
            payload = _to_json(self.payload)
        return {"kind": self.kind.value, "payload": payload}


@dataclass(frozen=True)
class OutgoingEnvelope:
    kind: str
    message: OutgoingMessage
    connection_id: Any = None
    write_complete: asyncio.Future[None] | None = None

    @classmethod
    def to_connection(
        cls,
        connection_id: Any,
        message: OutgoingMessage,
        *,
        write_complete: asyncio.Future[None] | None = None,
    ) -> "OutgoingEnvelope":
        return cls("ToConnection", message=message, connection_id=connection_id, write_complete=write_complete)

    @classmethod
    def broadcast(cls, message: OutgoingMessage) -> "OutgoingEnvelope":
        return cls("Broadcast", message=message)


@dataclass
class PendingCallbackEntry:
    callback: asyncio.Future[ClientRequestResult]
    thread_id: Any | None
    request: ServerRequest


class OutgoingMessageSender:
    def __init__(
        self,
        sender: asyncio.Queue[OutgoingEnvelope] | None = None,
        analytics_events_client: Any | None = None,
    ) -> None:
        self._next_server_request_id = 0
        self.sender = sender if sender is not None else asyncio.Queue()
        self.request_id_to_callback: dict[RequestId, PendingCallbackEntry] = {}
        self.request_contexts: dict[ConnectionRequestId, RequestContext] = {}
        self.analytics_events_client = analytics_events_client or DisabledAnalyticsEventsClient()
        self._lock = asyncio.Lock()

    @classmethod
    def new(
        cls,
        sender: asyncio.Queue[OutgoingEnvelope] | None = None,
        analytics_events_client: Any | None = None,
    ) -> "OutgoingMessageSender":
        return cls(sender, analytics_events_client)

    async def register_request_context(self, request_context: RequestContext) -> None:
        async with self._lock:
            self.request_contexts[request_context.request_id] = request_context

    async def connection_closed(self, connection_id: Any) -> None:
        async with self._lock:
            self.request_contexts = {
                request_id: context
                for request_id, context in self.request_contexts.items()
                if request_id.connection_id != connection_id
            }

    async def request_trace_context(self, request_id: ConnectionRequestId) -> Any:
        async with self._lock:
            context = self.request_contexts.get(request_id)
            return None if context is None else context.request_trace()

    async def record_request_turn_id(self, request_id: ConnectionRequestId, turn_id: str) -> None:
        async with self._lock:
            context = self.request_contexts.get(request_id)
            if context is not None:
                self.request_contexts[request_id] = context.record_turn_id(turn_id)

    async def request_context_count(self) -> int:
        async with self._lock:
            return len(self.request_contexts)

    async def send_request(self, request: Any) -> tuple[RequestId, asyncio.Future[ClientRequestResult]]:
        return await self.send_request_to_connections(None, request, None)

    async def send_request_to_connections(
        self,
        connection_ids: list[Any] | tuple[Any, ...] | None,
        request: Any,
        thread_id: Any | None,
    ) -> tuple[RequestId, asyncio.Future[ClientRequestResult]]:
        request_id = self._next_request_id()
        server_request = _request_with_id(request, request_id)
        waiter: asyncio.Future[ClientRequestResult] = asyncio.get_running_loop().create_future()
        async with self._lock:
            self.request_id_to_callback[request_id] = PendingCallbackEntry(waiter, thread_id, server_request)

        outgoing_message = OutgoingMessage.request(server_request)
        try:
            if connection_ids is None:
                await self.sender.put(OutgoingEnvelope.broadcast(outgoing_message))
            else:
                for connection_id in connection_ids:
                    await self.sender.put(OutgoingEnvelope.to_connection(connection_id, outgoing_message))
                    _call_analytics(self.analytics_events_client, "track_server_request", connection_id, server_request)
        except Exception:
            async with self._lock:
                self.request_id_to_callback.pop(request_id, None)
        return request_id, waiter

    async def replay_requests_to_connection_for_thread(self, connection_id: Any, thread_id: Any) -> None:
        for request in await self.pending_requests_for_thread(thread_id):
            await self.sender.put(OutgoingEnvelope.to_connection(connection_id, OutgoingMessage.request(request)))

    async def notify_client_response(self, id: RequestId | str | int, result: Any) -> None:
        request_id = RequestId.from_value(id)
        entry = await self._take_request_callback(request_id)
        if entry is None:
            return
        _safe_set_result(entry.callback, result)

    async def notify_client_error(self, id: RequestId | str | int, error: JSONRPCErrorError) -> None:
        request_id = RequestId.from_value(id)
        entry = await self._take_request_callback(request_id)
        if entry is None:
            return
        _call_analytics(self.analytics_events_client, "track_server_request_aborted", now_unix_timestamp_ms(), request_id)
        _safe_set_result(entry.callback, error)

    async def cancel_request(self, id: RequestId | str | int) -> bool:
        request_id = RequestId.from_value(id)
        entry = await self._take_request_callback(request_id)
        if entry is None:
            return False
        _call_analytics(self.analytics_events_client, "track_server_request_aborted", now_unix_timestamp_ms(), request_id)
        return True

    async def cancel_all_requests(self, error: JSONRPCErrorError | None = None) -> None:
        async with self._lock:
            entries = list(self.request_id_to_callback.values())
            self.request_id_to_callback.clear()
        for entry in entries:
            _call_analytics(self.analytics_events_client, "track_server_request_aborted", now_unix_timestamp_ms(), entry.request.request_id)
            if error is not None:
                _safe_set_result(entry.callback, error)

    async def pending_requests_for_thread(self, thread_id: Any) -> list[ServerRequest]:
        async with self._lock:
            requests = [
                entry.request
                for entry in self.request_id_to_callback.values()
                if entry.thread_id == thread_id
            ]
        return sorted(requests, key=lambda request: RequestId.from_value(request.request_id).to_json())

    async def cancel_requests_for_thread(self, thread_id: Any, error: JSONRPCErrorError | None = None) -> None:
        async with self._lock:
            request_ids = [
                request_id
                for request_id, entry in self.request_id_to_callback.items()
                if entry.thread_id == thread_id
            ]
            entries = [
                self.request_id_to_callback.pop(request_id)
                for request_id in request_ids
            ]
        for entry in entries:
            _call_analytics(self.analytics_events_client, "track_server_request_aborted", now_unix_timestamp_ms(), entry.request.request_id)
            if error is not None:
                _safe_set_result(entry.callback, error)

    async def send_response(self, request_id: ConnectionRequestId, response: Any) -> None:
        await self.send_response_as(request_id, _response_payload(response))

    async def send_response_as(self, request_id: ConnectionRequestId, response: Any) -> None:
        await self._take_request_context(request_id)
        message = OutgoingMessage.response(OutgoingResponse(request_id.request_id, _to_json(response)))
        await self.sender.put(OutgoingEnvelope.to_connection(request_id.connection_id, message))

    async def send_server_notification(self, notification: ServerNotification) -> None:
        await self.send_server_notification_to_connections([], notification)

    def try_send_server_notification(self, notification: ServerNotification) -> None:
        self.sender.put_nowait(
            OutgoingEnvelope.broadcast(OutgoingMessage.app_server_notification(notification))
        )

    async def send_server_notification_to_connections(
        self,
        connection_ids: list[Any] | tuple[Any, ...],
        notification: ServerNotification,
    ) -> None:
        message = OutgoingMessage.app_server_notification(notification)
        if not connection_ids:
            await self.sender.put(OutgoingEnvelope.broadcast(message))
            return
        for connection_id in connection_ids:
            await self.sender.put(OutgoingEnvelope.to_connection(connection_id, message))

    async def send_server_notification_to_connection_and_wait(
        self,
        connection_id: Any,
        notification: ServerNotification,
    ) -> None:
        loop = asyncio.get_running_loop()
        write_complete: asyncio.Future[None] = loop.create_future()
        await self.sender.put(
            OutgoingEnvelope.to_connection(
                connection_id,
                OutgoingMessage.app_server_notification(notification),
                write_complete=write_complete,
            )
        )
        await write_complete

    async def send_error(self, request_id: ConnectionRequestId, error: JSONRPCErrorError) -> None:
        await self._take_request_context(request_id)
        message = OutgoingMessage.error(OutgoingError(request_id.request_id, error))
        await self.sender.put(OutgoingEnvelope.to_connection(request_id.connection_id, message))

    async def send_result(self, request_id: ConnectionRequestId, result: Any) -> None:
        if isinstance(result, JSONRPCErrorError):
            await self.send_error(request_id, result)
        else:
            await self.send_response(request_id, result)

    async def _take_request_context(self, request_id: ConnectionRequestId) -> RequestContext | None:
        async with self._lock:
            return self.request_contexts.pop(request_id, None)

    async def _take_request_callback(self, request_id: RequestId) -> PendingCallbackEntry | None:
        async with self._lock:
            return self.request_id_to_callback.pop(request_id, None)

    def _next_request_id(self) -> RequestId:
        request_id = RequestId.integer(self._next_server_request_id)
        self._next_server_request_id += 1
        return request_id


class ThreadScopedOutgoingMessageSender:
    def __init__(self, outgoing: OutgoingMessageSender, connection_ids: list[Any], thread_id: Any) -> None:
        self.outgoing = outgoing
        self.connection_ids = tuple(connection_ids)
        self.thread_id = thread_id

    @classmethod
    def new(
        cls,
        outgoing: OutgoingMessageSender,
        connection_ids: list[Any],
        thread_id: Any,
    ) -> "ThreadScopedOutgoingMessageSender":
        return cls(outgoing, connection_ids, thread_id)

    async def send_request(self, payload: Any) -> tuple[RequestId, asyncio.Future[ClientRequestResult]]:
        return await self.outgoing.send_request_to_connections(list(self.connection_ids), payload, self.thread_id)

    def track_effective_permissions_approval_response(self, request_id: RequestId | str | int, response: Any) -> None:
        _call_analytics(
            self.outgoing.analytics_events_client,
            "track_effective_permissions_approval_response",
            now_unix_timestamp_ms(),
            RequestId.from_value(request_id),
            response,
        )

    async def send_server_notification(self, notification: ServerNotification) -> None:
        _call_analytics(self.outgoing.analytics_events_client, "track_notification", notification)
        if not self.connection_ids:
            return
        await self.outgoing.send_server_notification_to_connections(list(self.connection_ids), notification)

    async def send_global_server_notification(self, notification: ServerNotification) -> None:
        await self.outgoing.send_server_notification(notification)

    async def abort_pending_server_requests(self) -> None:
        error = internal_error("client request resolved because the turn state was changed")
        error = JSONRPCErrorError(
            code=error.code,
            message=error.message,
            data={"reason": TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON},
        )
        await self.outgoing.cancel_requests_for_thread(self.thread_id, error)

    async def send_response(self, request_id: ConnectionRequestId, response: Any) -> None:
        await self.outgoing.send_response(request_id, response)

    async def send_error(self, request_id: ConnectionRequestId, error: JSONRPCErrorError) -> None:
        await self.outgoing.send_error(request_id, error)


class DisabledAnalyticsEventsClient:
    def __getattr__(self, name: str) -> Any:
        def no_op(*args: Any, **kwargs: Any) -> None:
            return None

        return no_op


def now_unix_timestamp_ms() -> int:
    return int(time.time() * 1000)


def _request_with_id(request: Any, request_id: RequestId) -> ServerRequest:
    if isinstance(request, ServerRequest):
        return ServerRequest(type=request.type, request_id=request_id.to_json(), params=request.params)
    if isinstance(request, tuple):
        type_name, params = request
        return ServerRequest(type=str(type_name), request_id=request_id.to_json(), params=_to_json(params))
    if isinstance(request, Mapping):
        type_name = request.get("type")
        params = request.get("params")
        return ServerRequest(type=str(type_name), request_id=request_id.to_json(), params=_to_json(params))
    type_name = getattr(request, "type", request.__class__.__name__)
    params = getattr(request, "params", None)
    return ServerRequest(type=str(type_name), request_id=request_id.to_json(), params=_to_json(params))


def _response_payload(response: Any) -> Any:
    return {} if response is None else response


def _safe_set_result(future: asyncio.Future[Any], result: Any) -> None:
    if not future.done():
        future.set_result(result)


def _call_analytics(client: Any, method_name: str, *args: Any) -> None:
    method = getattr(client, method_name, None)
    if callable(method):
        method(*args)


def _to_json(value: Any) -> Any:
    if hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, RequestId):
        return value.to_json()
    if isinstance(value, Mapping):
        return {key: _to_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json(item) for item in value]
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    return value


__all__ = [
    "ClientRequestResult",
    "ConnectionRequestId",
    "DisabledAnalyticsEventsClient",
    "OutgoingEnvelope",
    "OutgoingError",
    "OutgoingMessage",
    "OutgoingMessageKind",
    "OutgoingMessageSender",
    "OutgoingResponse",
    "RequestContext",
    "ThreadScopedOutgoingMessageSender",
    "now_unix_timestamp_ms",
]
