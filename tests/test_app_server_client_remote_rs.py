from __future__ import annotations

import errno
import json

import pytest

from pycodex.app_server_client import (
    AppServerEvent,
    AppServerEventKind,
    REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
    REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS,
    REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    UDS_WEBSOCKET_HANDSHAKE_URL,
    RemoteAppServerClient,
    RemoteAppServerConnectArgs,
    RemoteAppServerEndpoint,
    RemoteAppServerEndpointKind,
    RemoteClientCommandProjection,
    RemoteEventDeliveryProjection,
    RemoteWriteJsonrpcMessageProjection,
    TypedRequestError,
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
    remote_server_version_from_user_agent,
    remote_websocket_close_error_is_already_closed,
    remote_websocket_connect_error_message,
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
    request_id_from_client_request,
    websocket_url_supports_auth_token,
    _to_exec_remote_connect_args,
)
from pycodex.app_server_protocol import ClientNotification, ClientRequest, JSONRPCErrorError
from pycodex.exec.session import ClientRequest as ExecClientRequest
from pycodex.exec.websocket import OPCODE_BINARY, OPCODE_CLOSE, OPCODE_TEXT, WebSocketFrame


class FakeWebSocket:
    def __init__(
        self,
        frames: list[dict[str, object] | WebSocketFrame | BaseException],
        *,
        close_error: Exception | None = None,
        send_error: Exception | None = None,
        send_error_after: int | None = None,
    ) -> None:
        self.frames = list(frames)
        self.sent_text: list[str] = []
        self.closed = False
        self.close_error = close_error
        self.send_error = send_error
        self.send_error_after = send_error_after

    def send_text(self, text: str) -> None:
        if (
            self.send_error is not None
            and self.send_error_after is not None
            and len(self.sent_text) >= self.send_error_after
        ):
            raise self.send_error
        self.sent_text.append(text)

    def recv_frame(self) -> WebSocketFrame:
        if not self.frames:
            raise EOFError("no websocket frames")
        frame = self.frames.pop(0)
        if isinstance(frame, BaseException):
            raise frame
        if isinstance(frame, WebSocketFrame):
            return frame
        return WebSocketFrame(True, 1, json.dumps(frame, separators=(",", ":")).encode())

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def test_remote_connect_args_initialize_params_match_rust_shape() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: RemoteAppServerConnectArgs builds initialize params from client metadata.
    args = RemoteAppServerConnectArgs(
        endpoint=RemoteAppServerEndpoint.websocket("wss://example.test/rpc"),
        client_name="codex-tui",
        client_version="1.2.3",
        experimental_api=True,
        opt_out_notification_methods=["thread/tokenUsage/updated"],
    )

    assert args.initialize_params() == {
        "client_info": {"name": "codex-tui", "title": None, "version": "1.2.3"},
        "capabilities": {
            "experimental_api": True,
            "request_attestation": False,
            "opt_out_notification_methods": ["thread/tokenUsage/updated"],
        },
    }


def test_remote_connect_endpoint_projection_matches_rust_connectors() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: websocket and Unix endpoint connectors keep their distinct setup steps.
    websocket = remote_connect_endpoint_projection(
        RemoteAppServerEndpoint.websocket("wss://example.com/rpc", auth_token="token")
    )
    assert websocket.endpoint_kind == "websocket"
    assert websocket.endpoint_label == "wss://example.com/rpc"
    assert websocket.parses_websocket_url is True
    assert websocket.checks_auth_token_policy is True
    assert websocket.builds_client_request is True
    assert websocket.inserts_authorization_header is True
    assert websocket.ensures_rustls_crypto_provider is True
    assert websocket.uses_websocket_config is True
    assert websocket.connect_timeout_seconds == 10
    assert websocket.socket_connect_step is None
    assert websocket.websocket_upgrade_step == "connect_async_with_config"
    assert websocket.returns_endpoint_label is True

    unix_socket = remote_connect_endpoint_projection(
        RemoteAppServerEndpoint.unix_socket("/tmp/codex.sock")
    )
    assert unix_socket.endpoint_kind == "unix_socket"
    assert unix_socket.endpoint_label == "unix:///tmp/codex.sock"
    assert unix_socket.parses_websocket_url is False
    assert unix_socket.checks_auth_token_policy is False
    assert unix_socket.builds_client_request is True
    assert unix_socket.inserts_authorization_header is False
    assert unix_socket.ensures_rustls_crypto_provider is False
    assert unix_socket.uses_websocket_config is True
    assert unix_socket.connect_timeout_seconds == 10
    assert unix_socket.socket_connect_step == "UnixStream::connect"
    assert unix_socket.websocket_upgrade_step == "client_async_with_config"
    assert unix_socket.returns_endpoint_label is True


def test_remote_connect_dispatch_projection_matches_rust_connect() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: RemoteAppServerClient::connect dispatches by endpoint and calls connect_with_stream.
    websocket = remote_connect_dispatch_projection(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("wss://example.com/rpc"),
            client_name="codex",
            client_version="1.0.0",
            channel_capacity=0,
        )
    )
    assert websocket.endpoint_kind == "websocket"
    assert websocket.connector_function == "connect_websocket_endpoint"
    assert websocket.channel_capacity == 1
    assert websocket.builds_initialize_params_before_connect is True
    assert websocket.passes_initialize_params_to_connect_with_stream is True
    assert websocket.calls_connect_with_stream is True
    assert websocket.returns_remote_client is True

    unix_socket = remote_connect_dispatch_projection(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.unix_socket("/tmp/codex.sock"),
            client_name="codex",
            client_version="1.0.0",
            channel_capacity=8,
        )
    )
    assert unix_socket.endpoint_kind == "unix_socket"
    assert unix_socket.connector_function == "connect_unix_socket_endpoint"
    assert unix_socket.channel_capacity == 8
    assert unix_socket.calls_connect_with_stream is True


def test_remote_connect_with_stream_projection_matches_rust_lifecycle() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: connect_with_stream initializes first, then creates channels and returns worker-backed client.
    projection = remote_connect_with_stream_projection(8)

    assert projection.initialize_before_channels is True
    assert projection.initialize_timeout_seconds == 10
    assert projection.command_channel_type == "mpsc::channel<RemoteClientCommand>"
    assert projection.command_capacity == 8
    assert projection.event_channel_type == "mpsc::unbounded_channel<AppServerEvent>"
    assert projection.event_bounded is False
    assert projection.pending_events_storage == "VecDeque<AppServerEvent>"
    assert projection.stores_server_version is True
    assert projection.spawns_worker is True
    assert projection.returns_worker_handle is True


def test_remote_client_command_projection_matches_rust_variants() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: RemoteClientCommand variant shape and oneshot response boundary.
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})
    error = JSONRPCErrorError(code=-32603, message="failed")

    commands = [
        RemoteClientCommandProjection.request_command(request),
        RemoteClientCommandProjection.notify(ClientNotification("initialized")),
        RemoteClientCommandProjection.resolve_server_request("srv-1", {"ok": True}),
        RemoteClientCommandProjection.reject_server_request("srv-2", error),
        RemoteClientCommandProjection.shutdown(),
    ]

    assert [command.kind for command in commands] == [
        "Request",
        "Notify",
        "ResolveServerRequest",
        "RejectServerRequest",
        "Shutdown",
    ]
    assert commands[0].request == request
    assert commands[0].request_is_boxed is True
    assert commands[1].notification == ClientNotification("initialized")
    assert commands[2].request_id == "srv-1"
    assert commands[2].result == {"ok": True}
    assert commands[3].request_id == "srv-2"
    assert commands[3].error == error
    assert commands[4].has_response_oneshot is True
    assert all(command.has_response_oneshot for command in commands)


def test_remote_command_entrypoint_projection_matches_rust_public_methods() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: public command entrypoints send a command with oneshot and map send/response closures.
    projections = {
        operation: remote_command_entrypoint_projection(operation)
        for operation in ("request", "notify", "resolve", "reject")
    }

    assert {name: projection.command_kind for name, projection in projections.items()} == {
        "request": "Request",
        "notify": "Notify",
        "resolve": "ResolveServerRequest",
        "reject": "RejectServerRequest",
    }
    assert all(projection.has_response_oneshot for projection in projections.values())
    assert {name: projection.worker_send_error_message for name, projection in projections.items()} == {
        "request": "remote app-server worker channel is closed",
        "notify": "remote app-server worker channel is closed",
        "resolve": "remote app-server worker channel is closed",
        "reject": "remote app-server worker channel is closed",
    }
    assert {name: projection.response_closed_error_message for name, projection in projections.items()} == {
        "request": "remote app-server request channel is closed",
        "notify": "remote app-server notify channel is closed",
        "resolve": "remote app-server resolve channel is closed",
        "reject": "remote app-server reject channel is closed",
    }


def test_remote_worker_command_projection_matches_rust_match_branches() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: worker-side RemoteClientCommand match branches keep distinct write/close outcomes.
    projections = {
        kind: remote_worker_command_projection(kind)
        for kind in (
            "Request",
            "Notify",
            "ResolveServerRequest",
            "RejectServerRequest",
            "Shutdown",
        )
    }

    assert {kind: projection.jsonrpc_message_kind for kind, projection in projections.items()} == {
        "Request": "Request",
        "Notify": "Notification",
        "ResolveServerRequest": "Response",
        "RejectServerRequest": "Error",
        "Shutdown": None,
    }
    assert projections["Request"].registers_pending_request is True
    assert projections["Request"].removes_pending_request_on_write_failure is True
    assert projections["Request"].emits_disconnected_on_write_failure is True
    assert projections["Request"].stores_worker_exit_error_on_write_failure is True
    assert projections["Notify"].response_tx_receives_write_result is True
    assert projections["ResolveServerRequest"].response_tx_receives_write_result is True
    assert projections["RejectServerRequest"].response_tx_receives_write_result is True
    assert projections["Shutdown"].response_tx_receives_write_result is True
    assert projections["Shutdown"].breaks_worker_after_command is True
    assert projections["Shutdown"].close_uses_already_closed_tolerance is True

    duplicate = remote_worker_command_projection("Request", duplicate_request_id="req-1")
    assert duplicate.registers_pending_request is False
    assert duplicate.duplicate_request_error_message == (
        "duplicate remote app-server request id `req-1`"
    )
    assert duplicate.jsonrpc_message_kind is None


