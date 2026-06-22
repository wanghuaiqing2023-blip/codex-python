import asyncio
from types import SimpleNamespace

import pytest

from pycodex.app_server import (
    AppServerRuntimeHooks,
    AppServerRuntimeOptions,
    AppServerRuntimeResult,
    LogFormat,
    OutboundControlEvent,
    CrateRootModuleInventoryProjection,
    OutboundRouterControlProjection,
    OutboundRouterOutgoingProjection,
    OutboundRouterStartupProjection,
    OutgoingMessageRuntimeProjection,
    PluginStartupTasks,
    ProcessorExitProjection,
    ProcessorLoopUpdateProjection,
    ProcessorRunningTurnWatcherProjection,
    ProcessorSelectTopologyProjection,
    ProcessorShutdownSignalProjection,
    ProcessorStartupProjection,
    ProcessorWorkerSpawnProjection,
    RunMainWithTransportOptionsCall,
    RemoteControlRuntimeDecision,
    RemoteControlStartupProjection,
    RuntimeChannelStartupProjection,
    RuntimeTransportDecisions,
    RuntimeFinalizationProjection,
    ShutdownAction,
    ShutdownSignal,
    ShutdownSignalWaiters,
    ShutdownState,
    StateDbStartupProjection,
    state_db_startup_projection,
    SystemBwrapWarningProjection,
    system_bwrap_warning_projection,
    TelemetryStartupProjection,
    telemetry_startup_projection,
    ThreadCreatedProjection,
    TransportEventChannelClosedProjection,
    TransportStartupProjection,
    analytics_rpc_transport,
    app_text_range,
    collect_config_warnings,
    crate_root_module_inventory_projection,
    ConnectionClosedProjection,
    connection_closed_projection,
    ConnectionOpenedProjection,
    connection_opened_projection,
    configured_thread_config_loader,
    config_error_location,
    ConfigPreloadProjection,
    config_preload_projection,
    ConfigProviderStartupProjection,
    config_provider_startup_projection,
    config_warning_from_error,
    exec_policy_warning_location,
    IncomingNonRequestProjection,
    incoming_non_request_projection,
    IncomingRequestProjection,
    incoming_request_projection,
    log_format_from_env,
    LoggingSubscriberProjection,
    logging_subscriber_projection,
    MainConfigLoadProjection,
    main_config_load_projection,
    MessageProcessorArgsProjection,
    message_processor_args_projection,
    outbound_router_control_projection,
    outbound_router_outgoing_projection,
    outbound_router_startup_projection,
    outgoing_message_runtime_projection,
    PersonalityMigrationProjection,
    personality_migration_projection,
    processor_exit_projection,
    processor_loop_update_projection,
    processor_running_turn_watcher_projection,
    processor_select_topology_projection,
    processor_shutdown_signal_projection,
    processor_startup_projection,
    processor_worker_spawn_projection,
    project_config_warning,
    RemoteControlStatusProjection,
    remote_control_status_projection,
    run_main,
    run_main_default_transport_options,
    run_main_with_transport_options,
    remote_control_runtime_decision,
    remote_control_startup_projection,
    runtime_channel_startup_projection,
    RuntimeResourceStartupProjection,
    runtime_resource_startup_projection,
    RuntimeStartupHandlesProjection,
    runtime_startup_handles_projection,
    RuntimeAuthManagerProjection,
    runtime_auth_manager_projection,
    runtime_transport_decisions,
    runtime_finalization_projection,
    shutdown_signal,
    thread_created_projection,
    TransportAcceptorStartupProjection,
    transport_acceptor_startup_projection,
    transport_event_channel_closed_projection,
    transport_startup_projection,
    UnixSocketStartupLockProjection,
    unix_socket_startup_lock_projection,
)
from pycodex.analytics import AppServerRpcTransport
from pycodex.app_server_protocol import ConfigWarningNotification, TextPosition, TextRange
from pycodex.config import NoopThreadConfigLoader, RemoteThreadConfigLoader


class _Point:
    def __init__(self, line: int, column: int) -> None:
        self.line = line
        self.column = column


class _Range:
    def __init__(self) -> None:
        self.start = _Point(2, 4)
        self.end = _Point(3, 8)


class _ConfigError:
    path = "config.toml"
    range = _Range()


class _ConfigLoadError(Exception):
    def config_error(self) -> _ConfigError:
        return _ConfigError()


class _ExecPolicyLocation:
    path = "policy.exec"
    range = _Range()


class _ExecPolicyError(Exception):
    def location(self) -> _ExecPolicyLocation:
        return _ExecPolicyLocation()


class _AppServerConfig:
    chatgpt_base_url = "https://chatgpt.example.test"


def _ready_future(result: object = None) -> asyncio.Future[object]:
    future: asyncio.Future[object] = asyncio.Future()
    future.set_result(result)
    return future


def test_log_format_from_env_value_matches_json_values_case_insensitively() -> None:
    # Rust: codex-app-server/src/lib.rs
    # log_format_from_env_value_matches_json_values_case_insensitively
    assert LogFormat.from_env_value("json") is LogFormat.JSON
    assert LogFormat.from_env_value("JSON") is LogFormat.JSON
    assert LogFormat.from_env_value("  Json  ") is LogFormat.JSON


def test_log_format_from_env_value_defaults_for_non_json_values() -> None:
    # Rust: codex-app-server/src/lib.rs
    # log_format_from_env_value_defaults_for_non_json_values
    assert LogFormat.from_env_value(None) is LogFormat.DEFAULT
    assert LogFormat.from_env_value("") is LogFormat.DEFAULT
    assert LogFormat.from_env_value("text") is LogFormat.DEFAULT
    assert LogFormat.from_env_value("jsonl") is LogFormat.DEFAULT


def test_log_format_from_env_value_rejects_json_like_values() -> None:
    # Rust: LogFormat::from_env_value only accepts the trimmed string "json" after ASCII lowercase.
    assert LogFormat.from_env_value("application/json") is LogFormat.DEFAULT
    assert LogFormat.from_env_value("json=true") is LogFormat.DEFAULT
    assert LogFormat.from_env_value("json5") is LogFormat.DEFAULT
    assert LogFormat.from_env_value(" jsonl ") is LogFormat.DEFAULT


def test_log_format_from_env_reads_log_format_key() -> None:
    # Rust: log_format_from_env reads the LOG_FORMAT environment variable.
    assert log_format_from_env({"LOG_FORMAT": " json "}) is LogFormat.JSON
    assert log_format_from_env({}) is LogFormat.DEFAULT


def test_crate_root_module_inventory_projection_matches_rust_declarations() -> None:
    # Rust: codex-app-server/src/lib.rs module declarations and pub re-exports.
    projection = crate_root_module_inventory_projection()

    assert isinstance(projection, CrateRootModuleInventoryProjection)
    assert projection.private_modules == (
        "analytics_utils",
        "app_server_tracing",
        "attestation",
        "bespoke_event_handling",
        "command_exec",
        "config",
        "config_manager",
        "config_manager_service",
        "connection_rpc_gate",
        "dynamic_tools",
        "error_code",
        "extensions",
        "filters",
        "fs_watch",
        "fuzzy_file_search",
        "mcp_refresh",
        "message_processor",
        "models",
        "outgoing_message",
        "request_processors",
        "request_serialization",
        "server_request_error",
        "skills_watcher",
        "thread_state",
        "thread_status",
        "transport",
    )
    assert projection.public_modules == ("in_process",)
    assert projection.public_reexports == (
        "INPUT_TOO_LARGE_ERROR_CODE",
        "INVALID_PARAMS_ERROR_CODE",
        "AppServerTransport",
        "app_server_control_socket_path",
        "AppServerWebsocketAuthArgs",
        "AppServerWebsocketAuthSettings",
        "WebsocketAuthCliMode",
    )
    assert projection.python_private_module_count == 26
    assert projection.python_public_module_count == 1
    assert projection.python_reexport_count == 7


def test_logging_subscriber_projection_assembles_default_layers() -> None:
    # Rust: default stderr fmt layer plus feedback layers are always included.
    projection = logging_subscriber_projection(
        log_format=LogFormat.DEFAULT,
        state_db_available=False,
        otel_available=False,
    )

    assert projection == LoggingSubscriberProjection(
        stderr_json=False,
        stderr_span_events_full=True,
        stderr_uses_env_filter=True,
        include_feedback_logger_layer=True,
        include_feedback_metadata_layer=True,
        start_log_db=False,
        include_log_db_layer=False,
        include_otel_logger_layer=False,
        include_otel_tracing_layer=False,
        ignore_try_init_result=True,
        emitted_config_warning_count=0,
        emitted_warning_detail_count=0,
    )


def test_logging_subscriber_projection_assembles_json_optional_layers_and_warnings() -> None:
    # Rust: JSON stderr, log DB, otel layers, and warning error logs are assembled locally.
    warnings = [
        {"summary": "Invalid configuration; using defaults.", "details": "bad config"},
        {"summary": "Project config disabled.", "details": None},
    ]
    projection = logging_subscriber_projection(
        log_format="json",
        state_db_available=True,
        otel_available=True,
        config_warnings=warnings,
    )

    assert projection == LoggingSubscriberProjection(
        stderr_json=True,
        stderr_span_events_full=True,
        stderr_uses_env_filter=True,
        include_feedback_logger_layer=True,
        include_feedback_metadata_layer=True,
        start_log_db=True,
        include_log_db_layer=True,
        include_otel_logger_layer=True,
        include_otel_tracing_layer=True,
        ignore_try_init_result=True,
        emitted_config_warning_count=2,
        emitted_warning_detail_count=1,
    )


def test_runtime_resource_startup_projection_starts_log_db_from_state_db() -> None:
    # Rust: CodexFeedback is always created; state_db.clone().map(log_db::start) starts log DB.
    projection = runtime_resource_startup_projection(state_db_available=True)

    assert projection == RuntimeResourceStartupProjection(
        create_feedback=True,
        clone_state_db_for_log_db=True,
        start_log_db=True,
        log_db_available=True,
        pass_feedback_to_logging=True,
        pass_feedback_to_message_processor=True,
        pass_log_db_to_logging=True,
        pass_log_db_to_message_processor=True,
    )


