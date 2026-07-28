"""Python API boundary for Rust crate ``codex-app-server-client``.

The Rust crate is an async facade over in-process and remote app-server
transports.  This module defines the Python-side interfaces consumed by the TUI
port; transport behavior is intentionally not implemented until the matching
app-server runtime slice is ported.
"""

from __future__ import annotations

import json
import copy
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar
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
from pycodex.core.state_db_bridge import StateDbHandle
from pycodex.exec_server import EnvironmentManager, ExecServerRuntimePaths

from . import legacy_core as legacy_core


DEFAULT_IN_PROCESS_CHANNEL_CAPACITY = 1024
SHUTDOWN_TIMEOUT_SECONDS = 5
RequestResult = Any
T = TypeVar("T")
RequestHandler = Callable[[Any], RequestResult | Awaitable[RequestResult]]
NotificationHandler = Callable[[Any], None | Awaitable[None]]
LOSSLESS_SERVER_NOTIFICATION_TYPES = frozenset(
    {
        "TurnCompleted",
        "ThreadSettingsUpdated",
        "ItemCompleted",
        "AgentMessageDelta",
        "PlanDelta",
        "ReasoningSummaryTextDelta",
        "ReasoningTextDelta",
    }
)


class AppServerClientNotImplementedError(NotImplementedError):
    """Raised when an app-server client transport method is not ported yet."""


class TypedRequestError(RuntimeError):
    """Python boundary for Rust ``TypedRequestError``."""

    def __init__(
        self,
        method: str,
        kind: str,
        source: BaseException | JSONRPCErrorError | str | None = None,
    ) -> None:
        self.method = method
        self.kind = kind
        self.source = source
        if kind in {"transport", "deserialize"} and isinstance(source, BaseException):
            self.__cause__ = source
        super().__init__(str(self))

    @classmethod
    def transport(cls, method: str, source: BaseException | str) -> "TypedRequestError":
        return cls(method, "transport", source)

    @classmethod
    def server(cls, method: str, source: JSONRPCErrorError) -> "TypedRequestError":
        return cls(method, "server", source)

    @classmethod
    def deserialize(cls, method: str, source: BaseException | str) -> "TypedRequestError":
        return cls(method, "deserialize", source)

    def __str__(self) -> str:
        if self.kind == "transport":
            return f"{self.method} transport error: {self.source}"
        if self.kind == "server":
            source = self.source
            message = getattr(source, "message", source)
            code = getattr(source, "code", None)
            data = getattr(source, "data", None)
            text = f"{self.method} failed: {message}"
            if code is not None:
                text += f" (code {code})"
            if data is not None:
                text += f", data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}"
            return text
        if self.kind == "deserialize":
            return f"{self.method} response decode error: {self.source}"
        return f"{self.method} {self.kind} error" + (f": {self.source}" if self.source else "")


@dataclass(frozen=True)
class InProcessServerEvent:
    """Placeholder for Rust ``InProcessServerEvent`` re-exported by this crate."""

    kind: str
    payload: Any = None
    skipped: int | None = None

    @classmethod
    def lagged(cls, skipped: int) -> "InProcessServerEvent":
        return cls("Lagged", skipped=skipped)

    @classmethod
    def server_notification(cls, notification: Any) -> "InProcessServerEvent":
        return cls("ServerNotification", payload=notification)

    @classmethod
    def server_request(cls, request: Any) -> "InProcessServerEvent":
        return cls("ServerRequest", payload=request)


class ForwardEventResult(Enum):
    """Rust internal ``ForwardEventResult`` projection."""

    CONTINUE = "Continue"
    DISABLE_STREAM = "DisableStream"


@dataclass(frozen=True)
class InProcessEventForwardProjection:
    """Deterministic projection of Rust in-process event forwarding."""

    events: list[InProcessServerEvent]
    skipped_events: int = 0
    rejected_server_requests: dict[Any, JSONRPCErrorError] = field(default_factory=dict)
    result: ForwardEventResult = ForwardEventResult.CONTINUE
    stream_enabled: bool = True


@dataclass(frozen=True)
class InProcessWorkerEventProjection:
    """Rust worker-side ``handle.next_event()`` branch outcome."""

    event_present: bool
    unsupported_auth_refresh: bool
    rejection_error: JSONRPCErrorError | None
    forwards_event: bool
    forward_result: ForwardEventResult | None
    disables_event_stream: bool
    breaks_worker: bool
    continues_worker: bool


@dataclass(frozen=True)
class InProcessCommandEntrypointProjection:
    """Rust public in-process command entrypoint send/response outcome."""

    operation: str
    command_kind: str
    has_response_oneshot: bool
    worker_send_error_kind: str
    worker_send_error_message: str
    response_closed_error_kind: str
    response_closed_error_message: str


@dataclass(frozen=True)
class InProcessRequestResponseProjection:
    """Rust in-process raw request response boundary."""

    command_kind: str
    boxes_request: bool
    creates_response_oneshot: bool
    sends_on_worker_channel: bool
    awaits_response_oneshot: bool
    returns_raw_request_result: bool
    worker_send_error_kind: str
    worker_send_error_message: str
    response_closed_error_kind: str
    response_closed_error_message: str
    typed_wrapper_maps_transport: bool
    typed_wrapper_maps_server_error: bool
    typed_wrapper_maps_deserialize_error: bool


@dataclass(frozen=True)
class InProcessWorkerRequestTaskProjection:
    """Rust worker detached request task response-delivery boundary."""

    command_kind: str
    spawned_from_worker_branch: bool
    clones_request_sender: bool
    moves_boxed_request_into_task: bool
    awaits_runtime_request: bool
    runtime_result_expression: str
    sends_result_to_response_oneshot: bool
    ignores_response_receiver_dropped: bool
    worker_loop_keeps_draining_events_while_request_waits: bool
    fabricates_message_processor_result: bool


@dataclass(frozen=True)
class InProcessRequestHandleProjection:
    """Rust in-process request-handle factory and request boundary."""

    factory_method: str
    clones_command_sender: bool
    handle_request_command_kind: str
    handle_request_boxes_request: bool
    handle_request_uses_response_oneshot: bool
    handle_typed_uses_request_method_name: bool
    handle_typed_wraps_transport_error: bool
    handle_typed_wraps_server_error: bool
    handle_typed_wraps_deserialize_error: bool


