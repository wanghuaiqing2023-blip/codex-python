from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pycodex.app_server_client import (
    AppServerClient,
    AppServerClientNotImplementedError,
    AppServerEvent,
    AppServerEventKind,
    DEFAULT_IN_PROCESS_CHANNEL_CAPACITY,
    EnvironmentManager,
    ExecServerRuntimePaths,
    ForwardEventResult,
    InProcessCommandChannelBackpressureProjection,
    InProcessCommandEntrypointProjection,
    InProcessAppServerClient,
    InProcessClientCommandProjection,
    InProcessClientStartArgs,
    InProcessNextEventProjection,
    InProcessRequestHandleProjection,
    InProcessRequestResponseProjection,
    InProcessRuntimeDependencyProjection,
    InProcessShutdownEntrypointProjection,
    InProcessShutdownProjection,
    InProcessWorkerRequestTaskProjection,
    InProcessServerEvent,
    InProcessWorkerCommandProjection,
    InProcessWorkerEventProjection,
    InProcessWorkerSelectTimingProjection,
    InProcessWorkerTopologyProjection,
    RemoteAppServerClient,
    SHUTDOWN_TIMEOUT_SECONDS,
    StateDbHandle,
    TypedRequestError,
    app_server_control_socket_path,
    event_requires_delivery,
    in_process_command_channel_backpressure_projection,
    in_process_command_entrypoint_projection,
    in_process_next_event_projection,
    in_process_request_response_projection,
    in_process_request_handle_projection,
    in_process_runtime_dependency_projection,
    in_process_shutdown_entrypoint_projection,
    in_process_shutdown_projection,
    in_process_worker_request_task_projection,
    in_process_unsupported_server_request_error,
    in_process_worker_command_projection,
    in_process_worker_event_projection,
    in_process_worker_select_timing_projection,
    in_process_worker_topology_projection,
    into_app_server_in_process_start_args,
    project_in_process_event_forwarding,
    request_method_name,
    server_notification_requires_delivery,
)
from pycodex.app_server_client import legacy_core
from pycodex.app_server.error_code import (
    INTERNAL_ERROR_CODE,
    INVALID_REQUEST_ERROR_CODE,
    OVERLOADED_ERROR_CODE,
)
from pycodex.app_server.in_process import InProcessRuntimeProjection
from pycodex.app_server_protocol import ClientRequest, JSONRPCErrorError, ServerNotification, ServerRequest
from pycodex.core import state_db_bridge
from pycodex import exec_server
from pycodex.config import (
    NoopThreadConfigLoader,
    RemoteThreadConfigLoader,
    ThreadConfigContext,
    ThreadConfigLoadError,
    ThreadConfigLoadErrorCode,
)


def test_initialize_params_matches_rust_shape() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: initialize_params builds client info and capabilities.
    args = InProcessClientStartArgs(
        arg0_paths=object(),
        config=object(),
        client_name="codex-app-server-client-test",
        client_version="0.0.0-test",
        experimental_api=True,
        opt_out_notification_methods=[],
    )

    assert args.initialize_params() == {
        "client_info": {
            "name": "codex-app-server-client-test",
            "title": None,
            "version": "0.0.0-test",
        },
        "capabilities": {
            "experimental_api": True,
            "request_attestation": False,
            "opt_out_notification_methods": None,
        },
    }

    args.opt_out_notification_methods = ["turn/delta", "thread/item/completed"]
    params = args.initialize_params()

    assert params["capabilities"]["opt_out_notification_methods"] == [
        "turn/delta",
        "thread/item/completed",
    ]
    args.opt_out_notification_methods.append("later")
    assert params["capabilities"]["opt_out_notification_methods"] == [
        "turn/delta",
        "thread/item/completed",
    ]


def test_shutdown_timeout_constant_matches_rust_module_boundary() -> None:
    # Rust source: app-server-client/src/lib.rs SHUTDOWN_TIMEOUT = Duration::from_secs(5).
    assert SHUTDOWN_TIMEOUT_SECONDS == 5


def test_in_process_runtime_dependency_projection_tracks_app_server_owner() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: InProcessAppServerClient::start delegates embedded runtime ownership to codex-app-server.
    assert in_process_runtime_dependency_projection() == InProcessRuntimeDependencyProjection(
        client_crate_module="codex-app-server-client/src/lib.rs",
        runtime_owner_crate="codex-app-server",
        runtime_owner_python_package="pycodex.app_server",
        rust_runtime_function="codex_app_server::run_app_server",
        python_runtime_entrypoint="pycodex.app_server.run_main_with_transport_options",
        runtime_package_exists=True,
        full_runtime_complete=False,
        client_should_fabricate_runtime=False,
    )


def test_in_process_worker_topology_projection_matches_rust_start_loop() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: start creates bounded command/event channels and spawns a two-arm worker loop.
    assert in_process_worker_topology_projection(0) == InProcessWorkerTopologyProjection(
        starts_runtime_handle=True,
        runtime_start_function="codex_app_server::in_process::start",
        request_sender_source="InProcessClientHandle::sender()",
        command_channel_type="mpsc::channel<ClientCommand>",
        event_channel_type="mpsc::channel<InProcessServerEvent>",
        channel_capacity=1,
        owns_command_sender=True,
        owns_event_receiver=True,
        owns_worker_handle=True,
        worker_initial_event_stream_enabled=True,
        worker_initial_skipped_events=0,
        select_arms=("command_rx.recv()", "handle.next_event()"),
        event_arm_guard="event_stream_enabled",
        returns_worker_backed_client=True,
    )


def test_in_process_worker_select_timing_projection_matches_unbiased_select_contract() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: worker loop uses an unbiased tokio::select! with event_stream_enabled guarding events.
    assert in_process_worker_select_timing_projection(
        command_ready=False,
        event_ready=True,
        event_stream_enabled=False,
    ) == InProcessWorkerSelectTimingProjection(
        select_macro="tokio::select!",
        biased=False,
        command_ready=False,
        event_ready=True,
        event_stream_enabled=False,
        event_arm_enabled=False,
        awaits_progress=True,
        selected_branch=None,
        selected_branch_is_deterministic=False,
        simultaneous_ready_order_is_unspecified=False,
        selection_guarantee="worker awaits command_rx.recv() or an enabled handle.next_event()",
        python_executes_scheduler=False,
    )

    assert in_process_worker_select_timing_projection(
        command_ready=True,
        event_ready=False,
    ).selected_branch == "command_rx.recv()"
    assert in_process_worker_select_timing_projection(
        command_ready=False,
        event_ready=True,
    ).selected_branch == "handle.next_event()"

    both_ready = in_process_worker_select_timing_projection(
        command_ready=True,
        event_ready=True,
    )
    assert both_ready.selected_branch is None
    assert both_ready.biased is False
    assert both_ready.simultaneous_ready_order_is_unspecified is True
    assert both_ready.selection_guarantee == (
        "unbiased tokio::select! does not promise stable branch order"
    )


