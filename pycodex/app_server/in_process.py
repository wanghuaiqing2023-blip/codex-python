"""In-process app-server host projections for ``src/in_process.rs``.

The Rust module owns the low-level in-memory app-server runtime host. Python
keeps a dependency-light projection of the module-owned contracts that can be
verified without starting Tokio tasks, sockets, or a real ``MessageProcessor``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.app_server.error_code import OVERLOADED_ERROR_CODE, internal_error, invalid_request
from pycodex.app_server_protocol import JSONRPCErrorError, RequestId

try:
    from pycodex.app_server.transport import CHANNEL_CAPACITY as _CHANNEL_CAPACITY
except ImportError:  # pragma: no cover - compatibility for older transport projections.
    _CHANNEL_CAPACITY = 128

IN_PROCESS_CONNECTION_ID = 0
SHUTDOWN_TIMEOUT_SECONDS = 5
DEFAULT_IN_PROCESS_CHANNEL_CAPACITY = _CHANNEL_CAPACITY


class InProcessIoErrorKind(Enum):
    WOULD_BLOCK = "WouldBlock"
    BROKEN_PIPE = "BrokenPipe"
    INVALID_DATA = "InvalidData"


class InProcessIoError(OSError):
    """Rust ``std::io::ErrorKind``-shaped error for in-process transport calls."""

    def __init__(self, kind: InProcessIoErrorKind, message: str) -> None:
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True)
class InProcessStartArgs:
    """Input needed to start an in-process app-server runtime."""

    arg0_paths: Any = None
    config: Any = None
    cli_overrides: tuple[tuple[str, Any], ...] = ()
    loader_overrides: Any = None
    strict_config: bool = False
    cloud_requirements: Any = None
    thread_config_loader: Any = None
    feedback: Any = None
    log_db: Any = None
    state_db: Any = None
    environment_manager: Any = None
    config_warnings: tuple[Any, ...] = ()
    session_source: Any = None
    enable_codex_api_key_env: bool = False
    initialize: Any = None
    channel_capacity: int = DEFAULT_IN_PROCESS_CHANNEL_CAPACITY

    def effective_channel_capacity(self) -> int:
        """Mirror Rust ``args.channel_capacity.max(1)``."""

        return max(1, int(self.channel_capacity))


@dataclass(frozen=True)
class InProcessServerEvent:
    """Rust ``InProcessServerEvent`` shape."""

    kind: str
    payload: Any = None
    skipped: int | None = None

    @classmethod
    def server_request(cls, request: Any) -> "InProcessServerEvent":
        return cls("ServerRequest", request)

    @classmethod
    def server_notification(cls, notification: Any) -> "InProcessServerEvent":
        return cls("ServerNotification", notification)

    @classmethod
    def lagged(cls, skipped: int) -> "InProcessServerEvent":
        return cls("Lagged", skipped=skipped)


@dataclass(frozen=True)
class InProcessClientMessage:
    """Internal Rust ``InProcessClientMessage`` shape."""

    kind: str
    request: Any = None
    notification: Any = None
    request_id: RequestId | None = None
    result: Any = None
    error: JSONRPCErrorError | None = None

    @classmethod
    def request(cls, request: Any) -> "InProcessClientMessage":
        return cls("Request", request=request)

    @classmethod
    def notification(cls, notification: Any) -> "InProcessClientMessage":
        return cls("Notification", notification=notification)

    @classmethod
    def server_request_response(cls, request_id: RequestId | str | int, result: Any) -> "InProcessClientMessage":
        return cls("ServerRequestResponse", request_id=RequestId.from_value(request_id), result=result)

    @classmethod
    def server_request_error(cls, request_id: RequestId | str | int, error: JSONRPCErrorError) -> "InProcessClientMessage":
        return cls("ServerRequestError", request_id=RequestId.from_value(request_id), error=error)

    @classmethod
    def shutdown(cls) -> "InProcessClientMessage":
        return cls("Shutdown")


@dataclass(frozen=True)
class ProcessorCommand:
    """Internal Rust ``ProcessorCommand`` shape."""

    kind: str
    payload: Any

    @classmethod
    def request(cls, request: Any) -> "ProcessorCommand":
        return cls("Request", request)

    @classmethod
    def notification(cls, notification: Any) -> "ProcessorCommand":
        return cls("Notification", notification)


@dataclass
class BoundedInProcessQueue:
    """Small deterministic stand-in for Rust bounded ``mpsc`` try_send."""

    capacity: int
    closed: bool = False
    items: deque[Any] = field(default_factory=deque)

    def __post_init__(self) -> None:
        self.capacity = max(1, int(self.capacity))

    def try_send(self, item: Any, *, full_message: str, closed_message: str) -> None:
        if self.closed:
            raise InProcessIoError(InProcessIoErrorKind.BROKEN_PIPE, closed_message)
        if len(self.items) >= self.capacity:
            raise InProcessIoError(InProcessIoErrorKind.WOULD_BLOCK, full_message)
        self.items.append(item)

    def recv_nowait(self) -> Any | None:
        return self.items.popleft() if self.items else None

    def close(self) -> None:
        self.closed = True


@dataclass
class InProcessClientSender:
    """Rust ``InProcessClientSender`` queue boundary."""

    client_queue: BoundedInProcessQueue

    def try_send_client_message(self, message: InProcessClientMessage) -> None:
        self.client_queue.try_send(
            message,
            full_message="in-process app-server client queue is full",
            closed_message="in-process app-server runtime is closed",
        )

    def notify(self, notification: Any) -> None:
        self.try_send_client_message(InProcessClientMessage.notification(notification))

    def respond_to_server_request(self, request_id: RequestId | str | int, result: Any) -> None:
        self.try_send_client_message(InProcessClientMessage.server_request_response(request_id, result))

    def fail_server_request(self, request_id: RequestId | str | int, error: JSONRPCErrorError) -> None:
        self.try_send_client_message(InProcessClientMessage.server_request_error(request_id, error))


@dataclass(frozen=True)
class PendingRequestOutcome:
    accepted: bool
    request_id: RequestId
    processor_command: ProcessorCommand | None = None
    immediate_error: JSONRPCErrorError | None = None
    breaks_runtime: bool = False


@dataclass
class InProcessRuntimeProjection:
    """Deterministic projection of Rust's runtime select-loop bookkeeping."""

    channel_capacity: int
    processor_queue_size: int = 0
    processor_closed: bool = False
    pending_request_responses: dict[RequestId, str] = field(default_factory=dict)
    notifications_dropped: int = 0
    shutdown_ack_requested: bool = False
    server_request_errors: dict[RequestId, JSONRPCErrorError] = field(default_factory=dict)
    delivered_events: list[InProcessServerEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.channel_capacity = max(1, int(self.channel_capacity))

    @classmethod
    def from_start_args(cls, args: InProcessStartArgs) -> "InProcessRuntimeProjection":
        return cls(args.effective_channel_capacity())

    def handle_client_request(self, request: Any) -> PendingRequestOutcome:
        request_id = RequestId.from_value(_request_id(request))
        if request_id in self.pending_request_responses:
            return PendingRequestOutcome(
                accepted=False,
                request_id=request_id,
                immediate_error=invalid_request(f"duplicate request id: {request_id!r}"),
            )
        self.pending_request_responses[request_id] = "pending"
        if self.processor_closed:
            self.pending_request_responses.pop(request_id, None)
            return PendingRequestOutcome(
                accepted=False,
                request_id=request_id,
                immediate_error=internal_error("in-process app-server request processor is closed"),
                breaks_runtime=True,
            )
        if self.processor_queue_size >= self.channel_capacity:
            self.pending_request_responses.pop(request_id, None)
            return PendingRequestOutcome(
                accepted=False,
                request_id=request_id,
                immediate_error=JSONRPCErrorError(
                    code=OVERLOADED_ERROR_CODE,
                    message="in-process app-server request queue is full",
                    data=None,
                ),
            )
        self.processor_queue_size += 1
        command = ProcessorCommand.request(request)
        return PendingRequestOutcome(accepted=True, request_id=request_id, processor_command=command)

    def handle_client_notification(self, notification: Any) -> bool:
        if self.processor_closed:
            return False
        if self.processor_queue_size >= self.channel_capacity:
            self.notifications_dropped += 1
            return True
        self.processor_queue_size += 1
        return True

    def handle_server_request_event(self, request: Any, event_queue_full: bool, event_queue_closed: bool = False) -> bool:
        request_id = RequestId.from_value(_request_id(request))
        if event_queue_closed:
            self.server_request_errors[request_id] = internal_error("in-process server request consumer is closed")
            return False
        if event_queue_full:
            self.server_request_errors[request_id] = JSONRPCErrorError(
                code=OVERLOADED_ERROR_CODE,
                message="in-process server request queue is full",
                data=None,
            )
            return False
        self.delivered_events.append(InProcessServerEvent.server_request(request))
        return True

    def handle_notification_event(self, notification: Any, event_queue_full: bool, event_queue_closed: bool = False) -> bool:
        event = InProcessServerEvent.server_notification(notification)
        if server_notification_requires_delivery(notification):
            if event_queue_closed:
                return False
            self.delivered_events.append(event)
            return True
        if event_queue_closed:
            return False
        if event_queue_full:
            self.notifications_dropped += 1
            return True
        self.delivered_events.append(event)
        return True

    def handle_shutdown(self) -> None:
        self.shutdown_ack_requested = True

    def finish_shutdown(self) -> dict[RequestId, JSONRPCErrorError]:
        errors = {
            request_id: internal_error("in-process app-server runtime is shutting down")
            for request_id in self.pending_request_responses
        }
        self.pending_request_responses.clear()
        return errors


@dataclass(frozen=True)
class StartProjection:
    """Rust ``start`` initialize/initialized handshake projection."""

    initialize_request_id: RequestId
    sends_initialized_notification: bool
    shuts_down_on_initialize_error: bool
    initialize_error_kind: InProcessIoErrorKind
    initialize_error_prefix: str


def start_projection() -> StartProjection:
    return StartProjection(
        initialize_request_id=RequestId.from_value(0),
        sends_initialized_notification=True,
        shuts_down_on_initialize_error=True,
        initialize_error_kind=InProcessIoErrorKind.INVALID_DATA,
        initialize_error_prefix="in-process initialize failed:",
    )


def server_notification_requires_delivery(notification: Any) -> bool:
    """Mirror Rust's terminal notification delivery helper."""

    return _notification_type(notification) in {"TurnCompleted", "ThreadSettingsUpdated"}


def route_notifications_with_backpressure(notifications: Iterable[Any], *, event_queue_full: bool) -> tuple[list[Any], int]:
    """Project Rust notification routing: guaranteed notifications are retained."""

    delivered: list[Any] = []
    dropped = 0
    for notification in notifications:
        if server_notification_requires_delivery(notification) or not event_queue_full:
            delivered.append(notification)
        else:
            dropped += 1
    return delivered, dropped


def _request_id(request: Any) -> Any:
    if hasattr(request, "id") and callable(request.id):
        return request.id()
    if hasattr(request, "request_id"):
        return getattr(request, "request_id")
    if isinstance(request, dict):
        return request.get("request_id", request.get("requestId", request.get("id")))
    raise ValueError("request must expose an id")


def _notification_type(notification: Any) -> str:
    if isinstance(notification, str):
        return notification
    if isinstance(notification, dict):
        return str(notification.get("type") or notification.get("kind") or notification.get("method"))
    value = getattr(notification, "type", None)
    if value is not None:
        return str(value)
    value = getattr(notification, "kind", None)
    if value is not None:
        return str(value)
    return type(notification).__name__


__all__ = [
    "DEFAULT_IN_PROCESS_CHANNEL_CAPACITY",
    "IN_PROCESS_CONNECTION_ID",
    "SHUTDOWN_TIMEOUT_SECONDS",
    "BoundedInProcessQueue",
    "InProcessClientMessage",
    "InProcessClientSender",
    "InProcessIoError",
    "InProcessIoErrorKind",
    "InProcessRuntimeProjection",
    "InProcessServerEvent",
    "InProcessStartArgs",
    "PendingRequestOutcome",
    "ProcessorCommand",
    "StartProjection",
    "route_notifications_with_backpressure",
    "server_notification_requires_delivery",
    "start_projection",
]