@dataclass(frozen=True)
class InProcessNextEventProjection:
    """Rust in-process ``next_event`` facade boundary."""

    event_receiver_source: str
    requires_mutable_client: bool
    awaits_receiver_recv: bool
    returns_option: bool
    closed_receiver_returns_none: bool
    preserves_in_process_event: bool
    converts_to_app_server_event: bool


@dataclass
class InProcessRuntimeStartArgs:
    """Python boundary for Rust runtime start args produced from in-process args."""

    arg0_paths: Any
    config: Any
    cli_overrides: list[tuple[str, Any]]
    loader_overrides: Any
    strict_config: bool
    cloud_requirements: Any
    feedback: Any
    log_db: Any
    state_db: StateDbHandle | None
    environment_manager: EnvironmentManager | Any
    config_warnings: list[Any]
    session_source: Any
    enable_codex_api_key_env: bool
    initialize_params: dict[str, Any]
    thread_config_loader: Any
    channel_capacity: int


@dataclass(frozen=True)
class InProcessRuntimeDependencyProjection:
    """Rust in-process client runtime ownership boundary."""

    client_crate_module: str
    runtime_owner_crate: str
    runtime_owner_python_package: str
    rust_runtime_function: str
    python_runtime_entrypoint: str
    runtime_package_exists: bool
    full_runtime_complete: bool
    client_should_fabricate_runtime: bool


@dataclass(frozen=True)
class InProcessWorkerTopologyProjection:
    """Rust in-process worker setup and select-loop topology."""

    starts_runtime_handle: bool
    runtime_start_function: str
    request_sender_source: str
    command_channel_type: str
    event_channel_type: str
    channel_capacity: int
    owns_command_sender: bool
    owns_event_receiver: bool
    owns_worker_handle: bool
    worker_initial_event_stream_enabled: bool
    worker_initial_skipped_events: int
    select_arms: tuple[str, ...]
    event_arm_guard: str
    returns_worker_backed_client: bool


@dataclass(frozen=True)
class InProcessWorkerSelectTimingProjection:
    """Rust in-process worker ``tokio::select!`` timing boundary."""

    select_macro: str
    biased: bool
    command_ready: bool
    event_ready: bool
    event_stream_enabled: bool
    event_arm_enabled: bool
    awaits_progress: bool
    selected_branch: str | None
    selected_branch_is_deterministic: bool
    simultaneous_ready_order_is_unspecified: bool
    selection_guarantee: str
    python_executes_scheduler: bool


@dataclass(frozen=True)
class InProcessCommandChannelBackpressureProjection:
    """Rust in-process command-channel capacity/backpressure boundary."""

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
    event_channel_bounded: bool
    event_channel_capacity: int
    event_backpressure_handler: str


@dataclass(frozen=True)
class InProcessShutdownProjection:
    """Rust ``InProcessAppServerClient::shutdown`` local control flow."""

    drop_event_receiver_before_shutdown_command: bool
    send_shutdown_command: bool
    await_response_timeout_seconds: int
    return_command_result: bool
    drop_command_sender_before_worker_wait: bool
    await_worker_timeout_seconds: int
    abort_worker_on_timeout: bool


@dataclass(frozen=True)
class InProcessShutdownEntrypointProjection:
    """Rust in-process shutdown command entrypoint boundary."""

    consumes_client: bool
    destructures_command_sender: bool
    destructures_event_receiver: bool
    destructures_worker_handle: bool
    drop_event_receiver_before_shutdown_command: bool
    command_kind: str
    has_response_oneshot: bool
    ignores_worker_send_error: bool
    ignores_response_timeout: bool
    propagates_in_time_command_result: bool
    response_closed_error_kind: str
    response_closed_error_message: str


@dataclass(frozen=True)
class InProcessClientCommandProjection:
    """Rust internal ``ClientCommand`` variant shape."""

    kind: str
    request: Any = None
    notification: Any = None
    request_id: Any = None
    result: Any = None
    error: Any = None
    has_response_oneshot: bool = True
    request_is_boxed: bool = False

    @classmethod
    def request_command(cls, request: Any) -> "InProcessClientCommandProjection":
        return cls(kind="Request", request=request, request_is_boxed=True)

    @classmethod
    def notify(cls, notification: Any) -> "InProcessClientCommandProjection":
        return cls(kind="Notify", notification=notification)

    @classmethod
    def resolve_server_request(
        cls,
        request_id: Any,
        result: Any,
    ) -> "InProcessClientCommandProjection":
        return cls(kind="ResolveServerRequest", request_id=request_id, result=result)

    @classmethod
    def reject_server_request(
        cls,
        request_id: Any,
        error: Any,
    ) -> "InProcessClientCommandProjection":
        return cls(kind="RejectServerRequest", request_id=request_id, error=error)

    @classmethod
    def shutdown(cls) -> "InProcessClientCommandProjection":
        return cls(kind="Shutdown")


@dataclass(frozen=True)
class InProcessWorkerCommandProjection:
    """Rust worker-side ``ClientCommand`` match branch outcome."""

    command_kind: str
    request_sender_method: str | None
    clones_request_sender: bool
    uses_detached_task: bool
    sends_response: bool
    response_result_source: str | None
    calls_handle_shutdown: bool
    breaks_worker_after_command: bool
    channel_closed_branch: bool = False


def app_server_control_socket_path(codex_home: Any) -> Any:
    """Return the default app-server control socket path.

    Rust re-exports this from ``codex-app-server`` at the crate root. Python
    delegates to the existing exec/session port to keep one path policy.
    """

    from pycodex.exec.session import app_server_control_socket_path as _path_for_home

    return _path_for_home(codex_home)


def in_process_runtime_dependency_projection() -> InProcessRuntimeDependencyProjection:
    """Project Rust ``InProcessAppServerClient::start`` runtime handoff."""

    return InProcessRuntimeDependencyProjection(
        client_crate_module="codex-app-server-client/src/lib.rs",
        runtime_owner_crate="codex-app-server",
        runtime_owner_python_package="pycodex.app_server",
        rust_runtime_function="codex_app_server::run_app_server",
        python_runtime_entrypoint="pycodex.app_server.run_main_with_transport_options",
        runtime_package_exists=True,
        full_runtime_complete=False,
        client_should_fabricate_runtime=False,
    )