def test_in_process_command_channel_backpressure_projection_matches_rust_sender_boundary() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: start creates bounded ClientCommand channel and public senders await capacity.
    projection = in_process_command_channel_backpressure_projection(
        ["Request", "Notify", "Shutdown"],
        channel_capacity=2,
        initially_queued=1,
    )

    assert projection == InProcessCommandChannelBackpressureProjection(
        command_channel_type="mpsc::channel<ClientCommand>",
        capacity=2,
        initially_queued=1,
        receiver_open=True,
        commands_sent_without_wait=("Request",),
        commands_waiting_for_capacity=("Notify", "Shutdown"),
        send_waits_when_full=True,
        send_fails_only_when_receiver_closed=True,
        send_error_message=None,
        event_channel_type="mpsc::channel<InProcessServerEvent>",
        event_channel_bounded=True,
        event_channel_capacity=2,
        event_backpressure_handler="forward_in_process_event",
    )

    assert in_process_command_channel_backpressure_projection(
        ["Request"],
        channel_capacity=0,
        receiver_open=False,
    ) == InProcessCommandChannelBackpressureProjection(
        command_channel_type="mpsc::channel<ClientCommand>",
        capacity=1,
        initially_queued=0,
        receiver_open=False,
        commands_sent_without_wait=(),
        commands_waiting_for_capacity=(),
        send_waits_when_full=True,
        send_fails_only_when_receiver_closed=True,
        send_error_message="in-process app-server worker channel is closed",
        event_channel_type="mpsc::channel<InProcessServerEvent>",
        event_channel_bounded=True,
        event_channel_capacity=1,
        event_backpressure_handler="forward_in_process_event",
    )


def test_in_process_worker_command_projection_matches_rust_match_branches() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: worker command branch maps ClientCommand variants to runtime handle calls.
    assert in_process_worker_command_projection("Request") == InProcessWorkerCommandProjection(
        command_kind="Request",
        request_sender_method="request",
        clones_request_sender=True,
        uses_detached_task=True,
        sends_response=True,
        response_result_source="request_sender.request(*request).await",
        calls_handle_shutdown=False,
        breaks_worker_after_command=False,
    )
    assert in_process_worker_command_projection("Notify") == InProcessWorkerCommandProjection(
        command_kind="Notify",
        request_sender_method="notify",
        clones_request_sender=False,
        uses_detached_task=False,
        sends_response=True,
        response_result_source="request_sender.notify(notification)",
        calls_handle_shutdown=False,
        breaks_worker_after_command=False,
    )
    assert in_process_worker_command_projection(
        "ResolveServerRequest"
    ) == InProcessWorkerCommandProjection(
        command_kind="ResolveServerRequest",
        request_sender_method="respond_to_server_request",
        clones_request_sender=False,
        uses_detached_task=False,
        sends_response=True,
        response_result_source="request_sender.respond_to_server_request(request_id, result)",
        calls_handle_shutdown=False,
        breaks_worker_after_command=False,
    )
    assert in_process_worker_command_projection(
        "RejectServerRequest"
    ) == InProcessWorkerCommandProjection(
        command_kind="RejectServerRequest",
        request_sender_method="fail_server_request",
        clones_request_sender=False,
        uses_detached_task=False,
        sends_response=True,
        response_result_source="request_sender.fail_server_request(request_id, error)",
        calls_handle_shutdown=False,
        breaks_worker_after_command=False,
    )
    assert in_process_worker_command_projection("Shutdown") == InProcessWorkerCommandProjection(
        command_kind="Shutdown",
        request_sender_method=None,
        clones_request_sender=False,
        uses_detached_task=False,
        sends_response=True,
        response_result_source="handle.shutdown().await",
        calls_handle_shutdown=True,
        breaks_worker_after_command=True,
    )
    assert in_process_worker_command_projection("ChannelClosed") == InProcessWorkerCommandProjection(
        command_kind="ChannelClosed",
        request_sender_method=None,
        clones_request_sender=False,
        uses_detached_task=False,
        sends_response=False,
        response_result_source=None,
        calls_handle_shutdown=True,
        breaks_worker_after_command=True,
        channel_closed_branch=True,
    )


def test_in_process_worker_event_projection_matches_rust_next_event_branch() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: worker event branch handles stream end, unsupported auth refresh, and forwarding.
    assert in_process_worker_event_projection(None) == InProcessWorkerEventProjection(
        event_present=False,
        unsupported_auth_refresh=False,
        rejection_error=None,
        forwards_event=False,
        forward_result=None,
        disables_event_stream=False,
        breaks_worker=True,
        continues_worker=False,
    )

    auth_request = ServerRequest(
        "ChatgptAuthTokensRefresh",
        request_id="auth-1",
        params={},
    )
    assert in_process_worker_event_projection(
        InProcessServerEvent.server_request(auth_request)
    ) == InProcessWorkerEventProjection(
        event_present=True,
        unsupported_auth_refresh=True,
        rejection_error=JSONRPCErrorError(
            code=-32000,
            message="chatgpt auth token refresh is not supported for in-process app-server clients",
        ),
        forwards_event=False,
        forward_result=None,
        disables_event_stream=False,
        breaks_worker=False,
        continues_worker=True,
    )

    notification = InProcessServerEvent.server_notification(ServerNotification("TurnCompleted", None))
    assert in_process_worker_event_projection(
        notification,
        forward_result=ForwardEventResult.DISABLE_STREAM,
    ) == InProcessWorkerEventProjection(
        event_present=True,
        unsupported_auth_refresh=False,
        rejection_error=None,
        forwards_event=True,
        forward_result=ForwardEventResult.DISABLE_STREAM,
        disables_event_stream=True,
        breaks_worker=False,
        continues_worker=True,
    )


