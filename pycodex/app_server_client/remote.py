"""Remote app-server client owned by Rust ``remote.rs``."""

from __future__ import annotations

import copy
import json
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pycodex.app_server_protocol import (
    ClientNotification,
    ClientRequest,
    JSONRPCErrorError,
    JSONRPCNotification,
    JSONRPCRequest,
    ServerNotification,
    ServerRequest,
    server_notification_from_jsonrpc,
)

from . import (
    AppServerClientNotImplementedError,
    AppServerEvent,
    AppServerEventKind,
    DEFAULT_IN_PROCESS_CHANNEL_CAPACITY,
    NotificationHandler,
    RequestHandler,
    RequestResult,
    SHUTDOWN_TIMEOUT_SECONDS,
    TypedRequestError,
    _maybe_await,
    request_method_name,
)

REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS = 10
REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS = 10
REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE = 128 << 20
UDS_WEBSOCKET_HANDSHAKE_URL = "ws://localhost/rpc"

class RemoteAppServerEndpointKind(Enum):
    WEB_SOCKET = "WebSocket"
    UNIX_SOCKET = "UnixSocket"


@dataclass(frozen=True)
class RemoteClientCommandProjection:
    """Rust internal ``RemoteClientCommand`` variant shape."""

    kind: str
    request: Any = None
    notification: Any = None
    request_id: Any = None
    result: Any = None
    error: Any = None
    has_response_oneshot: bool = True
    request_is_boxed: bool = False

    @classmethod
    def request_command(cls, request: Any) -> "RemoteClientCommandProjection":
        return cls(kind="Request", request=request, request_is_boxed=True)

    @classmethod
    def notify(cls, notification: Any) -> "RemoteClientCommandProjection":
        return cls(kind="Notify", notification=notification)

    @classmethod
    def resolve_server_request(
        cls,
        request_id: Any,
        result: Any,
    ) -> "RemoteClientCommandProjection":
        return cls(kind="ResolveServerRequest", request_id=request_id, result=result)

    @classmethod
    def reject_server_request(
        cls,
        request_id: Any,
        error: Any,
    ) -> "RemoteClientCommandProjection":
        return cls(kind="RejectServerRequest", request_id=request_id, error=error)

    @classmethod
    def shutdown(cls) -> "RemoteClientCommandProjection":
        return cls(kind="Shutdown")


@dataclass(frozen=True)
class RemoteCommandEntrypointProjection:
    """Rust public remote command entrypoint send/response outcome."""

    operation: str
    command_kind: str
    has_response_oneshot: bool
    worker_send_error_kind: str
    worker_send_error_message: str
    response_closed_error_kind: str
    response_closed_error_message: str


@dataclass(frozen=True)
class RemoteWorkerCommandProjection:
    """Rust worker-side ``RemoteClientCommand`` match branch outcome."""

    command_kind: str
    jsonrpc_message_kind: str | None
    registers_pending_request: bool
    duplicate_request_error_message: str | None
    response_tx_receives_write_result: bool
    removes_pending_request_on_write_failure: bool
    emits_disconnected_on_write_failure: bool
    stores_worker_exit_error_on_write_failure: bool
    breaks_worker_after_command: bool
    close_uses_already_closed_tolerance: bool


@dataclass(frozen=True)
class RemoteWorkerStreamMessageProjection:
    """Rust worker-side websocket ``stream.next()`` match branch outcome."""

    frame_kind: str
    jsonrpc_message_kind: str | None
    removes_pending_request: bool
    pending_request_result: str | None
    delivers_event: bool
    event_kind: str | None
    writes_rejection: bool
    rejection_error_code: int | None
    rejection_error_message: str | None
    write_failure_emits_disconnected: bool
    worker_exit_error_kind: str | None
    worker_exit_message: str | None
    breaks_worker: bool
    ignored: bool


@dataclass(frozen=True)
class RemoteChannelTopologyProjection:
    """Rust remote worker channel topology."""

    command_channel_type: str
    command_capacity: int
    event_channel_type: str
    event_bounded: bool
    pending_events_buffer: str
    pending_requests_map: str


@dataclass(frozen=True)
class RemoteEventDeliveryProjection:
    """Rust ``deliver_event`` helper outcome."""

    delivered_events: list[Any]
    error_kind: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class RemoteNextEventProjection:
    """Rust ``RemoteAppServerClient::next_event`` pending-event behavior."""

    returned_event: Any | None
    pending_events_remaining: tuple[Any, ...]
    awaited_event_channel: bool


@dataclass(frozen=True)
class RemoteInitializeHandshakeProjection:
    """Rust remote initialize handshake write/wait sequence."""

    initialize_request_id: str
    initialize_request_method: str
    waits_for_matching_response_id: str
    sends_initialized_after_success: bool
    initialized_notification_method: str


@dataclass(frozen=True)
class RemoteInitializeFrameProjection:
    """Rust initialize-time frame handling outcome."""

    action: str
    completes_initialize: bool = False
    queued_event_kind: str | None = None
    rejection_code: int | None = None
    rejection_message: str | None = None
    ignored: bool = False


@dataclass(frozen=True)
class RemoteWriteJsonrpcMessageProjection:
    """Rust ``write_jsonrpc_message`` helper outcome."""

    payload: str
    error_message: str | None = None


@dataclass(frozen=True)
class RemoteWorkerExitProjection:
    """Rust remote worker pending-request exit outcome."""

    error_kind: str
    error_message: str
    pending_request_errors: tuple[str, ...]
    uses_default_exit_error: bool
    worker_exit_error_was_set: bool


@dataclass(frozen=True)
class RemoteWorkerCommandChannelClosedProjection:
    """Rust worker command-channel closed branch outcome."""

    closes_stream: bool
    close_error_ignored: bool
    breaks_worker: bool
    worker_exit_error_kind: str
    worker_exit_error_message: str
    pending_request_errors: tuple[str, ...]


@dataclass(frozen=True)
class RemoteWorkerSelectLoopProjection:
    """Rust remote worker ``tokio::select!`` loop topology."""

    select_arms: tuple[str, ...]
    biased: bool
    command_arm_source: str
    stream_arm_source: str
    pending_requests_map: str
    worker_exit_error_storage: str
    fans_out_pending_requests_after_loop: bool
    default_exit_error_kind: str
    default_exit_error_message: str


@dataclass(frozen=True)
class RemoteWorkerTimingBoundaryProjection:
    """Rust remote worker timing compatibility boundary."""

    command_channel_bounded: bool
    command_backpressure_owned_by_tokio: bool
    event_channel_unbounded: bool
    remote_lagged_synthesis: bool
    executes_select_loop: bool
    executes_branch_wakeup_timing: bool
    delegated_wire_client_module: str
    owns_second_websocket_state_machine: bool


@dataclass(frozen=True)
class RemoteWorkerSelectTimingProjection:
    """Rust remote worker ``tokio::select!`` readiness timing contract."""

    select_macro: str
    biased: bool
    command_ready: bool
    stream_ready: bool
    awaits_progress: bool
    selected_branch: str | None
    selected_branch_is_deterministic: bool
    simultaneous_ready_order_is_unspecified: bool
    selection_guarantee: str
    python_executes_scheduler: bool


@dataclass(frozen=True)
class RemoteCommandChannelBackpressureProjection:
    """Rust remote command-channel capacity/backpressure boundary."""

    command_channel_type: str
    capacity: int
    initially_queued: int
    receiver_open: bool
    commands_sent_without_wait: tuple[str, ...]
    commands_waiting_for_capacity: tuple[str, ...]
    send_waits_when_full: bool
    send_fails_only_when_receiver_closed: bool
    send_error_message: str | None
    event_channel_type: str
    event_channel_unbounded: bool
    remote_lagged_synthesis: bool