def in_process_worker_topology_projection(channel_capacity: int) -> InProcessWorkerTopologyProjection:
    """Project Rust ``InProcessAppServerClient::start`` worker topology."""

    return InProcessWorkerTopologyProjection(
        starts_runtime_handle=True,
        runtime_start_function="codex_app_server::in_process::start",
        request_sender_source="InProcessClientHandle::sender()",
        command_channel_type="mpsc::channel<ClientCommand>",
        event_channel_type="mpsc::channel<InProcessServerEvent>",
        channel_capacity=max(int(channel_capacity), 1),
        owns_command_sender=True,
        owns_event_receiver=True,
        owns_worker_handle=True,
        worker_initial_event_stream_enabled=True,
        worker_initial_skipped_events=0,
        select_arms=("command_rx.recv()", "handle.next_event()"),
        event_arm_guard="event_stream_enabled",
        returns_worker_backed_client=True,
    )


def in_process_worker_select_timing_projection(
    *,
    command_ready: bool,
    event_ready: bool,
    event_stream_enabled: bool = True,
) -> InProcessWorkerSelectTimingProjection:
    """Project the observable Rust worker ``tokio::select!`` ready-set contract."""

    event_arm_enabled = bool(event_stream_enabled)
    command_branch_ready = bool(command_ready)
    event_branch_ready = bool(event_ready) and event_arm_enabled
    ready_count = int(command_branch_ready) + int(event_branch_ready)

    if ready_count == 0:
        selected_branch = None
        awaits_progress = True
        selected_branch_is_deterministic = False
        simultaneous_ready_order_is_unspecified = False
        selection_guarantee = "worker awaits command_rx.recv() or an enabled handle.next_event()"
    elif ready_count == 1:
        selected_branch = "command_rx.recv()" if command_branch_ready else "handle.next_event()"
        awaits_progress = False
        selected_branch_is_deterministic = True
        simultaneous_ready_order_is_unspecified = False
        selection_guarantee = f"only {selected_branch} is ready"
    else:
        selected_branch = None
        awaits_progress = False
        selected_branch_is_deterministic = False
        simultaneous_ready_order_is_unspecified = True
        selection_guarantee = "unbiased tokio::select! does not promise stable branch order"

    return InProcessWorkerSelectTimingProjection(
        select_macro="tokio::select!",
        biased=False,
        command_ready=command_branch_ready,
        event_ready=bool(event_ready),
        event_stream_enabled=bool(event_stream_enabled),
        event_arm_enabled=event_arm_enabled,
        awaits_progress=awaits_progress,
        selected_branch=selected_branch,
        selected_branch_is_deterministic=selected_branch_is_deterministic,
        simultaneous_ready_order_is_unspecified=simultaneous_ready_order_is_unspecified,
        selection_guarantee=selection_guarantee,
        python_executes_scheduler=False,
    )


def in_process_command_channel_backpressure_projection(
    commands: Iterable[str],
    *,
    channel_capacity: int,
    initially_queued: int = 0,
    receiver_open: bool = True,
) -> InProcessCommandChannelBackpressureProjection:
    """Project Rust ``mpsc::Sender::send`` behavior for in-process commands."""

    capacity = max(int(channel_capacity), 1)
    queued = min(max(int(initially_queued), 0), capacity)
    command_names = tuple(str(command) for command in commands)
    if not receiver_open:
        return InProcessCommandChannelBackpressureProjection(
            command_channel_type="mpsc::channel<ClientCommand>",
            capacity=capacity,
            initially_queued=queued,
            receiver_open=False,
            commands_sent_without_wait=(),
            commands_waiting_for_capacity=(),
            send_waits_when_full=True,
            send_fails_only_when_receiver_closed=True,
            send_error_message="in-process app-server worker channel is closed",
            event_channel_type="mpsc::channel<InProcessServerEvent>",
            event_channel_bounded=True,
            event_channel_capacity=capacity,
            event_backpressure_handler="forward_in_process_event",
        )

    available_slots = max(capacity - queued, 0)
    return InProcessCommandChannelBackpressureProjection(
        command_channel_type="mpsc::channel<ClientCommand>",
        capacity=capacity,
        initially_queued=queued,
        receiver_open=True,
        commands_sent_without_wait=command_names[:available_slots],
        commands_waiting_for_capacity=command_names[available_slots:],
        send_waits_when_full=True,
        send_fails_only_when_receiver_closed=True,
        send_error_message=None,
        event_channel_type="mpsc::channel<InProcessServerEvent>",
        event_channel_bounded=True,
        event_channel_capacity=capacity,
        event_backpressure_handler="forward_in_process_event",
    )


def in_process_worker_command_projection(command_kind: str) -> InProcessWorkerCommandProjection:
    """Project the Rust worker ``ClientCommand`` match branch shape."""

    if command_kind == "Request":
        return InProcessWorkerCommandProjection(
            command_kind=command_kind,
            request_sender_method="request",
            clones_request_sender=True,
            uses_detached_task=True,
            sends_response=True,
            response_result_source="request_sender.request(*request).await",
            calls_handle_shutdown=False,
            breaks_worker_after_command=False,
        )
    if command_kind == "Notify":
        return InProcessWorkerCommandProjection(
            command_kind=command_kind,
            request_sender_method="notify",
            clones_request_sender=False,
            uses_detached_task=False,
            sends_response=True,
            response_result_source="request_sender.notify(notification)",
            calls_handle_shutdown=False,
            breaks_worker_after_command=False,
        )
    if command_kind == "ResolveServerRequest":
        return InProcessWorkerCommandProjection(
            command_kind=command_kind,
            request_sender_method="respond_to_server_request",
            clones_request_sender=False,
            uses_detached_task=False,
            sends_response=True,
            response_result_source="request_sender.respond_to_server_request(request_id, result)",
            calls_handle_shutdown=False,
            breaks_worker_after_command=False,
        )
    if command_kind == "RejectServerRequest":
        return InProcessWorkerCommandProjection(
            command_kind=command_kind,
            request_sender_method="fail_server_request",
            clones_request_sender=False,
            uses_detached_task=False,
            sends_response=True,
            response_result_source="request_sender.fail_server_request(request_id, error)",
            calls_handle_shutdown=False,
            breaks_worker_after_command=False,
        )
    if command_kind == "Shutdown":
        return InProcessWorkerCommandProjection(
            command_kind=command_kind,
            request_sender_method=None,
            clones_request_sender=False,
            uses_detached_task=False,
            sends_response=True,
            response_result_source="handle.shutdown().await",
            calls_handle_shutdown=True,
            breaks_worker_after_command=True,
        )
    if command_kind == "ChannelClosed":
        return InProcessWorkerCommandProjection(
            command_kind=command_kind,
            request_sender_method=None,
            clones_request_sender=False,
            uses_detached_task=False,
            sends_response=False,
            response_result_source=None,
            calls_handle_shutdown=True,
            breaks_worker_after_command=True,
            channel_closed_branch=True,
        )
    raise ValueError(f"unsupported in-process worker command `{command_kind}`")