def test_in_process_command_entrypoint_projection_matches_rust_public_methods() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: public command methods send ClientCommand variants and await oneshot responses.
    expected = {
        "request": ("Request", "request"),
        "notify": ("Notify", "notify"),
        "resolve": ("ResolveServerRequest", "resolve"),
        "reject": ("RejectServerRequest", "reject"),
    }

    for operation, (command_kind, response_channel) in expected.items():
        assert in_process_command_entrypoint_projection(
            operation
        ) == InProcessCommandEntrypointProjection(
            operation=operation,
            command_kind=command_kind,
            has_response_oneshot=True,
            worker_send_error_kind="BrokenPipe",
            worker_send_error_message="in-process app-server worker channel is closed",
            response_closed_error_kind="BrokenPipe",
            response_closed_error_message=(
                f"in-process app-server {response_channel} channel is closed"
            ),
        )


def test_in_process_request_response_projection_matches_rust_request_flow() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: request sends boxed ClientCommand::Request and awaits raw RequestResult.
    assert in_process_request_response_projection() == InProcessRequestResponseProjection(
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


def test_in_process_worker_request_task_projection_matches_rust_detached_delivery() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: worker request branch detaches runtime wait and sends raw RequestResult to response_tx.
    assert in_process_worker_request_task_projection() == InProcessWorkerRequestTaskProjection(
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


def test_in_process_request_handle_projection_matches_rust_factory() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: request_handle clones command_tx and handle request paths mirror client request paths.
    assert in_process_request_handle_projection() == InProcessRequestHandleProjection(
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


def test_in_process_next_event_projection_matches_rust_facade() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: next_event awaits event_rx.recv() and returns Option<InProcessServerEvent>.
    assert in_process_next_event_projection() == InProcessNextEventProjection(
        event_receiver_source="self.event_rx.recv().await",
        requires_mutable_client=True,
        awaits_receiver_recv=True,
        returns_option=True,
        closed_receiver_returns_none=True,
        preserves_in_process_event=True,
        converts_to_app_server_event=False,
    )


def test_in_process_shutdown_entrypoint_projection_matches_rust_method() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: shutdown consumes self, sends Shutdown, and only propagates in-time command results.
    assert in_process_shutdown_entrypoint_projection() == InProcessShutdownEntrypointProjection(
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


def test_in_process_shutdown_projection_returns_prompt_command_result() -> None:
    # Rust: shutdown returns the command result when response_rx completes within SHUTDOWN_TIMEOUT.
    assert in_process_shutdown_projection(
        command_send_ok=True,
        response_within_timeout=True,
        worker_exits_within_timeout=True,
    ) == InProcessShutdownProjection(
        drop_event_receiver_before_shutdown_command=True,
        send_shutdown_command=True,
        await_response_timeout_seconds=5,
        return_command_result=True,
        drop_command_sender_before_worker_wait=True,
        await_worker_timeout_seconds=5,
        abort_worker_on_timeout=False,
    )


def test_in_process_shutdown_projection_aborts_worker_after_timeout() -> None:
    # Rust: shutdown drops command_tx, waits for worker, then aborts if the worker timeout elapses.
    assert in_process_shutdown_projection(
        command_send_ok=False,
        response_within_timeout=False,
        worker_exits_within_timeout=False,
    ) == InProcessShutdownProjection(
        drop_event_receiver_before_shutdown_command=True,
        send_shutdown_command=True,
        await_response_timeout_seconds=5,
        return_command_result=False,
        drop_command_sender_before_worker_wait=True,
        await_worker_timeout_seconds=5,
        abort_worker_on_timeout=True,
    )


def test_in_process_client_command_projection_matches_rust_variants() -> None:
    # Rust source: app-server-client/src/lib.rs ClientCommand enum.
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})
    error = JSONRPCErrorError(code=-32603, message="failed")

    commands = [
        InProcessClientCommandProjection.request_command(request),
        InProcessClientCommandProjection.notify("initialized"),
        InProcessClientCommandProjection.resolve_server_request("srv-1", {"ok": True}),
        InProcessClientCommandProjection.reject_server_request("srv-2", error),
        InProcessClientCommandProjection.shutdown(),
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
    assert commands[1].notification == "initialized"
    assert commands[2].request_id == "srv-1"
    assert commands[2].result == {"ok": True}
    assert commands[3].request_id == "srv-2"
    assert commands[3].error == error
    assert commands[4].has_response_oneshot is True
    assert all(command.has_response_oneshot for command in commands)


def test_default_in_process_channel_capacity_matches_rust_reexport() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: crate root re-exports the default in-process channel capacity.
    assert DEFAULT_IN_PROCESS_CHANNEL_CAPACITY == 1024

    args = InProcessClientStartArgs(arg0_paths=object(), config=object())

    assert args.channel_capacity == DEFAULT_IN_PROCESS_CHANNEL_CAPACITY
    assert args.into_runtime_start_args().channel_capacity == DEFAULT_IN_PROCESS_CHANNEL_CAPACITY


def test_in_process_start_effective_channel_capacity_clamps_to_one() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: InProcessAppServerClient::start applies channel_capacity.max(1).
    args = InProcessClientStartArgs(arg0_paths=object(), config=object(), channel_capacity=0)

    assert args.into_runtime_start_args().channel_capacity == 0
    assert args.effective_channel_capacity() == 1
    assert InProcessClientStartArgs(
        arg0_paths=object(),
        config=object(),
        channel_capacity=7,
    ).effective_channel_capacity() == 7


@pytest.mark.asyncio
async def test_in_process_start_projects_runtime_args_and_effective_capacity() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: start projects runtime args and applies channel_capacity.max(1).
    args = InProcessClientStartArgs(
        arg0_paths="arg0",
        config=object(),
        client_name="codex-app-server-client-test",
        client_version="0.0.0-test",
        channel_capacity=0,
    )

    client = await InProcessAppServerClient.start(args)

    assert client.runtime_start_args is not None
    assert client.runtime_start_args.arg0_paths == "arg0"
    assert client.runtime_start_args.channel_capacity == 0
    assert client.runtime_start_args.initialize_params == args.initialize_params()
    assert client.channel_capacity == 1


def test_into_app_server_in_process_start_args_preserves_runtime_handoff_fields() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: start passes args.into_runtime_start_args() into codex_app_server::in_process::start.
    config_warnings = [{"message": "warn"}]
    args = InProcessClientStartArgs(
        arg0_paths="arg0",
        config={"experimental_thread_config_endpoint": "https://threads.example"},
        cli_overrides=[("model", "gpt")],
        loader_overrides="loader",
        strict_config=True,
        cloud_requirements="requirements",
        feedback="feedback",
        log_db="log-db",
        state_db=StateDbHandle({"db": "state"}),
        environment_manager="env-manager",
        config_warnings=config_warnings,
        session_source="exec",
        enable_codex_api_key_env=True,
        client_name="client",
        client_version="1.2.3",
        experimental_api=True,
        opt_out_notification_methods=["m1"],
        channel_capacity=0,
    )

    start_args = into_app_server_in_process_start_args(args)

    assert start_args.arg0_paths == "arg0"
    assert start_args.cli_overrides == (("model", "gpt"),)
    assert start_args.loader_overrides == "loader"
    assert start_args.strict_config is True
    assert start_args.cloud_requirements == "requirements"
    assert isinstance(start_args.thread_config_loader, RemoteThreadConfigLoader)
    assert start_args.feedback == "feedback"
    assert start_args.log_db == "log-db"
    assert start_args.state_db is args.state_db
    assert start_args.environment_manager == "env-manager"
    assert start_args.config_warnings == tuple(config_warnings)
    assert start_args.session_source == "exec"
    assert start_args.enable_codex_api_key_env is True
    assert start_args.initialize == args.initialize_params()
    assert start_args.channel_capacity == 0
    assert start_args.effective_channel_capacity() == 1


@pytest.mark.asyncio
async def test_in_process_start_returns_empty_shutdownable_facade() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: lightweight start facade has no pending events and can shut down.
    client = await InProcessAppServerClient.start(
        InProcessClientStartArgs(arg0_paths=object(), config=object())
    )

    assert await client.next_event() is None

    await asyncio.wait_for(client.shutdown(), timeout=0.1)

    with pytest.raises(BrokenPipeError, match="in-process app-server next_event channel is closed"):
        await client.next_event()


@pytest.mark.asyncio
async def test_in_process_start_request_uses_runtime_projection_bookkeeping() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: start-created facade sends requests into the app-server-owned runtime projection.
    client = await InProcessAppServerClient.start(
        InProcessClientStartArgs(arg0_paths=object(), config=object())
    )
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    result = await client.request(request)

    assert isinstance(result, JSONRPCErrorError)
    assert result.code == -32000
    assert result.message == "in-process app-server request response is pending in the Python runtime projection"
    assert result.data == {"requestId": "RequestId(value='req-1')"}


@pytest.mark.asyncio
async def test_in_process_request_returns_runtime_projection_immediate_errors() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: request returns raw RequestResult errors produced by the app-server runtime path.
    duplicate_runtime = InProcessRuntimeProjection(channel_capacity=2)
    duplicate_client = InProcessAppServerClient(runtime_projection=duplicate_runtime)
    first = await duplicate_client.request(ClientRequest("ThreadRead", request_id=7, params={}))
    duplicate = await duplicate_client.request(ClientRequest("ThreadRead", request_id=7, params={}))

    assert isinstance(first, JSONRPCErrorError)
    assert first.message == "in-process app-server request response is pending in the Python runtime projection"
    assert isinstance(duplicate, JSONRPCErrorError)
    assert duplicate.code == INVALID_REQUEST_ERROR_CODE
    assert duplicate.message == "duplicate request id: RequestId(value=7)"

    full_client = InProcessAppServerClient(
        runtime_projection=InProcessRuntimeProjection(channel_capacity=1, processor_queue_size=1)
    )
    full = await full_client.request(ClientRequest("ThreadRead", request_id=8, params={}))
    assert isinstance(full, JSONRPCErrorError)
    assert full.code == OVERLOADED_ERROR_CODE
    assert full.message == "in-process app-server request queue is full"

    closed_client = InProcessAppServerClient(
        runtime_projection=InProcessRuntimeProjection(channel_capacity=1, processor_closed=True)
    )
    closed = await closed_client.request(ClientRequest("ThreadRead", request_id=9, params={}))
    assert isinstance(closed, JSONRPCErrorError)
    assert closed.code == INTERNAL_ERROR_CODE
    assert closed.message == "in-process app-server request processor is closed"


@pytest.mark.asyncio
async def test_in_process_start_request_handle_uses_runtime_projection_bookkeeping() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: cloned start-created handles share the runtime projection request path.
    client = await InProcessAppServerClient.start(
        InProcessClientStartArgs(arg0_paths=object(), config=object())
    )
    handle = client.request_handle()
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    result = await handle.request(request)

    assert isinstance(result, JSONRPCErrorError)
    assert result.code == -32000
    assert result.data == {"requestId": "RequestId(value='req-1')"}


@pytest.mark.asyncio
async def test_in_process_start_notify_uses_runtime_projection_bookkeeping() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: start-created facade sends notifications into the runtime projection.
    client = await InProcessAppServerClient.start(
        InProcessClientStartArgs(arg0_paths=object(), config=object())
    )

    await client.notify({"type": "Initialized"})


@pytest.mark.asyncio
async def test_in_process_start_server_request_response_uses_runtime_projection_bookkeeping() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: start-created facade records server-request responses and rejections.
    client = await InProcessAppServerClient.start(
        InProcessClientStartArgs(arg0_paths=object(), config=object())
    )

    await client.resolve_server_request("srv-1", {"ok": True})
    error = JSONRPCErrorError(code=-32603, message="nope")
    await client.reject_server_request("srv-2", error)

    assert client.resolved_server_requests() == {"srv-1": {"ok": True}}
    assert client.rejected_server_requests() == {"srv-2": error}


@pytest.mark.asyncio
async def test_in_process_start_push_event_uses_runtime_projection_bookkeeping() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: start-created facade accepts runtime events and preserves next_event delivery.
    client = await InProcessAppServerClient.start(
        InProcessClientStartArgs(arg0_paths=object(), config=object())
    )

    client.push_event(InProcessServerEvent.lagged(1))

    assert await client.next_event() == InProcessServerEvent.lagged(1)


def test_legacy_core_reexports_existing_core_boundaries() -> None:
    # Rust contract: src/lib.rs re-exports legacy codex-core symbols under legacy_core.
    assert legacy_core.DEFAULT_AGENTS_MD_FILENAME == "AGENTS.md"
    assert legacy_core.LOCAL_AGENTS_MD_FILENAME == "AGENTS.override.md"
    assert legacy_core.McpManager.__name__ == "McpManager"
    assert callable(legacy_core.check_execpolicy_for_warnings)
    assert callable(legacy_core.format_exec_policy_error_with_source)
    assert callable(legacy_core.grant_read_root_non_elevated)
    assert callable(legacy_core.web_search_detail)
    assert legacy_core.config.__name__ == "pycodex.core.config"
    assert legacy_core.review_prompts.__name__ == "pycodex.core.review_prompts"


def test_app_server_control_socket_path_reexports_exec_session_policy() -> None:
    # Rust contract: src/lib.rs re-exports app_server_control_socket_path at the crate root.
    codex_home = Path("/tmp/codex-home")

    assert app_server_control_socket_path(codex_home) == (
        codex_home / "app-server-control" / "app-server-control.sock"
    )


def test_crate_root_reexports_existing_state_and_exec_server_types() -> None:
    # Rust contract: src/lib.rs re-exports StateDbHandle and exec-server runtime types.
    assert StateDbHandle is state_db_bridge.StateDbHandle
    assert EnvironmentManager is exec_server.EnvironmentManager
    assert ExecServerRuntimePaths is exec_server.ExecServerRuntimePaths


def test_runtime_start_args_forward_environment_manager() -> None:
    # Rust test: runtime_start_args_forward_environment_manager.
    config = object()
    environment_manager = EnvironmentManager({"default": "remote"})
    args = InProcessClientStartArgs(
        arg0_paths=object(),
        config=config,
        environment_manager=environment_manager,
        client_name="codex-app-server-client-test",
        client_version="0.0.0-test",
        experimental_api=True,
        channel_capacity=1,
    )

    runtime_args = args.into_runtime_start_args()

    assert runtime_args.config is config
    assert runtime_args.environment_manager is environment_manager
    assert runtime_args.initialize_params == args.initialize_params()
    assert runtime_args.channel_capacity == 1


def test_runtime_start_args_forward_and_clone_startup_fields() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: into_runtime_start_args projects startup fields into InProcessStartArgs.
    cli_overrides = [("model", "gpt-5")]
    config_warnings = [{"message": "warn"}]
    state_db = StateDbHandle("state-db")
    args = InProcessClientStartArgs(
        arg0_paths="arg0",
        config=object(),
        cli_overrides=cli_overrides,
        loader_overrides={"profile": "test"},
        strict_config=True,
        cloud_requirements={"required": True},
        feedback="feedback",
        log_db="log-db",
        state_db=state_db,
        config_warnings=config_warnings,
        session_source="cli",
        enable_codex_api_key_env=True,
    )

    runtime_args = args.into_runtime_start_args()

    assert runtime_args.arg0_paths == "arg0"
    assert runtime_args.cli_overrides == [("model", "gpt-5")]
    assert runtime_args.loader_overrides == {"profile": "test"}
    assert runtime_args.strict_config is True
    assert runtime_args.cloud_requirements == {"required": True}
    assert runtime_args.feedback == "feedback"
    assert runtime_args.log_db == "log-db"
    assert runtime_args.state_db is state_db
    assert runtime_args.config_warnings == [{"message": "warn"}]
    assert runtime_args.session_source == "cli"
    assert runtime_args.enable_codex_api_key_env is True

    cli_overrides.append(("approval_policy", "never"))
    config_warnings.append({"message": "later"})

    assert runtime_args.cli_overrides == [("model", "gpt-5")]
    assert runtime_args.config_warnings == [{"message": "warn"}]


def test_runtime_start_args_clone_initialize_opt_out_methods() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: into_runtime_start_args stores cloned initialize opt-out methods.
    opt_out_methods = ["turn/delta"]
    args = InProcessClientStartArgs(
        arg0_paths=object(),
        config=object(),
        opt_out_notification_methods=opt_out_methods,
    )

    runtime_args = args.into_runtime_start_args()
    opt_out_methods.append("thread/item/completed")
    args.opt_out_notification_methods.append("turn/completed")

    assert runtime_args.initialize_params["capabilities"]["opt_out_notification_methods"] == [
        "turn/delta"
    ]


@pytest.mark.asyncio
async def test_runtime_start_args_use_noop_thread_config_loader_by_default() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: configured_thread_config_loader returns NoopThreadConfigLoader without endpoint.
    args = InProcessClientStartArgs(arg0_paths=object(), config=object())

    runtime_args = args.into_runtime_start_args()

    assert isinstance(runtime_args.thread_config_loader, NoopThreadConfigLoader)
    assert await runtime_args.thread_config_loader.load(ThreadConfigContext()) == []


@pytest.mark.asyncio
async def test_runtime_start_args_use_remote_thread_config_loader_when_configured() -> None:
    # Rust test: runtime_start_args_use_remote_thread_config_loader_when_configured.
    class Config:
        experimental_thread_config_endpoint = "not-a-valid-endpoint"

    args = InProcessClientStartArgs(
        arg0_paths=object(),
        config=Config(),
        environment_manager=EnvironmentManager(),
        client_name="codex-app-server-client-test",
        client_version="0.0.0-test",
    )

    runtime_args = args.into_runtime_start_args()

    assert isinstance(runtime_args.thread_config_loader, RemoteThreadConfigLoader)
    with pytest.raises(ThreadConfigLoadError) as error_info:
        await runtime_args.thread_config_loader.load(ThreadConfigContext())
    assert error_info.value.code() is ThreadConfigLoadErrorCode.REQUEST_FAILED


def test_typed_request_error_messages_match_rust_display() -> None:
    # Rust contract: TypedRequestError display separates transport, server, and deserialize layers.
    assert str(TypedRequestError.transport("config/read", "closed")) == (
        "config/read transport error: closed"
    )
    server_error = JSONRPCErrorError(code=-32603, message="internal", data={"detail": "lock"})
    assert str(TypedRequestError.server("thread/read", server_error)) == (
        'thread/read failed: internal (code -32603), data: {"detail":"lock"}'
    )
    assert str(TypedRequestError.deserialize("thread/start", "bad json")) == (
        "thread/start response decode error: bad json"
    )


def test_typed_request_error_exposes_sources() -> None:
    # Rust test: typed_request_error_exposes_sources.
    transport_source = BrokenPipeError("closed")
    transport = TypedRequestError.transport("config/read", transport_source)
    assert transport.__cause__ is transport_source

    server_error = JSONRPCErrorError(code=-32603, message="internal", data={"detail": "config lock mismatch"})
    server = TypedRequestError.server("thread/read", server_error)
    assert server.__cause__ is None
    assert str(server) == (
        'thread/read failed: internal (code -32603), data: {"detail":"config lock mismatch"}'
    )

    deserialize_source = ValueError("invalid literal for int()")
    deserialize = TypedRequestError.deserialize("thread/start", deserialize_source)
    assert deserialize.__cause__ is deserialize_source


def test_in_process_event_projection_matches_rust_from_impl() -> None:
    # Rust contract: From<InProcessServerEvent> preserves Lagged, ServerNotification, and ServerRequest.
    lagged = AppServerEvent.from_in_process(InProcessServerEvent.lagged(3))
    assert lagged.kind is AppServerEventKind.LAGGED
    assert lagged.skipped == 3

    notification = ServerNotification("AgentMessageDelta", {"delta": "hello"})
    projected = AppServerEvent.from_in_process(InProcessServerEvent.server_notification(notification))
    assert projected.kind is AppServerEventKind.SERVER_NOTIFICATION
    assert projected.payload == notification

    request = object()
    projected_request = AppServerEvent.from_in_process(InProcessServerEvent.server_request(request))
    assert projected_request.kind is AppServerEventKind.SERVER_REQUEST
    assert projected_request.payload is request

    disconnected = AppServerEvent.disconnected("connection closed")
    assert disconnected.kind is AppServerEventKind.DISCONNECTED
    assert disconnected.message == "connection closed"


@pytest.mark.asyncio
async def test_next_event_surfaces_lagged_markers() -> None:
    # Rust test: next_event_surfaces_lagged_markers.
    client = InProcessAppServerClient(events=[InProcessServerEvent.lagged(3)])

    event = await client.next_event()

    assert event == InProcessServerEvent.lagged(3)


def test_event_requires_delivery_marks_transcript_and_terminal_events() -> None:
    # Rust test: event_requires_delivery_marks_transcript_and_terminal_events.
    cases = [
        ("TurnCompleted", True),
        ("ThreadSettingsUpdated", True),
        ("ItemCompleted", True),
        ("AgentMessageDelta", True),
        ("PlanDelta", True),
        ("ReasoningSummaryTextDelta", True),
        ("ReasoningTextDelta", True),
        ("CommandExecutionOutputDelta", False),
    ]

    for variant, requires_delivery in cases:
        notification = ServerNotification(variant, {})
        event = InProcessServerEvent.server_notification(notification)

        assert server_notification_requires_delivery(notification) is requires_delivery
        assert event_requires_delivery(event) is requires_delivery

    assert event_requires_delivery(InProcessServerEvent.lagged(1)) is False


def test_project_in_process_event_forwarding_preserves_lossless_order() -> None:
    # Rust test: forward_in_process_event_preserves_transcript_notifications_under_backpressure.
    initial = [
        InProcessServerEvent.server_notification(
            ServerNotification("CommandExecutionOutputDelta", {"delta": "stdout-1"})
        )
    ]
    incoming = [
        InProcessServerEvent.server_notification(
            ServerNotification("CommandExecutionOutputDelta", {"delta": "stdout-2"})
        ),
        InProcessServerEvent.server_notification(
            ServerNotification("AgentMessageDelta", {"delta": "hello"})
        ),
        InProcessServerEvent.server_notification(
            ServerNotification("ItemCompleted", {"text": "hello"})
        ),
        InProcessServerEvent.server_notification(ServerNotification("TurnCompleted", {})),
    ]

    projection = project_in_process_event_forwarding(initial, incoming, capacity=1)

    assert projection.skipped_events == 0
    assert projection.result is ForwardEventResult.CONTINUE
    assert projection.stream_enabled is True
    assert projection.events == [
        initial[0],
        InProcessServerEvent.lagged(1),
        incoming[1],
        incoming[2],
        incoming[3],
    ]


def test_project_in_process_event_forwarding_accumulates_skipped_best_effort_events() -> None:
    # Rust contract: repeated full-queue best-effort drops accumulate into one Lagged marker.
    initial = [
        InProcessServerEvent.server_notification(
            ServerNotification("CommandExecutionOutputDelta", {"delta": "stdout-1"})
        )
    ]
    incoming = [
        InProcessServerEvent.server_notification(
            ServerNotification("CommandExecutionOutputDelta", {"delta": "stdout-2"})
        ),
        InProcessServerEvent.server_notification(
            ServerNotification("CommandExecutionOutputDelta", {"delta": "stdout-3"})
        ),
        InProcessServerEvent.server_notification(
            ServerNotification("AgentMessageDelta", {"delta": "hello"})
        ),
    ]

    projection = project_in_process_event_forwarding(initial, incoming, capacity=1)

    assert projection.skipped_events == 0
    assert projection.stream_enabled is True
    assert projection.events == [
        initial[0],
        InProcessServerEvent.lagged(2),
        incoming[2],
    ]


def test_project_in_process_event_forwarding_flushes_existing_skipped_before_best_effort() -> None:
    # Rust contract: existing skipped events are flushed before a later best-effort event when possible.
    event = InProcessServerEvent.server_notification(
        ServerNotification("CommandExecutionOutputDelta", {"delta": "stdout"})
    )

    projection = project_in_process_event_forwarding(
        [],
        [event],
        capacity=2,
        initial_skipped_events=3,
    )

    assert projection.skipped_events == 0
    assert projection.stream_enabled is True
    assert projection.events == [
        InProcessServerEvent.lagged(3),
        event,
    ]


def test_project_in_process_event_forwarding_rejects_dropped_server_requests() -> None:
    # Rust contract: dropped server requests are rejected so the server is not left waiting.
    request = ServerRequest("CommandExecutionRequestApproval", request_id="approval-1", params={})

    projection = project_in_process_event_forwarding(
        [
            InProcessServerEvent.server_notification(
                ServerNotification("CommandExecutionOutputDelta", {})
            )
        ],
        [InProcessServerEvent.server_request(request)],
        capacity=1,
    )

    assert projection.events == [
        InProcessServerEvent.server_notification(
            ServerNotification("CommandExecutionOutputDelta", {})
        )
    ]
    assert projection.skipped_events == 1
    assert projection.rejected_server_requests == {
        "approval-1": JSONRPCErrorError(
            code=-32001,
            message="in-process app-server event queue is full",
        )
    }
    assert projection.result is ForwardEventResult.CONTINUE
    assert projection.stream_enabled is True


def test_project_in_process_event_forwarding_marks_closed_consumer_disabled() -> None:
    # Rust contract: a closed consumer channel maps to ForwardEventResult::DisableStream.
    event = InProcessServerEvent.server_notification(ServerNotification("AgentMessageDelta", {}))

    projection = project_in_process_event_forwarding(
        [],
        [event],
        capacity=1,
        consumer_open=False,
    )

    assert projection.events == []
    assert projection.skipped_events == 0
    assert projection.rejected_server_requests == {}
    assert projection.result is ForwardEventResult.DISABLE_STREAM
    assert projection.stream_enabled is False


@pytest.mark.asyncio
async def test_in_process_chatgpt_auth_refresh_request_is_rejected_not_delivered() -> None:
    # Source: codex/codex-rs/app-server-client/src/lib.rs
    # Rust crate: codex-app-server-client
    # Rust module: src/lib.rs
    # Contract: in-process worker rejects ChatGPT token refresh requests instead of delivering them.
    request = ServerRequest(
        "ChatgptAuthTokensRefresh",
        request_id="auth-refresh-1",
        params={"reason": "unauthorized"},
    )

    rejection = in_process_unsupported_server_request_error(request)

    assert rejection == JSONRPCErrorError(
        code=-32000,
        message="chatgpt auth token refresh is not supported for in-process app-server clients",
    )
    assert (
        in_process_unsupported_server_request_error(
            ServerRequest("CommandExecutionRequestApproval", request_id="approval-1", params={})
        )
        is None
    )

    client = InProcessAppServerClient()
    client.push_event(InProcessServerEvent.server_request(request))

    assert await client.next_event() is None
    assert client.rejected_server_requests() == {"auth-refresh-1": rejection}


def test_request_method_name_uses_client_request_method() -> None:
    # Rust contract: request_method_name returns the JSON-RPC method or <unknown>.
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert request_method_name(request) == "thread/read"
    assert request_method_name({"method": "thread/start"}) == "thread/start"
    assert request_method_name({"params": {}}) == "<unknown>"
    assert request_method_name(object()) == "<unknown>"


@pytest.mark.asyncio
async def test_in_process_request_handle_delegates_to_client_request() -> None:
    # Rust contract: InProcessAppServerRequestHandle clones the command sender and forwards requests.
    seen: list[ClientRequest] = []

    async def handler(request: ClientRequest) -> dict[str, object]:
        seen.append(request)
        return {"ok": True}

    client = InProcessAppServerClient(request_handler=handler)
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert await client.request_handle().request(request) == {"ok": True}
    assert seen == [request]
    assert await client.request_typed(request) == {"ok": True}


@pytest.mark.asyncio
async def test_in_process_request_handles_share_client_channel() -> None:
    # Rust contract: cloned InProcessAppServerRequestHandle values share the same command sender.
    seen: list[tuple[str, str | int | None]] = []

    async def handler(request: ClientRequest) -> dict[str, object]:
        seen.append((request.method(), request.request_id))
        return {"requestId": request.request_id}

    client = InProcessAppServerClient(request_handler=handler)
    first_handle = client.request_handle()
    second_handle = client.request_handle()
    first_request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})
    second_request = ClientRequest("ThreadList", request_id="req-2", params={})

    assert await first_handle.request(first_request) == {"requestId": "req-1"}
    assert await second_handle.request(second_request) == {"requestId": "req-2"}
    assert seen == [("thread/read", "req-1"), ("thread/list", "req-2")]


@pytest.mark.asyncio
async def test_in_process_request_handle_observes_client_shutdown() -> None:
    # Rust contract: cloned request handles use the same worker channel and close with the client.
    client = InProcessAppServerClient(request_handler=lambda _request: {"ok": True})
    handle = client.request_handle()
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    await client.shutdown()

    with pytest.raises(BrokenPipeError, match="in-process app-server request channel is closed"):
        await handle.request(request)
    with pytest.raises(TypedRequestError) as error_info:
        await handle.request_typed(request)

    assert error_info.value.kind == "transport"
    assert isinstance(error_info.value.__cause__, BrokenPipeError)
    assert str(error_info.value) == (
        "thread/read transport error: in-process app-server request channel is closed"
    )


@pytest.mark.asyncio
async def test_in_process_request_handle_typed_wraps_server_and_decode_errors() -> None:
    # Rust contract: InProcessAppServerRequestHandle::request_typed wraps server/decode failures.
    server_error = JSONRPCErrorError(code=-32603, message="missing thread", data={"threadId": "missing"})
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "missing"})
    server_client = InProcessAppServerClient(request_handler=lambda _request: server_error)

    with pytest.raises(TypedRequestError) as server_info:
        await server_client.request_handle().request_typed(request)

    assert server_info.value.kind == "server"
    assert server_info.value.__cause__ is None
    assert str(server_info.value) == (
        'thread/read failed: missing thread (code -32603), data: {"threadId":"missing"}'
    )

    decode_client = InProcessAppServerClient(request_handler=lambda _request: {"count": "nan"})

    def decode_count(result: dict[str, object]) -> int:
        return int(result["count"])

    with pytest.raises(TypedRequestError) as decode_info:
        await decode_client.request_handle().request_typed(request, decoder=decode_count)

    assert decode_info.value.kind == "deserialize"
    assert isinstance(decode_info.value.__cause__, ValueError)
    assert str(decode_info.value).startswith("thread/read response decode error: ")