@dataclass(frozen=True)
class RemoteConnectEndpointProjection:
    """Rust remote endpoint connector control-flow projection."""

    endpoint_kind: str
    endpoint_label: str
    parses_websocket_url: bool
    checks_auth_token_policy: bool
    builds_client_request: bool
    inserts_authorization_header: bool
    ensures_rustls_crypto_provider: bool
    uses_websocket_config: bool
    connect_timeout_seconds: int
    socket_connect_step: str | None
    websocket_upgrade_step: str
    returns_endpoint_label: bool


@dataclass(frozen=True)
class RemoteConnectDispatchProjection:
    """Rust ``RemoteAppServerClient::connect`` top-level dispatch."""

    endpoint_kind: str
    connector_function: str
    channel_capacity: int
    builds_initialize_params_before_connect: bool
    passes_initialize_params_to_connect_with_stream: bool
    calls_connect_with_stream: bool
    returns_remote_client: bool


@dataclass(frozen=True)
class RemoteConnectWithStreamProjection:
    """Rust ``connect_with_stream`` lifecycle projection."""

    initialize_before_channels: bool
    initialize_timeout_seconds: int
    command_channel_type: str
    command_capacity: int
    event_channel_type: str
    event_bounded: bool
    pending_events_storage: str
    stores_server_version: bool
    spawns_worker: bool
    returns_worker_handle: bool


@dataclass(frozen=True)
class RemoteRequestHandleProjection:
    """Rust ``RemoteAppServerClient::request_handle`` shape."""

    clones_command_sender: bool
    owns_event_receiver: bool
    stores_server_version: bool
    request_uses_request_command: bool
    request_typed_uses_client_typed_error_mapping: bool


@dataclass(frozen=True)
class RemoteShutdownProjection:
    """Rust ``RemoteAppServerClient::shutdown`` control flow."""

    drop_event_receiver_before_shutdown_command: bool
    send_shutdown_command: bool
    await_response_timeout_seconds: int
    propagate_close_result: bool
    return_ok: bool
    await_worker_timeout_seconds: int
    abort_worker_on_timeout: bool


def remote_deliver_event_projection(
    event: AppServerEvent,
    *,
    consumer_open: bool = True,
) -> RemoteEventDeliveryProjection:
    """Project Rust remote ``deliver_event(...)`` channel result."""

    if consumer_open:
        return RemoteEventDeliveryProjection(delivered_events=[event])
    return RemoteEventDeliveryProjection(
        delivered_events=[],
        error_kind="BrokenPipe",
        error_message="remote app-server event consumer channel is closed",
    )


def remote_next_event_projection(pending_events: Iterable[Any]) -> RemoteNextEventProjection:
    """Project Rust remote ``next_event`` pending-event drain order."""

    events = tuple(pending_events)
    if events:
        return RemoteNextEventProjection(
            returned_event=events[0],
            pending_events_remaining=events[1:],
            awaited_event_channel=False,
        )
    return RemoteNextEventProjection(
        returned_event=None,
        pending_events_remaining=(),
        awaited_event_channel=True,
    )


def remote_channel_topology_projection(channel_capacity: int) -> RemoteChannelTopologyProjection:
    """Project Rust remote worker channel and pending-queue topology."""

    return RemoteChannelTopologyProjection(
        command_channel_type="mpsc::channel<RemoteClientCommand>",
        command_capacity=max(channel_capacity, 1),
        event_channel_type="mpsc::unbounded_channel<AppServerEvent>",
        event_bounded=False,
        pending_events_buffer="VecDeque<AppServerEvent>",
        pending_requests_map="HashMap<RequestId, oneshot::Sender<IoResult<RequestResult>>>",
    )


def remote_connect_with_stream_projection(channel_capacity: int) -> RemoteConnectWithStreamProjection:
    """Project Rust ``connect_with_stream(...)`` setup lifecycle."""

    return RemoteConnectWithStreamProjection(
        initialize_before_channels=True,
        initialize_timeout_seconds=REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS,
        command_channel_type="mpsc::channel<RemoteClientCommand>",
        command_capacity=int(channel_capacity),
        event_channel_type="mpsc::unbounded_channel<AppServerEvent>",
        event_bounded=False,
        pending_events_storage="VecDeque<AppServerEvent>",
        stores_server_version=True,
        spawns_worker=True,
        returns_worker_handle=True,
    )


def remote_worker_select_loop_projection() -> RemoteWorkerSelectLoopProjection:
    """Project Rust remote worker ``tokio::select!`` loop topology."""

    return RemoteWorkerSelectLoopProjection(
        select_arms=("command_rx.recv()", "stream.next()"),
        biased=False,
        command_arm_source="mpsc::Receiver<RemoteClientCommand>",
        stream_arm_source="WebSocketStream::next()",
        pending_requests_map="HashMap<RequestId, oneshot::Sender<IoResult<RequestResult>>>",
        worker_exit_error_storage="Option<(ErrorKind, String)>",
        fans_out_pending_requests_after_loop=True,
        default_exit_error_kind="BrokenPipe",
        default_exit_error_message="remote app-server worker channel is closed",
    )


def remote_worker_timing_boundary_projection() -> RemoteWorkerTimingBoundaryProjection:
    """Project the remaining Rust remote worker timing boundary."""

    return RemoteWorkerTimingBoundaryProjection(
        command_channel_bounded=True,
        command_backpressure_owned_by_tokio=True,
        event_channel_unbounded=True,
        remote_lagged_synthesis=False,
        executes_select_loop=False,
        executes_branch_wakeup_timing=False,
        delegated_wire_client_module="pycodex.exec.session",
        owns_second_websocket_state_machine=False,
    )


def remote_worker_select_timing_projection(
    *,
    command_ready: bool,
    stream_ready: bool,
) -> RemoteWorkerSelectTimingProjection:
    """Project Rust's observable remote worker ``tokio::select!`` timing.

    The Rust worker does not use ``biased;``. When both arms are ready, branch
    order is intentionally not a stable behavior contract.
    """

    ready_count = int(bool(command_ready)) + int(bool(stream_ready))
    selected_branch: str | None
    deterministic: bool
    awaits_progress = ready_count == 0
    if ready_count == 1:
        selected_branch = "command_rx.recv()" if command_ready else "stream.next()"
        deterministic = True
    else:
        selected_branch = None
        deterministic = False

    if ready_count == 0:
        guarantee = "worker awaits the next ready command or websocket message"
    elif ready_count == 1:
        guarantee = f"only the ready branch can be selected: {selected_branch}"
    else:
        guarantee = "unbiased tokio::select! does not promise a stable branch order"

    return RemoteWorkerSelectTimingProjection(
        select_macro="tokio::select!",
        biased=False,
        command_ready=bool(command_ready),
        stream_ready=bool(stream_ready),
        awaits_progress=awaits_progress,
        selected_branch=selected_branch,
        selected_branch_is_deterministic=deterministic,
        simultaneous_ready_order_is_unspecified=ready_count == 2,
        selection_guarantee=guarantee,
        python_executes_scheduler=False,
    )


