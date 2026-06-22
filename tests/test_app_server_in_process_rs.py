from __future__ import annotations

import pytest

from pycodex.app_server.error_code import (
    INTERNAL_ERROR_CODE,
    INVALID_REQUEST_ERROR_CODE,
    OVERLOADED_ERROR_CODE,
    internal_error,
)
from pycodex.app_server.in_process import (
    DEFAULT_IN_PROCESS_CHANNEL_CAPACITY,
    SHUTDOWN_TIMEOUT_SECONDS,
    BoundedInProcessQueue,
    InProcessClientMessage,
    InProcessClientSender,
    InProcessIoError,
    InProcessIoErrorKind,
    InProcessRuntimeProjection,
    InProcessStartArgs,
    route_notifications_with_backpressure,
    server_notification_requires_delivery,
    start_projection,
)


def test_in_process_start_initializes_and_handles_typed_v2_request_projection() -> None:
    # Rust test: in_process_start_initializes_and_handles_typed_v2_request.
    # The Python module keeps the local start handshake contract without
    # starting MessageProcessor/Tokio runtime dependencies.
    projection = start_projection()

    assert projection.initialize_request_id.to_json() == 0
    assert projection.sends_initialized_notification
    assert projection.shuts_down_on_initialize_error
    assert projection.initialize_error_kind is InProcessIoErrorKind.INVALID_DATA
    assert projection.initialize_error_prefix == "in-process initialize failed:"


def test_in_process_start_uses_requested_session_source_for_thread_start_projection() -> None:
    # Rust test: in_process_start_uses_requested_session_source_for_thread_start.
    # Session source is stored in InProcessStartArgs and forwarded into
    # MessageProcessorArgs by the runtime startup branch.
    cli = InProcessStartArgs(session_source="cli")
    exec_ = InProcessStartArgs(session_source="exec")

    assert cli.session_source == "cli"
    assert exec_.session_source == "exec"


def test_in_process_start_clamps_zero_channel_capacity() -> None:
    # Rust test: in_process_start_clamps_zero_channel_capacity.
    args = InProcessStartArgs(channel_capacity=0)

    assert args.effective_channel_capacity() == 1
    assert InProcessRuntimeProjection.from_start_args(args).channel_capacity == 1
    assert InProcessStartArgs(channel_capacity=3).effective_channel_capacity() == 3


def test_guaranteed_delivery_helpers_cover_terminal_server_notifications() -> None:
    # Rust test: guaranteed_delivery_helpers_cover_terminal_server_notifications.
    assert server_notification_requires_delivery({"type": "TurnCompleted"})
    assert server_notification_requires_delivery({"type": "ThreadSettingsUpdated"})
    assert not server_notification_requires_delivery({"type": "Warning"})

    delivered, dropped = route_notifications_with_backpressure(
        (
            {"type": "Warning", "message": "drop under saturation"},
            {"type": "TurnCompleted", "turn": {}},
            {"type": "ThreadSettingsUpdated", "settings": {}},
        ),
        event_queue_full=True,
    )
    assert [item["type"] for item in delivered] == ["TurnCompleted", "ThreadSettingsUpdated"]
    assert dropped == 1


def test_client_sender_try_send_maps_full_and_closed_queue_errors() -> None:
    # Rust source contract: InProcessClientSender::try_send_client_message maps
    # full queues to WouldBlock and closed queues to BrokenPipe.
    queue = BoundedInProcessQueue(capacity=1)
    sender = InProcessClientSender(queue)

    sender.notify({"type": "Initialized"})
    with pytest.raises(InProcessIoError) as full:
        sender.notify({"type": "Initialized"})
    assert full.value.kind is InProcessIoErrorKind.WOULD_BLOCK
    assert str(full.value) == "in-process app-server client queue is full"

    queue.close()
    with pytest.raises(InProcessIoError) as closed:
        sender.respond_to_server_request(1, {"ok": True})
    assert closed.value.kind is InProcessIoErrorKind.BROKEN_PIPE
    assert str(closed.value) == "in-process app-server runtime is closed"