@pytest.mark.asyncio
async def test_in_process_request_observes_client_shutdown() -> None:
    # Rust contract: InProcessAppServerClient::request and request_typed observe request-channel closure.
    client = InProcessAppServerClient(request_handler=lambda _request: {"ok": True})
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    await client.shutdown()

    with pytest.raises(BrokenPipeError, match="in-process app-server request channel is closed"):
        await client.request(request)
    with pytest.raises(TypedRequestError) as error_info:
        await client.request_typed(request)

    assert error_info.value.kind == "transport"
    assert isinstance(error_info.value.__cause__, BrokenPipeError)
    assert str(error_info.value) == (
        "thread/read transport error: in-process app-server request channel is closed"
    )


@pytest.mark.asyncio
async def test_in_process_request_typed_wraps_transport_errors() -> None:
    # Rust contract: InProcessAppServerClient::request_typed maps request I/O errors to transport.
    async def handler(_request: ClientRequest) -> dict[str, object]:
        raise BrokenPipeError("in-process app-server request channel is closed")

    client = InProcessAppServerClient(request_handler=handler)
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    with pytest.raises(TypedRequestError) as error_info:
        await client.request_typed(request)

    assert error_info.value.kind == "transport"
    assert isinstance(error_info.value.__cause__, BrokenPipeError)
    assert str(error_info.value) == (
        "thread/read transport error: in-process app-server request channel is closed"
    )