def test_runtime_resource_startup_projection_skips_log_db_without_state_db() -> None:
    # Rust: absent state DB keeps log_db as None while feedback is still shared.
    projection = runtime_resource_startup_projection(state_db_available=False)

    assert projection == RuntimeResourceStartupProjection(
        create_feedback=True,
        clone_state_db_for_log_db=True,
        start_log_db=False,
        log_db_available=False,
        pass_feedback_to_logging=True,
        pass_feedback_to_message_processor=True,
        pass_log_db_to_logging=False,
        pass_log_db_to_message_processor=False,
    )


def test_runtime_channel_startup_projection_uses_shared_channel_capacity() -> None:
    # Rust: runtime creates TransportEvent, OutgoingEnvelope, and OutboundControlEvent channels.
    assert runtime_channel_startup_projection() == RuntimeChannelStartupProjection(
        transport_event_capacity=128,
        outgoing_capacity=128,
        outbound_control_capacity=128,
        transport_event_payload="TransportEvent",
        outgoing_payload="OutgoingEnvelope",
        outbound_control_payload="OutboundControlEvent",
        creates_transport_event_receiver=True,
        creates_outgoing_receiver=True,
        creates_outbound_control_receiver=True,
    )


def test_runtime_startup_handles_projection_initializes_after_installation_id() -> None:
    # Rust: resolved installation id is followed by shutdown token and empty accept handle vec.
    projection = runtime_startup_handles_projection(
        installation_id_ok=True,
        installation_id="install-123",
    )

    assert projection == RuntimeStartupHandlesProjection(
        resolve_installation_id=True,
        installation_id="install-123",
        create_transport_shutdown_token=True,
        init_transport_accept_handles_empty=True,
        init_app_server_client_name_rx_none=True,
    )


def test_runtime_startup_handles_projection_stops_on_installation_id_error() -> None:
    # Rust: resolve_installation_id errors before creating shutdown token or handle vec.
    projection = runtime_startup_handles_projection(installation_id_ok=False)

    assert projection == RuntimeStartupHandlesProjection(
        resolve_installation_id=True,
        installation_id=None,
        create_transport_shutdown_token=False,
        init_transport_accept_handles_empty=False,
        init_app_server_client_name_rx_none=False,
        return_error=True,
        error_stage="resolve_installation_id",
    )


def test_app_server_runtime_options_default_matches_rust() -> None:
    # Rust: AppServerRuntimeOptions::default.
    options = AppServerRuntimeOptions()

    assert options.plugin_startup_tasks is PluginStartupTasks.START
    assert options.remote_control_enabled is False
    assert options.install_shutdown_signal_handler is True


def test_run_main_default_transport_options_projects_rust_defaults() -> None:
    # Rust: run_main delegates with Stdio, VSCode, default auth, and runtime defaults.
    arg0_paths = object()
    cli_config_overrides = object()
    loader_overrides = object()

    call = run_main_default_transport_options(
        arg0_paths=arg0_paths,
        cli_config_overrides=cli_config_overrides,
        loader_overrides=loader_overrides,
        strict_config=True,
        default_analytics_enabled=False,
    )

    assert isinstance(call, RunMainWithTransportOptionsCall)
    assert call.arg0_paths is arg0_paths
    assert call.cli_config_overrides is cli_config_overrides
    assert call.loader_overrides is loader_overrides
    assert call.strict_config is True
    assert call.default_analytics_enabled is False
    assert call.transport == "stdio"
    assert call.session_source == "vscode"
    assert call.auth == "default"
    assert call.runtime_options == AppServerRuntimeOptions()


def test_runtime_transport_decisions_match_stdio_single_client_mode() -> None:
    # Rust: Stdio transport is single-client and shuts down when no connections remain.
    decisions = runtime_transport_decisions("stdio", AppServerRuntimeOptions())

    assert decisions == RuntimeTransportDecisions(
        single_client_mode=True,
        shutdown_when_no_connections=True,
        graceful_signal_restart_enabled=False,
    )


def test_runtime_transport_decisions_enable_graceful_signal_for_non_stdio() -> None:
    # Rust: non-stdio transports can use graceful signal restart when enabled.
    decisions = runtime_transport_decisions("websocket", AppServerRuntimeOptions())

    assert decisions.single_client_mode is False
    assert decisions.shutdown_when_no_connections is False
    assert decisions.graceful_signal_restart_enabled is True

    disabled = runtime_transport_decisions(
        "unix_socket",
        AppServerRuntimeOptions(install_shutdown_signal_handler=False),
    )
    assert disabled.graceful_signal_restart_enabled is False


def test_remote_control_runtime_decision_requires_request_and_state_db() -> None:
    # Rust: remote control is enabled only when requested and state_db is available.
    enabled = remote_control_runtime_decision(
        runtime_options=AppServerRuntimeOptions(remote_control_enabled=True),
        state_db_available=True,
        transport_accept_handle_count=0,
    )
    disabled = remote_control_runtime_decision(
        runtime_options=AppServerRuntimeOptions(remote_control_enabled=True),
        state_db_available=False,
        transport_accept_handle_count=1,
    )

    assert enabled == RemoteControlRuntimeDecision(requested=True, enabled=True)
    assert disabled == RemoteControlRuntimeDecision(
        requested=True,
        enabled=False,
        log_disabled_missing_state_db=True,
    )


def test_remote_control_runtime_decision_logs_when_requested_without_state_db() -> None:
    # Rust: requested remote control without state DB logs even when another transport exists.
    decision = remote_control_runtime_decision(
        runtime_options=AppServerRuntimeOptions(remote_control_enabled=True),
        state_db_available=False,
        transport_accept_handle_count=1,
    )

    assert decision.log_disabled_missing_state_db is True
    assert decision.error_message is None


def test_remote_control_runtime_decision_reports_no_transport_errors() -> None:
    # Rust: no accept handles and no remote control is an InvalidInput runtime error.
    plain = remote_control_runtime_decision(
        runtime_options=AppServerRuntimeOptions(remote_control_enabled=False),
        state_db_available=False,
        transport_accept_handle_count=0,
    )
    requested_without_db = remote_control_runtime_decision(
        runtime_options=AppServerRuntimeOptions(remote_control_enabled=True),
        state_db_available=False,
        transport_accept_handle_count=0,
    )

    assert plain == RemoteControlRuntimeDecision(
        requested=False,
        enabled=False,
        error_message="no transport configured; use --listen or enable remote control",
    )
    assert requested_without_db == RemoteControlRuntimeDecision(
        requested=True,
        enabled=False,
        log_disabled_missing_state_db=True,
        error_message=(
            "no transport configured; remote control disabled because sqlite "
            "state db is unavailable"
        ),
    )


def test_transport_startup_projection_starts_stdio_connection() -> None:
    # Rust: Stdio creates a client-name oneshot receiver and calls start_stdio_connection.
    projection = transport_startup_projection("stdio")

    assert projection == TransportStartupProjection(
        create_stdio_client_name_channel=True,
        app_server_client_name_rx_available=True,
        start_stdio_connection=True,
        start_control_socket_acceptor=False,
        start_websocket_acceptor=False,
        push_accept_handle_count=0,
        requires_websocket_auth_policy=False,
        drop_unix_socket_startup_lock=True,
    )


def test_transport_startup_projection_starts_unix_socket_acceptor() -> None:
    # Rust: UnixSocket starts the control socket acceptor and pushes its handle.
    projection = transport_startup_projection("unix_socket")

    assert projection.start_stdio_connection is False
    assert projection.start_control_socket_acceptor is True
    assert projection.start_websocket_acceptor is False
    assert projection.push_accept_handle_count == 1
    assert projection.app_server_client_name_rx_available is False
    assert projection.requires_websocket_auth_policy is False


def test_transport_startup_projection_starts_websocket_acceptor_with_policy() -> None:
    # Rust: WebSocket builds policy_from_settings(auth), starts the acceptor, and pushes its handle.
    projection = transport_startup_projection("websocket")

    assert projection.start_stdio_connection is False
    assert projection.start_control_socket_acceptor is False
    assert projection.start_websocket_acceptor is True
    assert projection.push_accept_handle_count == 1
    assert projection.requires_websocket_auth_policy is True


def test_transport_startup_projection_off_starts_no_acceptor() -> None:
    # Rust: Off falls through without starting or pushing a transport acceptor.
    projection = transport_startup_projection("off")

    assert projection == TransportStartupProjection(
        create_stdio_client_name_channel=False,
        app_server_client_name_rx_available=False,
        start_stdio_connection=False,
        start_control_socket_acceptor=False,
        start_websocket_acceptor=False,
        push_accept_handle_count=0,
        requires_websocket_auth_policy=False,
        drop_unix_socket_startup_lock=True,
    )


def test_transport_startup_projection_rejects_unknown_transport() -> None:
    # Python guard: Rust's AppServerTransport enum has only Stdio/UnixSocket/WebSocket/Off here.
    with pytest.raises(ValueError, match="unsupported app-server transport"):
        transport_startup_projection("named_pipe")


def test_transport_acceptor_startup_projection_starts_stdio_before_lock_drop() -> None:
    # Rust: Stdio creates the client-name channel and awaits start_stdio_connection.
    projection = transport_acceptor_startup_projection("stdio")

    assert projection == TransportAcceptorStartupProjection(
        create_stdio_client_name_channel=True,
        set_app_server_client_name_rx=True,
        build_websocket_auth_policy=False,
        start_acceptor="stdio",
        push_accept_handle=False,
        drop_unix_socket_startup_lock=True,
    )


def test_transport_acceptor_startup_projection_unix_error_prevents_push_and_drop() -> None:
    # Rust: start_control_socket_acceptor failure returns before pushing handle or dropping lock.
    projection = transport_acceptor_startup_projection("unix_socket", acceptor_ok=False)

    assert projection == TransportAcceptorStartupProjection(
        create_stdio_client_name_channel=False,
        set_app_server_client_name_rx=False,
        build_websocket_auth_policy=False,
        start_acceptor="unix_socket",
        push_accept_handle=False,
        drop_unix_socket_startup_lock=False,
        return_error=True,
        error_stage="start_control_socket_acceptor",
    )


