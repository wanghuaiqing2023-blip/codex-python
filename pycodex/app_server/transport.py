"""Source-contract projections for Rust ``codex-app-server/src/transport.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping

TRANSPORT_PUBLIC_REEXPORTS: tuple[str, ...] = (
    "AppServerTransport",
    "app_server_control_socket_path",
    "auth",
)

TRANSPORT_CRATE_REEXPORTS: tuple[str, ...] = (
    "CHANNEL_CAPACITY",
    "ConnectionId",
    "ConnectionOrigin",
    "OutgoingMessage",
    "QueuedOutgoingMessage",
    "RemoteControlHandle",
    "RemoteControlStartConfig",
    "RemoteControlUnavailable",
    "TransportEvent",
    "acquire_app_server_startup_lock",
    "app_server_startup_lock_path",
    "prepare_control_socket_path",
    "start_control_socket_acceptor",
    "start_remote_control",
    "start_stdio_connection",
    "start_websocket_acceptor",
)


class OutgoingEnvelopeKind(Enum):
    TO_CONNECTION = "to_connection"
    BROADCAST = "broadcast"


@dataclass(frozen=True)
class OutboundConnectionStateProjection:
    """Rust ``OutboundConnectionState`` fields used by outbound routing."""

    initialized: bool = False
    experimental_api_enabled: bool = False
    opted_out_notification_methods: frozenset[str] = field(default_factory=frozenset)
    opted_out_readable: bool = True
    writer_queue_capacity: int | None = None
    writer_queue_size: int = 0
    writer_closed: bool = False
    disconnect_sender_present: bool = False

    def can_disconnect(self) -> bool:
        """Mirror Rust ``can_disconnect``."""

        return self.disconnect_sender_present

    def with_queued_message(self) -> "OutboundConnectionStateProjection":
        if self.writer_queue_capacity is None:
            return self
        return replace(self, writer_queue_size=self.writer_queue_size + 1)


@dataclass(frozen=True)
class ConnectionStateProjection:
    """Rust ``ConnectionState::new`` output shape."""

    origin_ignored: bool
    outbound_initialized: bool
    outbound_experimental_api_enabled: bool
    outbound_opted_out_notification_methods: frozenset[str]
    creates_new_session: bool


@dataclass(frozen=True)
class DisconnectConnectionProjection:
    """Decision trace for Rust ``disconnect_connection``."""

    removed: bool
    requested_disconnect: bool
    remaining_connection_ids: tuple[Any, ...]


@dataclass(frozen=True)
class TransportReexportSurfaceProjection:
    """Rust ``transport.rs`` re-export surface."""

    public_reexports: tuple[str, ...]
    crate_reexports: tuple[str, ...]
    path_helpers: tuple[str, ...]
    acceptor_start_functions: tuple[str, ...]
    remote_control_items: tuple[str, ...]


@dataclass(frozen=True)
class OutgoingEnvelopeProjection:
    """Minimal Rust ``OutgoingEnvelope`` shape."""

    kind: OutgoingEnvelopeKind
    message: Any
    connection_id: Any = None
    write_complete_tx: bool = False

    @classmethod
    def to_connection(
        cls,
        connection_id: Any,
        message: Any,
        *,
        write_complete_tx: bool = False,
    ) -> "OutgoingEnvelopeProjection":
        return cls(
            kind=OutgoingEnvelopeKind.TO_CONNECTION,
            connection_id=connection_id,
            message=message,
            write_complete_tx=write_complete_tx,
        )

    @classmethod
    def broadcast(cls, message: Any) -> "OutgoingEnvelopeProjection":
        return cls(kind=OutgoingEnvelopeKind.BROADCAST, message=message)


@dataclass(frozen=True)
class RouteOutgoingEnvelopeProjection:
    """Decision trace for Rust ``route_outgoing_envelope``."""

    delivered_connection_ids: tuple[Any, ...] = ()
    dropped_connection_ids: tuple[Any, ...] = ()
    disconnected_connection_ids: tuple[Any, ...] = ()
    waited_for_capacity_connection_ids: tuple[Any, ...] = ()
    write_complete_connection_ids: tuple[Any, ...] = ()
    filtered_messages_by_connection: tuple[tuple[Any, Any], ...] = ()
    remaining_connection_ids: tuple[Any, ...] = ()
    warnings: tuple[str, ...] = ()


def should_skip_notification_for_connection(
    connection_state: OutboundConnectionStateProjection,
    message: Any,
) -> tuple[bool, tuple[str, ...]]:
    """Mirror Rust notification opt-out and experimental-capability filtering."""

    if _message_kind(message) != "AppServerNotification":
        return False, ()

    if not connection_state.opted_out_readable:
        return False, ("failed to read outbound opted-out notifications",)

    experimental_reason = _experimental_reason(message)
    if experimental_reason is not None and not connection_state.experimental_api_enabled:
        return True, ()

    method = _notification_method(message)
    return method in connection_state.opted_out_notification_methods, ()


def connection_state_projection(
    *,
    origin: Any,
    outbound_initialized: bool,
    outbound_experimental_api_enabled: bool,
    outbound_opted_out_notification_methods: set[str] | frozenset[str],
) -> ConnectionStateProjection:
    """Mirror Rust ``ConnectionState::new`` local field wiring."""

    _ = origin
    return ConnectionStateProjection(
        origin_ignored=True,
        outbound_initialized=outbound_initialized,
        outbound_experimental_api_enabled=outbound_experimental_api_enabled,
        outbound_opted_out_notification_methods=frozenset(
            outbound_opted_out_notification_methods
        ),
        creates_new_session=True,
    )


def disconnect_connection_projection(
    connections: Mapping[Any, OutboundConnectionStateProjection],
    connection_id: Any,
) -> DisconnectConnectionProjection:
    """Mirror Rust ``disconnect_connection`` remove-and-cancel behavior."""

    mutable_connections = dict(connections)
    state = mutable_connections.pop(connection_id, None)
    return DisconnectConnectionProjection(
        removed=state is not None,
        requested_disconnect=bool(state and state.can_disconnect()),
        remaining_connection_ids=tuple(mutable_connections),
    )


def transport_reexport_surface_projection() -> TransportReexportSurfaceProjection:
    """Mirror Rust ``pub use`` / ``pub(crate) use`` declarations."""

    return TransportReexportSurfaceProjection(
        public_reexports=TRANSPORT_PUBLIC_REEXPORTS,
        crate_reexports=TRANSPORT_CRATE_REEXPORTS,
        path_helpers=(
            "app_server_control_socket_path",
            "app_server_startup_lock_path",
            "prepare_control_socket_path",
        ),
        acceptor_start_functions=(
            "start_control_socket_acceptor",
            "start_stdio_connection",
            "start_websocket_acceptor",
        ),
        remote_control_items=(
            "RemoteControlHandle",
            "RemoteControlStartConfig",
            "RemoteControlUnavailable",
            "start_remote_control",
        ),
    )


def filter_outgoing_message_for_connection(
    connection_state: OutboundConnectionStateProjection,
    message: Any,
) -> Any:
    """Mirror Rust experimental-field stripping for approval requests."""

    if (
        connection_state.experimental_api_enabled
        or _message_kind(message) != "Request"
        or _request_kind(message) != "CommandExecutionRequestApproval"
    ):
        return message

    params = _params(message)
    if params is None:
        return message

    stripped_params = _without_key(params, "additionalPermissions", "additional_permissions")
    return _replace_params(message, stripped_params)


def route_outgoing_envelope_projection(
    connections: Mapping[Any, OutboundConnectionStateProjection],
    envelope: OutgoingEnvelopeProjection,
) -> RouteOutgoingEnvelopeProjection:
    """Mirror Rust outbound envelope routing without real mpsc/websocket I/O."""

    mutable_connections = dict(connections)
    delivered: list[Any] = []
    dropped: list[Any] = []
    disconnected: list[Any] = []
    waited: list[Any] = []
    write_complete: list[Any] = []
    filtered_messages: list[tuple[Any, Any]] = []
    warnings: list[str] = []

    def send_one(connection_id: Any, message: Any, has_write_complete: bool) -> None:
        state = mutable_connections.get(connection_id)
        if state is None:
            warnings.append(f"dropping message for disconnected connection: {connection_id!r}")
            dropped.append(connection_id)
            return

        filtered = filter_outgoing_message_for_connection(state, message)
        filtered_messages.append((connection_id, filtered))
        skip, skip_warnings = should_skip_notification_for_connection(state, filtered)
        warnings.extend(skip_warnings)
        if skip:
            dropped.append(connection_id)
            return

        if state.writer_closed:
            mutable_connections.pop(connection_id, None)
            disconnected.append(connection_id)
            return

        queue_full = (
            state.writer_queue_capacity is not None
            and state.writer_queue_size >= state.writer_queue_capacity
        )
        if queue_full and state.can_disconnect():
            warnings.append(
                f"disconnecting slow connection after outbound queue filled: {connection_id!r}"
            )
            mutable_connections.pop(connection_id, None)
            disconnected.append(connection_id)
            return
        if queue_full:
            waited.append(connection_id)

        mutable_connections[connection_id] = state.with_queued_message()
        delivered.append(connection_id)
        if has_write_complete:
            write_complete.append(connection_id)

    if envelope.kind is OutgoingEnvelopeKind.TO_CONNECTION:
        send_one(envelope.connection_id, envelope.message, envelope.write_complete_tx)
    elif envelope.kind is OutgoingEnvelopeKind.BROADCAST:
        target_connections = []
        for connection_id, state in mutable_connections.items():
            skip, skip_warnings = should_skip_notification_for_connection(state, envelope.message)
            warnings.extend(skip_warnings)
            if state.initialized and not skip:
                target_connections.append(connection_id)
        for connection_id in target_connections:
            send_one(connection_id, envelope.message, False)
    else:
        raise ValueError(f"unsupported outgoing envelope kind: {envelope.kind}")

    return RouteOutgoingEnvelopeProjection(
        delivered_connection_ids=tuple(delivered),
        dropped_connection_ids=tuple(dropped),
        disconnected_connection_ids=tuple(disconnected),
        waited_for_capacity_connection_ids=tuple(waited),
        write_complete_connection_ids=tuple(write_complete),
        filtered_messages_by_connection=tuple(filtered_messages),
        remaining_connection_ids=tuple(mutable_connections),
        warnings=tuple(warnings),
    )


def _message_kind(message: Any) -> str | None:
    return _field(message, "kind", "type", "variant")


def _request_kind(message: Any) -> str | None:
    return _field(message, "request", "request_kind", "method")


def _notification_method(message: Any) -> str | None:
    return _field(message, "method", "notification", "notification_method")


def _experimental_reason(message: Any) -> Any:
    return _field(message, "experimental_reason", "experimentalReason")


def _params(message: Any) -> Any:
    return _field(message, "params")


def _field(value: Any, *names: str) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _without_key(value: Any, *names: str) -> Any:
    if isinstance(value, Mapping):
        return {key: item for key, item in value.items() if key not in names}
    result = dict(getattr(value, "__dict__", {}))
    for name in names:
        result.pop(name, None)
    return result


def _replace_params(message: Any, params: Any) -> Any:
    if isinstance(message, Mapping):
        result = dict(message)
        result["params"] = params
        return result
    if hasattr(message, "__dict__"):
        result = dict(message.__dict__)
        result["params"] = params
        return result
    return message


__all__ = [
    "ConnectionStateProjection",
    "DisconnectConnectionProjection",
    "OutgoingEnvelopeKind",
    "OutgoingEnvelopeProjection",
    "OutboundConnectionStateProjection",
    "RouteOutgoingEnvelopeProjection",
    "TRANSPORT_CRATE_REEXPORTS",
    "TRANSPORT_PUBLIC_REEXPORTS",
    "TransportReexportSurfaceProjection",
    "connection_state_projection",
    "disconnect_connection_projection",
    "filter_outgoing_message_for_connection",
    "route_outgoing_envelope_projection",
    "should_skip_notification_for_connection",
    "transport_reexport_surface_projection",
]