def remote_command_channel_backpressure_projection(
    commands: Iterable[str],
    *,
    channel_capacity: int,
    initially_queued: int = 0,
    receiver_open: bool = True,
) -> RemoteCommandChannelBackpressureProjection:
    """Project Rust ``mpsc::Sender::send`` bounded-capacity behavior.

    Rust awaits when the bounded ``RemoteClientCommand`` channel is full and
    only returns a send error once the worker receiver is closed. The remote
    event channel is separate and unbounded.
    """

    capacity = max(int(channel_capacity), 1)
    queued = min(max(int(initially_queued), 0), capacity)
    command_names = tuple(str(command) for command in commands)
    if not receiver_open:
        return RemoteCommandChannelBackpressureProjection(
            command_channel_type="mpsc::channel<RemoteClientCommand>",
            capacity=capacity,
            initially_queued=queued,
            receiver_open=False,
            commands_sent_without_wait=(),
            commands_waiting_for_capacity=(),
            send_waits_when_full=True,
            send_fails_only_when_receiver_closed=True,
            send_error_message="remote app-server worker channel is closed",
            event_channel_type="mpsc::unbounded_channel<AppServerEvent>",
            event_channel_unbounded=True,
            remote_lagged_synthesis=False,
        )

    available_slots = max(capacity - queued, 0)
    return RemoteCommandChannelBackpressureProjection(
        command_channel_type="mpsc::channel<RemoteClientCommand>",
        capacity=capacity,
        initially_queued=queued,
        receiver_open=True,
        commands_sent_without_wait=command_names[:available_slots],
        commands_waiting_for_capacity=command_names[available_slots:],
        send_waits_when_full=True,
        send_fails_only_when_receiver_closed=True,
        send_error_message=None,
        event_channel_type="mpsc::unbounded_channel<AppServerEvent>",
        event_channel_unbounded=True,
        remote_lagged_synthesis=False,
    )


def remote_request_handle_projection() -> RemoteRequestHandleProjection:
    """Project Rust remote request-handle construction and routing."""

    return RemoteRequestHandleProjection(
        clones_command_sender=True,
        owns_event_receiver=False,
        stores_server_version=False,
        request_uses_request_command=True,
        request_typed_uses_client_typed_error_mapping=True,
    )


def remote_command_entrypoint_projection(operation: str) -> RemoteCommandEntrypointProjection:
    """Project Rust request/notify/resolve/reject command entrypoint errors."""

    command_kinds = {
        "request": "Request",
        "notify": "Notify",
        "resolve": "ResolveServerRequest",
        "reject": "RejectServerRequest",
    }
    channel_names = {
        "request": "request",
        "notify": "notify",
        "resolve": "resolve",
        "reject": "reject",
    }
    try:
        command_kind = command_kinds[operation]
        response_channel_name = channel_names[operation]
    except KeyError as exc:
        raise ValueError(f"unsupported remote command entrypoint `{operation}`") from exc

    return RemoteCommandEntrypointProjection(
        operation=operation,
        command_kind=command_kind,
        has_response_oneshot=True,
        worker_send_error_kind="BrokenPipe",
        worker_send_error_message="remote app-server worker channel is closed",
        response_closed_error_kind="BrokenPipe",
        response_closed_error_message=(
            f"remote app-server {response_channel_name} channel is closed"
        ),
    )


def remote_worker_command_projection(
    command_kind: str,
    *,
    duplicate_request_id: Any | None = None,
) -> RemoteWorkerCommandProjection:
    """Project the Rust worker ``RemoteClientCommand`` match branch shape."""

    if command_kind == "Request":
        if duplicate_request_id is not None:
            return RemoteWorkerCommandProjection(
                command_kind=command_kind,
                jsonrpc_message_kind=None,
                registers_pending_request=False,
                duplicate_request_error_message=(
                    f"duplicate remote app-server request id `{duplicate_request_id}`"
                ),
                response_tx_receives_write_result=False,
                removes_pending_request_on_write_failure=False,
                emits_disconnected_on_write_failure=False,
                stores_worker_exit_error_on_write_failure=False,
                breaks_worker_after_command=False,
                close_uses_already_closed_tolerance=False,
            )
        return RemoteWorkerCommandProjection(
            command_kind=command_kind,
            jsonrpc_message_kind="Request",
            registers_pending_request=True,
            duplicate_request_error_message=None,
            response_tx_receives_write_result=False,
            removes_pending_request_on_write_failure=True,
            emits_disconnected_on_write_failure=True,
            stores_worker_exit_error_on_write_failure=True,
            breaks_worker_after_command=False,
            close_uses_already_closed_tolerance=False,
        )
    if command_kind == "Notify":
        return RemoteWorkerCommandProjection(
            command_kind=command_kind,
            jsonrpc_message_kind="Notification",
            registers_pending_request=False,
            duplicate_request_error_message=None,
            response_tx_receives_write_result=True,
            removes_pending_request_on_write_failure=False,
            emits_disconnected_on_write_failure=False,
            stores_worker_exit_error_on_write_failure=False,
            breaks_worker_after_command=False,
            close_uses_already_closed_tolerance=False,
        )
    if command_kind == "ResolveServerRequest":
        return RemoteWorkerCommandProjection(
            command_kind=command_kind,
            jsonrpc_message_kind="Response",
            registers_pending_request=False,
            duplicate_request_error_message=None,
            response_tx_receives_write_result=True,
            removes_pending_request_on_write_failure=False,
            emits_disconnected_on_write_failure=False,
            stores_worker_exit_error_on_write_failure=False,
            breaks_worker_after_command=False,
            close_uses_already_closed_tolerance=False,
        )
    if command_kind == "RejectServerRequest":
        return RemoteWorkerCommandProjection(
            command_kind=command_kind,
            jsonrpc_message_kind="Error",
            registers_pending_request=False,
            duplicate_request_error_message=None,
            response_tx_receives_write_result=True,
            removes_pending_request_on_write_failure=False,
            emits_disconnected_on_write_failure=False,
            stores_worker_exit_error_on_write_failure=False,
            breaks_worker_after_command=False,
            close_uses_already_closed_tolerance=False,
        )
    if command_kind == "Shutdown":
        return RemoteWorkerCommandProjection(
            command_kind=command_kind,
            jsonrpc_message_kind=None,
            registers_pending_request=False,
            duplicate_request_error_message=None,
            response_tx_receives_write_result=True,
            removes_pending_request_on_write_failure=False,
            emits_disconnected_on_write_failure=False,
            stores_worker_exit_error_on_write_failure=False,
            breaks_worker_after_command=True,
            close_uses_already_closed_tolerance=True,
        )
    raise ValueError(f"unsupported remote worker command `{command_kind}`")