def test_remote_worker_select_loop_projection_matches_rust_topology() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: worker loop selects command_rx.recv() and stream.next(), then fans out pending requests.
    projection = remote_worker_select_loop_projection()

    assert projection.select_arms == ("command_rx.recv()", "stream.next()")
    assert projection.biased is False
    assert projection.command_arm_source == "mpsc::Receiver<RemoteClientCommand>"
    assert projection.stream_arm_source == "WebSocketStream::next()"
    assert projection.pending_requests_map == (
        "HashMap<RequestId, oneshot::Sender<IoResult<RequestResult>>>"
    )
    assert projection.worker_exit_error_storage == "Option<(ErrorKind, String)>"
    assert projection.fans_out_pending_requests_after_loop is True
    assert projection.default_exit_error_kind == "BrokenPipe"
    assert projection.default_exit_error_message == (
        "remote app-server worker channel is closed"
    )


def test_remote_worker_stream_message_projection_matches_rust_match_branches() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: worker-side stream.next branches route JSON-RPC and websocket frames distinctly.
    endpoint = "ws://localhost/rpc"

    response = remote_worker_stream_message_projection("response", endpoint=endpoint)
    assert response.jsonrpc_message_kind == "Response"
    assert response.removes_pending_request is True
    assert response.pending_request_result == "Ok(Ok(result))"

    error = remote_worker_stream_message_projection("error", endpoint=endpoint)
    assert error.jsonrpc_message_kind == "Error"
    assert error.removes_pending_request is True
    assert error.pending_request_result == "Ok(Err(error))"

    known_notification = remote_worker_stream_message_projection("notification", endpoint=endpoint)
    assert known_notification.delivers_event is True
    assert known_notification.event_kind == "AppServerEvent"
    unknown_notification = remote_worker_stream_message_projection(
        "notification",
        endpoint=endpoint,
        known_notification=False,
    )
    assert unknown_notification.ignored is True
    assert unknown_notification.delivers_event is False

    supported_request = remote_worker_stream_message_projection("request", endpoint=endpoint)
    assert supported_request.delivers_event is True
    assert supported_request.event_kind == "ServerRequest"
    unsupported_request = remote_worker_stream_message_projection(
        "request",
        endpoint=endpoint,
        method="thread/unknown",
        supported_server_request=False,
    )
    assert unsupported_request.writes_rejection is True
    assert unsupported_request.rejection_error_code == -32601
    assert unsupported_request.rejection_error_message == (
        "unsupported remote app-server request `thread/unknown`"
    )

    failed_rejection = remote_worker_stream_message_projection(
        "request",
        endpoint=endpoint,
        method="thread/unknown",
        supported_server_request=False,
        reject_write_fails=True,
        error=RuntimeError("pipe closed"),
    )
    assert failed_rejection.write_failure_emits_disconnected is True
    assert failed_rejection.worker_exit_error_kind == "BrokenPipe"
    assert failed_rejection.breaks_worker is True
    assert failed_rejection.worker_exit_message == (
        "remote app server at `ws://localhost/rpc` write failed: pipe closed"
    )

    invalid = remote_worker_stream_message_projection(
        "invalid_jsonrpc",
        endpoint=endpoint,
        error=ValueError("expected value"),
    )
    assert invalid.worker_exit_error_kind == "InvalidData"
    assert invalid.event_kind == "Disconnected"
    assert invalid.breaks_worker is True

    close = remote_worker_stream_message_projection("close", endpoint=endpoint, close_reason="")
    assert close.worker_exit_error_kind == "ConnectionAborted"
    assert close.worker_exit_message == (
        "remote app server at `ws://localhost/rpc` disconnected: connection closed"
    )
    assert remote_worker_stream_message_projection("ping", endpoint=endpoint).ignored is True

    transport = remote_worker_stream_message_projection(
        "transport_failure",
        endpoint=endpoint,
        error=RuntimeError("socket reset"),
    )
    assert transport.worker_exit_error_kind == "InvalidData"
    assert transport.breaks_worker is True
    eof = remote_worker_stream_message_projection("eof", endpoint=endpoint)
    assert eof.worker_exit_error_kind == "UnexpectedEof"
    assert eof.breaks_worker is True


def test_remote_channel_topology_projection_matches_rust_worker_setup() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: remote worker uses bounded commands, unbounded events, and local pending buffers.
    projection = remote_channel_topology_projection(0)

    assert projection.command_channel_type == "mpsc::channel<RemoteClientCommand>"
    assert projection.command_capacity == 1
    assert projection.event_channel_type == "mpsc::unbounded_channel<AppServerEvent>"
    assert projection.event_bounded is False
    assert projection.pending_events_buffer == "VecDeque<AppServerEvent>"
    assert (
        projection.pending_requests_map
        == "HashMap<RequestId, oneshot::Sender<IoResult<RequestResult>>>"
    )


def test_remote_worker_timing_boundary_projection_matches_current_python_boundary() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: remote.rs uses Tokio bounded command timing, while Python delegates the wire state machine.
    projection = remote_worker_timing_boundary_projection()

    assert projection.command_channel_bounded is True
    assert projection.command_backpressure_owned_by_tokio is True
    assert projection.event_channel_unbounded is True
    assert projection.remote_lagged_synthesis is False
    assert projection.executes_select_loop is False
    assert projection.executes_branch_wakeup_timing is False
    assert projection.delegated_wire_client_module == "pycodex.exec.session"
    assert projection.owns_second_websocket_state_machine is False


def test_remote_worker_select_timing_projection_matches_unbiased_select_contract() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: tokio::select! has no biased priority, so simultaneous readiness is unspecified.
    waiting = remote_worker_select_timing_projection(command_ready=False, stream_ready=False)
    assert waiting.select_macro == "tokio::select!"
    assert waiting.biased is False
    assert waiting.awaits_progress is True
    assert waiting.selected_branch is None
    assert waiting.selected_branch_is_deterministic is False

    command_only = remote_worker_select_timing_projection(command_ready=True, stream_ready=False)
    assert command_only.selected_branch == "command_rx.recv()"
    assert command_only.selected_branch_is_deterministic is True
    assert command_only.simultaneous_ready_order_is_unspecified is False

    stream_only = remote_worker_select_timing_projection(command_ready=False, stream_ready=True)
    assert stream_only.selected_branch == "stream.next()"
    assert stream_only.selected_branch_is_deterministic is True

    both = remote_worker_select_timing_projection(command_ready=True, stream_ready=True)
    assert both.selected_branch is None
    assert both.selected_branch_is_deterministic is False
    assert both.simultaneous_ready_order_is_unspecified is True
    assert "does not promise a stable branch order" in both.selection_guarantee
    assert both.python_executes_scheduler is False


def test_remote_command_channel_backpressure_projection_matches_rust_sender_boundary() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: bounded RemoteClientCommand sends await capacity and fail only after receiver close.
    projection = remote_command_channel_backpressure_projection(
        ["request", "notify", "shutdown"],
        channel_capacity=2,
        initially_queued=1,
    )

    assert projection.command_channel_type == "mpsc::channel<RemoteClientCommand>"
    assert projection.capacity == 2
    assert projection.initially_queued == 1
    assert projection.receiver_open is True
    assert projection.commands_sent_without_wait == ("request",)
    assert projection.commands_waiting_for_capacity == ("notify", "shutdown")
    assert projection.send_waits_when_full is True
    assert projection.send_fails_only_when_receiver_closed is True
    assert projection.send_error_message is None
    assert projection.event_channel_type == "mpsc::unbounded_channel<AppServerEvent>"
    assert projection.event_channel_unbounded is True
    assert projection.remote_lagged_synthesis is False

    closed = remote_command_channel_backpressure_projection(
        ["request"],
        channel_capacity=0,
        initially_queued=10,
        receiver_open=False,
    )
    assert closed.capacity == 1
    assert closed.initially_queued == 1
    assert closed.receiver_open is False
    assert closed.commands_sent_without_wait == ()
    assert closed.commands_waiting_for_capacity == ()
    assert closed.send_error_message == "remote app-server worker channel is closed"


def test_remote_deliver_event_projection_matches_rust_helper() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: deliver_event maps closed event consumer to BrokenPipe.
    event = AppServerEvent.disconnected("closed")

    assert remote_deliver_event_projection(event) == RemoteEventDeliveryProjection(
        delivered_events=[event],
    )
    assert remote_deliver_event_projection(event, consumer_open=False) == RemoteEventDeliveryProjection(
        delivered_events=[],
        error_kind="BrokenPipe",
        error_message="remote app-server event consumer channel is closed",
    )


def test_remote_next_event_projection_matches_rust_pending_event_order() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: next_event drains pending_events before awaiting the runtime event channel.
    first = AppServerEvent.server_notification({"method": "thread/started"})
    second = AppServerEvent.disconnected("closed")

    pending_projection = remote_next_event_projection([first, second])
    assert pending_projection.returned_event == first
    assert pending_projection.pending_events_remaining == (second,)
    assert pending_projection.awaited_event_channel is False

    empty_projection = remote_next_event_projection([])
    assert empty_projection.returned_event is None
    assert empty_projection.pending_events_remaining == ()
    assert empty_projection.awaited_event_channel is True


def test_remote_websocket_close_error_projection_matches_rust_helper() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: websocket_close_error_is_already_closed recognizes already-closed close failures.
    assert remote_websocket_close_error_is_already_closed("ConnectionClosed") is True
    assert remote_websocket_close_error_is_already_closed("already closed") is True
    assert remote_websocket_close_error_is_already_closed(BrokenPipeError("broken pipe")) is True
    assert remote_websocket_close_error_is_already_closed(ConnectionResetError("reset")) is True
    assert remote_websocket_close_error_is_already_closed(OSError(errno.ENOTCONN, "not connected")) is True
    assert remote_websocket_close_error_is_already_closed(RuntimeError("tls alert")) is False


def test_remote_write_jsonrpc_message_projection_matches_rust_helper() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: write_jsonrpc_message serializes compact JSON and qualifies write errors by endpoint.
    notification = jsonrpc_notification_from_client_notification(ClientNotification("initialized"))

    assert remote_write_jsonrpc_message_projection(
        notification,
        endpoint="ws://localhost/rpc",
    ) == RemoteWriteJsonrpcMessageProjection(payload='{"method":"initialized"}')
    assert remote_write_jsonrpc_message_projection(
        notification,
        endpoint="ws://localhost/rpc",
        send_error=RuntimeError("pipe closed"),
    ) == RemoteWriteJsonrpcMessageProjection(
        payload='{"method":"initialized"}',
        error_message="failed to write websocket message to `ws://localhost/rpc`: pipe closed",
    )


