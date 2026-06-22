from pycodex.app_server.transport import (
    ConnectionStateProjection,
    DisconnectConnectionProjection,
    OutboundConnectionStateProjection,
    OutgoingEnvelopeProjection,
    RouteOutgoingEnvelopeProjection,
    TransportReexportSurfaceProjection,
    connection_state_projection,
    disconnect_connection_projection,
    filter_outgoing_message_for_connection,
    route_outgoing_envelope_projection,
    should_skip_notification_for_connection,
    transport_reexport_surface_projection,
)


def _notification(method: str, *, experimental_reason: str | None = None) -> dict[str, object]:
    return {
        "kind": "AppServerNotification",
        "method": method,
        "experimental_reason": experimental_reason,
    }


def _approval_request(**params: object) -> dict[str, object]:
    return {
        "kind": "Request",
        "request": "CommandExecutionRequestApproval",
        "params": {
            "threadId": "thr_123",
            "turnId": "turn_123",
            "itemId": "call_123",
            **params,
        },
    }


def test_transport_reexport_surface_projection_matches_rust_use_declarations() -> None:
    # Rust: transport.rs re-exports the app-server-transport surface locally.
    projection = transport_reexport_surface_projection()

    assert projection == TransportReexportSurfaceProjection(
        public_reexports=(
            "AppServerTransport",
            "app_server_control_socket_path",
            "auth",
        ),
        crate_reexports=(
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
        ),
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


def test_connection_state_projection_ignores_origin_and_creates_session() -> None:
    # Rust: ConnectionState::new ignores origin and creates a fresh ConnectionSessionState.
    projection = connection_state_projection(
        origin="websocket",
        outbound_initialized=False,
        outbound_experimental_api_enabled=True,
        outbound_opted_out_notification_methods={"configWarning"},
    )

    assert projection == ConnectionStateProjection(
        origin_ignored=True,
        outbound_initialized=False,
        outbound_experimental_api_enabled=True,
        outbound_opted_out_notification_methods=frozenset({"configWarning"}),
        creates_new_session=True,
    )


def test_disconnect_connection_projection_removes_and_cancels_when_present() -> None:
    # Rust: disconnect_connection removes known connections and requests disconnect.
    projection = disconnect_connection_projection(
        {
            "conn-1": OutboundConnectionStateProjection(disconnect_sender_present=True),
            "conn-2": OutboundConnectionStateProjection(disconnect_sender_present=False),
        },
        "conn-1",
    )

    assert projection == DisconnectConnectionProjection(
        removed=True,
        requested_disconnect=True,
        remaining_connection_ids=("conn-2",),
    )


def test_disconnect_connection_projection_reports_missing_connection() -> None:
    # Rust: disconnect_connection returns false without side effects for unknown IDs.
    projection = disconnect_connection_projection(
        {"conn-2": OutboundConnectionStateProjection(disconnect_sender_present=False)},
        "conn-1",
    )

    assert projection == DisconnectConnectionProjection(
        removed=False,
        requested_disconnect=False,
        remaining_connection_ids=("conn-2",),
    )


def test_transport_opted_out_notification_is_skipped() -> None:
    # Rust: to_connection_notifications_are_dropped_for_opted_out_clients.
    state = OutboundConnectionStateProjection(
        initialized=True,
        experimental_api_enabled=True,
        opted_out_notification_methods=frozenset({"configWarning"}),
    )

    skip, warnings = should_skip_notification_for_connection(
        state,
        _notification("configWarning"),
    )

    assert skip is True
    assert warnings == ()


def test_transport_experimental_notification_requires_capability() -> None:
    # Rust: experimental_notifications_are_dropped_without_capability.
    state = OutboundConnectionStateProjection(
        initialized=True,
        experimental_api_enabled=False,
    )

    skip, warnings = should_skip_notification_for_connection(
        state,
        _notification(
            "thread/realtime/started",
            experimental_reason="thread/realtime/started",
        ),
    )

    assert skip is True
    assert warnings == ()


def test_transport_unreadable_opt_outs_warn_and_do_not_skip() -> None:
    # Rust: opted-out RwLock read failure warns and returns false.
    state = OutboundConnectionStateProjection(
        initialized=True,
        experimental_api_enabled=True,
        opted_out_readable=False,
        opted_out_notification_methods=frozenset({"configWarning"}),
    )

    skip, warnings = should_skip_notification_for_connection(
        state,
        _notification("configWarning"),
    )

    assert skip is False
    assert warnings == ("failed to read outbound opted-out notifications",)


def test_transport_filters_approval_experimental_fields_without_capability() -> None:
    # Rust: CommandExecutionRequestApprovalParams::strip_experimental_fields.
    state = OutboundConnectionStateProjection(experimental_api_enabled=False)

    filtered = filter_outgoing_message_for_connection(
        state,
        _approval_request(
            additionalPermissions={"fileSystem": {"read": ["/tmp/allowed"]}},
            availableDecisions=["allow"],
        ),
    )

    assert "additionalPermissions" not in filtered["params"]
    # Rust currently strips only additional_permissions in this call site.
    assert filtered["params"]["availableDecisions"] == ["allow"]


def test_transport_keeps_approval_experimental_fields_with_capability() -> None:
    # Rust: command_execution_request_approval_keeps_additional_permissions_with_capability.
    state = OutboundConnectionStateProjection(experimental_api_enabled=True)
    message = _approval_request(
        additionalPermissions={"fileSystem": {"read": ["/tmp/allowed"]}},
    )

    assert filter_outgoing_message_for_connection(state, message) is message


def test_route_to_connection_drops_unknown_connection() -> None:
    # Rust: send_message_to_connection warns and returns false for disconnected IDs.
    projection = route_outgoing_envelope_projection(
        {},
        OutgoingEnvelopeProjection.to_connection("conn-1", _notification("configWarning")),
    )

    assert projection == RouteOutgoingEnvelopeProjection(
        dropped_connection_ids=("conn-1",),
        remaining_connection_ids=(),
        warnings=("dropping message for disconnected connection: 'conn-1'",),
    )


def test_route_broadcast_targets_initialized_non_filtered_connections() -> None:
    # Rust: Broadcast collects initialized connections that do not skip the notification.
    projection = route_outgoing_envelope_projection(
        {
            "ready": OutboundConnectionStateProjection(
                initialized=True,
                experimental_api_enabled=True,
                writer_queue_capacity=2,
            ),
            "not-initialized": OutboundConnectionStateProjection(
                initialized=False,
                experimental_api_enabled=True,
            ),
            "opted-out": OutboundConnectionStateProjection(
                initialized=True,
                experimental_api_enabled=True,
                opted_out_notification_methods=frozenset({"configWarning"}),
            ),
        },
        OutgoingEnvelopeProjection.broadcast(_notification("configWarning")),
    )

    assert projection.delivered_connection_ids == ("ready",)
    assert projection.dropped_connection_ids == ()
    assert projection.remaining_connection_ids == ("ready", "not-initialized", "opted-out")


def test_route_broadcast_disconnects_slow_disconnectable_connection() -> None:
    # Rust: broadcast_does_not_block_on_slow_connection.
    projection = route_outgoing_envelope_projection(
        {
            "fast": OutboundConnectionStateProjection(
                initialized=True,
                experimental_api_enabled=True,
                writer_queue_capacity=1,
                writer_queue_size=0,
                disconnect_sender_present=True,
            ),
            "slow": OutboundConnectionStateProjection(
                initialized=True,
                experimental_api_enabled=True,
                writer_queue_capacity=1,
                writer_queue_size=1,
                disconnect_sender_present=True,
            ),
        },
        OutgoingEnvelopeProjection.broadcast(_notification("configWarning")),
    )

    assert projection.delivered_connection_ids == ("fast",)
    assert projection.disconnected_connection_ids == ("slow",)
    assert projection.remaining_connection_ids == ("fast",)
    assert projection.warnings == (
        "disconnecting slow connection after outbound queue filled: 'slow'",
    )


def test_route_to_connection_stdio_waits_instead_of_disconnecting_when_full() -> None:
    # Rust: to_connection_stdio_waits_instead_of_disconnecting_when_writer_queue_is_full.
    projection = route_outgoing_envelope_projection(
        {
            "stdio": OutboundConnectionStateProjection(
                initialized=True,
                experimental_api_enabled=True,
                writer_queue_capacity=1,
                writer_queue_size=1,
                disconnect_sender_present=False,
            ),
        },
        OutgoingEnvelopeProjection.to_connection(
            "stdio",
            _notification("configWarning"),
            write_complete_tx=True,
        ),
    )

    assert projection.delivered_connection_ids == ("stdio",)
    assert projection.waited_for_capacity_connection_ids == ("stdio",)
    assert projection.disconnected_connection_ids == ()
    assert projection.write_complete_connection_ids == ("stdio",)