def remote_worker_stream_message_projection(
    frame_kind: str,
    *,
    endpoint: str,
    method: str | None = None,
    known_notification: bool = True,
    supported_server_request: bool = True,
    close_reason: Any = None,
    error: Any = None,
    reject_write_fails: bool = False,
) -> RemoteWorkerStreamMessageProjection:
    """Project Rust websocket ``stream.next()`` worker branch routing."""

    if frame_kind == "response":
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind="Response",
            removes_pending_request=True,
            pending_request_result="Ok(Ok(result))",
            delivers_event=False,
            event_kind=None,
            writes_rejection=False,
            rejection_error_code=None,
            rejection_error_message=None,
            write_failure_emits_disconnected=False,
            worker_exit_error_kind=None,
            worker_exit_message=None,
            breaks_worker=False,
            ignored=False,
        )
    if frame_kind == "error":
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind="Error",
            removes_pending_request=True,
            pending_request_result="Ok(Err(error))",
            delivers_event=False,
            event_kind=None,
            writes_rejection=False,
            rejection_error_code=None,
            rejection_error_message=None,
            write_failure_emits_disconnected=False,
            worker_exit_error_kind=None,
            worker_exit_message=None,
            breaks_worker=False,
            ignored=False,
        )
    if frame_kind == "notification":
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind="Notification",
            removes_pending_request=False,
            pending_request_result=None,
            delivers_event=known_notification,
            event_kind="AppServerEvent" if known_notification else None,
            writes_rejection=False,
            rejection_error_code=None,
            rejection_error_message=None,
            write_failure_emits_disconnected=False,
            worker_exit_error_kind=None,
            worker_exit_message=None,
            breaks_worker=False,
            ignored=not known_notification,
        )
    if frame_kind == "request":
        method_name = method or "<unknown>"
        rejection_message = remote_unsupported_server_request_error_message(method_name)
        write_failure_message = (
            remote_write_failed_disconnected_message(endpoint, error)
            if reject_write_fails
            else None
        )
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind="Request",
            removes_pending_request=False,
            pending_request_result=None,
            delivers_event=supported_server_request,
            event_kind="ServerRequest" if supported_server_request else None,
            writes_rejection=not supported_server_request,
            rejection_error_code=-32601 if not supported_server_request else None,
            rejection_error_message=None if supported_server_request else rejection_message,
            write_failure_emits_disconnected=reject_write_fails,
            worker_exit_error_kind="BrokenPipe" if reject_write_fails else None,
            worker_exit_message=write_failure_message,
            breaks_worker=reject_write_fails,
            ignored=False,
        )
    if frame_kind == "invalid_jsonrpc":
        message = remote_runtime_invalid_jsonrpc_disconnected_message(endpoint, error)
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind=None,
            removes_pending_request=False,
            pending_request_result=None,
            delivers_event=True,
            event_kind="Disconnected",
            writes_rejection=False,
            rejection_error_code=None,
            rejection_error_message=None,
            write_failure_emits_disconnected=False,
            worker_exit_error_kind="InvalidData",
            worker_exit_message=message,
            breaks_worker=True,
            ignored=False,
        )
    if frame_kind == "close":
        message = remote_runtime_close_frame_disconnected_message(endpoint, close_reason)
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind=None,
            removes_pending_request=False,
            pending_request_result=None,
            delivers_event=True,
            event_kind="Disconnected",
            writes_rejection=False,
            rejection_error_code=None,
            rejection_error_message=None,
            write_failure_emits_disconnected=False,
            worker_exit_error_kind="ConnectionAborted",
            worker_exit_message=message,
            breaks_worker=True,
            ignored=False,
        )
    if frame_kind in {"binary", "ping", "pong", "frame"}:
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind=None,
            removes_pending_request=False,
            pending_request_result=None,
            delivers_event=False,
            event_kind=None,
            writes_rejection=False,
            rejection_error_code=None,
            rejection_error_message=None,
            write_failure_emits_disconnected=False,
            worker_exit_error_kind=None,
            worker_exit_message=None,
            breaks_worker=False,
            ignored=True,
        )
    if frame_kind == "transport_failure":
        message = remote_runtime_transport_failure_disconnected_message(endpoint, error)
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind=None,
            removes_pending_request=False,
            pending_request_result=None,
            delivers_event=True,
            event_kind="Disconnected",
            writes_rejection=False,
            rejection_error_code=None,
            rejection_error_message=None,
            write_failure_emits_disconnected=False,
            worker_exit_error_kind="InvalidData",
            worker_exit_message=message,
            breaks_worker=True,
            ignored=False,
        )
    if frame_kind == "eof":
        message = remote_runtime_eof_disconnected_message(endpoint)
        return RemoteWorkerStreamMessageProjection(
            frame_kind=frame_kind,
            jsonrpc_message_kind=None,
            removes_pending_request=False,
            pending_request_result=None,
            delivers_event=True,
            event_kind="Disconnected",
            writes_rejection=False,
            rejection_error_code=None,
            rejection_error_message=None,
            write_failure_emits_disconnected=False,
            worker_exit_error_kind="UnexpectedEof",
            worker_exit_message=message,
            breaks_worker=True,
            ignored=False,
        )
    raise ValueError(f"unsupported remote worker stream frame `{frame_kind}`")


def remote_write_jsonrpc_message_projection(
    message: Any,
    *,
    endpoint: str,
    send_error: object | None = None,
) -> RemoteWriteJsonrpcMessageProjection:
    """Project Rust remote ``write_jsonrpc_message(...)`` serialization."""

    payload = json.dumps(_jsonrpc_message_mapping(message), separators=(",", ":"))
    if send_error is None:
        return RemoteWriteJsonrpcMessageProjection(payload=payload)
    return RemoteWriteJsonrpcMessageProjection(
        payload=payload,
        error_message=f"failed to write websocket message to `{endpoint}`: {send_error}",
    )


def remote_initialize_close_frame_error_message(endpoint: str, reason: Any = None) -> str:
    """Project Rust initialize close-frame reason/default error message."""

    reason_text = "" if reason is None else str(reason)
    if reason_text == "":
        reason_text = "connection closed during initialize"
    return f"remote app server at `{endpoint}` closed during initialize: {reason_text}"


def remote_initialize_error_message(endpoint: str, kind: str, detail: Any = None) -> str:
    """Project Rust ``initialize_remote_connection(...)`` error messages."""

    if kind == "rejected":
        return f"remote app server at `{endpoint}` rejected initialize: {detail}"
    if kind == "invalid_response":
        return f"remote app server at `{endpoint}` sent invalid initialize response: {detail}"
    if kind == "transport_failed":
        return f"remote app server at `{endpoint}` transport failed during initialize: {detail}"
    if kind == "eof":
        return f"remote app server at `{endpoint}` closed during initialize"
    if kind == "timeout":
        return f"timed out waiting for initialize response from `{endpoint}`"
    raise ValueError(f"unsupported remote initialize error kind `{kind}`")


def remote_initialize_handshake_projection() -> RemoteInitializeHandshakeProjection:
    """Project Rust ``initialize_remote_connection(...)`` write/wait sequence."""

    return RemoteInitializeHandshakeProjection(
        initialize_request_id="initialize",
        initialize_request_method="initialize",
        waits_for_matching_response_id="initialize",
        sends_initialized_after_success=True,
        initialized_notification_method="initialized",
    )


def remote_initialize_frame_projection(
    frame_kind: str,
    *,
    matching_initialize_id: bool = False,
    known_notification: bool = True,
    supported_server_request: bool = True,
    method: Any = None,
) -> RemoteInitializeFrameProjection:
    """Project Rust initialize-time JSON-RPC/non-text frame handling."""

    if frame_kind == "response":
        if matching_initialize_id:
            return RemoteInitializeFrameProjection(action="complete", completes_initialize=True)
        return RemoteInitializeFrameProjection(action="ignore", ignored=True)
    if frame_kind == "error":
        if matching_initialize_id:
            return RemoteInitializeFrameProjection(action="reject_initialize", completes_initialize=True)
        return RemoteInitializeFrameProjection(action="ignore", ignored=True)
    if frame_kind == "notification":
        if known_notification:
            return RemoteInitializeFrameProjection(
                action="queue_event",
                queued_event_kind="ServerNotification",
            )
        return RemoteInitializeFrameProjection(action="ignore", ignored=True)
    if frame_kind == "request":
        if supported_server_request:
            return RemoteInitializeFrameProjection(
                action="queue_event",
                queued_event_kind="ServerRequest",
            )
        message = remote_unsupported_server_request_error_message(method)
        return RemoteInitializeFrameProjection(
            action="write_rejection",
            rejection_code=-32601,
            rejection_message=message,
        )
    if frame_kind in {"binary", "ping", "pong", "frame"}:
        return RemoteInitializeFrameProjection(action="ignore", ignored=True)
    raise ValueError(f"unsupported remote initialize frame kind `{frame_kind}`")