def test_transport_acceptor_startup_projection_websocket_policy_error_prevents_acceptor() -> None:
    # Rust: policy_from_settings(&auth)? runs before start_websocket_acceptor.
    projection = transport_acceptor_startup_projection("websocket", policy_ok=False)

    assert projection == TransportAcceptorStartupProjection(
        create_stdio_client_name_channel=False,
        set_app_server_client_name_rx=False,
        build_websocket_auth_policy=True,
        start_acceptor=None,
        push_accept_handle=False,
        drop_unix_socket_startup_lock=False,
        return_error=True,
        error_stage="policy_from_settings",
    )


def test_transport_acceptor_startup_projection_websocket_success_pushes_handle() -> None:
    # Rust: WebSocket builds auth policy, starts acceptor, pushes accept handle.
    projection = transport_acceptor_startup_projection("websocket")

    assert projection == TransportAcceptorStartupProjection(
        create_stdio_client_name_channel=False,
        set_app_server_client_name_rx=False,
        build_websocket_auth_policy=True,
        start_acceptor="websocket",
        push_accept_handle=True,
        drop_unix_socket_startup_lock=True,
    )


def test_transport_acceptor_startup_projection_off_only_drops_lock() -> None:
    # Rust: Off starts no acceptor and then drops the Unix socket startup lock.
    projection = transport_acceptor_startup_projection("off")

    assert projection == TransportAcceptorStartupProjection(
        create_stdio_client_name_channel=False,
        set_app_server_client_name_rx=False,
        build_websocket_auth_policy=False,
        start_acceptor=None,
        push_accept_handle=False,
        drop_unix_socket_startup_lock=True,
    )


def test_unix_socket_startup_lock_projection_skips_non_unix_transports() -> None:
    # Rust: unix_socket_startup_lock is None for non-UnixSocket transports.
    assert unix_socket_startup_lock_projection("stdio") == UnixSocketStartupLockProjection(
        compute_startup_lock_path=False,
        acquire_startup_lock=False,
        prepare_control_socket_path=False,
        store_startup_lock=False,
    )


def test_unix_socket_startup_lock_projection_prepares_unix_socket() -> None:
    # Rust: UnixSocket computes startup lock, acquires it, prepares socket path, stores lock.
    projection = unix_socket_startup_lock_projection(
        "unix_socket",
        socket_path="/tmp/codex.sock",
    )

    assert projection == UnixSocketStartupLockProjection(
        compute_startup_lock_path=True,
        acquire_startup_lock=True,
        prepare_control_socket_path=True,
        store_startup_lock=True,
        socket_path="/tmp/codex.sock",
    )


def test_unix_socket_startup_lock_projection_stops_on_lock_path_error() -> None:
    # Rust: app_server_startup_lock_path failure returns before acquiring or preparing.
    projection = unix_socket_startup_lock_projection(
        "unix_socket",
        socket_path="/tmp/codex.sock",
        lock_path_ok=False,
    )

    assert projection == UnixSocketStartupLockProjection(
        compute_startup_lock_path=True,
        acquire_startup_lock=False,
        prepare_control_socket_path=False,
        store_startup_lock=False,
        socket_path="/tmp/codex.sock",
        return_error=True,
        error_stage="startup_lock_path",
    )


def test_unix_socket_startup_lock_projection_stops_on_acquire_error() -> None:
    # Rust: acquire_app_server_startup_lock failure returns before preparing socket path.
    projection = unix_socket_startup_lock_projection(
        "unix_socket",
        socket_path="/tmp/codex.sock",
        acquire_lock_ok=False,
    )

    assert projection == UnixSocketStartupLockProjection(
        compute_startup_lock_path=True,
        acquire_startup_lock=True,
        prepare_control_socket_path=False,
        store_startup_lock=False,
        socket_path="/tmp/codex.sock",
        return_error=True,
        error_stage="acquire_startup_lock",
    )


def test_unix_socket_startup_lock_projection_stops_on_prepare_error() -> None:
    # Rust: prepare_control_socket_path failure returns without storing the startup lock.
    projection = unix_socket_startup_lock_projection(
        "unix_socket",
        socket_path="/tmp/codex.sock",
        prepare_socket_ok=False,
    )

    assert projection == UnixSocketStartupLockProjection(
        compute_startup_lock_path=True,
        acquire_startup_lock=True,
        prepare_control_socket_path=True,
        store_startup_lock=False,
        socket_path="/tmp/codex.sock",
        return_error=True,
        error_stage="prepare_control_socket_path",
    )


def test_remote_control_startup_projection_passes_stdio_client_name_receiver() -> None:
    # Rust: start_remote_control receives RemoteControlStartConfig plus the stdio client-name receiver.
    projection = remote_control_startup_projection(
        config=_AppServerConfig(),
        installation_id="install-123",
        state_db_available=True,
        app_server_client_name_rx_available=True,
        remote_control_enabled=True,
    )

    assert projection == RemoteControlStartupProjection(
        start_remote_control=True,
        remote_control_url="https://chatgpt.example.test",
        installation_id="install-123",
        pass_state_db=True,
        pass_auth_manager=True,
        pass_transport_event_sender=True,
        pass_transport_shutdown_token=True,
        pass_app_server_client_name_rx=True,
        remote_control_enabled=True,
        push_accept_handle_count=1,
        keep_remote_control_handle=True,
    )


def test_remote_control_startup_projection_preserves_disabled_flag() -> None:
    # Rust: start_remote_control is still called, but receives remote_control_enabled=false.
    projection = remote_control_startup_projection(
        config={"chatgpt_base_url": "https://chatgpt.example.test"},
        installation_id="install-456",
        state_db_available=False,
        auth_manager_available=True,
        app_server_client_name_rx_available=False,
        remote_control_enabled=False,
    )

    assert projection.start_remote_control is True
    assert projection.pass_state_db is False
    assert projection.pass_auth_manager is True
    assert projection.pass_app_server_client_name_rx is False
    assert projection.remote_control_enabled is False
    assert projection.push_accept_handle_count == 1
    assert projection.keep_remote_control_handle is True


def test_remote_control_startup_projection_error_prevents_accept_handle_push() -> None:
    # Rust: start_remote_control(...).await? returns before pushing its accept handle.
    projection = remote_control_startup_projection(
        config={"chatgpt_base_url": "https://chatgpt.example.test"},
        installation_id="install-789",
        state_db_available=True,
        app_server_client_name_rx_available=False,
        remote_control_enabled=True,
        startup_ok=False,
    )

    assert projection == RemoteControlStartupProjection(
        start_remote_control=True,
        remote_control_url="https://chatgpt.example.test",
        installation_id="install-789",
        pass_state_db=True,
        pass_auth_manager=True,
        pass_transport_event_sender=True,
        pass_transport_shutdown_token=True,
        pass_app_server_client_name_rx=False,
        remote_control_enabled=True,
        push_accept_handle_count=0,
        keep_remote_control_handle=False,
        return_error=True,
        error_stage="start_remote_control",
    )


def test_app_text_range_projects_core_text_range_fields() -> None:
    # Rust: app_text_range copies CoreTextRange start/end line and column.
    result = app_text_range(_Range())

    assert result == TextRange(
        start=TextPosition(line=2, column=4),
        end=TextPosition(line=3, column=8),
    )


def test_config_warning_from_error_uses_config_location_when_present() -> None:
    # Rust: config_warning_from_error includes ConfigLoadError path/range.
    err = _ConfigLoadError("bad config")
    warning = config_warning_from_error("Invalid configuration; using defaults.", err)

    assert warning.summary == "Invalid configuration; using defaults."
    assert warning.details == "bad config"
    assert warning.path == "config.toml"
    assert warning.range == TextRange(
        start=TextPosition(line=2, column=4),
        end=TextPosition(line=3, column=8),
    )
    assert config_error_location(ValueError("plain")) is None


def test_config_warning_from_error_without_config_location_keeps_details_only() -> None:
    # Rust: config_warning_from_error keeps summary/details but omits path/range without ConfigLoadError.
    err = ValueError("plain failure")
    warning = config_warning_from_error("Invalid configuration; using defaults.", err)

    assert warning.summary == "Invalid configuration; using defaults."
    assert warning.details == "plain failure"
    assert warning.path is None
    assert warning.range is None


def test_exec_policy_warning_location_matches_parse_policy_branches() -> None:
    # Rust: parse-policy errors prefer source location, otherwise path only.
    assert exec_policy_warning_location(_ExecPolicyError("bad policy")) == (
        "policy.exec",
        TextRange(
            start=TextPosition(line=2, column=4),
            end=TextPosition(line=3, column=8),
        ),
    )

    path_only = Exception("parse failed")
    path_only.kind = "parse_policy"  # type: ignore[attr-defined]
    path_only.path = "fallback.exec"  # type: ignore[attr-defined]
    assert exec_policy_warning_location(path_only) == ("fallback.exec", None)
    assert exec_policy_warning_location(ValueError("other")) == (None, None)


def test_analytics_rpc_transport_buckets_like_rust() -> None:
    # Rust: Stdio maps to stdio; UnixSocket/WebSocket/Off map to websocket.
    assert analytics_rpc_transport("stdio") is AppServerRpcTransport.STDIO
    assert analytics_rpc_transport("unix_socket") is AppServerRpcTransport.WEBSOCKET
    assert analytics_rpc_transport("websocket") is AppServerRpcTransport.WEBSOCKET
    assert analytics_rpc_transport("off") is AppServerRpcTransport.WEBSOCKET


def test_project_config_warning_lists_disabled_project_layers() -> None:
    # Rust: project_config_warning lists disabled Project layers in order.
    config = {
        "config_layer_stack": {
            "layers": [
                {
                    "name": {"kind": "User"},
                    "disabled_reason": "ignored",
                },
                {
                    "name": {"kind": "Project", "dot_codex_folder": "repo/.codex"},
                    "disabled_reason": "project is untrusted",
                },
                {
                    "name": {"kind": "Project", "dot_codex_folder": "repo/sub/.codex"},
                    "disabled_reason": "parent is untrusted",
                },
                {
                    "name": {"kind": "Project", "dot_codex_folder": "repo/enabled/.codex"},
                    "disabled_reason": None,
                },
            ],
        },
    }

    warning = project_config_warning(config)

    assert warning is not None
    assert warning.details is None
    assert warning.path is None
    assert warning.range is None
    assert warning.summary == (
        "Project-local config, hooks, and exec policies are disabled in the "
        "following folders until the project is trusted, but skills still load.\n"
        "    1. repo/.codex\n"
        "       project is untrusted\n"
        "    2. repo/sub/.codex\n"
        "       parent is untrusted\n"
    )