def in_process_worker_event_projection(
    event: InProcessServerEvent | None,
    *,
    forward_result: ForwardEventResult = ForwardEventResult.CONTINUE,
) -> InProcessWorkerEventProjection:
    """Project the Rust worker ``handle.next_event()`` branch shape."""

    if event is None:
        return InProcessWorkerEventProjection(
            event_present=False,
            unsupported_auth_refresh=False,
            rejection_error=None,
            forwards_event=False,
            forward_result=None,
            disables_event_stream=False,
            breaks_worker=True,
            continues_worker=False,
        )

    rejection_error = None
    if event.kind == "ServerRequest":
        rejection_error = in_process_unsupported_server_request_error(event.payload)
    if rejection_error is not None:
        return InProcessWorkerEventProjection(
            event_present=True,
            unsupported_auth_refresh=True,
            rejection_error=rejection_error,
            forwards_event=False,
            forward_result=None,
            disables_event_stream=False,
            breaks_worker=False,
            continues_worker=True,
        )

    if not isinstance(forward_result, ForwardEventResult):
        raise TypeError("forward_result must be a ForwardEventResult")
    return InProcessWorkerEventProjection(
        event_present=True,
        unsupported_auth_refresh=False,
        rejection_error=None,
        forwards_event=True,
        forward_result=forward_result,
        disables_event_stream=forward_result is ForwardEventResult.DISABLE_STREAM,
        breaks_worker=False,
        continues_worker=True,
    )


def in_process_command_entrypoint_projection(operation: str) -> InProcessCommandEntrypointProjection:
    """Project Rust request/notify/resolve/reject command entrypoint errors."""

    try:
        command_kind, response_channel_name = {
            "request": ("Request", "request"),
            "notify": ("Notify", "notify"),
            "resolve": ("ResolveServerRequest", "resolve"),
            "reject": ("RejectServerRequest", "reject"),
        }[operation]
    except KeyError as exc:
        raise ValueError(f"unsupported in-process command entrypoint `{operation}`") from exc
    return InProcessCommandEntrypointProjection(
        operation=operation,
        command_kind=command_kind,
        has_response_oneshot=True,
        worker_send_error_kind="BrokenPipe",
        worker_send_error_message="in-process app-server worker channel is closed",
        response_closed_error_kind="BrokenPipe",
        response_closed_error_message=(
            f"in-process app-server {response_channel_name} channel is closed"
        ),
    )


def in_process_request_response_projection() -> InProcessRequestResponseProjection:
    """Project Rust ``InProcessAppServerClient::request`` response flow."""

    return InProcessRequestResponseProjection(
        command_kind="ClientCommand::Request",
        boxes_request=True,
        creates_response_oneshot=True,
        sends_on_worker_channel=True,
        awaits_response_oneshot=True,
        returns_raw_request_result=True,
        worker_send_error_kind="BrokenPipe",
        worker_send_error_message="in-process app-server worker channel is closed",
        response_closed_error_kind="BrokenPipe",
        response_closed_error_message="in-process app-server request channel is closed",
        typed_wrapper_maps_transport=True,
        typed_wrapper_maps_server_error=True,
        typed_wrapper_maps_deserialize_error=True,
    )


def in_process_worker_request_task_projection() -> InProcessWorkerRequestTaskProjection:
    """Project Rust worker's detached request task and response delivery."""

    return InProcessWorkerRequestTaskProjection(
        command_kind="ClientCommand::Request",
        spawned_from_worker_branch=True,
        clones_request_sender=True,
        moves_boxed_request_into_task=True,
        awaits_runtime_request=True,
        runtime_result_expression="request_sender.request(*request).await",
        sends_result_to_response_oneshot=True,
        ignores_response_receiver_dropped=True,
        worker_loop_keeps_draining_events_while_request_waits=True,
        fabricates_message_processor_result=False,
    )


def in_process_request_handle_projection() -> InProcessRequestHandleProjection:
    """Project Rust ``InProcessAppServerClient::request_handle`` behavior."""

    return InProcessRequestHandleProjection(
        factory_method="InProcessAppServerClient::request_handle",
        clones_command_sender=True,
        handle_request_command_kind="ClientCommand::Request",
        handle_request_boxes_request=True,
        handle_request_uses_response_oneshot=True,
        handle_typed_uses_request_method_name=True,
        handle_typed_wraps_transport_error=True,
        handle_typed_wraps_server_error=True,
        handle_typed_wraps_deserialize_error=True,
    )


def in_process_next_event_projection() -> InProcessNextEventProjection:
    """Project Rust ``InProcessAppServerClient::next_event`` behavior."""

    return InProcessNextEventProjection(
        event_receiver_source="self.event_rx.recv().await",
        requires_mutable_client=True,
        awaits_receiver_recv=True,
        returns_option=True,
        closed_receiver_returns_none=True,
        preserves_in_process_event=True,
        converts_to_app_server_event=False,
    )


def in_process_shutdown_entrypoint_projection() -> InProcessShutdownEntrypointProjection:
    """Project Rust ``InProcessAppServerClient::shutdown`` command entrypoint."""

    return InProcessShutdownEntrypointProjection(
        consumes_client=True,
        destructures_command_sender=True,
        destructures_event_receiver=True,
        destructures_worker_handle=True,
        drop_event_receiver_before_shutdown_command=True,
        command_kind="ClientCommand::Shutdown",
        has_response_oneshot=True,
        ignores_worker_send_error=True,
        ignores_response_timeout=True,
        propagates_in_time_command_result=True,
        response_closed_error_kind="BrokenPipe",
        response_closed_error_message="in-process app-server shutdown channel is closed",
    )


class AppServerEventKind(Enum):
    LAGGED = "Lagged"
    SERVER_NOTIFICATION = "ServerNotification"
    SERVER_REQUEST = "ServerRequest"
    DISCONNECTED = "Disconnected"