@pytest.mark.asyncio
async def test_in_process_request_typed_wraps_server_and_decode_errors() -> None:
    # Rust contract: InProcessAppServerClient::request_typed wraps JSON-RPC and decode failures.
    server_error = JSONRPCErrorError(code=-32603, message="missing thread", data={"threadId": "missing"})
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "missing"})
    server_client = InProcessAppServerClient(request_handler=lambda _request: server_error)

    with pytest.raises(TypedRequestError) as server_info:
        await server_client.request_typed(request)

    assert server_info.value.kind == "server"
    assert server_info.value.__cause__ is None
    assert str(server_info.value) == (
        'thread/read failed: missing thread (code -32603), data: {"threadId":"missing"}'
    )

    decode_client = InProcessAppServerClient(request_handler=lambda _request: {"count": "nan"})

    def decode_count(result: dict[str, object]) -> int:
        return int(result["count"])

    with pytest.raises(TypedRequestError) as decode_info:
        await decode_client.request_typed(request, decoder=decode_count)

    assert decode_info.value.kind == "deserialize"
    assert isinstance(decode_info.value.__cause__, ValueError)
    assert str(decode_info.value).startswith("thread/read response decode error: ")


@pytest.mark.asyncio
async def test_in_process_notify_resolve_reject_next_event_and_shutdown() -> None:
    # Rust contract: facade methods forward notify/resolve/reject commands and pop queued events.
    notifications: list[object] = []
    event = InProcessServerEvent.lagged(2)
    client = InProcessAppServerClient(
        notification_handler=lambda notification: notifications.append(notification),
        events=[event],
    )

    await client.notify("initialized")
    await client.resolve_server_request("srv-1", {"ok": True})
    await client.reject_server_request("srv-2", {"code": -32603})

    assert notifications == ["initialized"]
    assert client.resolved_server_requests() == {"srv-1": {"ok": True}}
    assert client.rejected_server_requests() == {"srv-2": {"code": -32603}}
    assert await client.next_event() == event
    assert await client.next_event() is None

    await client.shutdown()
    with pytest.raises(BrokenPipeError):
        await client.next_event()