def test_project_config_warning_returns_none_without_disabled_projects() -> None:
    # Rust: project_config_warning returns None when there are no disabled projects.
    assert project_config_warning({"config_layer_stack": {"layers": []}}) is None
    assert (
        project_config_warning(
            {
                "config_layer_stack": {
                    "layers": [
                        {
                            "name": {"kind": "Project", "dot_codex_folder": "repo/.codex"},
                            "disabled_reason": None,
                        }
                    ]
                }
            }
        )
        is None
    )


def test_collect_config_warnings_preserves_rust_accumulation_order() -> None:
    # Rust: run_main_with_transport_options appends config warnings in a fixed order.
    initial = ConfigWarningNotification(
        summary="Invalid configuration; using defaults.",
        details="bad config",
        path=None,
        range=None,
    )
    exec_err = _ExecPolicyError("bad policy")
    config = {
        "config_layer_stack": {
            "layers": [
                {
                    "name": {"kind": "Project", "dot_codex_folder": "repo/.codex"},
                    "disabled_reason": "project is untrusted",
                }
            ],
        },
        "startup_warnings": ["startup warning one", "startup warning two"],
    }

    warnings = collect_config_warnings(
        config,
        initial_warnings=[initial],
        exec_policy_error=exec_err,
        system_bwrap_warning="system bwrap warning",
    )

    assert [warning.summary for warning in warnings] == [
        "Invalid configuration; using defaults.",
        "Error parsing rules; custom rules not applied.",
        (
            "Project-local config, hooks, and exec policies are disabled in the "
            "following folders until the project is trusted, but skills still load.\n"
            "    1. repo/.codex\n"
            "       project is untrusted\n"
        ),
        "startup warning one",
        "startup warning two",
        "system bwrap warning",
    ]
    assert warnings[1].details == "bad policy"
    assert warnings[1].path == "policy.exec"
    assert warnings[1].range == TextRange(
        start=TextPosition(line=2, column=4),
        end=TextPosition(line=3, column=8),
    )
    assert warnings[3].details is None
    assert warnings[5].path is None


def test_collect_config_warnings_omits_absent_optional_sources() -> None:
    # Rust: warning sources are appended only when present.
    assert collect_config_warnings({"startup_warnings": []}) == []


def test_system_bwrap_warning_projection_appends_summary_only_notification() -> None:
    # Rust: app-server calls system_bwrap_warning(permission_profile) and appends summary-only warnings.
    config = {"permissions": {"permission_profile": "workspace-write"}}

    projection = system_bwrap_warning_projection(
        config,
        warning_result="system bwrap warning",
    )

    assert projection == SystemBwrapWarningProjection(
        call_system_bwrap_warning=True,
        permission_profile="workspace-write",
        append_config_warning=True,
        notification=ConfigWarningNotification(
            summary="system bwrap warning",
            details=None,
            path=None,
            range=None,
        ),
    )


def test_system_bwrap_warning_projection_omits_absent_warning() -> None:
    # Rust: None from system_bwrap_warning produces no ConfigWarningNotification.
    class _Permissions:
        def permission_profile(self) -> str:
            return "danger-full-access"

    projection = system_bwrap_warning_projection(
        {"permissions": _Permissions()},
        warning_result=None,
    )

    assert projection == SystemBwrapWarningProjection(
        call_system_bwrap_warning=True,
        permission_profile="danger-full-access",
        append_config_warning=False,
        notification=None,
    )


def test_configured_thread_config_loader_defaults_to_noop() -> None:
    # Rust: configured_thread_config_loader returns NoopThreadConfigLoader without endpoint.
    assert isinstance(configured_thread_config_loader({}), NoopThreadConfigLoader)
    assert isinstance(
        configured_thread_config_loader({"experimental_thread_config_endpoint": None}),
        NoopThreadConfigLoader,
    )


def test_configured_thread_config_loader_uses_remote_endpoint() -> None:
    # Rust: configured_thread_config_loader wraps configured endpoints in RemoteThreadConfigLoader.
    loader = configured_thread_config_loader(
        {"experimental_thread_config_endpoint": "http://127.0.0.1:8061"}
    )

    assert isinstance(loader, RemoteThreadConfigLoader)
    assert loader.endpoint == "http://127.0.0.1:8061"


def test_config_preload_projection_replaces_cloud_requirements_on_success() -> None:
    # Rust: successful preload replaces the thread loader and cloud requirements loader.
    projection = config_preload_projection(load_ok=True)

    assert projection == ConfigPreloadProjection(
        replace_thread_config_loader=True,
        load_auth_manager_with_codex_api_key_env=False,
        replace_cloud_requirements_loader=True,
        warn_failed_preload_cloud_requirements=False,
        continue_startup=True,
    )


def test_config_preload_projection_warns_and_continues_on_failure() -> None:
    # Rust: preload failure warns and continues; it is not fail-closed.
    projection = config_preload_projection(load_ok=False)

    assert projection == ConfigPreloadProjection(
        replace_thread_config_loader=False,
        load_auth_manager_with_codex_api_key_env=None,
        replace_cloud_requirements_loader=False,
        warn_failed_preload_cloud_requirements=True,
        continue_startup=True,
    )


def test_config_provider_startup_projection_uses_env_manager_when_ignoring_user_config() -> None:
    # Rust: ignore_user_config selects EnvironmentManager::from_env before ConfigManager::new.
    projection = config_provider_startup_projection(ignore_user_config=True)

    assert projection == ConfigProviderStartupProjection(
        parse_cli_overrides=True,
        find_codex_home=True,
        build_local_runtime_paths=True,
        use_env_environment_manager=True,
        use_codex_home_environment_manager=False,
        create_config_manager=True,
        config_manager_uses_noop_thread_loader=True,
        pass_loader_overrides=True,
        pass_strict_config=True,
        pass_arg0_paths=True,
        continue_startup=True,
    )


def test_config_provider_startup_projection_maps_fallible_setup_order() -> None:
    # Rust: -c parse errors stop before codex-home lookup and become InvalidInput.
    assert config_provider_startup_projection(
        ignore_user_config=False,
        parse_overrides_ok=False,
    ) == ConfigProviderStartupProjection(
        parse_cli_overrides=True,
        find_codex_home=False,
        build_local_runtime_paths=False,
        use_env_environment_manager=False,
        use_codex_home_environment_manager=False,
        create_config_manager=False,
        config_manager_uses_noop_thread_loader=False,
        pass_loader_overrides=False,
        pass_strict_config=False,
        pass_arg0_paths=False,
        continue_startup=False,
        return_parse_overrides_invalid_input=True,
    )

    # Rust: local runtime path construction errors stop before environment-manager creation.
    assert config_provider_startup_projection(
        ignore_user_config=False,
        local_runtime_paths_ok=False,
    ) == ConfigProviderStartupProjection(
        parse_cli_overrides=True,
        find_codex_home=True,
        build_local_runtime_paths=True,
        use_env_environment_manager=False,
        use_codex_home_environment_manager=False,
        create_config_manager=False,
        config_manager_uses_noop_thread_loader=False,
        pass_loader_overrides=False,
        pass_strict_config=False,
        pass_arg0_paths=False,
        continue_startup=False,
        return_local_runtime_paths_error=True,
    )

    # Rust: environment-manager failures happen after runtime-path construction.
    assert config_provider_startup_projection(
        ignore_user_config=False,
        environment_manager_ok=False,
    ) == ConfigProviderStartupProjection(
        parse_cli_overrides=True,
        find_codex_home=True,
        build_local_runtime_paths=True,
        use_env_environment_manager=False,
        use_codex_home_environment_manager=True,
        create_config_manager=False,
        config_manager_uses_noop_thread_loader=False,
        pass_loader_overrides=False,
        pass_strict_config=False,
        pass_arg0_paths=False,
        continue_startup=False,
        return_environment_manager_error=True,
    )


def test_runtime_auth_manager_projection_disables_codex_api_key_env() -> None:
    # Rust: runtime AuthManager::shared_from_config is called after transport startup with env opt-in false.
    assert runtime_auth_manager_projection() == RuntimeAuthManagerProjection(
        create_auth_manager=True,
        enable_codex_api_key_env=False,
        after_transport_startup=True,
        after_unix_socket_startup_lock_drop=True,
    )


def test_main_config_load_projection_uses_loaded_config_on_success() -> None:
    # Rust: successful load_latest_config enables the personality migration pass.
    projection = main_config_load_projection(load_ok=True, strict_config=True)

    assert projection == MainConfigLoadProjection(
        use_loaded_config=True,
        append_invalid_config_warning=False,
        load_default_config=False,
        should_run_personality_migration=True,
    )


def test_main_config_load_projection_strict_failure_returns_original_error() -> None:
    # Rust: strict_config returns the original load_latest_config error.
    projection = main_config_load_projection(load_ok=False, strict_config=True)

    assert projection == MainConfigLoadProjection(
        use_loaded_config=False,
        append_invalid_config_warning=False,
        load_default_config=False,
        should_run_personality_migration=False,
        return_original_error=True,
    )


def test_main_config_load_projection_nonstrict_failure_warns_and_loads_default() -> None:
    # Rust: non-strict config errors append a warning and load default config.
    projection = main_config_load_projection(load_ok=False, strict_config=False)

    assert projection == MainConfigLoadProjection(
        use_loaded_config=False,
        append_invalid_config_warning=True,
        load_default_config=True,
        should_run_personality_migration=False,
    )


def test_main_config_load_projection_default_config_error_maps_invalid_data() -> None:
    # Rust: default config load failure maps to a prefixed InvalidData error.
    projection = main_config_load_projection(
        load_ok=False,
        strict_config=False,
        default_load_ok=False,
    )

    assert projection == MainConfigLoadProjection(
        use_loaded_config=False,
        append_invalid_config_warning=True,
        load_default_config=True,
        should_run_personality_migration=False,
        return_default_config_error=True,
        default_config_error_prefix="error loading default config after config error:",
    )


def test_personality_migration_projection_skips_when_disabled() -> None:
    # Rust: should_run_personality_migration=false bypasses the migration block.
    projection = personality_migration_projection(should_run=False)

    assert projection == PersonalityMigrationProjection(
        attempt_deserialize_effective_config=False,
        call_maybe_migrate_personality=False,
        pass_state_db_clone=False,
        reload_latest_config=False,
        replace_config_with_reloaded=False,
    )