def test_remote_server_version_from_user_agent_matches_rust_initialize_parse() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: initialize parses server_version from userAgent with split_once('/') and first token.
    assert remote_server_version_from_user_agent("codex/1.2.3") == "1.2.3"
    assert remote_server_version_from_user_agent("codex/1.2.3 extra") == "1.2.3"
    assert remote_server_version_from_user_agent("codex-without-version") is None
    assert remote_server_version_from_user_agent("codex/   \t") is None
    assert remote_server_version_from_user_agent(None) is None


def test_remote_initialize_close_frame_error_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: initialize close frames preserve non-empty reasons and default empty ones.
    assert (
        remote_initialize_close_frame_error_message("ws://localhost/rpc", "initializing")
        == "remote app server at `ws://localhost/rpc` closed during initialize: initializing"
    )
    assert (
        remote_initialize_close_frame_error_message("ws://localhost/rpc", "")
        == "remote app server at `ws://localhost/rpc` closed during initialize: "
        "connection closed during initialize"
    )
    assert (
        remote_initialize_close_frame_error_message("ws://localhost/rpc")
        == "remote app server at `ws://localhost/rpc` closed during initialize: "
        "connection closed during initialize"
    )


def test_remote_initialize_error_message_matches_rust_branches() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: initialize_remote_connection keeps endpoint context in non-close failures.
    assert (
        remote_initialize_error_message(
            "ws://localhost/rpc",
            "rejected",
            "server refused initialize",
        )
        == "remote app server at `ws://localhost/rpc` rejected initialize: "
        "server refused initialize"
    )
    assert (
        remote_initialize_error_message("ws://localhost/rpc", "invalid_response", "bad json")
        == "remote app server at `ws://localhost/rpc` sent invalid initialize response: bad json"
    )
    assert (
        remote_initialize_error_message("ws://localhost/rpc", "transport_failed", "tls alert")
        == "remote app server at `ws://localhost/rpc` transport failed during initialize: tls alert"
    )
    assert (
        remote_initialize_error_message("ws://localhost/rpc", "eof")
        == "remote app server at `ws://localhost/rpc` closed during initialize"
    )
    assert (
        remote_initialize_error_message("ws://localhost/rpc", "timeout")
        == "timed out waiting for initialize response from `ws://localhost/rpc`"
    )


def test_remote_initialize_handshake_projection_matches_rust_sequence() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: initialize_remote_connection writes initialize, waits for matching id,
    # then writes initialized after success.
    projection = remote_initialize_handshake_projection()

    assert projection.initialize_request_id == "initialize"
    assert projection.initialize_request_method == "initialize"
    assert projection.waits_for_matching_response_id == "initialize"
    assert projection.sends_initialized_after_success is True
    assert projection.initialized_notification_method == "initialized"


def test_remote_initialize_frame_projection_matches_rust_loop_branches() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: initialize loop queues known events, rejects unknown requests,
    # completes only matching initialize responses/errors, and ignores unrelated frames.
    assert remote_initialize_frame_projection(
        "response",
        matching_initialize_id=True,
    ).completes_initialize is True
    assert remote_initialize_frame_projection("response").ignored is True
    assert remote_initialize_frame_projection(
        "error",
        matching_initialize_id=True,
    ).action == "reject_initialize"
    assert remote_initialize_frame_projection(
        "notification",
        known_notification=True,
    ).queued_event_kind == "ServerNotification"
    assert remote_initialize_frame_projection(
        "request",
        supported_server_request=True,
    ).queued_event_kind == "ServerRequest"

    rejection = remote_initialize_frame_projection(
        "request",
        supported_server_request=False,
        method="unknown/request",
    )
    assert rejection.action == "write_rejection"
    assert rejection.rejection_code == -32601
    assert rejection.rejection_message == "unsupported remote app-server request `unknown/request`"
    assert remote_initialize_frame_projection("binary").ignored is True


def test_remote_runtime_close_frame_disconnected_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: runtime close frames stream disconnected events with close reason defaulting.
    assert (
        remote_runtime_close_frame_disconnected_message("ws://localhost/rpc", "done")
        == "remote app server at `ws://localhost/rpc` disconnected: done"
    )
    assert (
        remote_runtime_close_frame_disconnected_message("ws://localhost/rpc", "")
        == "remote app server at `ws://localhost/rpc` disconnected: connection closed"
    )
    assert (
        remote_runtime_close_frame_disconnected_message("ws://localhost/rpc")
        == "remote app server at `ws://localhost/rpc` disconnected: connection closed"
    )


def test_remote_runtime_eof_disconnected_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: runtime EOF streams a Disconnected event with fixed closed-connection text.
    assert (
        remote_runtime_eof_disconnected_message("ws://localhost/rpc")
        == "remote app server at `ws://localhost/rpc` closed the connection"
    )


def test_remote_runtime_transport_failure_disconnected_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: runtime websocket transport errors stream disconnected events.
    assert (
        remote_runtime_transport_failure_disconnected_message(
            "ws://localhost/rpc",
            RuntimeError("socket reset"),
        )
        == "remote app server at `ws://localhost/rpc` transport failed: socket reset"
    )


def test_remote_runtime_invalid_jsonrpc_disconnected_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: runtime JSON-RPC parse failures stream disconnected events.
    assert (
        remote_runtime_invalid_jsonrpc_disconnected_message(
            "ws://localhost/rpc",
            ValueError("expected value"),
        )
        == "remote app server at `ws://localhost/rpc` sent invalid JSON-RPC: expected value"
    )


def test_remote_websocket_connect_error_message_matches_rust_branches() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: connect_websocket_endpoint keeps endpoint-qualified I/O error text.
    assert (
        remote_websocket_connect_error_message(
            "ws://localhost:bad/rpc",
            "invalid_url",
            "invalid port",
        )
        == "invalid websocket URL `ws://localhost:bad/rpc`: invalid port"
    )
    assert (
        remote_websocket_connect_error_message(
            "ws://example.test/rpc",
            "unsupported_auth_url",
        )
        == "remote auth tokens require `wss://` or loopback `ws://` URLs; "
        "got `ws://example.test/rpc`"
    )
    assert (
        remote_websocket_connect_error_message("ws://localhost/rpc", "timeout")
        == "timed out connecting to remote app server at `ws://localhost/rpc`"
    )
    assert (
        remote_websocket_connect_error_message(
            "ws://localhost/rpc",
            "failure",
            RuntimeError("tls handshake failed"),
        )
        == "failed to connect to remote app server at `ws://localhost/rpc`: "
        "tls handshake failed"
    )


def test_remote_unix_socket_connect_error_message_matches_rust_branches() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: connect_unix_socket_endpoint keeps unix:// endpoint context in errors.
    assert (
        remote_unix_socket_connect_error_message(
            "unix://codex.sock",
            "invalid_handshake_url",
            "invalid authority",
        )
        == "invalid UDS websocket handshake URL: invalid authority"
    )
    assert (
        remote_unix_socket_connect_error_message("unix://codex.sock", "connect_timeout")
        == "timed out connecting to remote app server at `unix://codex.sock`"
    )
    assert (
        remote_unix_socket_connect_error_message(
            "unix://codex.sock",
            "connect_failure",
            RuntimeError("socket missing"),
        )
        == "failed to connect to remote app server at `unix://codex.sock`: socket missing"
    )
    assert (
        remote_unix_socket_connect_error_message("unix://codex.sock", "upgrade_timeout")
        == "timed out upgrading remote app server at `unix://codex.sock`"
    )
    assert (
        remote_unix_socket_connect_error_message(
            "unix://codex.sock",
            "upgrade_failure",
            RuntimeError("bad handshake"),
        )
        == "failed to upgrade remote app server at `unix://codex.sock`: bad handshake"
    )


def test_remote_unsupported_server_request_error_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: unsupported server requests are rejected with Rust's method-qualified message.
    assert (
        remote_unsupported_server_request_error_message("thread/unknown")
        == "unsupported remote app-server request `thread/unknown`"
    )


def test_remote_write_failed_disconnected_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: websocket write failures produce endpoint-qualified disconnected events.
    assert (
        remote_write_failed_disconnected_message(
            "ws://localhost/rpc",
            "failed to write websocket message to `ws://localhost/rpc`: pipe closed",
        )
        == "remote app server at `ws://localhost/rpc` write failed: "
        "failed to write websocket message to `ws://localhost/rpc`: pipe closed"
    )


def test_remote_shutdown_close_failed_error_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: shutdown close failures keep endpoint context unless already closed.
    assert (
        remote_shutdown_close_failed_error_message(
            "ws://localhost/rpc",
            RuntimeError("tls close failed"),
        )
        == "failed to close websocket app server `ws://localhost/rpc`: tls close failed"
    )


def test_remote_worker_exit_pending_requests_projection_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: worker exit fans one error kind/message out to all pending requests.
    default_projection = remote_worker_exit_pending_requests_projection(2)
    assert default_projection.error_kind == "BrokenPipe"
    assert default_projection.error_message == "remote app-server worker channel is closed"
    assert default_projection.uses_default_exit_error is True
    assert default_projection.worker_exit_error_was_set is False
    assert default_projection.pending_request_errors == (
        "remote app-server worker channel is closed",
        "remote app-server worker channel is closed",
    )

    close_projection = remote_worker_exit_pending_requests_projection(
        1,
        error_kind="ConnectionAborted",
        error_message="remote app server at `ws://localhost/rpc` disconnected: maintenance",
    )
    assert close_projection.uses_default_exit_error is False
    assert close_projection.worker_exit_error_was_set is True
    assert close_projection.pending_request_errors == (
        "remote app server at `ws://localhost/rpc` disconnected: maintenance",
    )


def test_remote_worker_command_channel_closed_projection_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: command_rx closure closes the stream, breaks the worker, and defaults pending errors.
    projection = remote_worker_command_channel_closed_projection(2)

    assert projection.closes_stream is True
    assert projection.close_error_ignored is True
    assert projection.breaks_worker is True
    assert projection.worker_exit_error_kind == "BrokenPipe"
    assert projection.worker_exit_error_message == "remote app-server worker channel is closed"
    assert projection.pending_request_errors == (
        "remote app-server worker channel is closed",
        "remote app-server worker channel is closed",
    )