@pytest.mark.asyncio
async def test_in_process_closed_command_errors_use_rust_channel_names() -> None:
    # Rust contract: closed command response channels use notify/resolve/reject names.
    client = InProcessAppServerClient()
    await client.shutdown()

    with pytest.raises(BrokenPipeError, match="in-process app-server notify channel is closed"):
        await client.notify("initialized")
    with pytest.raises(BrokenPipeError, match="in-process app-server resolve channel is closed"):
        await client.resolve_server_request("srv-1", {"ok": True})
    with pytest.raises(BrokenPipeError, match="in-process app-server reject channel is closed"):
        await client.reject_server_request("srv-2", JSONRPCErrorError(code=-32603, message="nope"))


@pytest.mark.asyncio
async def test_shutdown_completes_promptly_without_retained_managers() -> None:
    # Rust test: shutdown_completes_promptly_without_retained_managers.
    client = InProcessAppServerClient(events=[InProcessServerEvent.lagged(1)])

    await asyncio.wait_for(client.shutdown(), timeout=0.1)

    with pytest.raises(BrokenPipeError):
        await client.next_event()


@pytest.mark.asyncio
async def test_app_server_client_next_event_converts_in_process_events() -> None:
    # Rust contract: AppServerClient::next_event maps in-process events through AppServerEvent::from.
    client = AppServerClient(InProcessAppServerClient(events=[InProcessServerEvent.lagged(4)]))

    event = await client.next_event()

    assert event == AppServerEvent.lagged(4)