def test_personality_migration_projection_warns_on_deserialize_failure() -> None:
    # Rust: effective config deserialization failure warns and continues.
    projection = personality_migration_projection(
        should_run=True,
        deserialize_ok=False,
    )

    assert projection == PersonalityMigrationProjection(
        attempt_deserialize_effective_config=True,
        call_maybe_migrate_personality=False,
        pass_state_db_clone=False,
        reload_latest_config=False,
        replace_config_with_reloaded=False,
        warn_deserialize_failed=True,
    )


def test_personality_migration_projection_reloads_after_applied_migration() -> None:
    # Rust: Applied migration reloads latest config and replaces the config value.
    projection = personality_migration_projection(
        should_run=True,
        migration_status="applied",
    )

    assert projection == PersonalityMigrationProjection(
        attempt_deserialize_effective_config=True,
        call_maybe_migrate_personality=True,
        pass_state_db_clone=True,
        reload_latest_config=True,
        replace_config_with_reloaded=True,
    )


def test_personality_migration_projection_maps_reload_error() -> None:
    # Rust: reload failure after Applied migration maps to a prefixed InvalidData error.
    projection = personality_migration_projection(
        should_run=True,
        migration_status="applied",
        reload_ok=False,
    )

    assert projection == PersonalityMigrationProjection(
        attempt_deserialize_effective_config=True,
        call_maybe_migrate_personality=True,
        pass_state_db_clone=True,
        reload_latest_config=True,
        replace_config_with_reloaded=False,
        return_reload_error=True,
        reload_error_prefix="error reloading config after personality migration:",
    )


def test_personality_migration_projection_ignores_skipped_statuses() -> None:
    # Rust: all skipped migration statuses take no further action.
    for status in (
        "skipped_marker",
        "skipped_explicit_personality",
        "skipped_no_sessions",
    ):
        assert personality_migration_projection(
            should_run=True,
            migration_status=status,
        ) == PersonalityMigrationProjection(
            attempt_deserialize_effective_config=True,
            call_maybe_migrate_personality=True,
            pass_state_db_clone=True,
            reload_latest_config=False,
            replace_config_with_reloaded=False,
        )


def test_personality_migration_projection_warns_on_migration_error() -> None:
    # Rust: maybe_migrate_personality errors warn and continue startup.
    projection = personality_migration_projection(
        should_run=True,
        migration_status="error",
    )

    assert projection == PersonalityMigrationProjection(
        attempt_deserialize_effective_config=True,
        call_maybe_migrate_personality=True,
        pass_state_db_clone=True,
        reload_latest_config=False,
        replace_config_with_reloaded=False,
        warn_migration_failed=True,
    )


def test_personality_migration_projection_rejects_unknown_status() -> None:
    # Rust: only the declared PersonalityMigrationStatus variants are handled.
    with pytest.raises(ValueError, match="unsupported personality migration status"):
        personality_migration_projection(should_run=True, migration_status="mystery")


def test_state_db_startup_projection_marks_state_db_available_on_success() -> None:
    # Rust: rollout_state_db::try_init success stores Some(state_db).
    projection = state_db_startup_projection(init_ok=True, sqlite_home="/tmp/codex-sqlite")

    assert projection == StateDbStartupProjection(
        try_init_state_db=True,
        state_db_available=True,
    )


def test_state_db_startup_projection_returns_sqlite_home_error_on_failure() -> None:
    # Rust: try_init failure returns an io::Error with sqlite_home in the message.
    projection = state_db_startup_projection(init_ok=False, sqlite_home="/tmp/codex-sqlite")

    assert projection == StateDbStartupProjection(
        try_init_state_db=True,
        state_db_available=False,
        return_error=True,
        error_prefix="failed to initialize sqlite state runtime under /tmp/codex-sqlite:",
    )


def test_telemetry_startup_projection_records_process_and_sqlite_on_success() -> None:
    # Rust: successful build_provider records process start and installs sqlite telemetry.
    projection = telemetry_startup_projection(
        build_ok=True,
        package_version="1.2.3",
        default_analytics_enabled=True,
    )

    assert projection == TelemetryStartupProjection(
        build_provider=True,
        package_version="1.2.3",
        service_name="codex-app-server",
        default_analytics_enabled=True,
        record_process_start=True,
        install_sqlite_telemetry=True,
    )


def test_telemetry_startup_projection_maps_build_error_before_install() -> None:
    # Rust: build_provider failure maps to InvalidData before telemetry side effects.
    projection = telemetry_startup_projection(
        build_ok=False,
        package_version="1.2.3",
        service_name="custom-service",
        default_analytics_enabled=False,
    )

    assert projection == TelemetryStartupProjection(
        build_provider=True,
        package_version="1.2.3",
        service_name="custom-service",
        default_analytics_enabled=False,
        record_process_start=False,
        install_sqlite_telemetry=False,
        return_error=True,
        error_prefix="error loading otel config:",
    )


def test_outbound_control_event_opened_preserves_router_fields() -> None:
    # Rust: OutboundControlEvent::Opened carries writer and connection state fields.
    event = OutboundControlEvent.opened(
        connection_id="conn-1",
        writer="writer",
        disconnect_sender="cancel",
        initialized=True,
        experimental_api_enabled=False,
        opted_out_notification_methods={"notifications/codex_event"},
    )

    assert event.kind == "opened"
    assert event.connection_id == "conn-1"
    assert event.writer == "writer"
    assert event.disconnect_sender == "cancel"
    assert event.initialized is True
    assert event.experimental_api_enabled is False
    assert event.opted_out_notification_methods == {"notifications/codex_event"}


def test_outbound_control_event_closed_and_disconnect_all_shapes() -> None:
    # Rust: OutboundControlEvent::Closed carries only connection_id; DisconnectAll has no payload.
    closed = OutboundControlEvent.closed("conn-1")
    disconnect_all = OutboundControlEvent.disconnect_all()

    assert closed.kind == "closed"
    assert closed.connection_id == "conn-1"
    assert closed.writer is None
    assert disconnect_all.kind == "disconnect_all"
    assert disconnect_all.connection_id is None


def test_outbound_router_startup_projection_initializes_biased_select_worker() -> None:
    # Rust: outbound router task starts with an empty map and a biased select control arm first.
    assert outbound_router_startup_projection() == OutboundRouterStartupProjection(
        spawn_worker=True,
        initialize_outbound_connections_empty=True,
        select_is_biased=True,
        control_arm_priority=0,
        outgoing_arm_priority=1,
        control_arm_receives_outbound_control=True,
        outgoing_arm_receives_envelopes=True,
        log_task_exited_after_loop=True,
    )


def test_outbound_router_control_projection_inserts_opened_connection() -> None:
    # Rust: OutboundControlEvent::Opened inserts an OutboundConnectionState.
    event = OutboundControlEvent.opened(
        connection_id="conn-1",
        writer="writer",
        disconnect_sender="disconnect",
        initialized=True,
        experimental_api_enabled=False,
        opted_out_notification_methods=frozenset(),
    )
    projection = outbound_router_control_projection(event, outbound_connection_count=0)

    assert projection == OutboundRouterControlProjection(
        action="opened",
        connection_id="conn-1",
        insert_connection=True,
    )


def test_outbound_router_control_projection_removes_closed_connection() -> None:
    # Rust: OutboundControlEvent::Closed removes the connection from outbound state.
    projection = outbound_router_control_projection(
        OutboundControlEvent.closed("conn-1"),
        outbound_connection_count=2,
    )

    assert projection == OutboundRouterControlProjection(
        action="closed",
        connection_id="conn-1",
        remove_connection=True,
    )


def test_outbound_router_control_projection_disconnects_and_clears_all() -> None:
    # Rust: DisconnectAll requests disconnect on every outbound connection and clears the map.
    projection = outbound_router_control_projection(
        OutboundControlEvent.disconnect_all(),
        outbound_connection_count=3,
    )

    assert projection == OutboundRouterControlProjection(
        action="disconnect_all",
        request_disconnect_count=3,
        clear_connections=True,
    )


def test_outbound_router_control_projection_breaks_on_closed_channel() -> None:
    # Rust: outbound_control_rx.recv() returning None breaks the router loop.
    projection = outbound_router_control_projection(None, outbound_connection_count=1)

    assert projection == OutboundRouterControlProjection(
        action="break",
        should_break=True,
        log_outbound_router_task_exited=True,
    )


def test_outbound_router_control_projection_rejects_negative_count() -> None:
    # Python guard: Rust's HashMap len cannot be negative.
    with pytest.raises(ValueError, match="outbound_connection_count"):
        outbound_router_control_projection(
            OutboundControlEvent.disconnect_all(),
            outbound_connection_count=-1,
        )


def test_outbound_router_outgoing_projection_routes_present_envelope() -> None:
    # Rust: Some(envelope) is delegated to route_outgoing_envelope.
    projection = outbound_router_outgoing_projection({"envelope": "value"})

    assert projection == OutboundRouterOutgoingProjection(route_outgoing_envelope=True)


def test_outbound_router_outgoing_projection_breaks_on_closed_channel() -> None:
    # Rust: outgoing_rx.recv() returning None breaks the router loop.
    projection = outbound_router_outgoing_projection(None)

    assert projection == OutboundRouterOutgoingProjection(
        route_outgoing_envelope=False,
        should_break=True,
        log_outbound_router_task_exited=True,
    )


def test_outgoing_message_runtime_projection_assembles_sender_and_analytics_client() -> None:
    # Rust: analytics client is built before OutgoingMessageSender and cloned into it.
    assert outgoing_message_runtime_projection() == OutgoingMessageRuntimeProjection(
        clone_auth_manager_for_analytics=True,
        build_analytics_events_client_from_config=True,
        pass_config_to_analytics_client=True,
        create_outgoing_message_sender=True,
        pass_outgoing_tx=True,
        clone_analytics_client_for_sender=True,
        wrap_sender_in_arc=True,
        clone_initialize_notification_sender=True,
    )