def test_remote_shutdown_projection_matches_rust_control_flow() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: shutdown drops event_rx, sends Shutdown, conditionally propagates close_result,
    # then waits for the worker and aborts on timeout.
    ok_projection = remote_shutdown_projection()
    assert ok_projection.drop_event_receiver_before_shutdown_command is True
    assert ok_projection.send_shutdown_command is True
    assert ok_projection.await_response_timeout_seconds == 5
    assert ok_projection.propagate_close_result is True
    assert ok_projection.return_ok is True
    assert ok_projection.await_worker_timeout_seconds == 5
    assert ok_projection.abort_worker_on_timeout is False

    timeout_projection = remote_shutdown_projection(
        response_within_timeout=False,
        close_result_ok=False,
        worker_exits_within_timeout=False,
    )
    assert timeout_projection.propagate_close_result is False
    assert timeout_projection.return_ok is True
    assert timeout_projection.abort_worker_on_timeout is True

    close_error_projection = remote_shutdown_projection(close_result_ok=False)
    assert close_error_projection.propagate_close_result is True
    assert close_error_projection.return_ok is False


def test_remote_duplicate_request_id_error_message_matches_rust_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: duplicate request ids are rejected before writing another request.
    assert (
        remote_duplicate_request_id_error_message("req-1")
        == "duplicate remote app-server request id `req-1`"
    )


def test_remote_endpoint_shape_validation_and_effective_channel_capacity() -> None:
    # Rust contract: endpoint variants are exclusive, and connect uses channel_capacity.max(1).
    with pytest.raises(ValueError, match="websocket endpoint requires websocket_url"):
        RemoteAppServerEndpoint(RemoteAppServerEndpointKind.WEB_SOCKET)
    with pytest.raises(ValueError, match="unix_socket endpoint cannot include websocket_url"):
        RemoteAppServerEndpoint(
            RemoteAppServerEndpointKind.UNIX_SOCKET,
            websocket_url="ws://localhost/rpc",
            socket_path="codex.sock",
        )

    args = RemoteAppServerConnectArgs(
        endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
        client_name="codex-tui",
        client_version="0.1.0",
        opt_out_notification_methods=("thread/tokenUsage/updated",),
        channel_capacity=0,
    )

    assert args.opt_out_notification_methods == ["thread/tokenUsage/updated"]
    assert args.channel_capacity == 0
    assert args.effective_channel_capacity == 1


def test_remote_connect_bridge_forwards_effective_command_channel_capacity() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: connect_with_stream builds a bounded RemoteClientCommand channel
    # with channel_capacity.max(1), while remote events use an unbounded channel.
    args = RemoteAppServerConnectArgs(
        endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
        client_name="codex-tui",
        client_version="0.1.0",
        channel_capacity=0,
    )

    exec_args = _to_exec_remote_connect_args(args)

    assert args.channel_capacity == 0
    assert args.effective_channel_capacity == 1
    assert exec_args.channel_capacity == 1


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("wss://example.com:443", True),
        ("ws://127.0.0.1:4500", True),
        ("ws://example.com:4500", False),
        ("ws://localhost/rpc", True),
        ("ws://127.0.0.1/rpc", True),
        ("ws://127.10.20.30/rpc", True),
        ("ws://[::1]/rpc", True),
        ("ws://[::2]/rpc", False),
        ("ws://example.com/rpc", False),
        ("http://localhost/rpc", False),
    ],
)
def test_remote_auth_token_transport_policy_allows_wss_and_loopback_ws(
    url: str,
    allowed: bool,
) -> None:
    # Rust test: remote_auth_token_transport_policy_allows_wss_and_loopback_ws.
    assert websocket_url_supports_auth_token(url) is allowed


def test_remote_constants_and_websocket_config_match_rust() -> None:
    # Rust contract: remote.rs uses 10s connect/initialize timeouts and 128 MiB frame/message caps.
    assert REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS == 10
    assert REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS == 10
    assert REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE == 128 << 20
    assert UDS_WEBSOCKET_HANDSHAKE_URL == "ws://localhost/rpc"
    assert remote_websocket_config() == {
        "max_frame_size": 128 << 20,
        "max_message_size": 128 << 20,
    }


def test_jsonrpc_request_projection_matches_client_request() -> None:
    # Rust contract: helper serde-projects ClientRequest into JSONRPCRequest and preserves id.
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    jsonrpc = jsonrpc_request_from_client_request(request)

    assert jsonrpc.method == "thread/read"
    assert jsonrpc.id.to_json() == "req-1"
    assert jsonrpc.params == {"threadId": "thread-1"}
    assert request_id_from_client_request(request) == "req-1"


def test_jsonrpc_request_projection_accepts_jsonrpc_mapping() -> None:
    # Rust contract: the helper's serde round-trip yields a JSONRPCRequest shape.
    request = {"id": "req-2", "method": "thread/read", "params": {"threadId": "thread-2"}}

    jsonrpc = jsonrpc_request_from_client_request(request)

    assert jsonrpc.method == "thread/read"
    assert jsonrpc.id.to_json() == "req-2"
    assert jsonrpc.params == {"threadId": "thread-2"}
    assert request_id_from_client_request(request) == "req-2"


def test_jsonrpc_notification_projection_matches_client_notification() -> None:
    # Rust contract: helper serde-projects ClientNotification into JSONRPCNotification.
    notification = ClientNotification("Initialized")

    jsonrpc = jsonrpc_notification_from_client_notification(notification)

    assert jsonrpc.method == "initialized"
    assert jsonrpc.params is None


def test_jsonrpc_notification_projection_accepts_jsonrpc_mapping() -> None:
    # Rust contract: the helper's serde round-trip yields a JSONRPCNotification shape.
    notification = {"method": "initialized"}

    jsonrpc = jsonrpc_notification_from_client_notification(notification)

    assert jsonrpc.method == "initialized"
    assert jsonrpc.params is None


def test_remote_jsonrpc_projection_panic_message_matches_rust_helpers() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: serde projection helpers keep stable panic diagnostics.
    assert (
        remote_jsonrpc_projection_panic_message("request", "serialize", "bad value")
        == "client request should serialize: bad value"
    )
    assert (
        remote_jsonrpc_projection_panic_message("request", "encode", "missing method")
        == "client request should encode as JSON-RPC request: missing method"
    )
    assert (
        remote_jsonrpc_projection_panic_message("notification", "serialize", "bad value")
        == "client notification should serialize: bad value"
    )
    assert (
        remote_jsonrpc_projection_panic_message("notification", "encode", "missing method")
        == "client notification should encode as JSON-RPC notification: missing method"
    )


def test_remote_app_server_event_from_notification_filters_like_rust() -> None:
    # Rust contract: app_server_event_from_notification returns Some(ServerNotification) only for known methods.
    known = {"method": "thread/started", "params": {"threadId": "thread-1"}}
    unknown = {"method": "unknown/notification", "params": {}}

    assert remote_app_server_event_from_notification(known) == AppServerEvent.server_notification(known)
    assert remote_app_server_event_from_notification(unknown) is None


def test_remote_request_handle_projection_matches_rust_factory() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: request_handle clones command_tx and leaves event/server-version state on the client.
    projection = remote_request_handle_projection()

    assert projection.clones_command_sender is True
    assert projection.owns_event_receiver is False
    assert projection.stores_server_version is False
    assert projection.request_uses_request_command is True
    assert projection.request_typed_uses_client_typed_error_mapping is True


@pytest.mark.asyncio
async def test_remote_request_handle_delegates_and_reports_server_version() -> None:
    # Rust contract: RemoteAppServerRequestHandle forwards requests through the remote command channel.
    seen: list[ClientRequest] = []

    async def handler(request: ClientRequest) -> dict[str, object]:
        seen.append(request)
        return {"ok": True}

    client = RemoteAppServerClient(request_handler=handler, server_version="1.2.3")
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert client.server_version() == "1.2.3"
    assert await client.request_handle().request(request) == {"ok": True}
    assert await client.request_typed(request) == {"ok": True}
    assert seen == [request, request]


@pytest.mark.asyncio
async def test_remote_notify_resolve_reject_next_event_and_shutdown() -> None:
    # Rust contract: remote facade forwards notify/resolve/reject commands and drains pending events.
    notifications: list[object] = []
    event = AppServerEvent.disconnected("closed")
    client = RemoteAppServerClient(
        notification_handler=lambda notification: notifications.append(notification),
        events=[event],
    )

    await client.notify("initialized")
    await client.resolve_server_request("srv-1", {"ok": True})
    await client.reject_server_request("srv-2", {"code": -32601})

    assert notifications == ["initialized"]
    assert client.resolved_server_requests() == {"srv-1": {"ok": True}}
    assert client.rejected_server_requests() == {"srv-2": {"code": -32601}}
    assert await client.next_event() == event
    assert await client.next_event() is None

    client.push_event(AppServerEvent.lagged(1))
    assert await client.next_event() == AppServerEvent.lagged(1)

    await client.shutdown()
    with pytest.raises(BrokenPipeError):
        await client.next_event()


@pytest.mark.asyncio
async def test_remote_shutdown_tolerates_worker_closed_after_command_is_queued() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust test: shutdown_tolerates_worker_exit_after_command_is_queued
    class WorkerClosedWireClient:
        def close(self) -> object:
            class CloseResult:
                close_error_message = "remote app-server worker channel is closed"

            return CloseResult()

    client = RemoteAppServerClient(wire_client=WorkerClosedWireClient())

    await client.shutdown()
    with pytest.raises(BrokenPipeError):
        await client.next_event()


@pytest.mark.asyncio
async def test_remote_wire_worker_closed_commands_surface_os_error() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: command_tx send failure maps command entrypoints to the
    # remote app-server worker-channel-closed I/O error.
    class WorkerClosedCommandsWireClient:
        @staticmethod
        def _step() -> object:
            class Step:
                event = None
                response_error = None
                response_result = None
                error_message = "remote app-server worker channel is closed"

            return Step()

        def request(self, _request: object) -> object:
            return self._step()

        def send_notification(self, _method: str, _params: object) -> object:
            return self._step()

        def resolve_or_reject_server_request(self, _decision: object) -> object:
            return self._step()

    client = RemoteAppServerClient(wire_client=WorkerClosedCommandsWireClient())
    request = ClientRequest("account/read", params={"refreshToken": False}, request_id="req-1")

    with pytest.raises(OSError, match="remote app-server worker channel is closed"):
        await client.request(request)
    with pytest.raises(OSError, match="remote app-server worker channel is closed"):
        await client.notify(ClientNotification("Initialized"))
    with pytest.raises(OSError, match="remote app-server worker channel is closed"):
        await client.resolve_server_request("srv-1", {"ok": True})
    with pytest.raises(OSError, match="remote app-server worker channel is closed"):
        await client.reject_server_request("srv-2", {"code": -32603, "message": "failed"})