@dataclass(frozen=True)
class AppServerEvent:
    """Python boundary for Rust ``AppServerEvent``."""

    kind: AppServerEventKind
    payload: Any = None
    skipped: int | None = None
    message: str | None = None

    @classmethod
    def lagged(cls, skipped: int) -> "AppServerEvent":
        return cls(AppServerEventKind.LAGGED, skipped=skipped)

    @classmethod
    def server_notification(cls, notification: Any) -> "AppServerEvent":
        return cls(AppServerEventKind.SERVER_NOTIFICATION, payload=notification)

    @classmethod
    def server_request(cls, request: Any) -> "AppServerEvent":
        return cls(AppServerEventKind.SERVER_REQUEST, payload=request)

    @classmethod
    def disconnected(cls, message: str) -> "AppServerEvent":
        return cls(AppServerEventKind.DISCONNECTED, message=message)

    @classmethod
    def from_in_process(cls, event: InProcessServerEvent) -> "AppServerEvent":
        if event.kind == "Lagged":
            return cls.lagged(event.skipped or 0)
        if event.kind == "ServerNotification":
            return cls.server_notification(event.payload)
        if event.kind == "ServerRequest":
            return cls.server_request(event.payload)
        raise ValueError(f"unknown InProcessServerEvent kind: {event.kind}")


@dataclass
class InProcessClientStartArgs:
    """Python boundary for Rust ``InProcessClientStartArgs``."""

    arg0_paths: Any
    config: Any
    cli_overrides: list[tuple[str, Any]] = field(default_factory=list)
    loader_overrides: Any = None
    strict_config: bool = False
    cloud_requirements: Any = None
    feedback: Any = None
    log_db: Any = None
    state_db: StateDbHandle | None = None
    environment_manager: EnvironmentManager | Any = None
    config_warnings: list[Any] = field(default_factory=list)
    session_source: Any = None
    enable_codex_api_key_env: bool = False
    client_name: str = "pycodex"
    client_version: str = "0"
    experimental_api: bool = False
    opt_out_notification_methods: list[str] = field(default_factory=list)
    channel_capacity: int = DEFAULT_IN_PROCESS_CHANNEL_CAPACITY

    def initialize_params(self) -> dict[str, Any]:
        return {
            "client_info": {"name": self.client_name, "title": None, "version": self.client_version},
            "capabilities": {
                "experimental_api": self.experimental_api,
                "request_attestation": False,
                "opt_out_notification_methods": list(self.opt_out_notification_methods) or None,
            },
        }

    def into_runtime_start_args(self) -> InProcessRuntimeStartArgs:
        thread_config_loader = _configured_thread_config_loader(self.config)
        return InProcessRuntimeStartArgs(
            arg0_paths=self.arg0_paths,
            config=self.config,
            cli_overrides=list(self.cli_overrides),
            loader_overrides=self.loader_overrides,
            strict_config=self.strict_config,
            cloud_requirements=self.cloud_requirements,
            feedback=self.feedback,
            log_db=self.log_db,
            state_db=self.state_db,
            environment_manager=self.environment_manager,
            config_warnings=list(self.config_warnings),
            session_source=self.session_source,
            enable_codex_api_key_env=self.enable_codex_api_key_env,
            initialize_params=self.initialize_params(),
            thread_config_loader=thread_config_loader,
            channel_capacity=self.channel_capacity,
        )

    def effective_channel_capacity(self) -> int:
        """Mirror Rust start-layer ``channel_capacity.max(1)``."""

        return max(self.channel_capacity, 1)


def into_app_server_in_process_start_args(args: InProcessClientStartArgs) -> Any:
    """Convert client start args into the app-server-owned start args shape."""

    from pycodex.app_server.in_process import InProcessStartArgs

    runtime_args = args.into_runtime_start_args()
    return InProcessStartArgs(
        arg0_paths=runtime_args.arg0_paths,
        config=runtime_args.config,
        cli_overrides=tuple(runtime_args.cli_overrides),
        loader_overrides=runtime_args.loader_overrides,
        strict_config=runtime_args.strict_config,
        cloud_requirements=runtime_args.cloud_requirements,
        thread_config_loader=runtime_args.thread_config_loader,
        feedback=runtime_args.feedback,
        log_db=runtime_args.log_db,
        state_db=runtime_args.state_db,
        environment_manager=runtime_args.environment_manager,
        config_warnings=tuple(runtime_args.config_warnings),
        session_source=runtime_args.session_source,
        enable_codex_api_key_env=runtime_args.enable_codex_api_key_env,
        initialize=runtime_args.initialize_params,
        channel_capacity=runtime_args.channel_capacity,
    )


def _configured_thread_config_loader(config: Any) -> Any:
    from pycodex.config import NoopThreadConfigLoader, RemoteThreadConfigLoader

    endpoint = getattr(config, "experimental_thread_config_endpoint", None)
    if endpoint is None and isinstance(config, dict):
        endpoint = config.get("experimental_thread_config_endpoint")
    if endpoint is not None:
        return RemoteThreadConfigLoader.new(str(endpoint))
    return NoopThreadConfigLoader()


class InProcessAppServerRequestHandle:
    """Python boundary for Rust ``InProcessAppServerRequestHandle``."""

    def __init__(self, client: "InProcessAppServerClient | None" = None) -> None:
        self._client = client

    async def request(self, request: Any) -> RequestResult:
        if self._client is None:
            raise AppServerClientNotImplementedError("InProcessAppServerRequestHandle.request is not ported yet")
        return await self._client.request(request)

    async def request_typed(self, request: Any, decoder: Callable[[Any], Any] | None = None) -> Any:
        if self._client is None:
            raise AppServerClientNotImplementedError("InProcessAppServerRequestHandle.request_typed is not ported yet")
        return await self._client.request_typed(request, decoder=decoder)