def test_message_processor_args_projection_assembles_runtime_fields() -> None:
    # Rust: MessageProcessorArgs receives runtime handles plus analytics_rpc_transport(&transport).
    projection = message_processor_args_projection(
        transport="websocket",
        runtime_options=AppServerRuntimeOptions(),
        config_warnings=["warning one", "warning two"],
        session_source="vscode",
        installation_id="install-123",
        log_db_available=True,
        state_db_available=True,
    )

    assert projection == MessageProcessorArgsProjection(
        pass_outgoing=True,
        pass_analytics_events_client=True,
        pass_arg0_paths=True,
        wrap_config_in_arc=True,
        pass_config_manager=True,
        pass_environment_manager=True,
        clone_feedback=True,
        has_log_db=True,
        has_state_db=True,
        config_warning_count=2,
        session_source="vscode",
        pass_auth_manager=True,
        installation_id="install-123",
        rpc_transport=AppServerRpcTransport.WEBSOCKET,
        remote_control_handle_some=True,
        plugin_startup_tasks=PluginStartupTasks.START,
    )


def test_message_processor_args_projection_preserves_optional_state_and_plugin_task() -> None:
    # Rust: log_db/state_db are optional and plugin_startup_tasks is copied from runtime_options.
    projection = message_processor_args_projection(
        transport="stdio",
        runtime_options=AppServerRuntimeOptions(
            plugin_startup_tasks=PluginStartupTasks.SKIP,
        ),
        config_warnings=[],
        session_source="cli",
        installation_id="install-456",
        log_db_available=False,
        state_db_available=False,
        remote_control_handle_available=True,
    )

    assert projection.has_log_db is False
    assert projection.has_state_db is False
    assert projection.config_warning_count == 0
    assert projection.rpc_transport is AppServerRpcTransport.STDIO
    assert projection.plugin_startup_tasks is PluginStartupTasks.SKIP
    assert projection.remote_control_handle_some is True


def test_processor_startup_projection_initializes_loop_state() -> None:
    # Rust: processor worker subscribes watchers and initializes empty connection/shutdown state.
    assert processor_startup_projection() == ProcessorStartupProjection(
        create_processor_arc=True,
        subscribe_thread_created=True,
        subscribe_running_turn_count=True,
        initialize_connections_empty=True,
        subscribe_remote_control_status=True,
        clone_initial_remote_control_status=True,
        clone_transport_shutdown_token=True,
        spawn_worker=True,
        initialize_listen_for_threads_true=True,
        initialize_shutdown_state_default=True,
    )


def test_processor_worker_spawn_projection_matches_rust_capture_boundary() -> None:
    # Rust: processor_handle spawn clones auth, moves outbound_control_tx, and captures state in async move.
    assert processor_worker_spawn_projection() == ProcessorWorkerSpawnProjection(
        spawn_processor_worker=True,
        clone_auth_manager_before_analytics=True,
        move_outbound_control_tx_into_worker=True,
        create_processor_before_async_move=True,
        async_move_captures_processor_state=True,
        processor_handle_awaited_during_finalization=True,
    )


def test_processor_select_topology_projection_matches_rust_arm_order_and_gates() -> None:
    # Rust: processor loop select arms appear in this order with only signal, turn, and thread gates.
    assert processor_select_topology_projection() == ProcessorSelectTopologyProjection(
        arms=(
            "shutdown_signal",
            "running_turn_count_changed",
            "transport_event",
            "remote_control_status_changed",
            "thread_created",
        ),
        shutdown_signal_gate=(
            "graceful_signal_restart_enabled && !shutdown_state.forced()"
        ),
        running_turn_gate=(
            "graceful_signal_restart_enabled && shutdown_state.requested()"
        ),
        thread_created_gate="listen_for_threads",
        transport_event_ungated=True,
        remote_control_status_ungated=True,
    )


def test_connection_opened_projection_creates_outbound_and_connection_state() -> None:
    # Rust: ConnectionOpened creates outbound control state and connection state together.
    projection = connection_opened_projection(
        connection_id="conn-1",
        origin="stdio",
        writer="writer",
        disconnect_sender="cancel",
    )

    assert isinstance(projection, ConnectionOpenedProjection)
    assert projection.connection_id == "conn-1"
    assert projection.origin == "stdio"
    assert projection.initialized is False
    assert projection.experimental_api_enabled is False
    assert projection.opted_out_notification_methods == frozenset()
    assert projection.insert_connection is True
    assert projection.should_break is False
    assert projection.outbound_event == OutboundControlEvent.opened(
        connection_id="conn-1",
        writer="writer",
        disconnect_sender="cancel",
        initialized=False,
        experimental_api_enabled=False,
        opted_out_notification_methods=frozenset(),
    )


def test_connection_opened_projection_breaks_when_outbound_control_send_fails() -> None:
    # Rust: failed outbound_control_tx.send(Opened) breaks before inserting the connection.
    projection = connection_opened_projection(
        connection_id="conn-1",
        origin="stdio",
        writer="writer",
        disconnect_sender="cancel",
        outbound_control_send_ok=False,
    )

    assert projection.outbound_event.kind == "opened"
    assert projection.insert_connection is False
    assert projection.should_break is True


def test_connection_closed_projection_skips_unknown_connections() -> None:
    # Rust: ConnectionClosed for an unknown connection continues without side effects.
    projection = connection_closed_projection(
        connection_id="conn-missing",
        known_connection=False,
        remaining_connection_count=0,
        shutdown_when_no_connections=True,
    )

    assert projection == ConnectionClosedProjection(
        outbound_event=None,
        notify_processor=False,
        should_break=False,
    )


def test_connection_closed_projection_notifies_for_known_connections() -> None:
    # Rust: known ConnectionClosed sends outbound Closed and notifies the processor.
    projection = connection_closed_projection(
        connection_id="conn-1",
        known_connection=True,
        remaining_connection_count=2,
        shutdown_when_no_connections=True,
    )

    assert projection == ConnectionClosedProjection(
        outbound_event=OutboundControlEvent.closed("conn-1"),
        notify_processor=True,
        should_break=False,
    )


def test_connection_closed_projection_breaks_when_outbound_control_send_fails() -> None:
    # Rust: failed outbound_control_tx.send(Closed) breaks before processor notification.
    projection = connection_closed_projection(
        connection_id="conn-1",
        known_connection=True,
        remaining_connection_count=0,
        shutdown_when_no_connections=True,
        outbound_control_send_ok=False,
    )

    assert projection == ConnectionClosedProjection(
        outbound_event=OutboundControlEvent.closed("conn-1"),
        notify_processor=False,
        should_break=True,
    )


def test_connection_closed_projection_breaks_when_single_client_drains() -> None:
    # Rust: stdio single-client mode breaks when the last connection closes.
    projection = connection_closed_projection(
        connection_id="conn-1",
        known_connection=True,
        remaining_connection_count=0,
        shutdown_when_no_connections=True,
    )
    non_single_client = connection_closed_projection(
        connection_id="conn-1",
        known_connection=True,
        remaining_connection_count=0,
        shutdown_when_no_connections=False,
    )

    assert projection.should_break is True
    assert non_single_client.should_break is False


def test_transport_event_channel_closed_projection_breaks_processor_loop() -> None:
    # Rust: transport_event_rx.recv() returning None breaks the processor loop.
    projection = transport_event_channel_closed_projection()

    assert projection == TransportEventChannelClosedProjection(should_break=True)


def test_incoming_request_projection_skips_unknown_connection() -> None:
    # Rust: incoming requests for unknown connections warn and drop before processing.
    projection = incoming_request_projection(
        known_connection=False,
        was_initialized=False,
        is_initialized=True,
        experimental_api_enabled=True,
        opted_out_notification_methods={"notifications/codex_event"},
    )

    assert projection == IncomingRequestProjection(
        process_request=False,
        warn_unknown_connection=True,
    )


def test_incoming_request_projection_syncs_session_flags_after_processing() -> None:
    # Rust: after processing a request, outbound opt-out/API flags mirror session state.
    projection = incoming_request_projection(
        known_connection=True,
        was_initialized=True,
        is_initialized=True,
        experimental_api_enabled=True,
        opted_out_notification_methods={"notifications/codex_event", "experimental/foo"},
    )

    assert projection.process_request is True
    assert projection.update_outbound_opted_out_notification_methods == frozenset(
        {"notifications/codex_event", "experimental/foo"}
    )
    assert projection.update_outbound_experimental_api_enabled is True
    assert projection.warn_failed_update_outbound_opted_out_notifications is False
    assert projection.send_initialize_notifications is False
    assert projection.send_remote_control_status is False
    assert projection.notify_connection_initialized is False
    assert projection.mark_outbound_initialized is False


def test_incoming_request_projection_warns_when_opted_out_update_fails() -> None:
    # Rust: poisoned outbound opt-out write lock warns but continues later updates.
    projection = incoming_request_projection(
        known_connection=True,
        was_initialized=False,
        is_initialized=True,
        experimental_api_enabled=True,
        opted_out_notification_methods={"notifications/codex_event"},
        opted_out_update_ok=False,
    )

    assert projection.process_request is True
    assert projection.update_outbound_opted_out_notification_methods is None
    assert projection.warn_failed_update_outbound_opted_out_notifications is True
    assert projection.update_outbound_experimental_api_enabled is True
    assert projection.send_initialize_notifications is True
    assert projection.send_remote_control_status is True
    assert projection.notify_connection_initialized is True
    assert projection.mark_outbound_initialized is True


def test_incoming_request_projection_triggers_initialize_side_effects_once() -> None:
    # Rust: initialization side effects run only on false -> true transition.
    projection = incoming_request_projection(
        known_connection=True,
        was_initialized=False,
        is_initialized=True,
        experimental_api_enabled=False,
        opted_out_notification_methods=(),
        request_attestation="attestation-request",
    )
    not_yet_initialized = incoming_request_projection(
        known_connection=True,
        was_initialized=False,
        is_initialized=False,
        experimental_api_enabled=False,
        opted_out_notification_methods=(),
        request_attestation="attestation-request",
    )

    assert projection.send_initialize_notifications is True
    assert projection.send_remote_control_status is True
    assert projection.notify_connection_initialized is True
    assert projection.connection_initialized_request_attestation == "attestation-request"
    assert projection.mark_outbound_initialized is True
    assert not_yet_initialized.send_initialize_notifications is False
    assert not_yet_initialized.connection_initialized_request_attestation is None