@pytest.mark.asyncio
async def test_remote_wire_command_response_channel_closure_surfaces_os_error() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: response_rx closure maps each command entrypoint to its
    # operation-specific remote app-server channel-closed I/O error.
    class ClosedCommandResponseWireClient:
        @staticmethod
        def _step(message: str) -> object:
            class Step:
                event = None
                response_error = None
                response_result = None
                error_message = message

            return Step()

        def request(self, _request: object) -> object:
            return self._step("remote app-server request channel is closed")

        def send_notification(self, _method: str, _params: object) -> object:
            return self._step("remote app-server notify channel is closed")

        def resolve_or_reject_server_request(self, decision: object) -> object:
            action = getattr(decision, "action", "")
            if action == "reject":
                return self._step("remote app-server reject channel is closed")
            return self._step("remote app-server resolve channel is closed")

    client = RemoteAppServerClient(wire_client=ClosedCommandResponseWireClient())
    request = ClientRequest("account/read", params={"refreshToken": False}, request_id="req-1")

    with pytest.raises(OSError, match="remote app-server request channel is closed"):
        await client.request(request)
    with pytest.raises(OSError, match="remote app-server notify channel is closed"):
        await client.notify(ClientNotification("Initialized"))
    with pytest.raises(OSError, match="remote app-server resolve channel is closed"):
        await client.resolve_server_request("srv-1", {"ok": True})
    with pytest.raises(OSError, match="remote app-server reject channel is closed"):
        await client.reject_server_request("srv-2", {"code": -32603, "message": "failed"})


@pytest.mark.asyncio
async def test_remote_request_handle_preserves_request_channel_closure_errors() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: RemoteAppServerRequestHandle uses the same request command path
    # and preserves worker/request response-channel closure errors.
    class HandleClosureWireClient:
        def __init__(self, message: str) -> None:
            self.message = message

        def request(self, _request: object) -> object:
            message = self.message

            class Step:
                event = None
                response_error = None
                response_result = None
                error_message = message

            return Step()

    request = ClientRequest("account/read", params={"refreshToken": False}, request_id="req-1")

    worker_closed = RemoteAppServerClient(
        wire_client=HandleClosureWireClient("remote app-server worker channel is closed")
    )
    with pytest.raises(OSError, match="remote app-server worker channel is closed"):
        await worker_closed.request_handle().request(request)

    request_closed = RemoteAppServerClient(
        wire_client=HandleClosureWireClient("remote app-server request channel is closed")
    )
    with pytest.raises(TypedRequestError) as exc_info:
        await request_closed.request_handle().request_typed(request)

    error = exc_info.value
    assert error.kind == "transport"
    assert "remote app-server request channel is closed" in str(error.source)


@pytest.mark.asyncio
async def test_remote_request_handle_typed_wraps_server_and_decode_errors() -> None:
    # Source: codex/codex-rs/app-server-client/src/remote.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/remote.rs
    # Contract: RemoteAppServerRequestHandle::request_typed wraps server and
    # deserialize failures with method-qualified TypedRequestError variants.
    server_error = JSONRPCErrorError(code=-32603, message="missing thread", data={"threadId": "missing"})
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "missing"})
    server_client = RemoteAppServerClient(request_handler=lambda _request: server_error)

    with pytest.raises(TypedRequestError) as server_info:
        await server_client.request_handle().request_typed(request)

    assert server_info.value.kind == "server"
    assert server_info.value.__cause__ is None
    assert str(server_info.value) == (
        'thread/read failed: missing thread (code -32603), data: {"threadId":"missing"}'
    )

    decode_client = RemoteAppServerClient(request_handler=lambda _request: {"count": "nan"})

    def decode_count(result: dict[str, object]) -> int:
        return int(result["count"])

    with pytest.raises(TypedRequestError) as decode_info:
        await decode_client.request_handle().request_typed(request, decoder=decode_count)

    assert decode_info.value.kind == "deserialize"
    assert isinstance(decode_info.value.__cause__, ValueError)
    assert str(decode_info.value).startswith("thread/read response decode error: ")


@pytest.mark.asyncio
async def test_remote_connect_reuses_exec_session_wire_client_for_requests() -> None:
    # Rust contract: connect performs initialize, sends initialized, and routes requests over JSON-RPC.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {"userAgent": "codex/1.2.3"}},
            {"id": "req-1", "result": {"thread": {"id": "thread-1"}}},
        ]
    )

    def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        return fake_socket

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=connector,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})
    result = await client.request(request)

    assert result == {"thread": {"id": "thread-1"}}
    assert client.server_version() == "1.2.3"
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"
    assert sent[1]["method"] == "initialized"
    assert sent[2] == {"id": "req-1", "method": "thread/read", "params": {"threadId": "thread-1"}}

    await client.shutdown()
    assert fake_socket.closed is True


@pytest.mark.asyncio
async def test_remote_connect_ignores_malformed_initialize_user_agent_version() -> None:
    # Rust contract: server_version is parsed only from userAgent strings containing a non-empty version after '/'.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {"userAgent": "codex-without-version"}}])

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert client.server_version() is None
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"
    assert sent[1] == {"method": "initialized"}


@pytest.mark.asyncio
async def test_remote_connect_ignores_blank_initialize_user_agent_version() -> None:
    # Rust contract: userAgent with only whitespace after '/' does not set server_version.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {"userAgent": "codex/   \t"}}])

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert client.server_version() is None


@pytest.mark.asyncio
async def test_remote_connected_request_handle_routes_over_wire_client() -> None:
    # Rust contract: RemoteAppServerRequestHandle clones the remote request command path.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"id": "req-1", "result": {"thread": {"id": "thread-1"}}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert await client.request_handle().request(request) == {"thread": {"id": "thread-1"}}
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[2] == {"id": "req-1", "method": "thread/read", "params": {"threadId": "thread-1"}}


@pytest.mark.asyncio
async def test_remote_connect_preserves_initialize_pending_events() -> None:
    # Rust contract: notifications and server requests received before initialize response are queued.
    server_request = {
        "id": "srv-1",
        "method": "item/tool/requestUserInput",
        "params": {"prompt": "Continue?"},
    }
    fake_socket = FakeWebSocket(
        [
            {"method": "thread/started", "params": {"threadId": "thread-1"}},
            server_request,
            {"id": "initialize", "result": {}},
        ]
    )

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert await client.next_event() == AppServerEvent.server_notification(
        {"method": "thread/started", "params": {"threadId": "thread-1"}}
    )
    assert await client.next_event() == AppServerEvent.server_request(server_request)


@pytest.mark.asyncio
async def test_remote_connect_initialize_server_request_resolution_roundtrip() -> None:
    # Rust test: remote_server_request_received_during_initialize_is_delivered.
    server_request = {
        "id": "srv-init",
        "method": "item/tool/requestUserInput",
        "params": {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "itemId": "call-1",
            "questions": [
                {
                    "id": "question-1",
                    "header": "Mode",
                    "question": "Pick one",
                    "isOther": False,
                    "isSecret": False,
                    "options": [],
                }
            ],
        },
    }
    fake_socket = FakeWebSocket([server_request, {"id": "initialize", "result": {}}])

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert await client.next_event() == AppServerEvent.server_request(server_request)
    await client.resolve_server_request("srv-init", {})

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"
    assert sent[1]["method"] == "initialized"
    assert sent[2] == {"id": "srv-init", "result": {}}


@pytest.mark.asyncio
async def test_remote_connect_ignores_non_initialize_responses_during_initialize() -> None:
    # Rust contract: non-matching response/error frames during initialize are ignored while waiting.
    fake_socket = FakeWebSocket(
        [
            {"id": "other-response", "result": {"ignored": True}},
            {
                "id": "other-error",
                "error": {"code": -32000, "message": "ignored initialize-time error"},
            },
            {"id": "initialize", "result": {"userAgent": "codex/9.8.7 extra"}},
        ]
    )

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert client.server_version() == "9.8.7"
    assert await client.next_event() is None
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"
    assert sent[1] == {"method": "initialized"}


@pytest.mark.asyncio
async def test_remote_connect_ignores_non_text_frames_during_initialize() -> None:
    # Rust contract: Binary/Ping/Pong/Frame websocket messages are ignored during initialize.
    fake_socket = FakeWebSocket(
        [
            WebSocketFrame(True, OPCODE_BINARY, b"ignored initialize frame"),
            {"id": "initialize", "result": {"userAgent": "codex/2.0.0"}},
        ]
    )

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert client.server_version() == "2.0.0"
    assert await client.next_event() is None
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"
    assert sent[1] == {"method": "initialized"}


@pytest.mark.asyncio
async def test_remote_connect_maps_initialize_error_to_os_error() -> None:
    # Rust contract: a matching initialize JSON-RPC error rejects connect with endpoint context.
    fake_socket = FakeWebSocket(
        [
            {
                "id": "initialize",
                "error": {"code": -32000, "message": "server refused initialize"},
            },
        ]
    )

    with pytest.raises(
        OSError,
        match="remote app server at `ws://localhost/rpc` rejected initialize: server refused initialize",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: fake_socket,
        )

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent == [
        {
            "id": "initialize",
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "codex-tui", "title": None, "version": "0.1.0"},
                "capabilities": {"experimentalApi": False, "requestAttestation": False},
            },
        }
    ]


@pytest.mark.asyncio
async def test_remote_connect_maps_initialize_close_frame_to_os_error() -> None:
    # Rust contract: a websocket close frame during initialize rejects connect with close reason context.
    fake_socket = FakeWebSocket([WebSocketFrame(True, OPCODE_CLOSE, b"\x03\xe8initializing")])

    with pytest.raises(
        OSError,
        match="remote app server at `ws://localhost/rpc` closed during initialize: initializing",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: fake_socket,
        )

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"


@pytest.mark.asyncio
async def test_remote_connect_maps_initialize_eof_to_os_error() -> None:
    # Rust contract: websocket EOF during initialize rejects connect with closed-during-initialize context.
    fake_socket = FakeWebSocket([])

    with pytest.raises(
        OSError,
        match="remote app server at `ws://localhost/rpc` closed during initialize",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: fake_socket,
        )

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"