def test_client_message_shapes_match_rust_variants() -> None:
    # Rust enum: InProcessClientMessage variants carry request, notification,
    # server-request response/error, and shutdown payloads.
    request = InProcessClientMessage.request({"id": 1})
    notification = InProcessClientMessage.notification({"type": "Initialized"})
    response = InProcessClientMessage.server_request_response(2, {"answer": "yes"})
    error = InProcessClientMessage.server_request_error(3, internal_error("failed"))
    shutdown = InProcessClientMessage.shutdown()

    assert request.kind == "Request"
    assert notification.kind == "Notification"
    assert response.kind == "ServerRequestResponse"
    assert response.request_id.to_json() == 2
    assert error.kind == "ServerRequestError"
    assert shutdown.kind == "Shutdown"


def test_runtime_projection_rejects_duplicate_request_id() -> None:
    # Rust select-loop branch: duplicate in-flight request IDs return
    # INVALID_REQUEST without replacing the original pending response sender.
    runtime = InProcessRuntimeProjection(channel_capacity=2)

    first = runtime.handle_client_request({"id": 7})
    duplicate = runtime.handle_client_request({"id": 7})

    assert first.accepted
    assert duplicate.immediate_error is not None
    assert duplicate.immediate_error.code == INVALID_REQUEST_ERROR_CODE
    assert duplicate.immediate_error.message == "duplicate request id: RequestId(value=7)"
    assert len(runtime.pending_request_responses) == 1


def test_runtime_projection_maps_full_and_closed_processor_request_queue() -> None:
    # Rust select-loop branch: full processor queue returns OVERLOADED, while a
    # closed processor returns INTERNAL_ERROR and exits the runtime loop.
    full_runtime = InProcessRuntimeProjection(channel_capacity=1, processor_queue_size=1)
    full = full_runtime.handle_client_request({"id": 8})
    assert not full.accepted
    assert full.immediate_error is not None
    assert full.immediate_error.code == OVERLOADED_ERROR_CODE
    assert full.immediate_error.message == "in-process app-server request queue is full"
    assert not full_runtime.pending_request_responses

    closed_runtime = InProcessRuntimeProjection(channel_capacity=1, processor_closed=True)
    closed = closed_runtime.handle_client_request({"id": 9})
    assert closed.breaks_runtime
    assert closed.immediate_error is not None
    assert closed.immediate_error.code == INTERNAL_ERROR_CODE
    assert closed.immediate_error.message == "in-process app-server request processor is closed"


def test_runtime_projection_handles_server_request_backpressure() -> None:
    # Rust writer branch: server requests are never silently dropped; queue
    # saturation or closure is reported back to the outgoing request waiter.
    runtime = InProcessRuntimeProjection(channel_capacity=1)

    assert not runtime.handle_server_request_event({"id": 10}, event_queue_full=True)
    assert runtime.server_request_errors[next(iter(runtime.server_request_errors))].code == OVERLOADED_ERROR_CODE

    closed_runtime = InProcessRuntimeProjection(channel_capacity=1)
    assert not closed_runtime.handle_server_request_event({"id": 11}, event_queue_full=False, event_queue_closed=True)
    error = closed_runtime.server_request_errors[next(iter(closed_runtime.server_request_errors))]
    assert error.code == INTERNAL_ERROR_CODE
    assert error.message == "in-process server request consumer is closed"


def test_runtime_projection_shutdown_fans_out_pending_request_errors() -> None:
    # Rust shutdown cleanup: pending request responders receive an internal
    # runtime-shutting-down error and the pending map is drained.
    runtime = InProcessRuntimeProjection(channel_capacity=2)
    runtime.handle_client_request({"id": 12})
    runtime.handle_client_request({"id": 13})
    runtime.handle_shutdown()
    errors = runtime.finish_shutdown()

    assert runtime.shutdown_ack_requested
    assert sorted(request_id.to_json() for request_id in errors) == [12, 13]
    assert {error.message for error in errors.values()} == {"in-process app-server runtime is shutting down"}
    assert not runtime.pending_request_responses


def test_constants_match_rust_module_boundary() -> None:
    # Rust constants: IN_PROCESS_CONNECTION_ID = 0, SHUTDOWN_TIMEOUT = 5s, and
    # default capacity reuses transport CHANNEL_CAPACITY.
    assert SHUTDOWN_TIMEOUT_SECONDS == 5
    assert DEFAULT_IN_PROCESS_CHANNEL_CAPACITY == 128