def test_incoming_non_request_projection_routes_known_connections() -> None:
    # Rust: response/notification/error messages for known connections reach processor methods.
    assert incoming_non_request_projection(
        known_connection=True,
        message_kind="response",
    ) == IncomingNonRequestProjection(
        process_message=True,
        processor_method="process_response",
        message_kind="response",
    )
    assert incoming_non_request_projection(
        known_connection=True,
        message_kind="notification",
    ) == IncomingNonRequestProjection(
        process_message=True,
        processor_method="process_notification",
        message_kind="notification",
    )
    assert incoming_non_request_projection(
        known_connection=True,
        message_kind="error",
    ) == IncomingNonRequestProjection(
        process_message=True,
        processor_method="process_error",
        message_kind="error",
    )


def test_incoming_non_request_projection_drops_unknown_connections() -> None:
    # Rust: non-request messages for unknown connections warn and drop.
    assert incoming_non_request_projection(
        known_connection=False,
        message_kind="response",
    ) == IncomingNonRequestProjection(
        process_message=False,
        warn_unknown_connection=True,
        message_kind="response",
    )


def test_incoming_non_request_projection_rejects_unknown_kind() -> None:
    # Python guard: Rust's match arms only cover response/notification/error here.
    with pytest.raises(ValueError, match="unsupported JSON-RPC message kind"):
        incoming_non_request_projection(known_connection=True, message_kind="request")


def test_remote_control_status_projection_ignores_closed_watcher() -> None:
    # Rust: changed().is_err() continues without updating or notifying.
    projection = remote_control_status_projection(
        current_status="old",
        changed_ok=False,
        observed_status="new",
    )

    assert projection == RemoteControlStatusProjection(
        next_status="old",
        send_status_notification=False,
        continue_loop=True,
    )


def test_remote_control_status_projection_ignores_unchanged_status() -> None:
    # Rust: equal remote_control_status values do not send a notification.
    projection = remote_control_status_projection(
        current_status={"connected": True},
        changed_ok=True,
        observed_status={"connected": True},
    )

    assert projection == RemoteControlStatusProjection(
        next_status={"connected": True},
        send_status_notification=False,
        continue_loop=True,
    )


def test_remote_control_status_projection_notifies_on_change() -> None:
    # Rust: changed remote control status is stored and broadcast as a notification.
    projection = remote_control_status_projection(
        current_status="old",
        changed_ok=True,
        observed_status="new",
    )

    assert projection == RemoteControlStatusProjection(
        next_status="new",
        send_status_notification=True,
        continue_loop=True,
    )


class _InitializedSession:
    def __init__(self, initialized: bool) -> None:
        self._initialized = initialized

    def initialized(self) -> bool:
        return self._initialized


class _ConnectionState:
    def __init__(self, initialized: bool) -> None:
        self.session = _InitializedSession(initialized)


def test_thread_created_projection_attaches_initialized_connections_only() -> None:
    # Rust: Ok(thread_id) attaches only connections whose sessions are initialized.
    projection = thread_created_projection(
        recv_result="ok",
        thread_id="thread-1",
        connections={
            "conn-1": _ConnectionState(True),
            "conn-2": _ConnectionState(False),
            "conn-3": True,
        },
    )

    assert projection == ThreadCreatedProjection(
        attach_thread_listener=True,
        listen_for_threads=True,
        thread_id="thread-1",
        initialized_connection_ids=("conn-1", "conn-3"),
        continue_loop=True,
    )


def test_thread_created_projection_lagged_keeps_listener_without_attach() -> None:
    # Rust: lagged broadcast receivers log and continue without resyncing.
    projection = thread_created_projection(
        recv_result="lagged",
        thread_id="thread-1",
        connections={"conn-1": True},
    )

    assert projection == ThreadCreatedProjection(
        attach_thread_listener=False,
        listen_for_threads=True,
        warn_lagged_receiver=True,
        continue_loop=True,
    )


def test_thread_created_projection_closed_disables_thread_listener() -> None:
    # Rust: closed broadcast receiver disables future thread-created listening.
    projection = thread_created_projection(recv_result="closed", connections={"conn-1": True})

    assert projection == ThreadCreatedProjection(
        attach_thread_listener=False,
        listen_for_threads=False,
        continue_loop=True,
    )


def test_thread_created_projection_rejects_unknown_result() -> None:
    # Python guard: Rust only handles Ok, Lagged, and Closed recv results here.
    with pytest.raises(ValueError, match="unsupported thread-created recv result"):
        thread_created_projection(recv_result="empty")


def test_processor_exit_projection_cleans_up_when_not_forced() -> None:
    # Rust: processor task exit shuts down gates/background tasks/threads unless forced.
    projection = processor_exit_projection(shutdown_forced=False)

    assert projection == ProcessorExitProjection(
        shutdown_rpc_gates=True,
        drain_background_tasks=True,
        shutdown_threads=True,
        log_processor_task_exited=True,
    )


def test_processor_exit_projection_skips_cleanup_when_forced() -> None:
    # Rust: forced shutdown skips the graceful processor cleanup block.
    projection = processor_exit_projection(shutdown_forced=True)

    assert projection == ProcessorExitProjection(
        shutdown_rpc_gates=False,
        drain_background_tasks=False,
        shutdown_threads=False,
        log_processor_task_exited=True,
    )


def test_processor_loop_update_projection_finishes_with_disconnect_all() -> None:
    # Rust: ShutdownAction::Finish cancels transport shutdown, sends DisconnectAll, and breaks.
    projection = processor_loop_update_projection(ShutdownAction.FINISH)

    assert projection == ProcessorLoopUpdateProjection(
        action=ShutdownAction.FINISH,
        cancel_transport_shutdown_token=True,
        outbound_event=OutboundControlEvent.disconnect_all(),
        should_break=True,
    )


def test_processor_loop_update_projection_noop_continues_loop() -> None:
    # Rust: ShutdownAction::Noop falls through into the select loop.
    projection = processor_loop_update_projection(ShutdownAction.NOOP)

    assert projection == ProcessorLoopUpdateProjection(
        action=ShutdownAction.NOOP,
        cancel_transport_shutdown_token=False,
    )


def test_processor_shutdown_signal_projection_disabled_when_not_graceful() -> None:
    # Rust: shutdown_signal select arm is gated by graceful_signal_restart_enabled.
    projection = processor_shutdown_signal_projection(
        graceful_signal_restart_enabled=False,
        shutdown_forced=False,
        signal_result_ok=True,
        signal=ShutdownSignal.FORCEABLE,
        connection_count=2,
        running_turn_count=1,
    )

    assert projection == ProcessorShutdownSignalProjection(listen_for_shutdown_signal=False)


def test_processor_shutdown_signal_projection_disabled_when_forced() -> None:
    # Rust: shutdown_signal select arm is disabled once shutdown_state.forced().
    projection = processor_shutdown_signal_projection(
        graceful_signal_restart_enabled=True,
        shutdown_forced=True,
        signal_result_ok=True,
        signal=ShutdownSignal.FORCEABLE,
    )

    assert projection == ProcessorShutdownSignalProjection(listen_for_shutdown_signal=False)


def test_processor_shutdown_signal_projection_error_continues_loop() -> None:
    # Rust: shutdown_signal() errors warn and continue the processor loop.
    projection = processor_shutdown_signal_projection(
        graceful_signal_restart_enabled=True,
        shutdown_forced=False,
        signal_result_ok=False,
    )

    assert projection == ProcessorShutdownSignalProjection(
        listen_for_shutdown_signal=True,
        continue_loop=True,
    )


def test_processor_shutdown_signal_projection_calls_on_signal_with_counts() -> None:
    # Rust: successful shutdown_signal() calls shutdown_state.on_signal with live counts.
    projection = processor_shutdown_signal_projection(
        graceful_signal_restart_enabled=True,
        shutdown_forced=False,
        signal_result_ok=True,
        signal=ShutdownSignal.GRACEFUL_ONLY,
        connection_count=3,
        running_turn_count=2,
    )

    assert projection == ProcessorShutdownSignalProjection(
        listen_for_shutdown_signal=True,
        call_shutdown_state_on_signal=True,
        signal=ShutdownSignal.GRACEFUL_ONLY,
        connection_count=3,
        running_turn_count=2,
    )


def test_processor_running_turn_watcher_projection_disabled_until_shutdown_requested() -> None:
    # Rust: running-turn changed arm is gated by graceful restart and shutdown_state.requested().
    projection = processor_running_turn_watcher_projection(
        graceful_signal_restart_enabled=True,
        shutdown_requested=False,
        changed_ok=True,
    )

    assert projection == ProcessorRunningTurnWatcherProjection(
        listen_for_running_turn_changes=False,
    )


def test_processor_running_turn_watcher_projection_continues_on_change() -> None:
    # Rust: successful running-turn changed events have no side effect beyond waking the loop.
    projection = processor_running_turn_watcher_projection(
        graceful_signal_restart_enabled=True,
        shutdown_requested=True,
        changed_ok=True,
    )

    assert projection == ProcessorRunningTurnWatcherProjection(
        listen_for_running_turn_changes=True,
        warn_closed_watcher=False,
        continue_loop=True,
    )


def test_processor_running_turn_watcher_projection_warns_when_closed() -> None:
    # Rust: closed running-turn watcher warns and keeps the loop alive.
    projection = processor_running_turn_watcher_projection(
        graceful_signal_restart_enabled=True,
        shutdown_requested=True,
        changed_ok=False,
    )

    assert projection == ProcessorRunningTurnWatcherProjection(
        listen_for_running_turn_changes=True,
        warn_closed_watcher=True,
        continue_loop=True,
    )


def test_runtime_finalization_projection_orders_shutdown_with_otel() -> None:
    # Rust: finalization drops transport tx, awaits workers, cancels transport, awaits handles, then shuts down otel.
    projection = runtime_finalization_projection(
        transport_accept_handle_count=3,
        has_otel=True,
    )

    assert projection == RuntimeFinalizationProjection(
        drop_transport_event_sender=True,
        await_processor_handle=True,
        await_outbound_handle=True,
        cancel_transport_shutdown_token=True,
        await_transport_accept_handle_count=3,
        shutdown_otel=True,
    )