@pytest.mark.asyncio
async def test_remote_connect_maps_initialize_transport_failure_to_os_error() -> None:
    # Rust contract: websocket transport failures during initialize reject connect with endpoint context.
    fake_socket = FakeWebSocket([RuntimeError("read exploded")])

    with pytest.raises(
        OSError,
        match="remote app server at `ws://localhost/rpc` transport failed during initialize: read exploded",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: fake_socket,
        )

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"


@pytest.mark.asyncio
async def test_remote_connect_maps_initialize_timeout_to_os_error() -> None:
    # Rust contract: initialize timeout rejects connect with endpoint context.
    fake_socket = FakeWebSocket([{"method": "thread/started", "params": {"threadId": "thread-1"}}])

    with pytest.raises(
        OSError,
        match="timed out waiting for initialize response from `ws://localhost/rpc`",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: fake_socket,
            initialize_max_frames=1,
        )

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"


@pytest.mark.asyncio
async def test_remote_connect_maps_invalid_initialize_jsonrpc_to_os_error() -> None:
    # Rust contract: invalid JSON-RPC text during initialize rejects connect with endpoint context.
    fake_socket = FakeWebSocket([WebSocketFrame(True, OPCODE_TEXT, b"not-json")])

    with pytest.raises(
        OSError,
        match="remote app server at `ws://localhost/rpc` sent invalid initialize response:",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: fake_socket,
        )

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"


@pytest.mark.asyncio
async def test_remote_connect_maps_initialize_write_failure_to_os_error() -> None:
    # Rust contract: failing to write the initialize request rejects connect with endpoint context.
    fake_socket = FakeWebSocket(
        [{"id": "initialize", "result": {}}],
        send_error=RuntimeError("socket refused write"),
        send_error_after=0,
    )

    with pytest.raises(
        OSError,
        match="failed to write websocket message to `ws://localhost/rpc`: socket refused write",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: fake_socket,
        )

    assert fake_socket.sent_text == []


@pytest.mark.asyncio
async def test_remote_connect_maps_initialized_notification_write_failure_to_os_error() -> None:
    # Rust contract: failing to write the initialized notification rejects connect with endpoint context.
    fake_socket = FakeWebSocket(
        [{"id": "initialize", "result": {}}],
        send_error=RuntimeError("initialized write failed"),
        send_error_after=1,
    )

    with pytest.raises(
        OSError,
        match="failed to write websocket message to `ws://localhost/rpc`: initialized write failed",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: fake_socket,
        )

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[0]["method"] == "initialize"


@pytest.mark.asyncio
async def test_remote_connect_rejects_unknown_initialize_server_request() -> None:
    # Rust contract: unknown server requests during initialize are rejected and not queued.
    fake_socket = FakeWebSocket(
        [
            {"id": "srv-1", "method": "unknown/request", "params": {}},
            {"id": "initialize", "result": {}},
            {"method": "thread/started", "params": {"threadId": "thread-1"}},
        ]
    )

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert await client.next_event() == AppServerEvent.server_notification(
        {"method": "thread/started", "params": {"threadId": "thread-1"}}
    )
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[1] == {
        "id": "srv-1",
        "error": {
            "code": -32601,
            "message": "unsupported remote app-server request `unknown/request`",
        },
    }
    assert sent[2]["method"] == "initialized"


@pytest.mark.asyncio
async def test_remote_connect_unix_socket_uses_uds_handshake_url() -> None:
    # Rust contract: Unix socket remotes use the fixed websocket handshake URL over the UDS stream.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}])
    seen: dict[str, object] = {}

    def unix_connector(*args: object, **kwargs: object) -> FakeWebSocket:
        seen["args"] = args
        seen["kwargs"] = kwargs
        return fake_socket

    await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.unix_socket("codex.sock"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        unix_socket_connector=unix_connector,
    )

    assert seen["args"] == ("codex.sock",)
    assert seen["kwargs"] == {
        "websocket_url": UDS_WEBSOCKET_HANDSHAKE_URL,
        "timeout": REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
        "max_message_size": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    }


@pytest.mark.asyncio
async def test_remote_unix_socket_typed_request_roundtrip() -> None:
    # Rust test: remote_unix_socket_typed_request_roundtrip_works.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"id": "req-1", "result": {"account": None, "requiresOpenaiAuth": False}},
        ]
    )

    def unix_connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        return fake_socket

    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.unix_socket("codex.sock"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        unix_socket_connector=unix_connector,
    )

    def account_response(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise TypeError("expected object")
        return {
            "account": value.get("account"),
            "requires_openai_auth": value["requiresOpenaiAuth"],
        }

    request = ClientRequest("GetAccount", request_id="req-1", params={"refreshToken": False})

    assert await client.request_typed(request, decoder=account_response) == {
        "account": None,
        "requires_openai_auth": False,
    }
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[2] == {"id": "req-1", "method": "account/read", "params": {"refreshToken": False}}


@pytest.mark.asyncio
async def test_remote_connect_maps_unix_socket_connector_failure_to_os_error() -> None:
    # Rust contract: Unix socket connect failures keep the unix:// endpoint context in the I/O error.
    def unix_connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        raise RuntimeError("socket missing")

    with pytest.raises(
        OSError,
        match="failed to connect to remote app server at `unix://codex.sock`: socket missing",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.unix_socket("codex.sock"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            unix_socket_connector=unix_connector,
        )


@pytest.mark.asyncio
async def test_remote_connect_maps_unix_socket_connector_timeout_to_os_error() -> None:
    # Rust contract: Unix socket connect timeouts keep the unix:// endpoint context in the I/O error.
    def unix_connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        raise TimeoutError()

    with pytest.raises(
        OSError,
        match="timed out connecting to remote app server at `unix://codex.sock`",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.unix_socket("codex.sock"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            unix_socket_connector=unix_connector,
        )


@pytest.mark.asyncio
async def test_remote_connect_maps_unix_socket_connector_invalid_input_to_os_error() -> None:
    # Rust contract: Unix socket connector invalid-input errors surface directly as connect failures.
    def unix_connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        raise ValueError("invalid UDS websocket handshake URL: invalid authority")

    with pytest.raises(OSError, match="invalid UDS websocket handshake URL"):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.unix_socket("codex.sock"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            unix_socket_connector=unix_connector,
        )


@pytest.mark.asyncio
async def test_remote_connect_rejects_non_loopback_ws_auth_before_connector() -> None:
    # Rust test: remote_connect_rejects_non_loopback_ws_when_auth_configured.
    called = False

    def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        nonlocal called
        called = True
        return FakeWebSocket([{"id": "initialize", "result": {}}])

    with pytest.raises(OSError, match="remote auth tokens require `wss://` or loopback `ws://` URLs"):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket(
                    "ws://example.com:4500",
                    auth_token="remote-bearer-token",
                ),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=connector,
        )

    assert called is False


@pytest.mark.asyncio
async def test_remote_connect_rejects_invalid_websocket_url_before_connector() -> None:
    # Rust contract: invalid websocket URLs fail before connector setup.
    called = False

    def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        nonlocal called
        called = True
        return FakeWebSocket([{"id": "initialize", "result": {}}])

    with pytest.raises(OSError, match="invalid websocket URL `ws://localhost:bad/rpc`"):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost:bad/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=connector,
        )

    assert called is False


@pytest.mark.asyncio
async def test_remote_connect_forwards_safe_websocket_auth_token_to_connector() -> None:
    # Rust contract: supported websocket auth tokens are attached to the websocket connection request.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}])
    seen: dict[str, object] = {}

    def connector(*args: object, **kwargs: object) -> FakeWebSocket:
        seen["args"] = args
        seen["kwargs"] = kwargs
        return fake_socket

    await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("wss://codex.example/rpc", auth_token="token-1"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=connector,
    )

    assert seen["args"] == ("wss://codex.example/rpc",)
    assert seen["kwargs"] == {
        "auth_token": "token-1",
        "timeout": REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
        "max_message_size": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    }


@pytest.mark.asyncio
async def test_remote_connect_forwards_loopback_websocket_auth_token_to_connector() -> None:
    # Rust test: remote_connect_includes_auth_header_when_configured.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}])
    seen: dict[str, object] = {}

    def connector(*args: object, **kwargs: object) -> FakeWebSocket:
        seen["args"] = args
        seen["kwargs"] = kwargs
        return fake_socket

    await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://127.0.0.1:4500/rpc", auth_token="loopback-token"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=connector,
    )

    assert seen["args"] == ("ws://127.0.0.1:4500/rpc",)
    assert seen["kwargs"] == {
        "auth_token": "loopback-token",
        "timeout": REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
        "max_message_size": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    }


@pytest.mark.asyncio
async def test_remote_connect_rejects_invalid_authorization_header_before_connector() -> None:
    # Rust contract: invalid Authorization header values fail before opening the websocket.
    called = False

    def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        nonlocal called
        called = True
        return FakeWebSocket([{"id": "initialize", "result": {}}])

    with pytest.raises(OSError, match="invalid remote authorization header value"):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("wss://codex.example/rpc", auth_token="bad\r\nvalue"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=connector,
        )

    assert called is False


@pytest.mark.asyncio
async def test_remote_connect_maps_connector_timeout_to_os_error() -> None:
    # Rust contract: connect timeouts surface as remote app-server I/O errors.
    def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        raise TimeoutError()

    with pytest.raises(OSError, match="timed out connecting to remote app server at `ws://localhost/rpc`"):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=connector,
        )


@pytest.mark.asyncio
async def test_remote_connect_maps_connector_failure_to_os_error() -> None:
    # Rust contract: non-timeout websocket connect failures keep endpoint context in the I/O error.
    def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        raise RuntimeError("tls handshake failed")

    with pytest.raises(
        OSError,
        match="failed to connect to remote app server at `ws://localhost/rpc`: tls handshake failed",
    ):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=connector,
        )


@pytest.mark.asyncio
async def test_remote_connect_maps_connector_invalid_input_to_os_error() -> None:
    # Rust contract: connector invalid-input errors surface directly as connect failures.
    def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        raise ValueError("invalid websocket URL `ws:// bad`: invalid domain")

    with pytest.raises(OSError, match="invalid websocket URL"):
        await RemoteAppServerClient.connect(
            RemoteAppServerConnectArgs(
                endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                client_name="codex-tui",
                client_version="0.1.0",
            ),
            websocket_connector=connector,
        )