class InProcessAppServerClient:
    """Python boundary for Rust ``InProcessAppServerClient``."""

    def __init__(
        self,
        *,
        request_handler: RequestHandler | None = None,
        notification_handler: NotificationHandler | None = None,
        events: list[InProcessServerEvent] | None = None,
        runtime_start_args: InProcessRuntimeStartArgs | None = None,
        channel_capacity: int | None = None,
        runtime_connected: bool = True,
        runtime_projection: Any = None,
    ) -> None:
        self._request_handler = request_handler
        self._notification_handler = notification_handler
        self._events = deque(events or [])
        self._runtime_start_args = runtime_start_args
        self._channel_capacity = channel_capacity
        self._runtime_connected = runtime_connected
        self._runtime_projection = runtime_projection
        self._server_request_results: dict[Any, Any] = {}
        self._server_request_errors: dict[Any, Any] = {}
        self._shutdown = False

    @classmethod
    async def start(cls, args: InProcessClientStartArgs) -> "InProcessAppServerClient":
        from pycodex.app_server.in_process import InProcessRuntimeProjection

        app_server_args = into_app_server_in_process_start_args(args)
        return cls(
            runtime_start_args=args.into_runtime_start_args(),
            channel_capacity=args.effective_channel_capacity(),
            runtime_connected=True,
            runtime_projection=InProcessRuntimeProjection.from_start_args(app_server_args),
        )

    @property
    def runtime_start_args(self) -> InProcessRuntimeStartArgs | None:
        return self._runtime_start_args

    @property
    def channel_capacity(self) -> int | None:
        return self._channel_capacity

    def request_handle(self) -> InProcessAppServerRequestHandle:
        return InProcessAppServerRequestHandle(self)

    async def request(self, request: Any) -> RequestResult:
        self._ensure_running("request")
        if self._request_handler is None:
            if self._runtime_projection is not None:
                outcome = self._runtime_projection.handle_client_request(request)
                if outcome.immediate_error is not None:
                    return outcome.immediate_error
                return JSONRPCErrorError(
                    code=-32000,
                    message=(
                        "in-process app-server request response is pending in the "
                        "Python runtime projection"
                    ),
                    data={"requestId": repr(outcome.request_id)},
                )
            raise AppServerClientNotImplementedError("InProcessAppServerClient.request is not ported yet")
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
        if self._notification_handler is None:
            if self._runtime_projection is not None:
                self._runtime_projection.handle_client_notification(notification)
                return None
            if not self._runtime_connected:
                raise AppServerClientNotImplementedError("InProcessAppServerClient.notify is not ported yet")
            return None
        await _maybe_await(self._notification_handler(notification))
        return None

    async def resolve_server_request(self, request_id: Any, result: Any) -> None:
        self._ensure_running("resolve_server_request")
        if not self._runtime_connected:
            raise AppServerClientNotImplementedError(
                "InProcessAppServerClient.resolve_server_request is not ported yet"
            )
        if self._runtime_projection is not None:
            from pycodex.app_server.in_process import InProcessClientMessage

            self._runtime_projection.handle_client_notification(
                InProcessClientMessage.server_request_response(request_id, result)
            )
        self._server_request_results[request_id] = result

    async def reject_server_request(self, request_id: Any, error: Any) -> None:
        self._ensure_running("reject_server_request")
        if not self._runtime_connected:
            raise AppServerClientNotImplementedError(
                "InProcessAppServerClient.reject_server_request is not ported yet"
            )
        if self._runtime_projection is not None:
            from pycodex.app_server.in_process import InProcessClientMessage

            self._runtime_projection.handle_client_notification(
                InProcessClientMessage.server_request_error(request_id, error)
            )
        self._server_request_errors[request_id] = error

    async def next_event(self) -> InProcessServerEvent | None:
        self._ensure_running("next_event")
        if not self._events:
            return None
        return self._events.popleft()

    async def shutdown(self) -> None:
        self._shutdown = True
        self._events.clear()
        return None

    def push_event(self, event: InProcessServerEvent) -> None:
        self._ensure_running("push_event")
        if not self._runtime_connected:
            raise AppServerClientNotImplementedError(
                "InProcessAppServerClient.push_event is not ported yet"
            )
        if event.kind == "ServerRequest":
            rejection = in_process_unsupported_server_request_error(event.payload)
            request_id = _server_request_id(event.payload)
            if rejection is not None and request_id is not None:
                self._server_request_errors[request_id] = rejection
                return
            if self._runtime_projection is not None:
                accepted = self._runtime_projection.handle_server_request_event(
                    event.payload,
                    event_queue_full=len(self._events) >= max(self._channel_capacity or 1, 1),
                )
                self._server_request_errors.update(
                    {
                        key.to_json() if hasattr(key, "to_json") else key: value
                        for key, value in self._runtime_projection.server_request_errors.items()
                    }
                )
                if not accepted:
                    return
        self._events.append(event)

    def resolved_server_requests(self) -> dict[Any, Any]:
        return dict(self._server_request_results)

    def rejected_server_requests(self) -> dict[Any, Any]:
        return dict(self._server_request_errors)

    def _ensure_running(self, operation: str) -> None:
        if self._shutdown:
            channel = {
                "resolve_server_request": "resolve",
                "reject_server_request": "reject",
            }.get(operation, operation)
            raise BrokenPipeError(f"in-process app-server {channel} channel is closed")


def in_process_shutdown_projection(
    *,
    command_send_ok: bool,
    response_within_timeout: bool,
    worker_exits_within_timeout: bool,
) -> InProcessShutdownProjection:
    """Project Rust shutdown timeout and abort-fallback behavior."""

    return InProcessShutdownProjection(
        drop_event_receiver_before_shutdown_command=True,
        send_shutdown_command=True,
        await_response_timeout_seconds=SHUTDOWN_TIMEOUT_SECONDS,
        return_command_result=bool(command_send_ok and response_within_timeout),
        drop_command_sender_before_worker_wait=True,
        await_worker_timeout_seconds=SHUTDOWN_TIMEOUT_SECONDS,
        abort_worker_on_timeout=not bool(worker_exits_within_timeout),
    )


@dataclass(frozen=True)
class AppServerRequestHandle:
    """Python boundary for Rust ``AppServerRequestHandle``."""

    inner: InProcessAppServerRequestHandle | RemoteAppServerRequestHandle

    async def request(self, request: Any) -> RequestResult:
        return await self.inner.request(request)

    async def request_typed(self, request: Any, decoder: Callable[[Any], Any] | None = None) -> Any:
        return await self.inner.request_typed(request, decoder=decoder)


@dataclass(frozen=True)
class AppServerClient:
    """Python boundary for Rust ``AppServerClient``."""

    inner: InProcessAppServerClient | RemoteAppServerClient

    def request_handle(self) -> AppServerRequestHandle:
        return AppServerRequestHandle(self.inner.request_handle())

    async def request(self, request: Any) -> RequestResult:
        return await self.inner.request(request)

    async def request_typed(self, request: Any, decoder: Callable[[Any], Any] | None = None) -> Any:
        return await self.inner.request_typed(request, decoder=decoder)

    async def notify(self, notification: Any) -> None:
        return await self.inner.notify(notification)

    async def resolve_server_request(self, request_id: Any, result: Any) -> None:
        return await self.inner.resolve_server_request(request_id, result)

    async def reject_server_request(self, request_id: Any, error: Any) -> None:
        return await self.inner.reject_server_request(request_id, error)

    async def next_event(self) -> AppServerEvent | None:
        event = await self.inner.next_event()
        if isinstance(event, InProcessServerEvent):
            return AppServerEvent.from_in_process(event)
        return event

    async def shutdown(self) -> None:
        return await self.inner.shutdown()