def test_runtime_finalization_projection_skips_absent_otel() -> None:
    # Rust: otel shutdown is conditional on Some(otel); other finalization remains unconditional.
    projection = runtime_finalization_projection(
        transport_accept_handle_count=0,
        has_otel=False,
    )

    assert projection == RuntimeFinalizationProjection(
        drop_transport_event_sender=True,
        await_processor_handle=True,
        await_outbound_handle=True,
        cancel_transport_shutdown_token=True,
        await_transport_accept_handle_count=0,
        shutdown_otel=False,
    )


def test_runtime_finalization_projection_ignores_join_results() -> None:
    # Rust: processor, outbound, and accept-handle awaits use `let _ = ...await`.
    projection = runtime_finalization_projection(
        transport_accept_handle_count=2,
        has_otel=False,
    )

    assert projection.ignore_processor_join_result is True
    assert projection.ignore_outbound_join_result is True
    assert projection.ignore_transport_accept_join_results is True


def test_runtime_finalization_projection_rejects_negative_handle_count() -> None:
    # Python guard: Rust's handle list length cannot be negative.
    with pytest.raises(ValueError, match="transport_accept_handle_count"):
        runtime_finalization_projection(transport_accept_handle_count=-1, has_otel=False)


def test_shutdown_state_waits_for_running_turns_after_first_signal() -> None:
    # Rust: ShutdownState::on_signal + update enters drain on the first signal.
    state = ShutdownState()

    assert state.requested() is False
    assert state.forced() is False
    state.on_signal(ShutdownSignal.FORCEABLE, connection_count=2, running_turn_count=3)

    assert state.requested() is True
    assert state.forced() is False
    assert state.update(running_turn_count=3, connection_count=2) is ShutdownAction.NOOP
    assert state.last_logged_running_turn_count == 3


def test_shutdown_state_finishes_when_no_turns_are_running() -> None:
    # Rust: ShutdownState::update returns Finish once running_turn_count is 0.
    state = ShutdownState()
    state.on_signal(ShutdownSignal.GRACEFUL_ONLY, connection_count=1, running_turn_count=1)

    assert state.update(running_turn_count=0, connection_count=1) is ShutdownAction.FINISH
    assert state.forced() is False


def test_shutdown_state_forceable_second_signal_forces_finish() -> None:
    # Rust: a second forceable signal marks forced and update returns Finish.
    state = ShutdownState()
    state.on_signal(ShutdownSignal.GRACEFUL_ONLY, connection_count=1, running_turn_count=2)
    state.on_signal(ShutdownSignal.FORCEABLE, connection_count=1, running_turn_count=2)

    assert state.forced() is True
    assert state.update(running_turn_count=2, connection_count=1) is ShutdownAction.FINISH


def test_shutdown_state_repeated_graceful_signal_does_not_force() -> None:
    # Rust: repeated GracefulOnly signals do not set forced.
    state = ShutdownState()
    state.on_signal(ShutdownSignal.GRACEFUL_ONLY, connection_count=1, running_turn_count=2)
    state.on_signal(ShutdownSignal.GRACEFUL_ONLY, connection_count=1, running_turn_count=2)

    assert state.requested() is True
    assert state.forced() is False
    assert state.update(running_turn_count=2, connection_count=1) is ShutdownAction.NOOP


def test_shutdown_state_repeated_signals_do_not_reset_wait_log_count() -> None:
    # Rust: once shutdown is requested, later signals return before clearing last_logged_running_turn_count.
    state = ShutdownState()
    state.on_signal(ShutdownSignal.GRACEFUL_ONLY, connection_count=1, running_turn_count=2)
    assert state.update(running_turn_count=2, connection_count=1) is ShutdownAction.NOOP
    assert state.last_logged_running_turn_count == 2

    state.on_signal(ShutdownSignal.GRACEFUL_ONLY, connection_count=1, running_turn_count=4)
    assert state.last_logged_running_turn_count == 2

    state.on_signal(ShutdownSignal.FORCEABLE, connection_count=1, running_turn_count=4)
    assert state.forced() is True
    assert state.last_logged_running_turn_count == 2


@pytest.mark.asyncio
async def test_shutdown_signal_maps_ctrl_c_to_forceable() -> None:
    # Rust: shutdown_signal maps tokio::signal::ctrl_c to ShutdownSignal::Forceable.
    signal = await shutdown_signal(
        ShutdownSignalWaiters(ctrl_c=_ready_future(), is_unix=False)
    )

    assert signal is ShutdownSignal.FORCEABLE


@pytest.mark.asyncio
async def test_shutdown_signal_maps_unix_terminate_to_forceable() -> None:
    # Rust: Unix shutdown_signal maps SIGTERM to ShutdownSignal::Forceable.
    signal = await shutdown_signal(
        ShutdownSignalWaiters(
            ctrl_c=asyncio.Future(),
            terminate=_ready_future(),
            hangup=asyncio.Future(),
            is_unix=True,
        )
    )

    assert signal is ShutdownSignal.FORCEABLE


@pytest.mark.asyncio
async def test_shutdown_signal_maps_unix_hangup_to_graceful_only() -> None:
    # Rust: Unix shutdown_signal maps SIGHUP to ShutdownSignal::GracefulOnly.
    signal = await shutdown_signal(
        ShutdownSignalWaiters(
            ctrl_c=asyncio.Future(),
            terminate=asyncio.Future(),
            hangup=_ready_future(),
            is_unix=True,
        )
    )

    assert signal is ShutdownSignal.GRACEFUL_ONLY


@pytest.mark.asyncio
async def test_shutdown_signal_non_unix_ignores_hangup_waiter() -> None:
    # Rust: non-Unix shutdown_signal only waits for ctrl_c.
    signal = await shutdown_signal(
        ShutdownSignalWaiters(
            ctrl_c=_ready_future(),
            hangup=_ready_future(),
            is_unix=False,
        )
    )

    assert signal is ShutdownSignal.FORCEABLE


@pytest.mark.asyncio
async def test_run_main_executes_default_runtime_orchestration() -> None:
    # Rust: run_main delegates to Stdio/VSCode/default-auth runtime startup.
    result = await run_main(
        arg0_paths=object(),
        cli_config_overrides={},
        loader_overrides={},
        strict_config=False,
        default_analytics_enabled=False,
    )

    assert isinstance(result, AppServerRuntimeResult)
    assert result.transport == "stdio"
    assert result.session_source == "vscode"
    assert result.channel_startup == runtime_channel_startup_projection()
    assert result.config_provider_startup.continue_startup is True
    assert result.main_config_load.use_loaded_config is True
    assert result.remote_control_runtime.error_message is None
    assert result.message_processor_args.rpc_transport is AppServerRpcTransport.STDIO
    assert result.runtime_finalization.ignore_processor_join_result is True


@pytest.mark.asyncio
async def test_run_main_with_transport_options_runs_hooks_in_rust_order() -> None:
    # Rust: run_main_with_transport_options wires startup resources before processor spawn.
    calls: list[str] = []

    def record(name: str, result: object | None = None) -> object:
        calls.append(name)
        return SimpleNamespace() if result is None else result

    config = SimpleNamespace(
        codex_home="home",
        sqlite_home="home/state",
        chatgpt_base_url="https://example.test",
        package_version="9.9.9",
        config_layer_stack=(),
        startup_warnings=(),
        permissions=SimpleNamespace(permission_profile=lambda: None),
        experimental_thread_config_endpoint=None,
        installation_id="install-123",
    )
    hooks = AppServerRuntimeHooks(
        parse_cli_overrides=lambda _: record("parse_cli_overrides", {}),
        find_codex_home=lambda: record("find_codex_home", "home"),
        build_local_runtime_paths=lambda _: record("build_local_runtime_paths"),
        create_environment_manager=lambda *_: record("create_environment_manager"),
        create_config_manager=lambda *_: record("create_config_manager"),
        preload_config=lambda _: record("preload_config", config),
        load_config=lambda _: record("load_config", config),
        build_telemetry=lambda *_: record("build_telemetry"),
        init_state_db=lambda _: record("init_state_db"),
        maybe_migrate_personality=lambda *_: record("maybe_migrate_personality"),
        check_execpolicy=lambda _: record("check_execpolicy", None),
        build_feedback=lambda: record("build_feedback"),
        start_log_db=lambda _: record("start_log_db"),
        install_logging=lambda *_: record("install_logging", None),
        resolve_installation_id=lambda _: record("resolve_installation_id", "install-123"),
        start_transport=lambda *_: record("start_transport", None),
        create_auth_manager=lambda _: record("create_auth_manager"),
        start_remote_control=lambda *_: record("start_remote_control"),
        run_outbound_router=lambda _: record("run_outbound_router", None),
        run_processor=lambda _: record("run_processor", None),
        finalize_transport=lambda _: record("finalize_transport", None),
        shutdown_otel=lambda _: record("shutdown_otel", None),
    )

    result = await run_main_with_transport_options(
        arg0_paths=object(),
        cli_config_overrides={},
        loader_overrides={},
        strict_config=False,
        default_analytics_enabled=True,
        transport="websocket",
        session_source="web",
        auth="default",
        hooks=hooks,
    )

    assert result.transport == "websocket"
    assert result.telemetry_startup.package_version == "9.9.9"
    assert result.message_processor_args.rpc_transport is AppServerRpcTransport.WEBSOCKET
    assert calls == [
        "parse_cli_overrides",
        "find_codex_home",
        "build_local_runtime_paths",
        "create_environment_manager",
        "create_config_manager",
        "preload_config",
        "load_config",
        "build_telemetry",
        "init_state_db",
        "maybe_migrate_personality",
        "check_execpolicy",
        "build_feedback",
        "start_log_db",
        "install_logging",
        "resolve_installation_id",
        "start_transport",
        "create_auth_manager",
        "start_remote_control",
        "run_outbound_router",
        "run_processor",
        "finalize_transport",
        "shutdown_otel",
    ]


@pytest.mark.asyncio
async def test_run_main_with_transport_options_errors_without_transport_or_remote_control() -> None:
    # Rust: startup errors when no transport handle exists and remote control is disabled.
    with pytest.raises(OSError, match="no transport configured"):
        await run_main_with_transport_options(
            arg0_paths=object(),
            cli_config_overrides={},
            loader_overrides={},
            strict_config=False,
            default_analytics_enabled=False,
            transport="off",
            session_source="vscode",
            auth="default",
            runtime_options=AppServerRuntimeOptions(remote_control_enabled=False),
        )