def remote_runtime_close_frame_disconnected_message(endpoint: str, reason: Any = None) -> str:
    """Project Rust runtime close-frame disconnected event message."""

    reason_text = "" if reason is None else str(reason)
    if reason_text == "":
        reason_text = "connection closed"
    return f"remote app server at `{endpoint}` disconnected: {reason_text}"


def remote_runtime_eof_disconnected_message(endpoint: str) -> str:
    """Project Rust runtime EOF disconnected event message."""

    return f"remote app server at `{endpoint}` closed the connection"


def remote_runtime_transport_failure_disconnected_message(endpoint: str, error: Any) -> str:
    """Project Rust runtime transport-failure disconnected event message."""

    return f"remote app server at `{endpoint}` transport failed: {error}"


def remote_runtime_invalid_jsonrpc_disconnected_message(endpoint: str, error: Any) -> str:
    """Project Rust runtime invalid JSON-RPC disconnected event message."""

    return f"remote app server at `{endpoint}` sent invalid JSON-RPC: {error}"


def remote_websocket_connect_error_message(
    websocket_url: str,
    kind: str,
    error: Any = None,
) -> str:
    """Project Rust ``connect_websocket_endpoint(...)`` error messages."""

    if kind == "invalid_url":
        return f"invalid websocket URL `{websocket_url}`: {error}"
    if kind == "unsupported_auth_url":
        return (
            "remote auth tokens require `wss://` or loopback `ws://` URLs; "
            f"got `{websocket_url}`"
        )
    if kind == "timeout":
        return f"timed out connecting to remote app server at `{websocket_url}`"
    if kind == "failure":
        return f"failed to connect to remote app server at `{websocket_url}`: {error}"
    raise ValueError(f"unsupported remote websocket connect error kind `{kind}`")


def remote_unix_socket_connect_error_message(endpoint: str, kind: str, error: Any = None) -> str:
    """Project Rust ``connect_unix_socket_endpoint(...)`` error messages."""

    if kind == "invalid_handshake_url":
        return f"invalid UDS websocket handshake URL: {error}"
    if kind == "connect_timeout":
        return f"timed out connecting to remote app server at `{endpoint}`"
    if kind == "connect_failure":
        return f"failed to connect to remote app server at `{endpoint}`: {error}"
    if kind == "upgrade_timeout":
        return f"timed out upgrading remote app server at `{endpoint}`"
    if kind == "upgrade_failure":
        return f"failed to upgrade remote app server at `{endpoint}`: {error}"
    raise ValueError(f"unsupported remote unix socket connect error kind `{kind}`")


def remote_connect_endpoint_projection(
    endpoint: RemoteAppServerEndpoint,
) -> RemoteConnectEndpointProjection:
    """Project Rust websocket/Unix endpoint connector control flow."""

    if endpoint.kind == RemoteAppServerEndpointKind.WEB_SOCKET:
        assert endpoint.websocket_url is not None
        return RemoteConnectEndpointProjection(
            endpoint_kind="websocket",
            endpoint_label=endpoint.websocket_url,
            parses_websocket_url=True,
            checks_auth_token_policy=endpoint.auth_token is not None,
            builds_client_request=True,
            inserts_authorization_header=endpoint.auth_token is not None,
            ensures_rustls_crypto_provider=True,
            uses_websocket_config=True,
            connect_timeout_seconds=REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
            socket_connect_step=None,
            websocket_upgrade_step="connect_async_with_config",
            returns_endpoint_label=True,
        )
    if endpoint.kind == RemoteAppServerEndpointKind.UNIX_SOCKET:
        endpoint_label = f"unix://{endpoint.socket_path}"
        return RemoteConnectEndpointProjection(
            endpoint_kind="unix_socket",
            endpoint_label=endpoint_label,
            parses_websocket_url=False,
            checks_auth_token_policy=False,
            builds_client_request=True,
            inserts_authorization_header=False,
            ensures_rustls_crypto_provider=False,
            uses_websocket_config=True,
            connect_timeout_seconds=REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
            socket_connect_step="UnixStream::connect",
            websocket_upgrade_step="client_async_with_config",
            returns_endpoint_label=True,
        )
    raise ValueError(f"unsupported remote app-server endpoint kind `{endpoint.kind}`")


def remote_connect_dispatch_projection(
    args: RemoteAppServerConnectArgs,
) -> RemoteConnectDispatchProjection:
    """Project Rust ``RemoteAppServerClient::connect(...)`` dispatch."""

    if args.endpoint.kind == RemoteAppServerEndpointKind.WEB_SOCKET:
        endpoint_kind = "websocket"
        connector_function = "connect_websocket_endpoint"
    elif args.endpoint.kind == RemoteAppServerEndpointKind.UNIX_SOCKET:
        endpoint_kind = "unix_socket"
        connector_function = "connect_unix_socket_endpoint"
    else:
        raise ValueError(f"unsupported remote app-server endpoint kind `{args.endpoint.kind}`")
    return RemoteConnectDispatchProjection(
        endpoint_kind=endpoint_kind,
        connector_function=connector_function,
        channel_capacity=args.effective_channel_capacity,
        builds_initialize_params_before_connect=True,
        passes_initialize_params_to_connect_with_stream=True,
        calls_connect_with_stream=True,
        returns_remote_client=True,
    )


def remote_unsupported_server_request_error_message(method: Any) -> str:
    """Project Rust unsupported remote server-request JSON-RPC error message."""

    return f"unsupported remote app-server request `{method}`"


def remote_write_failed_disconnected_message(endpoint: str, error: Any) -> str:
    """Project Rust websocket write-failure disconnected event message."""

    return f"remote app server at `{endpoint}` write failed: {error}"


def remote_shutdown_close_failed_error_message(endpoint: str, error: Any) -> str:
    """Project Rust shutdown websocket close-failure error message."""

    return f"failed to close websocket app server `{endpoint}`: {error}"


def remote_worker_exit_pending_requests_projection(
    pending_request_count: int,
    *,
    error_kind: str | None = None,
    error_message: str | None = None,
) -> RemoteWorkerExitProjection:
    """Project Rust remote worker exit error fan-out to pending requests."""

    if pending_request_count < 0:
        raise ValueError("pending_request_count must be non-negative")
    uses_default_exit_error = error_kind is None and error_message is None
    if error_kind is None:
        error_kind = "BrokenPipe"
    if error_message is None:
        error_message = "remote app-server worker channel is closed"
    return RemoteWorkerExitProjection(
        error_kind=error_kind,
        error_message=error_message,
        pending_request_errors=(error_message,) * pending_request_count,
        uses_default_exit_error=uses_default_exit_error,
        worker_exit_error_was_set=not uses_default_exit_error,
    )


def remote_worker_command_channel_closed_projection(
    pending_request_count: int,
) -> RemoteWorkerCommandChannelClosedProjection:
    """Project Rust worker behavior when the command receiver is closed."""

    exit_projection = remote_worker_exit_pending_requests_projection(pending_request_count)
    return RemoteWorkerCommandChannelClosedProjection(
        closes_stream=True,
        close_error_ignored=True,
        breaks_worker=True,
        worker_exit_error_kind=exit_projection.error_kind,
        worker_exit_error_message=exit_projection.error_message,
        pending_request_errors=exit_projection.pending_request_errors,
    )