def request_method_name(request: Any) -> str:
    """Return the Rust ``ClientRequest`` JSON-RPC method name for diagnostics."""

    if isinstance(request, ClientRequest):
        try:
            return request.method()
        except ValueError:
            return request.type
    method = getattr(request, "method", None)
    if callable(method):
        return method()
    request_type = getattr(request, "type", None)
    if isinstance(request_type, str):
        return request_type
    if isinstance(request, dict):
        if isinstance(request.get("method"), str):
            return request["method"]
        if isinstance(request.get("type"), str):
            return request["type"]
    return "<unknown>"


def server_notification_requires_delivery(notification: Any) -> bool:
    """Mirror Rust's lossless tier for transcript and completion notifications."""

    notification_type = getattr(notification, "type", None)
    if isinstance(notification_type, str):
        return notification_type in LOSSLESS_SERVER_NOTIFICATION_TYPES
    if isinstance(notification, dict):
        for key in ("type", "variant", "kind"):
            value = notification.get(key)
            if isinstance(value, str):
                return value in LOSSLESS_SERVER_NOTIFICATION_TYPES
    return type(notification).__name__.removesuffix("Notification") in LOSSLESS_SERVER_NOTIFICATION_TYPES


def event_requires_delivery(event: InProcessServerEvent) -> bool:
    if event.kind != "ServerNotification":
        return False
    return server_notification_requires_delivery(event.payload)


def project_in_process_event_forwarding(
    initial_events: list[InProcessServerEvent],
    incoming_events: list[InProcessServerEvent],
    *,
    capacity: int,
    consumer_open: bool = True,
    initial_skipped_events: int = 0,
) -> InProcessEventForwardProjection:
    """Project Rust ``forward_in_process_event`` ordering without Tokio.

    This keeps the observable lossless ordering contract for tests and status
    checks. It does not claim exact async wakeup or bounded-channel timing.
    """

    capacity = max(capacity, 1)
    delivered = list(initial_events)
    skipped_events = max(initial_skipped_events, 0)
    rejected_server_requests: dict[Any, JSONRPCErrorError] = {}

    for event in incoming_events:
        if not consumer_open:
            return InProcessEventForwardProjection(
                events=delivered,
                skipped_events=skipped_events,
                rejected_server_requests=rejected_server_requests,
                result=ForwardEventResult.DISABLE_STREAM,
                stream_enabled=False,
            )
        is_lossless = event_requires_delivery(event)
        is_full = len(delivered) >= capacity
        if is_lossless:
            if skipped_events:
                delivered.append(InProcessServerEvent.lagged(skipped_events))
                skipped_events = 0
            delivered.append(event)
            continue
        if is_full:
            skipped_events += 1
            if event.kind == "ServerRequest":
                request_id = _server_request_id(event.payload)
                if request_id is not None:
                    rejected_server_requests[request_id] = JSONRPCErrorError(
                        code=-32001,
                        message="in-process app-server event queue is full",
                    )
            continue
        if skipped_events:
            delivered.append(InProcessServerEvent.lagged(skipped_events))
            skipped_events = 0
        delivered.append(event)

    return InProcessEventForwardProjection(
        events=delivered,
        skipped_events=skipped_events,
        rejected_server_requests=rejected_server_requests,
        result=ForwardEventResult.CONTINUE,
        stream_enabled=True,
    )


def in_process_unsupported_server_request_error(request: Any) -> JSONRPCErrorError | None:
    """Return Rust's rejection for server requests unsupported in-process."""

    request_type = getattr(request, "type", None)
    method = None
    method_attr = getattr(request, "method", None)
    if callable(method_attr):
        try:
            method = method_attr()
        except Exception:
            method = None
    if isinstance(request, dict):
        request_type = request.get("type", request_type)
        method = request.get("method", method)
    if request_type == "ChatgptAuthTokensRefresh" or method == "account/chatgptAuthTokens/refresh":
        return JSONRPCErrorError(
            code=-32000,
            message="chatgpt auth token refresh is not supported for in-process app-server clients",
            data=None,
        )
    return None


def _server_request_id(request: Any) -> Any:
    if isinstance(request, ServerRequest):
        return request.request_id
    if isinstance(request, dict):
        return request.get("id", request.get("request_id"))
    value = getattr(request, "request_id", None)
    if value is not None:
        return value
    request_id = getattr(request, "id", None)
    if callable(request_id):
        return request_id()
    return request_id


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


from .remote import (
    RemoteAppServerClient,
    RemoteAppServerConnectArgs,
    RemoteAppServerEndpoint,
    RemoteAppServerEndpointKind,
    RemoteAppServerRequestHandle,
    RemoteChannelTopologyProjection,
    RemoteClientCommandProjection,
    RemoteCommandChannelBackpressureProjection,
    RemoteCommandEntrypointProjection,
    RemoteConnectDispatchProjection,
    RemoteConnectEndpointProjection,
    RemoteConnectWithStreamProjection,
    RemoteEventDeliveryProjection,
    RemoteInitializeFrameProjection,
    RemoteInitializeHandshakeProjection,
    RemoteNextEventProjection,
    RemoteRequestHandleProjection,
    RemoteWriteJsonrpcMessageProjection,
    RemoteWorkerCommandChannelClosedProjection,
    RemoteWorkerCommandProjection,
    RemoteWorkerExitProjection,
    RemoteWorkerSelectLoopProjection,
    RemoteWorkerSelectTimingProjection,
    RemoteWorkerStreamMessageProjection,
    RemoteWorkerTimingBoundaryProjection,
    RemoteShutdownProjection,
    REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
    REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS,
    REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    UDS_WEBSOCKET_HANDSHAKE_URL,
    jsonrpc_notification_from_client_notification,
    jsonrpc_request_from_client_request,
    remote_app_server_event_from_notification,
    remote_channel_topology_projection,
    remote_command_channel_backpressure_projection,
    remote_command_entrypoint_projection,
    remote_connect_dispatch_projection,
    remote_connect_endpoint_projection,
    remote_connect_with_stream_projection,
    remote_deliver_event_projection,
    remote_duplicate_request_id_error_message,
    remote_initialize_close_frame_error_message,
    remote_initialize_error_message,
    remote_initialize_frame_projection,
    remote_initialize_handshake_projection,
    remote_jsonrpc_projection_panic_message,
    remote_next_event_projection,
    remote_request_handle_projection,
    remote_runtime_close_frame_disconnected_message,
    remote_runtime_eof_disconnected_message,
    remote_runtime_invalid_jsonrpc_disconnected_message,
    remote_runtime_transport_failure_disconnected_message,
    remote_shutdown_close_failed_error_message,
    remote_shutdown_projection,
    remote_unix_socket_connect_error_message,
    remote_unsupported_server_request_error_message,
    remote_websocket_connect_error_message,
    remote_websocket_close_error_is_already_closed,
    remote_websocket_config,
    remote_worker_command_channel_closed_projection,
    remote_worker_command_projection,
    remote_worker_exit_pending_requests_projection,
    remote_worker_select_loop_projection,
    remote_worker_select_timing_projection,
    remote_worker_stream_message_projection,
    remote_worker_timing_boundary_projection,
    remote_write_failed_disconnected_message,
    remote_write_jsonrpc_message_projection,
    remote_server_version_from_user_agent,
    request_id_from_client_request,
    websocket_url_supports_auth_token,
)