@pytest.mark.asyncio
async def test_remote_wire_client_notifies_resolves_rejects_and_streams_events() -> None:
    # Rust contract: remote worker writes notifications/responses and surfaces server notifications as events.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"method": "thread/started", "params": {"threadId": "thread-1"}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    await client.notify(ClientNotification("Initialized"))
    await client.resolve_server_request("srv-1", {"ok": True})
    await client.reject_server_request("srv-2", {"code": -32601, "message": "unsupported", "data": None})
    event = await client.next_event()

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[2] == {"method": "initialized"}
    assert sent[3] == {"id": "srv-1", "result": {"ok": True}}
    assert sent[4] == {"id": "srv-2", "error": {"code": -32601, "message": "unsupported"}}
    assert event == AppServerEvent.server_notification(
        {"method": "thread/started", "params": {"threadId": "thread-1"}}
    )
    assert event.kind == AppServerEventKind.SERVER_NOTIFICATION


@pytest.mark.asyncio
async def test_remote_wire_notify_write_failure_maps_to_os_error() -> None:
    # Rust contract: notification write failures are reported to the caller as I/O errors.
    fake_socket = FakeWebSocket(
        [{"id": "initialize", "result": {}}],
        send_error=RuntimeError("disk full"),
        send_error_after=2,
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    with pytest.raises(OSError, match="failed to write websocket message to `ws://localhost/rpc`: disk full"):
        await client.notify(ClientNotification("Initialized"))


@pytest.mark.asyncio
async def test_remote_wire_server_request_response_write_failure_maps_to_os_error() -> None:
    # Rust contract: server-request resolve/reject write failures are reported as I/O errors.
    fake_socket = FakeWebSocket(
        [{"id": "initialize", "result": {}}],
        send_error=RuntimeError("socket gone"),
        send_error_after=2,
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    with pytest.raises(OSError, match="failed to write websocket message to `ws://localhost/rpc`: socket gone"):
        await client.resolve_server_request("srv-1", {"ok": True})

    reject_socket = FakeWebSocket(
        [{"id": "initialize", "result": {}}],
        send_error=RuntimeError("socket gone"),
        send_error_after=2,
    )
    reject_client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: reject_socket,
    )

    with pytest.raises(OSError, match="failed to write websocket message to `ws://localhost/rpc`: socket gone"):
        await reject_client.reject_server_request("srv-1", {"code": -32603, "message": "failed"})


@pytest.mark.asyncio
async def test_remote_wire_ignores_non_text_websocket_frames() -> None:
    # Rust contract: Binary/Ping/Pong/Frame websocket messages are ignored by the remote worker.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            WebSocketFrame(True, OPCODE_BINARY, b"\x00\x01"),
            {"method": "thread/started", "params": {"threadId": "thread-1"}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert await client.next_event() == AppServerEvent.server_notification(
        {"method": "thread/started", "params": {"threadId": "thread-1"}}
    )


@pytest.mark.asyncio
async def test_remote_wire_invalid_jsonrpc_text_streams_disconnected_event() -> None:
    # Rust contract: invalid runtime JSON-RPC text is surfaced as a Disconnected event.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            WebSocketFrame(True, OPCODE_TEXT, b"not-json"),
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    event = await client.next_event()

    assert event is not None
    assert event.kind == AppServerEventKind.DISCONNECTED
    assert event.message is not None
    assert "sent invalid JSON-RPC" in event.message


@pytest.mark.asyncio
async def test_remote_wire_close_frame_streams_disconnected_event() -> None:
    # Rust contract: websocket close frames stream a Disconnected event with the close reason.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            WebSocketFrame(True, OPCODE_CLOSE, b"\x03\xe8done"),
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    event = await client.next_event()

    assert event == AppServerEvent.disconnected("remote app server at `ws://localhost/rpc` disconnected: done")


@pytest.mark.asyncio
async def test_remote_wire_disconnect_surfaces_as_event_with_default_close_message() -> None:
    # Rust test: remote_disconnect_surfaces_as_event.
    # Rust contract: websocket close frames without a reason use "connection closed".
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            WebSocketFrame(True, OPCODE_CLOSE, b""),
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    event = await client.next_event()

    assert event == AppServerEvent.disconnected(
        "remote app server at `ws://localhost/rpc` disconnected: connection closed"
    )


@pytest.mark.asyncio
async def test_remote_wire_eof_streams_closed_connection_event() -> None:
    # Rust contract: websocket EOF streams a Disconnected event with the closed-connection message.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}])
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    event = await client.next_event()

    assert event == AppServerEvent.disconnected("remote app server at `ws://localhost/rpc` closed the connection")


@pytest.mark.asyncio
async def test_remote_wire_transport_failure_streams_disconnected_event() -> None:
    # Rust contract: websocket transport errors stream a Disconnected event with the transport-failed message.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            TimeoutError("slow read"),
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    event = await client.next_event()

    assert event is not None
    assert event.kind == AppServerEventKind.DISCONNECTED
    assert event.message is not None
    assert "remote app server at `ws://localhost/rpc` transport failed: slow read" in event.message


@pytest.mark.asyncio
async def test_remote_wire_unknown_server_notification_is_ignored() -> None:
    # Rust contract: notifications that do not parse as ServerNotification are ignored and streaming continues.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"method": "unknown/notification", "params": {}},
            {"method": "thread/started", "params": {"threadId": "thread-1"}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert await client.next_event() == AppServerEvent.server_notification(
        {"method": "thread/started", "params": {"threadId": "thread-1"}}
    )


@pytest.mark.asyncio
async def test_remote_wire_account_updated_notification_arrives_over_websocket() -> None:
    # Rust test: remote_notifications_arrive_over_websocket.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"method": "account/updated", "params": {"authMode": None, "planType": None}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert await client.next_event() == AppServerEvent.server_notification(
        {"method": "account/updated", "params": {"authMode": None, "planType": None}}
    )


@pytest.mark.asyncio
async def test_remote_wire_transcript_notifications_stream_in_order() -> None:
    # Rust source: remote_backpressure_preserves_transcript_notifications notification set.
    notifications = [
        {
            "method": "item/commandExecution/outputDelta",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1", "delta": "stdout-1"},
        },
        {
            "method": "item/commandExecution/outputDelta",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1", "delta": "stdout-2"},
        },
        {
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-2", "delta": "hello"},
        },
        {
            "method": "item/completed",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "completedAtMs": 0,
                "item": {"type": "agentMessage", "id": "item-2", "text": "hello"},
            },
        },
        {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}},
        },
    ]
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}, *notifications])
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    received = [await client.next_event() for _ in notifications]

    assert received == [AppServerEvent.server_notification(notification) for notification in notifications]
    assert [event.payload["method"] for event in received if event is not None] == [
        "item/commandExecution/outputDelta",
        "item/commandExecution/outputDelta",
        "item/agentMessage/delta",
        "item/completed",
        "turn/completed",
    ]


@pytest.mark.asyncio
async def test_remote_wire_supported_server_request_streams_event() -> None:
    # Rust contract: supported JSON-RPC requests from the server become ServerRequest events.
    server_request = {
        "id": "srv-1",
        "method": "item/tool/requestUserInput",
        "params": {"prompt": "Continue?"},
    }
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            server_request,
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    event = await client.next_event()

    assert event == AppServerEvent.server_request(server_request)
    assert event.kind == AppServerEventKind.SERVER_REQUEST


@pytest.mark.asyncio
async def test_remote_wire_server_request_resolution_roundtrip() -> None:
    # Rust test: remote_server_request_resolution_roundtrip_works.
    server_request = {
        "id": "srv-1",
        "method": "item/tool/requestUserInput",
        "params": {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "itemId": "call-1",
            "questions": [
                {
                    "id": "question-1",
                    "header": "Mode",
                    "question": "Pick one",
                    "isOther": False,
                    "isSecret": False,
                    "options": [],
                }
            ],
        },
    }
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}, server_request])
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    event = await client.next_event()
    assert event == AppServerEvent.server_request(server_request)

    await client.resolve_server_request("srv-1", {})

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[2] == {"id": "srv-1", "result": {}}


@pytest.mark.asyncio
async def test_remote_wire_unknown_server_request_is_rejected() -> None:
    # Rust contract: unsupported remote server requests are rejected with JSON-RPC -32601 and streaming continues.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"id": "srv-1", "method": "unknown/request", "params": {}},
            {"method": "thread/started", "params": {"threadId": "thread-1"}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert await client.next_event() == AppServerEvent.server_notification(
        {"method": "thread/started", "params": {"threadId": "thread-1"}}
    )

    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[-1] == {
        "id": "srv-1",
        "error": {
            "code": -32601,
            "message": "unsupported remote app-server request `unknown/request`",
        },
    }


@pytest.mark.asyncio
async def test_remote_wire_thread_unknown_server_request_is_rejected() -> None:
    # Rust test: remote_unknown_server_request_is_rejected.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"id": "srv-unknown", "method": "thread/unknown"},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    assert await client.next_event() is None
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[2] == {
        "id": "srv-unknown",
        "error": {
            "code": -32601,
            "message": "unsupported remote app-server request `thread/unknown`",
        },
    }


@pytest.mark.asyncio
async def test_remote_wire_unknown_server_request_reject_write_failure_streams_disconnected_event() -> None:
    # Rust contract: failed unknown-request rejection writes deliver a Disconnected event.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"id": "srv-1", "method": "unknown/request", "params": {}},
        ],
        send_error=RuntimeError("pipe closed"),
        send_error_after=2,
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    event = await client.next_event()

    assert event is not None
    assert event.kind == AppServerEventKind.DISCONNECTED
    assert event.message is not None
    assert (
        "remote app server at `ws://localhost/rpc` write failed: "
        "failed to write websocket message to `ws://localhost/rpc`: pipe closed"
    ) in event.message


@pytest.mark.asyncio
async def test_remote_wire_request_error_maps_to_typed_request_error() -> None:
    # Rust contract: JSON-RPC error responses are RequestResult::Err and request_typed maps them to Server.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"id": "req-1", "error": {"code": -32602, "message": "bad params", "data": {"field": "x"}}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    with pytest.raises(TypedRequestError) as error_info:
        await client.request_typed(request)

    error = error_info.value
    assert error.kind == "server"
    assert error.method == "thread/read"
    assert "bad params" in str(error)
    assert "code -32602" in str(error)