def remote_shutdown_projection(
    *,
    command_send_ok: bool = True,
    response_within_timeout: bool = True,
    close_result_ok: bool = True,
    worker_exits_within_timeout: bool = True,
) -> RemoteShutdownProjection:
    """Project Rust remote shutdown timeout and close-result behavior."""

    propagate_close_result = bool(command_send_ok and response_within_timeout)
    return RemoteShutdownProjection(
        drop_event_receiver_before_shutdown_command=True,
        send_shutdown_command=True,
        await_response_timeout_seconds=SHUTDOWN_TIMEOUT_SECONDS,
        propagate_close_result=propagate_close_result,
        return_ok=not propagate_close_result or bool(close_result_ok),
        await_worker_timeout_seconds=SHUTDOWN_TIMEOUT_SECONDS,
        abort_worker_on_timeout=not bool(worker_exits_within_timeout),
    )


def remote_duplicate_request_id_error_message(request_id: Any) -> str:
    """Project Rust duplicate remote request-id error message."""

    return f"duplicate remote app-server request id `{request_id}`"


@dataclass(frozen=True)
class RemoteAppServerEndpoint:
    """Python boundary for Rust ``RemoteAppServerEndpoint``."""

    kind: RemoteAppServerEndpointKind
    websocket_url: str | None = None
    auth_token: str | None = None
    socket_path: Any = None

    def __post_init__(self) -> None:
        if self.kind == RemoteAppServerEndpointKind.WEB_SOCKET:
            if not self.websocket_url:
                raise ValueError("websocket endpoint requires websocket_url")
            if self.socket_path is not None:
                raise ValueError("websocket endpoint cannot include socket_path")
            return
        if self.kind == RemoteAppServerEndpointKind.UNIX_SOCKET:
            if self.socket_path is None:
                raise ValueError("unix_socket endpoint requires socket_path")
            if self.websocket_url is not None or self.auth_token is not None:
                raise ValueError("unix_socket endpoint cannot include websocket_url or auth_token")
            return
        raise ValueError(f"unsupported remote app-server endpoint kind `{self.kind}`")

    @classmethod
    def websocket(cls, websocket_url: str, auth_token: str | None = None) -> "RemoteAppServerEndpoint":
        return cls(RemoteAppServerEndpointKind.WEB_SOCKET, websocket_url=websocket_url, auth_token=auth_token)

    @classmethod
    def unix_socket(cls, socket_path: Any) -> "RemoteAppServerEndpoint":
        return cls(RemoteAppServerEndpointKind.UNIX_SOCKET, socket_path=socket_path)


@dataclass(frozen=True)
class RemoteAppServerConnectArgs:
    """Python boundary for Rust ``RemoteAppServerConnectArgs``."""

    endpoint: RemoteAppServerEndpoint
    client_name: str
    client_version: str
    experimental_api: bool = False
    opt_out_notification_methods: list[str] = field(default_factory=list)
    channel_capacity: int = DEFAULT_IN_PROCESS_CHANNEL_CAPACITY

    def __post_init__(self) -> None:
        if not isinstance(self.opt_out_notification_methods, list):
            object.__setattr__(self, "opt_out_notification_methods", list(self.opt_out_notification_methods))

    @property
    def effective_channel_capacity(self) -> int:
        return max(self.channel_capacity, 1)

    def initialize_params(self) -> dict[str, Any]:
        return {
            "client_info": {
                "name": self.client_name,
                "title": None,
                "version": self.client_version,
            },
            "capabilities": {
                "experimental_api": self.experimental_api,
                "request_attestation": False,
                "opt_out_notification_methods": list(self.opt_out_notification_methods) or None,
            },
        }


class RemoteAppServerRequestHandle:
    """Python boundary for Rust ``RemoteAppServerRequestHandle``."""

    def __init__(self, client: "RemoteAppServerClient | None" = None) -> None:
        self._client = client

    async def request(self, request: Any) -> RequestResult:
        if self._client is None:
            raise AppServerClientNotImplementedError("RemoteAppServerRequestHandle.request is not ported yet")
        return await self._client.request(request)

    async def request_typed(self, request: Any, decoder: Callable[[Any], Any] | None = None) -> Any:
        if self._client is None:
            raise AppServerClientNotImplementedError("RemoteAppServerRequestHandle.request_typed is not ported yet")
        return await self._client.request_typed(request, decoder=decoder)