@pytest.mark.asyncio
async def test_app_server_client_and_request_handle_forward_in_process_methods() -> None:
    # Rust contract: AppServerClient and AppServerRequestHandle dispatch to the inner client variant.
    seen_requests: list[ClientRequest] = []
    seen_notifications: list[object] = []

    async def handler(request: ClientRequest) -> dict[str, object]:
        seen_requests.append(request)
        return {"count": "7"}

    inner = InProcessAppServerClient(
        request_handler=handler,
        notification_handler=lambda notification: seen_notifications.append(notification),
    )
    client = AppServerClient(inner)
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert await client.request(request) == {"count": "7"}
    assert await client.request_typed(request, decoder=lambda result: int(result["count"])) == 7
    assert await client.request_handle().request_typed(
        request,
        decoder=lambda result: int(result["count"]),
    ) == 7

    await client.notify("initialized")
    await client.resolve_server_request("srv-1", {"ok": True})
    await client.reject_server_request("srv-2", JSONRPCErrorError(code=-32603, message="nope"))

    assert seen_requests == [request, request, request]
    assert seen_notifications == ["initialized"]
    assert inner.resolved_server_requests() == {"srv-1": {"ok": True}}
    assert inner.rejected_server_requests() == {
        "srv-2": JSONRPCErrorError(code=-32603, message="nope")
    }

    await client.shutdown()
    with pytest.raises(BrokenPipeError, match="in-process app-server request channel is closed"):
        await client.request(request)