__all__ = [
    "AppServerClient",
    "AppServerClientNotImplementedError",
    "AppServerEvent",
    "AppServerEventKind",
    "AppServerRequestHandle",
    "DEFAULT_IN_PROCESS_CHANNEL_CAPACITY",
    "EnvironmentManager",
    "ExecServerRuntimePaths",
    "ForwardEventResult",
    "InProcessCommandChannelBackpressureProjection",
    "InProcessCommandEntrypointProjection",
    "InProcessRequestHandleProjection",
    "InProcessNextEventProjection",
    "InProcessAppServerClient",
    "InProcessAppServerRequestHandle",
    "InProcessClientStartArgs",
    "InProcessClientCommandProjection",
    "InProcessEventForwardProjection",
    "InProcessRuntimeDependencyProjection",
    "InProcessRuntimeStartArgs",
    "InProcessRequestResponseProjection",
    "InProcessWorkerRequestTaskProjection",
    "InProcessShutdownEntrypointProjection",
    "InProcessShutdownProjection",
    "InProcessServerEvent",
    "InProcessWorkerCommandProjection",
    "InProcessWorkerEventProjection",
    "InProcessWorkerSelectTimingProjection",
    "InProcessWorkerTopologyProjection",
    "RemoteAppServerClient",
    "RemoteAppServerConnectArgs",
    "RemoteAppServerEndpoint",
    "RemoteAppServerEndpointKind",
    "RemoteAppServerRequestHandle",
    "RemoteChannelTopologyProjection",
    "RemoteClientCommandProjection",
    "RemoteCommandChannelBackpressureProjection",
    "RemoteCommandEntrypointProjection",
    "RemoteConnectDispatchProjection",
    "RemoteConnectEndpointProjection",
    "RemoteConnectWithStreamProjection",
    "RemoteEventDeliveryProjection",
    "RemoteInitializeFrameProjection",
    "RemoteInitializeHandshakeProjection",
    "RemoteNextEventProjection",
    "RemoteRequestHandleProjection",
    "RemoteWriteJsonrpcMessageProjection",
    "RemoteWorkerCommandChannelClosedProjection",
    "RemoteWorkerCommandProjection",
    "RemoteWorkerExitProjection",
    "RemoteWorkerSelectLoopProjection",
    "RemoteWorkerSelectTimingProjection",
    "RemoteWorkerStreamMessageProjection",
    "RemoteWorkerTimingBoundaryProjection",
    "RemoteShutdownProjection",
    "REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS",
    "REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS",
    "REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE",
    "RequestResult",
    "SHUTDOWN_TIMEOUT_SECONDS",
    "StateDbHandle",
    "TypedRequestError",
    "UDS_WEBSOCKET_HANDSHAKE_URL",
    "app_server_control_socket_path",
    "event_requires_delivery",
    "in_process_command_channel_backpressure_projection",
    "in_process_command_entrypoint_projection",
    "in_process_next_event_projection",
    "in_process_request_response_projection",
    "in_process_worker_request_task_projection",
    "in_process_request_handle_projection",
    "in_process_runtime_dependency_projection",
    "in_process_shutdown_entrypoint_projection",
    "in_process_shutdown_projection",
    "in_process_unsupported_server_request_error",
    "in_process_worker_command_projection",
    "in_process_worker_event_projection",
    "in_process_worker_select_timing_projection",
    "in_process_worker_topology_projection",
    "into_app_server_in_process_start_args",
    "jsonrpc_notification_from_client_notification",
    "jsonrpc_request_from_client_request",
    "legacy_core",
    "project_in_process_event_forwarding",
    "remote_app_server_event_from_notification",
    "remote_channel_topology_projection",
    "remote_command_channel_backpressure_projection",
    "remote_command_entrypoint_projection",
    "remote_connect_dispatch_projection",
    "remote_connect_endpoint_projection",
    "remote_connect_with_stream_projection",
    "remote_deliver_event_projection",
    "remote_duplicate_request_id_error_message",
    "remote_initialize_close_frame_error_message",
    "remote_initialize_error_message",
    "remote_initialize_frame_projection",
    "remote_initialize_handshake_projection",
    "remote_jsonrpc_projection_panic_message",
    "remote_next_event_projection",
    "remote_request_handle_projection",
    "remote_runtime_close_frame_disconnected_message",
    "remote_runtime_eof_disconnected_message",
    "remote_runtime_invalid_jsonrpc_disconnected_message",
    "remote_runtime_transport_failure_disconnected_message",
    "remote_shutdown_close_failed_error_message",
    "remote_shutdown_projection",
    "remote_unix_socket_connect_error_message",
    "remote_unsupported_server_request_error_message",
    "remote_websocket_connect_error_message",
    "remote_websocket_close_error_is_already_closed",
    "remote_websocket_config",
    "remote_worker_command_channel_closed_projection",
    "remote_worker_command_projection",
    "remote_worker_exit_pending_requests_projection",
    "remote_worker_select_loop_projection",
    "remote_worker_select_timing_projection",
    "remote_worker_stream_message_projection",
    "remote_worker_timing_boundary_projection",
    "remote_write_failed_disconnected_message",
    "remote_write_jsonrpc_message_projection",
    "remote_server_version_from_user_agent",
    "request_id_from_client_request",
    "request_method_name",
    "server_notification_requires_delivery",
    "websocket_url_supports_auth_token",
]