class RemoteAppServerClient:
    """Python boundary for Rust ``RemoteAppServerClient``."""

    def __init__(
        self,
        *,
        request_handler: RequestHandler | None = None,
        notification_handler: NotificationHandler | None = None,
        events: list[AppServerEvent] | None = None,
        server_version: str | None = None,
        wire_client: Any = None,
        suppress_next_eof_event: bool = False,
    ) -> None:
        self._request_handler = request_handler
        self._notification_handler = notification_handler
        self._events = deque(events or [])
        self._server_version = server_version
        self._wire_client = wire_client
        self._suppress_next_eof_event = suppress_next_eof_event
        self._server_request_results: dict[Any, Any] = {}
        self._server_request_errors: dict[Any, Any] = {}
        self._shutdown = False

    @classmethod
    async def connect(
        cls,
        args: RemoteAppServerConnectArgs,
        *,
        websocket_connector: Callable[..., Any] | None = None,
        unix_socket_connector: Callable[..., Any] | None = None,
        trace: Any = None,
        initialize_max_frames: int | None = None,
    ) -> "RemoteAppServerClient":
        remote_session = _remote_session_module()
        websocket_url_error = _remote_websocket_url_error(args.endpoint)
        if websocket_url_error is not None:
            raise OSError(f"invalid websocket URL `{args.endpoint.websocket_url}`: {websocket_url_error}")
        auth_header_error = _remote_authorization_header_error(args.endpoint)
        if auth_header_error is not None:
            raise OSError(remote_session.remote_invalid_authorization_header_message(auth_header_error))
        connect_observation: dict[str, Any] = {"server_version": None, "frames_seen": 0}
        result = remote_session.remote_app_server_client_connect(
            _to_exec_remote_connect_args(args),
            websocket_connector=_observing_websocket_connector(
                websocket_connector or remote_session.StdlibWebSocket.connect,
                connect_observation,
            ),
            unix_socket_connector=_observing_websocket_connector(
                _unix_socket_connector_with_str_path(
                    unix_socket_connector or remote_session.StdlibWebSocket.connect_unix_socket
                ),
                connect_observation,
            ),
            trace=trace,
            initialize_max_frames=initialize_max_frames,
        )
        if not result.ok:
            raise OSError(result.error_message or "failed to connect to remote app server")
        events = [_from_exec_app_server_event(event) for event in result.client.state.pending_events]
        return cls(
            events=[event for event in events if event is not None],
            server_version=connect_observation["server_version"],
            wire_client=result.client,
            suppress_next_eof_event=connect_observation["frames_seen"] > 1,
        )

    def server_version(self) -> str | None:
        return self._server_version

    def request_handle(self) -> RemoteAppServerRequestHandle:
        return RemoteAppServerRequestHandle(self)

    async def request(self, request: Any) -> RequestResult:
        self._ensure_running("request")
        if self._wire_client is not None:
            step = self._wire_client.request(_to_exec_client_request(request))
            event = _remote_request_transport_event(step)
            if event is not None:
                self._events.append(event)
            result = _remote_request_result_from_step(step)
            if event is None:
                self._suppress_next_eof_event = True
            return result
        if self._request_handler is None:
            raise AppServerClientNotImplementedError("RemoteAppServerClient.request is not ported yet")
        return await _maybe_await(self._request_handler(request))

    async def request_typed(self, request: Any, decoder: Callable[[Any], Any] | None = None) -> Any:
        method = request_method_name(request)
        try:
            response = await self.request(request)
        except OSError as exc:
            raise TypedRequestError.transport(method, exc) from exc
        if isinstance(response, JSONRPCErrorError):
            raise TypedRequestError.server(method, response)
        if decoder is not None:
            try:
                return decoder(response)
            except Exception as exc:
                raise TypedRequestError.deserialize(method, exc) from exc
        return response

    async def notify(self, notification: Any) -> None:
        self._ensure_running("notify")
        if self._wire_client is not None:
            jsonrpc = jsonrpc_notification_from_client_notification(notification)
            step = self._wire_client.send_notification(jsonrpc.method, jsonrpc.params)
            _raise_remote_step_error(step)
            return None
        if self._notification_handler is None:
            return None
        await _maybe_await(self._notification_handler(notification))
        return None

    async def resolve_server_request(self, request_id: Any, result: Any) -> None:
        self._ensure_running("resolve_server_request")
        if self._wire_client is not None:
            remote_session = _remote_session_module()
            decision = remote_session.ServerRequestDecision.resolve(request_id, "", result)
            step = self._wire_client.resolve_or_reject_server_request(decision)
            _raise_remote_step_error(step)
        self._server_request_results[request_id] = result

    async def reject_server_request(self, request_id: Any, error: Any) -> None:
        self._ensure_running("reject_server_request")
        if self._wire_client is not None:
            remote_session = _remote_session_module()
            error_value = _jsonrpc_error_error(error)
            decision = remote_session.ServerRequestDecision(
                action="reject",
                request_id=request_id,
                method="",
                error=remote_session.JsonRpcError(
                    error_value.message,
                    code=error_value.code,
                    data=error_value.data,
                ),
            )
            step = self._wire_client.resolve_or_reject_server_request(decision)
            _raise_remote_step_error(step)
        self._server_request_errors[request_id] = error

    async def next_event(self) -> AppServerEvent | None:
        self._ensure_running("next_event")
        while True:
            if self._events:
                return self._events.popleft()
            if self._wire_client is None:
                return None
            while True:
                step = self._wire_client.next_event()
                if step.event is not None:
                    if step.error_kind == "UnexpectedEof" and self._suppress_next_eof_event:
                        self._suppress_next_eof_event = False
                        return None
                    event = _from_exec_app_server_event(step.event)
                    if event is not None:
                        return event
                    continue
                if step.ignored or step.outgoing is not None:
                    self._suppress_next_eof_event = True
                event = _remote_write_failed_disconnected_event(step)
                if event is not None:
                    return event
                _raise_remote_step_error(step)
                continue

    async def shutdown(self) -> None:
        if self._wire_client is not None:
            try:
                result = self._wire_client.close()
            except OSError as exc:
                if not _remote_shutdown_close_error_is_tolerable(exc):
                    raise
            else:
                if result.close_error_message is not None:
                    if not _remote_shutdown_close_error_is_tolerable(result.close_error_message):
                        raise OSError(result.close_error_message)
        self._shutdown = True
        self._events.clear()
        return None

    def push_event(self, event: AppServerEvent) -> None:
        self._ensure_running("push_event")
        self._events.append(event)

    def resolved_server_requests(self) -> dict[Any, Any]:
        return dict(self._server_request_results)

    def rejected_server_requests(self) -> dict[Any, Any]:
        return dict(self._server_request_errors)

    def _ensure_running(self, operation: str) -> None:
        if self._shutdown:
            raise BrokenPipeError(f"remote app-server {operation} channel is closed")


def websocket_url_supports_auth_token(websocket_url: str) -> bool:
    """Return whether Rust permits an auth token for this WebSocket URL."""

    return _remote_session_module().websocket_url_supports_auth_token(websocket_url)


def _remote_websocket_url_error(endpoint: RemoteAppServerEndpoint) -> str | None:
    if endpoint.kind != RemoteAppServerEndpointKind.WEB_SOCKET:
        return None
    websocket_url = str(endpoint.websocket_url)
    try:
        parsed = urlparse(websocket_url)
        host = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        return str(exc)
    if parsed.scheme not in {"ws", "wss"} or host is None:
        return "expected `ws://host` or `wss://host`"
    return None


def _remote_authorization_header_error(endpoint: RemoteAppServerEndpoint) -> str | None:
    if endpoint.kind != RemoteAppServerEndpointKind.WEB_SOCKET or endpoint.auth_token is None:
        return None
    header_value = f"Bearer {endpoint.auth_token}"
    if any(_invalid_http_header_value_char(ch) for ch in header_value):
        return "failed to parse header value"
    return None


def _invalid_http_header_value_char(ch: str) -> bool:
    code = ord(ch)
    return code == 127 or (code < 32 and ch != "\t")


def remote_websocket_config() -> dict[str, int]:
    return {
        "max_frame_size": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
        "max_message_size": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    }


def jsonrpc_request_from_client_request(request: ClientRequest | dict[str, Any]) -> JSONRPCRequest:
    if isinstance(request, ClientRequest):
        try:
            return request.to_jsonrpc()
        except ValueError:
            return JSONRPCRequest(id=request.request_id, method=request.type, params=copy.deepcopy(request.params))
    if isinstance(request, dict):
        if "method" in request and "id" in request:
            return JSONRPCRequest.from_mapping(request)
        return ClientRequest(
            type=str(request["type"]),
            request_id=request.get("request_id", request.get("requestId")),
            params=request.get("params"),
        ).to_jsonrpc()
    raise TypeError("request must be a ClientRequest or mapping")


def remote_jsonrpc_projection_panic_message(subject: str, stage: str, error: Any) -> str:
    """Project Rust panic text for JSON-RPC serde projection helpers."""

    if subject not in {"request", "notification"}:
        raise ValueError(f"unsupported JSON-RPC projection subject `{subject}`")
    if stage == "serialize":
        return f"client {subject} should serialize: {error}"
    if stage == "encode":
        return f"client {subject} should encode as JSON-RPC {subject}: {error}"
    raise ValueError(f"unsupported JSON-RPC projection stage `{stage}`")


def request_id_from_client_request(request: ClientRequest | dict[str, Any]) -> Any:
    return jsonrpc_request_from_client_request(request).id.to_json()


def jsonrpc_notification_from_client_notification(
    notification: ClientNotification | dict[str, Any],
) -> JSONRPCNotification:
    if isinstance(notification, ClientNotification):
        try:
            return notification.to_jsonrpc()
        except ValueError:
            return JSONRPCNotification(method=notification.type, params=copy.deepcopy(notification.payload))
    if isinstance(notification, dict):
        if "method" in notification:
            return JSONRPCNotification.from_mapping(notification)
        return ClientNotification(
            type=str(notification["type"]),
            payload=notification.get("payload"),
        ).to_jsonrpc()
    raise TypeError("notification must be a ClientNotification or mapping")


def _jsonrpc_message_mapping(message: Any) -> dict[str, Any]:
    if hasattr(message, "to_mapping"):
        return message.to_mapping()
    if isinstance(message, dict):
        return dict(message)
    raise TypeError("message must be a JSON-RPC mapping or object with to_mapping()")


def _remote_session_module() -> Any:
    from pycodex.exec import session as remote_session

    return remote_session