@pytest.mark.asyncio
async def test_app_server_client_and_request_handle_forward_remote_methods() -> None:
    # Rust contract: AppServerClient and AppServerRequestHandle dispatch to the remote inner variant.
    seen_requests: list[ClientRequest] = []
    seen_notifications: list[object] = []
    remote_event = AppServerEvent.disconnected("remote closed")

    async def handler(request: ClientRequest) -> dict[str, object]:
        seen_requests.append(request)
        return {"count": "9"}

    inner = RemoteAppServerClient(
        request_handler=handler,
        notification_handler=lambda notification: seen_notifications.append(notification),
        events=[remote_event],
    )
    client = AppServerClient(inner)
    request = ClientRequest("ThreadRead", request_id="req-1", params={"threadId": "thread-1"})

    assert await client.request(request) == {"count": "9"}
    assert await client.request_typed(request, decoder=lambda result: int(result["count"])) == 9
    assert await client.request_handle().request_typed(
        request,
        decoder=lambda result: int(result["count"]),
    ) == 9

    await client.notify("initialized")
    await client.resolve_server_request("srv-1", {"ok": True})
    await client.reject_server_request("srv-2", JSONRPCErrorError(code=-32603, message="nope"))

    assert await client.next_event() == remote_event
    assert seen_requests == [request, request, request]
    assert seen_notifications == ["initialized"]
    assert inner.resolved_server_requests() == {"srv-1": {"ok": True}}
    assert inner.rejected_server_requests() == {
        "srv-2": JSONRPCErrorError(code=-32603, message="nope")
    }

    await client.shutdown()
    with pytest.raises(BrokenPipeError, match="remote app-server request channel is closed"):
        await client.request(request)