@pytest.mark.asyncio
async def test_remote_wire_request_preserves_interleaved_notification_event() -> None:
    # Rust contract: notifications received while a request is pending are delivered without blocking the response.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"method": "thread/started", "params": {"threadId": "thread-1"}},
            {"id": "req-1", "result": {"ok": True}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert await client.request(request) == {"ok": True}
    assert await client.next_event() == AppServerEvent.server_notification(
        {"method": "thread/started", "params": {"threadId": "thread-1"}}
    )


@pytest.mark.asyncio
async def test_remote_wire_request_ignores_interleaved_unknown_notification() -> None:
    # Rust contract: unknown notifications received while a request is pending are ignored.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"method": "unknown/notification", "params": {}},
            {"id": "req-1", "result": {"ok": True}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert await client.request(request) == {"ok": True}
    assert await client.next_event() is None


@pytest.mark.asyncio
async def test_remote_wire_request_preserves_interleaved_server_request_event() -> None:
    # Rust contract: server requests received while a request is pending are delivered without blocking the response.
    server_request = {
        "id": "srv-1",
        "method": "item/tool/requestUserInput",
        "params": {"prompt": "Continue?"},
    }
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            server_request,
            {"id": "req-1", "result": {"ok": True}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert await client.request(request) == {"ok": True}
    assert await client.next_event() == AppServerEvent.server_request(server_request)


@pytest.mark.asyncio
async def test_remote_wire_request_rejects_interleaved_unknown_server_request() -> None:
    # Rust contract: unknown server requests received while a request is pending are rejected without blocking response.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"id": "srv-1", "method": "unknown/request", "params": {}},
            {"id": "req-1", "result": {"ok": True}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert await client.request(request) == {"ok": True}
    assert await client.next_event() is None
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[-1] == {
        "id": "srv-1",
        "error": {
            "code": -32601,
            "message": "unsupported remote app-server request `unknown/request`",
        },
    }


@pytest.mark.asyncio
async def test_remote_wire_request_typed_decodes_response_or_reports_deserialize_error() -> None:
    # Rust contract: request_typed deserializes successful JSON results and maps decode errors to Deserialize.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {"id": "req-1", "result": {"thread": {"id": "thread-1"}}},
            {"id": "req-2", "result": {"thread": {}}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    def thread_id(value: object) -> str:
        if not isinstance(value, dict):
            raise TypeError("expected object")
        thread = value["thread"]
        if not isinstance(thread, dict):
            raise TypeError("expected thread object")
        return str(thread["id"])

    request_1 = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})
    request_2 = ClientRequest("ThreadRead", request_id="req-2", params={"threadId": "thread-2"})

    assert await client.request_typed(request_1, decoder=thread_id) == "thread-1"

    with pytest.raises(TypedRequestError) as error_info:
        await client.request_typed(request_2, decoder=thread_id)

    error = error_info.value
    assert error.kind == "deserialize"
    assert error.method == "thread/read"
    assert "response decode error" in str(error)


@pytest.mark.asyncio
async def test_remote_wire_typed_request_roundtrip_get_account() -> None:
    # Rust test: remote_typed_request_roundtrip_works.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {"userAgent": "codex/9.8.7-test"}},
            {"id": "req-1", "result": {"account": None, "requiresOpenaiAuth": False}},
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    def account_response(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise TypeError("expected object")
        return {
            "account": value.get("account"),
            "requires_openai_auth": value["requiresOpenaiAuth"],
        }

    request = ClientRequest("GetAccount", request_id="req-1", params={"refreshToken": False})

    assert client.server_version() == "9.8.7-test"
    assert await client.request_typed(request, decoder=account_response) == {
        "account": None,
        "requires_openai_auth": False,
    }
    sent = [json.loads(payload) for payload in fake_socket.sent_text]
    assert sent[2] == {"id": "req-1", "method": "account/read", "params": {"refreshToken": False}}


@pytest.mark.asyncio
async def test_remote_wire_request_typed_accepts_large_single_frame_response() -> None:
    # Rust test: remote_typed_request_accepts_large_single_frame_response.
    padding = "x" * ((17 << 20) + 1024)
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            {
                "id": "req-1",
                "result": {
                    "account": None,
                    "requiresOpenaiAuth": False,
                    "padding": padding,
                },
            },
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    def account_response(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise TypeError("expected object")
        return {
            "account": value.get("account"),
            "requires_openai_auth": value["requiresOpenaiAuth"],
        }

    request = ClientRequest("GetAccount", request_id="req-1", params={"refreshToken": False})

    assert await client.request_typed(request, decoder=account_response) == {
        "account": None,
        "requires_openai_auth": False,
    }


@pytest.mark.asyncio
async def test_remote_wire_request_typed_transport_error_maps_to_typed_error() -> None:
    # Rust contract: request_typed maps request transport failures to TypedRequestError::Transport.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}])
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    with pytest.raises(TypedRequestError) as error_info:
        await client.request_typed(request)

    error = error_info.value
    assert error.kind == "transport"
    assert error.method == "thread/read"
    assert "remote app server at `ws://localhost/rpc` closed" in str(error)


@pytest.mark.asyncio
async def test_remote_wire_request_write_failure_maps_to_os_error_and_disconnect_event() -> None:
    # Rust contract: request write failures report an I/O error and deliver a Disconnected event.
    fake_socket = FakeWebSocket(
        [{"id": "initialize", "result": {}}],
        send_error=RuntimeError("pipe closed"),
        send_error_after=2,
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    with pytest.raises(OSError, match="failed to write websocket message to `ws://localhost/rpc`: pipe closed"):
        await client.request(request)

    event = await client.next_event()
    assert event is not None
    assert event.kind == AppServerEventKind.DISCONNECTED
    assert event.message is not None
    assert (
        "remote app server at `ws://localhost/rpc` write failed: "
        "failed to write websocket message to `ws://localhost/rpc`: pipe closed"
    ) in event.message


@pytest.mark.asyncio
async def test_remote_wire_duplicate_request_id_maps_to_transport_error() -> None:
    # Rust test: remote_duplicate_request_id_keeps_original_waiter
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}])
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )
    request = ClientRequest("GetAccount", request_id="req-1", params={"refreshToken": False})

    client._wire_client.send_request(ExecClientRequest("account/read", {"refreshToken": False}, "req-1"))
    sent_before_duplicate = list(fake_socket.sent_text)
    with pytest.raises(TypedRequestError) as error_info:
        await client.request_typed(request)

    error = error_info.value
    assert error.kind == "transport"
    assert error.method == "account/read"
    assert "duplicate remote app-server request id `req-1`" in str(error)
    assert fake_socket.sent_text == sent_before_duplicate

    fake_socket.frames.append({"id": "req-1", "result": {"account": None, "requiresOpenaiAuth": False}})
    first_response = client._wire_client._read_socket_step()
    assert first_response.response_id == "req-1"
    assert first_response.response_result == {"account": None, "requiresOpenaiAuth": False}


@pytest.mark.asyncio
async def test_remote_wire_request_disconnect_maps_to_os_error_and_disconnect_event() -> None:
    # Rust contract: transport failures surface as remote app-server I/O errors and a Disconnected event.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}])
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    with pytest.raises(OSError, match="remote app server at `ws://localhost/rpc` closed"):
        await client.request(request)

    event = await client.next_event()
    assert event == AppServerEvent.disconnected("remote app server at `ws://localhost/rpc` closed the connection")


@pytest.mark.asyncio
async def test_remote_wire_request_transport_failure_maps_to_os_error_and_disconnect_event() -> None:
    # Rust contract: request-time transport failures report an I/O error and queue a Disconnected event.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}, TimeoutError("slow read")])
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    with pytest.raises(OSError, match="remote app server at `ws://localhost/rpc` transport failed: slow read"):
        await client.request(request)

    event = await client.next_event()
    assert event is not None
    assert event.kind == AppServerEventKind.DISCONNECTED
    assert event.message is not None
    assert "remote app server at `ws://localhost/rpc` transport failed: slow read" in event.message


@pytest.mark.asyncio
async def test_remote_wire_request_close_frame_maps_to_os_error_and_disconnect_event() -> None:
    # Rust contract: request-time close frames report an I/O error and queue a Disconnected event.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            WebSocketFrame(True, OPCODE_CLOSE, b"\x03\xe8done"),
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    with pytest.raises(OSError, match="remote app server at `ws://localhost/rpc` disconnected: done"):
        await client.request(request)

    event = await client.next_event()
    assert event == AppServerEvent.disconnected("remote app server at `ws://localhost/rpc` disconnected: done")


@pytest.mark.asyncio
async def test_remote_wire_request_invalid_jsonrpc_maps_to_os_error_and_disconnect_event() -> None:
    # Rust contract: request-time invalid JSON-RPC reports an I/O error and queues a Disconnected event.
    fake_socket = FakeWebSocket(
        [
            {"id": "initialize", "result": {}},
            WebSocketFrame(True, OPCODE_TEXT, b"not-json"),
        ]
    )
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    with pytest.raises(OSError, match="sent invalid JSON-RPC"):
        await client.request(request)

    event = await client.next_event()
    assert event is not None
    assert event.kind == AppServerEventKind.DISCONNECTED
    assert event.message is not None
    assert "sent invalid JSON-RPC" in event.message


@pytest.mark.asyncio
async def test_remote_shutdown_maps_close_error_to_os_error() -> None:
    # Rust contract: shutdown reports close errors that are not already-closed style errors.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}], close_error=RuntimeError("tls alert"))
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    with pytest.raises(OSError, match="failed to close websocket app server `ws://localhost/rpc`: tls alert"):
        await client.shutdown()


@pytest.mark.asyncio
async def test_remote_shutdown_tolerates_already_closed_close_error() -> None:
    # Rust contract: shutdown treats already-closed websocket close errors as successful close.
    fake_socket = FakeWebSocket([{"id": "initialize", "result": {}}], close_error=BrokenPipeError("closed"))
    client = await RemoteAppServerClient.connect(
        RemoteAppServerConnectArgs(
            endpoint=RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            client_name="codex-tui",
            client_version="0.1.0",
        ),
        websocket_connector=lambda *_args, **_kwargs: fake_socket,
    )

    await client.shutdown()
    assert fake_socket.closed is True


@pytest.mark.asyncio
async def test_remote_shutdown_tolerates_connection_reset_close_error_from_wire_client() -> None:
    # Rust contract: websocket_close_error_is_already_closed treats ConnectionReset as successful close.
    class ResetOnCloseWireClient:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True
            raise ConnectionResetError("reset by peer")

    wire_client = ResetOnCloseWireClient()
    client = RemoteAppServerClient(wire_client=wire_client)

    await client.shutdown()
    assert wire_client.closed is True