def _to_exec_remote_endpoint(endpoint: RemoteAppServerEndpoint) -> Any:
    remote_session = _remote_session_module()
    if endpoint.kind == RemoteAppServerEndpointKind.WEB_SOCKET:
        if endpoint.websocket_url is None:
            raise ValueError("websocket endpoint requires websocket_url")
        return remote_session.RemoteAppServerEndpoint.websocket(
            endpoint.websocket_url,
            auth_token=endpoint.auth_token,
        )
    if endpoint.kind == RemoteAppServerEndpointKind.UNIX_SOCKET:
        if endpoint.socket_path is None:
            raise ValueError("unix_socket endpoint requires socket_path")
        return remote_session.RemoteAppServerEndpoint.unix_socket(endpoint.socket_path)
    raise ValueError(f"unsupported remote app-server endpoint kind `{endpoint.kind}`")


def _to_exec_remote_connect_args(args: RemoteAppServerConnectArgs) -> Any:
    remote_session = _remote_session_module()
    return remote_session.RemoteAppServerConnectArgs(
        endpoint=_to_exec_remote_endpoint(args.endpoint),
        client_name=args.client_name,
        client_version=args.client_version,
        experimental_api=args.experimental_api,
        opt_out_notification_methods=tuple(args.opt_out_notification_methods),
        channel_capacity=args.effective_channel_capacity,
    )


def _to_exec_client_request(request: ClientRequest | dict[str, Any]) -> Any:
    remote_session = _remote_session_module()
    jsonrpc = jsonrpc_request_from_client_request(request)
    return remote_session.ClientRequest(
        method=jsonrpc.method,
        params=jsonrpc.params,
        request_id=jsonrpc.id.to_json(),
    )


class _InitializeUserAgentObserver:
    def __init__(self, websocket: Any, observation: dict[str, Any]) -> None:
        self._websocket = websocket
        self._observation = observation

    def __getattr__(self, name: str) -> Any:
        return getattr(self._websocket, name)

    def send_text(self, text: str) -> None:
        self._websocket.send_text(_initialize_payload_with_title(text))

    def recv_frame(self) -> Any:
        frame = self._websocket.recv_frame()
        self._observation["frames_seen"] = int(self._observation.get("frames_seen", 0)) + 1
        version = _server_version_from_initialize_frame(frame)
        if version is not None:
            self._observation["server_version"] = version
        return frame


def _initialize_payload_with_title(text: str) -> str:
    try:
        message = json.loads(text)
    except (TypeError, ValueError):
        return text
    if not isinstance(message, dict):
        return text
    if message.get("id") != "initialize" or message.get("method") != "initialize":
        return text
    params = message.get("params")
    if not isinstance(params, dict):
        return text
    client_info = params.get("clientInfo")
    if not isinstance(client_info, dict) or "title" in client_info:
        return text
    client_info = dict(client_info)
    client_info["title"] = None
    params = dict(params)
    params["clientInfo"] = client_info
    message = dict(message)
    message["params"] = params
    return json.dumps(message, separators=(",", ":"), ensure_ascii=False)


def _observing_websocket_connector(
    connector: Callable[..., Any],
    observation: dict[str, Any],
) -> Callable[..., Any]:
    def connect(*args: Any, **kwargs: Any) -> _InitializeUserAgentObserver:
        return _InitializeUserAgentObserver(connector(*args, **kwargs), observation)

    return connect


def _unix_socket_connector_with_str_path(connector: Callable[..., Any]) -> Callable[..., Any]:
    def connect(socket_path: Any, *args: Any, **kwargs: Any) -> Any:
        return connector(str(socket_path), *args, **kwargs)

    return connect


def _server_version_from_initialize_frame(frame: Any) -> str | None:
    text_method = getattr(frame, "text", None)
    if not callable(text_method):
        return None
    try:
        message = json.loads(text_method())
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(message, dict) or message.get("id") != "initialize":
        return None
    result = message.get("result")
    if not isinstance(result, dict):
        return None
    return _server_version_from_user_agent(result.get("userAgent"))


def remote_server_version_from_user_agent(user_agent: Any) -> str | None:
    """Project Rust initialize ``userAgent`` server-version parsing."""

    return _server_version_from_user_agent(user_agent)


def _server_version_from_user_agent(user_agent: Any) -> str | None:
    if not isinstance(user_agent, str):
        return None
    _, separator, rest = user_agent.partition("/")
    if not separator:
        return None
    parts = rest.split(maxsplit=1)
    if not parts:
        return None
    version = parts[0]
    return version or None


def _remote_shutdown_worker_already_closed(message: str) -> bool:
    return "remote app-server worker channel is closed" in message


def remote_websocket_close_error_is_already_closed(error: object) -> bool:
    """Project Rust ``websocket_close_error_is_already_closed(...)``."""

    return bool(_remote_session_module().websocket_close_error_is_already_closed(error))


def _remote_shutdown_close_error_is_tolerable(error: object) -> bool:
    if _remote_shutdown_worker_already_closed(str(error)):
        return True
    return remote_websocket_close_error_is_already_closed(error)


def remote_app_server_event_from_notification(notification: Any) -> AppServerEvent | None:
    try:
        server_notification_from_jsonrpc(notification)
    except (TypeError, ValueError, KeyError):
        return None
    return AppServerEvent.server_notification(notification)


def _from_exec_app_server_event(event: Any) -> AppServerEvent | None:
    kind = getattr(event, "kind", None)
    if kind == "server_notification":
        return remote_app_server_event_from_notification(getattr(event, "notification", None))
    if kind == "server_request":
        return AppServerEvent.server_request(getattr(event, "request", None))
    if kind == "lagged":
        return AppServerEvent.lagged(getattr(event, "skipped", 0) or 0)
    if kind == "disconnected":
        return AppServerEvent.disconnected(getattr(event, "message", "") or "")
    if isinstance(event, AppServerEvent):
        return event
    raise ValueError(f"unknown remote AppServerEvent kind: {kind}")


def _jsonrpc_error_error(error: Any) -> JSONRPCErrorError:
    if isinstance(error, JSONRPCErrorError):
        return error
    if isinstance(error, dict):
        return JSONRPCErrorError.from_mapping(error)
    code = getattr(error, "code", -32000)
    message = getattr(error, "message", str(error))
    data = getattr(error, "data", None)
    return JSONRPCErrorError(code=code, message=message, data=data)


def _jsonrpc_error_error_from_exec(error: Any) -> JSONRPCErrorError:
    return JSONRPCErrorError(
        code=getattr(error, "code", -32000),
        message=getattr(error, "message", str(error)),
        data=getattr(error, "data", None),
    )


def _raise_remote_step_error(step: Any) -> None:
    if getattr(step, "error_message", None) is not None:
        raise OSError(step.error_message)


def _remote_request_result_from_step(step: Any) -> RequestResult:
    if getattr(step, "event", None) is not None and getattr(step, "error_message", None) is not None:
        raise OSError(step.error_message)
    _raise_remote_step_error(step)
    if getattr(step, "response_error", None) is not None:
        return _jsonrpc_error_error_from_exec(step.response_error)
    return getattr(step, "response_result", None)


def _remote_request_transport_event(step: Any) -> AppServerEvent | None:
    if getattr(step, "event", None) is not None:
        return _from_exec_app_server_event(step.event)
    return _remote_write_failed_disconnected_event(step)


def _remote_write_failed_disconnected_event(step: Any) -> AppServerEvent | None:
    return _remote_write_failed_disconnected_event_from_error_message(getattr(step, "error_message", None))


def _remote_write_failed_disconnected_event_from_error_message(error_message: Any) -> AppServerEvent | None:
    if not isinstance(error_message, str):
        return None
    prefix = "failed to write websocket message to `"
    if not error_message.startswith(prefix):
        return None
    endpoint, separator, _reason = error_message[len(prefix) :].partition("`: ")
    if not separator:
        return None
    return AppServerEvent.disconnected(remote_write_failed_disconnected_message(endpoint, error_message))


