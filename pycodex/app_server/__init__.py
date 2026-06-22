"""Python alignment surface for Rust ``codex-app-server/src/lib.rs``.

This package owns app-server runtime entrypoints.  The real Rust runtime is
large and async; keep unported runtime paths explicit so client packages do not
duplicate app-server behavior locally.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace
from typing import Any

from pycodex.analytics import AppServerRpcTransport
from pycodex.app_server_protocol import ConfigWarningNotification, TextPosition, TextRange
from pycodex.config import NoopThreadConfigLoader, RemoteThreadConfigLoader


APP_SERVER_CHANNEL_CAPACITY = 128
RUST_PRIVATE_MODULES = (
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
RUST_PUBLIC_MODULES = ("in_process",)
RUST_PUBLIC_REEXPORTS = (
    "INPUT_TOO_LARGE_ERROR_CODE",
    "INVALID_PARAMS_ERROR_CODE",
    "AppServerTransport",
    "app_server_control_socket_path",
    "AppServerWebsocketAuthArgs",
    "AppServerWebsocketAuthSettings",
    "WebsocketAuthCliMode",
)


class AppServerNotImplementedError(NotImplementedError):
    """Raised for Rust app-server runtime behavior not ported to Python yet."""


class LogFormat(Enum):
    """Rust ``LogFormat`` values from ``src/lib.rs``."""

    DEFAULT = "default"
    JSON = "json"

    @classmethod
    def from_env_value(cls, value: str | None) -> "LogFormat":
        """Mirror Rust ``LogFormat::from_env_value`` trimming/case behavior."""

        if value is not None and value.strip().lower() == "json":
            return cls.JSON
        return cls.DEFAULT


def log_format_from_env(environ: dict[str, str] | None = None) -> LogFormat:
    """Mirror Rust ``log_format_from_env`` for the ``LOG_FORMAT`` key."""

    source = os.environ if environ is None else environ
    return LogFormat.from_env_value(source.get("LOG_FORMAT"))


def crate_root_module_inventory_projection() -> "CrateRootModuleInventoryProjection":
    """Project Rust ``src/lib.rs`` module declarations and re-exports."""

    return CrateRootModuleInventoryProjection(
        private_modules=RUST_PRIVATE_MODULES,
        public_modules=RUST_PUBLIC_MODULES,
        public_reexports=RUST_PUBLIC_REEXPORTS,
        python_private_module_count=len(RUST_PRIVATE_MODULES),
        python_public_module_count=len(RUST_PUBLIC_MODULES),
        python_reexport_count=len(RUST_PUBLIC_REEXPORTS),
    )


class PluginStartupTasks(Enum):
    """Rust ``PluginStartupTasks`` values from ``src/lib.rs``."""

    START = "start"
    SKIP = "skip"


class ShutdownAction(Enum):
    """Rust ``ShutdownAction`` values from ``src/lib.rs``."""

    NOOP = "noop"
    FINISH = "finish"


class ShutdownSignal(Enum):
    """Rust ``ShutdownSignal`` values from ``src/lib.rs``."""

    FORCEABLE = "forceable"
    GRACEFUL_ONLY = "graceful_only"


@dataclass(frozen=True)
class OutboundControlEvent:
    """Rust ``OutboundControlEvent`` shape for outbound router coordination."""

    kind: str
    connection_id: Any = None
    writer: Any = None
    disconnect_sender: Any = None
    initialized: Any = None
    experimental_api_enabled: Any = None
    opted_out_notification_methods: Any = None

    @classmethod
    def opened(
        cls,
        *,
        connection_id: Any,
        writer: Any,
        disconnect_sender: Any = None,
        initialized: Any,
        experimental_api_enabled: Any,
        opted_out_notification_methods: Any,
    ) -> "OutboundControlEvent":
        return cls(
            kind="opened",
            connection_id=connection_id,
            writer=writer,
            disconnect_sender=disconnect_sender,
            initialized=initialized,
            experimental_api_enabled=experimental_api_enabled,
            opted_out_notification_methods=opted_out_notification_methods,
        )

    @classmethod
    def closed(cls, connection_id: Any) -> "OutboundControlEvent":
        return cls(kind="closed", connection_id=connection_id)

    @classmethod
    def disconnect_all(cls) -> "OutboundControlEvent":
        return cls(kind="disconnect_all")


@dataclass(frozen=True)
class AppServerRuntimeOptions:
    """Rust ``AppServerRuntimeOptions`` default boundary."""

    plugin_startup_tasks: PluginStartupTasks = PluginStartupTasks.START
    remote_control_enabled: bool = False
    install_shutdown_signal_handler: bool = True


@dataclass(frozen=True)
class CrateRootModuleInventoryProjection:
    """Rust crate-root module declarations and public re-export surface."""

    private_modules: tuple[str, ...]
    public_modules: tuple[str, ...]
    public_reexports: tuple[str, ...]
    python_private_module_count: int
    python_public_module_count: int
    python_reexport_count: int


@dataclass(frozen=True)
class RunMainWithTransportOptionsCall:
    """Rust ``run_main`` default argument projection."""

    arg0_paths: Any
    cli_config_overrides: Any
    loader_overrides: Any
    strict_config: bool
    default_analytics_enabled: bool
    transport: str
    session_source: str
    auth: str
    runtime_options: AppServerRuntimeOptions


@dataclass(frozen=True)
class RuntimeTransportDecisions:
    """Rust runtime booleans derived after transport selection."""

    single_client_mode: bool
    shutdown_when_no_connections: bool
    graceful_signal_restart_enabled: bool


@dataclass(frozen=True)
class RemoteControlRuntimeDecision:
    """Rust remote-control enablement and no-transport validation result."""

    requested: bool
    enabled: bool
    log_disabled_missing_state_db: bool = False
    error_message: str | None = None


@dataclass(frozen=True)
class TransportStartupProjection:
    """Rust app-server transport startup match projection."""

    create_stdio_client_name_channel: bool
    app_server_client_name_rx_available: bool
    start_stdio_connection: bool
    start_control_socket_acceptor: bool
    start_websocket_acceptor: bool
    push_accept_handle_count: int
    requires_websocket_auth_policy: bool
    drop_unix_socket_startup_lock: bool


@dataclass(frozen=True)
class TransportAcceptorStartupProjection:
    """Rust transport match fallible startup order projection."""

    create_stdio_client_name_channel: bool
    set_app_server_client_name_rx: bool
    build_websocket_auth_policy: bool
    start_acceptor: str | None
    push_accept_handle: bool
    drop_unix_socket_startup_lock: bool
    return_error: bool = False
    error_stage: str | None = None


@dataclass(frozen=True)
class RemoteControlStartupProjection:
    """Rust remote-control startup call projection."""

    start_remote_control: bool
    remote_control_url: str
    installation_id: str
    pass_state_db: bool
    pass_auth_manager: bool
    pass_transport_event_sender: bool
    pass_transport_shutdown_token: bool
    pass_app_server_client_name_rx: bool
    remote_control_enabled: bool
    push_accept_handle_count: int
    keep_remote_control_handle: bool
    return_error: bool = False
    error_stage: str | None = None


@dataclass(frozen=True)
class OutboundRouterControlProjection:
    """Rust outbound router control-event projection."""

    action: str
    connection_id: Any = None
    insert_connection: bool = False
    remove_connection: bool = False
    request_disconnect_count: int = 0
    clear_connections: bool = False
    should_break: bool = False
    log_outbound_router_task_exited: bool = False


@dataclass(frozen=True)
class OutboundRouterOutgoingProjection:
    """Rust outbound router outgoing-envelope projection."""

    route_outgoing_envelope: bool
    should_break: bool = False
    log_outbound_router_task_exited: bool = False


@dataclass(frozen=True)
class OutboundRouterStartupProjection:
    """Rust outbound router worker startup/select-loop shape."""

    spawn_worker: bool
    initialize_outbound_connections_empty: bool
    select_is_biased: bool
    control_arm_priority: int
    outgoing_arm_priority: int
    control_arm_receives_outbound_control: bool
    outgoing_arm_receives_envelopes: bool
    log_task_exited_after_loop: bool


@dataclass(frozen=True)
class OutgoingMessageRuntimeProjection:
    """Rust outgoing message sender and analytics client setup."""

    clone_auth_manager_for_analytics: bool
    build_analytics_events_client_from_config: bool
    pass_config_to_analytics_client: bool
    create_outgoing_message_sender: bool
    pass_outgoing_tx: bool
    clone_analytics_client_for_sender: bool
    wrap_sender_in_arc: bool
    clone_initialize_notification_sender: bool


@dataclass(frozen=True)
class MessageProcessorArgsProjection:
    """Rust ``MessageProcessorArgs`` assembly projection."""

    pass_outgoing: bool
    pass_analytics_events_client: bool
    pass_arg0_paths: bool
    wrap_config_in_arc: bool
    pass_config_manager: bool
    pass_environment_manager: bool
    clone_feedback: bool
    has_log_db: bool
    has_state_db: bool
    config_warning_count: int
    session_source: Any
    pass_auth_manager: bool
    installation_id: str
    rpc_transport: AppServerRpcTransport
    remote_control_handle_some: bool
    plugin_startup_tasks: PluginStartupTasks


@dataclass(frozen=True)
class ConfigPreloadProjection:
    """Rust config preload branch before the main app-server config load."""

    replace_thread_config_loader: bool
    load_auth_manager_with_codex_api_key_env: bool | None
    replace_cloud_requirements_loader: bool
    warn_failed_preload_cloud_requirements: bool
    continue_startup: bool = True


@dataclass(frozen=True)
class ConfigProviderStartupProjection:
    """Rust config provider setup before the preload/main config loads."""

    parse_cli_overrides: bool
    find_codex_home: bool
    build_local_runtime_paths: bool
    use_env_environment_manager: bool
    use_codex_home_environment_manager: bool
    create_config_manager: bool
    config_manager_uses_noop_thread_loader: bool
    pass_loader_overrides: bool
    pass_strict_config: bool
    pass_arg0_paths: bool
    continue_startup: bool = True
    return_parse_overrides_invalid_input: bool = False
    return_local_runtime_paths_error: bool = False
    return_environment_manager_error: bool = False


@dataclass(frozen=True)
class RuntimeAuthManagerProjection:
    """Rust runtime auth manager creation branch."""

    create_auth_manager: bool
    enable_codex_api_key_env: bool
    after_transport_startup: bool
    after_unix_socket_startup_lock_drop: bool


@dataclass(frozen=True)
class MainConfigLoadProjection:
    """Rust main config-load branch before telemetry/runtime setup."""

    use_loaded_config: bool
    append_invalid_config_warning: bool
    load_default_config: bool
    should_run_personality_migration: bool
    return_original_error: bool = False
    return_default_config_error: bool = False
    default_config_error_prefix: str | None = None


@dataclass(frozen=True)
class SystemBwrapWarningProjection:
    """Rust system bwrap warning call-site projection."""

    call_system_bwrap_warning: bool
    permission_profile: Any
    append_config_warning: bool
    notification: ConfigWarningNotification | None


@dataclass(frozen=True)
class PersonalityMigrationProjection:
    """Rust personality migration control-flow branch."""

    attempt_deserialize_effective_config: bool
    call_maybe_migrate_personality: bool
    pass_state_db_clone: bool
    reload_latest_config: bool
    replace_config_with_reloaded: bool
    warn_deserialize_failed: bool = False
    warn_migration_failed: bool = False
    return_reload_error: bool = False
    reload_error_prefix: str | None = None


@dataclass(frozen=True)
class StateDbStartupProjection:
    """Rust rollout state DB startup branch."""

    try_init_state_db: bool
    state_db_available: bool
    return_error: bool = False
    error_prefix: str | None = None


@dataclass(frozen=True)
class TelemetryStartupProjection:
    """Rust OpenTelemetry provider startup branch."""

    build_provider: bool
    package_version: str
    service_name: str
    default_analytics_enabled: bool
    record_process_start: bool
    install_sqlite_telemetry: bool
    return_error: bool = False
    error_prefix: str | None = None


@dataclass(frozen=True)
class UnixSocketStartupLockProjection:
    """Rust Unix socket startup-lock preparation branch."""

    compute_startup_lock_path: bool
    acquire_startup_lock: bool
    prepare_control_socket_path: bool
    store_startup_lock: bool
    socket_path: Any = None
    return_error: bool = False
    error_stage: str | None = None


@dataclass(frozen=True)
class RuntimeResourceStartupProjection:
    """Rust feedback/log-DB runtime resource assembly branch."""

    create_feedback: bool
    clone_state_db_for_log_db: bool
    start_log_db: bool
    log_db_available: bool
    pass_feedback_to_logging: bool
    pass_feedback_to_message_processor: bool
    pass_log_db_to_logging: bool
    pass_log_db_to_message_processor: bool


@dataclass(frozen=True)
class LoggingSubscriberProjection:
    """Rust tracing subscriber layer assembly branch."""

    stderr_json: bool
    stderr_span_events_full: bool
    stderr_uses_env_filter: bool
    include_feedback_logger_layer: bool
    include_feedback_metadata_layer: bool
    start_log_db: bool
    include_log_db_layer: bool
    include_otel_logger_layer: bool
    include_otel_tracing_layer: bool
    ignore_try_init_result: bool
    emitted_config_warning_count: int
    emitted_warning_detail_count: int


@dataclass(frozen=True)
class RuntimeStartupHandlesProjection:
    """Rust runtime handle initialization before transport startup."""

    resolve_installation_id: bool
    installation_id: str | None
    create_transport_shutdown_token: bool
    init_transport_accept_handles_empty: bool
    init_app_server_client_name_rx_none: bool
    return_error: bool = False
    error_stage: str | None = None


@dataclass(frozen=True)
class RuntimeChannelStartupProjection:
    """Rust app-server runtime mpsc channel setup."""

    transport_event_capacity: int
    outgoing_capacity: int
    outbound_control_capacity: int
    transport_event_payload: str
    outgoing_payload: str
    outbound_control_payload: str
    creates_transport_event_receiver: bool
    creates_outgoing_receiver: bool
    creates_outbound_control_receiver: bool


@dataclass(frozen=True)
class ProcessorStartupProjection:
    """Rust processor worker startup/local state initialization shape."""

    create_processor_arc: bool
    subscribe_thread_created: bool
    subscribe_running_turn_count: bool
    initialize_connections_empty: bool
    subscribe_remote_control_status: bool
    clone_initial_remote_control_status: bool
    clone_transport_shutdown_token: bool
    spawn_worker: bool
    initialize_listen_for_threads_true: bool
    initialize_shutdown_state_default: bool


@dataclass(frozen=True)
class ProcessorWorkerSpawnProjection:
    """Rust processor worker spawn and capture boundary."""

    spawn_processor_worker: bool
    clone_auth_manager_before_analytics: bool
    move_outbound_control_tx_into_worker: bool
    create_processor_before_async_move: bool
    async_move_captures_processor_state: bool
    processor_handle_awaited_during_finalization: bool


@dataclass(frozen=True)
class ProcessorSelectTopologyProjection:
    """Rust processor loop select-arm topology and local gating."""

    arms: tuple[str, ...]
    shutdown_signal_gate: str
    running_turn_gate: str
    thread_created_gate: str
    transport_event_ungated: bool
    remote_control_status_ungated: bool


@dataclass(frozen=True)
class ConnectionOpenedProjection:
    """Rust connection-opened projection for processor/outbound state."""

    outbound_event: OutboundControlEvent
    connection_id: Any
    origin: Any
    initialized: bool
    experimental_api_enabled: bool
    opted_out_notification_methods: frozenset[str]
    insert_connection: bool = True
    should_break: bool = False


@dataclass(frozen=True)
class ConnectionClosedProjection:
    """Rust connection-closed projection for outbound/processor loop state."""

    outbound_event: OutboundControlEvent | None
    notify_processor: bool
    should_break: bool


@dataclass(frozen=True)
class TransportEventChannelClosedProjection:
    """Rust transport-event receiver closed projection."""

    should_break: bool


@dataclass(frozen=True)
class IncomingRequestProjection:
    """Rust incoming request post-processing projection."""

    process_request: bool
    warn_unknown_connection: bool = False
    update_outbound_opted_out_notification_methods: frozenset[str] | None = None
    warn_failed_update_outbound_opted_out_notifications: bool = False
    update_outbound_experimental_api_enabled: bool | None = None
    send_initialize_notifications: bool = False
    send_remote_control_status: bool = False
    notify_connection_initialized: bool = False
    connection_initialized_request_attestation: Any = None
    mark_outbound_initialized: bool = False


@dataclass(frozen=True)
class IncomingNonRequestProjection:
    """Rust non-request JSON-RPC message routing projection."""

    process_message: bool
    processor_method: str | None = None
    warn_unknown_connection: bool = False
    message_kind: str | None = None


@dataclass(frozen=True)
class RemoteControlStatusProjection:
    """Rust remote-control status changed projection."""

    next_status: Any
    send_status_notification: bool
    continue_loop: bool = True


@dataclass(frozen=True)
class ThreadCreatedProjection:
    """Rust thread-created watcher projection."""

    attach_thread_listener: bool
    listen_for_threads: bool
    thread_id: Any = None
    initialized_connection_ids: tuple[Any, ...] = ()
    warn_lagged_receiver: bool = False
    continue_loop: bool = True


@dataclass(frozen=True)
class ProcessorExitProjection:
    """Rust processor task exit cleanup projection."""

    shutdown_rpc_gates: bool
    drain_background_tasks: bool
    shutdown_threads: bool
    log_processor_task_exited: bool = True


@dataclass(frozen=True)
class RuntimeFinalizationProjection:
    """Rust app-server runtime finalization projection."""

    drop_transport_event_sender: bool
    await_processor_handle: bool
    await_outbound_handle: bool
    cancel_transport_shutdown_token: bool
    await_transport_accept_handle_count: int
    shutdown_otel: bool
    ignore_processor_join_result: bool = True
    ignore_outbound_join_result: bool = True
    ignore_transport_accept_join_results: bool = True


@dataclass(frozen=True)
class AppServerRuntimeResult:
    """Executable Python projection of Rust ``run_main_with_transport_options``."""

    transport: str
    session_source: Any
    runtime_options: AppServerRuntimeOptions
    channel_startup: RuntimeChannelStartupProjection
    config_provider_startup: ConfigProviderStartupProjection
    config_preload: ConfigPreloadProjection
    main_config_load: MainConfigLoadProjection
    telemetry_startup: TelemetryStartupProjection
    state_db_startup: StateDbStartupProjection
    runtime_resources: RuntimeResourceStartupProjection
    logging_subscriber: LoggingSubscriberProjection
    startup_handles: RuntimeStartupHandlesProjection
    transport_startup: TransportStartupProjection
    remote_control_runtime: RemoteControlRuntimeDecision
    remote_control_startup: RemoteControlStartupProjection
    outbound_router_startup: OutboundRouterStartupProjection
    outgoing_message_runtime: OutgoingMessageRuntimeProjection
    message_processor_args: MessageProcessorArgsProjection
    processor_startup: ProcessorStartupProjection
    processor_worker_spawn: ProcessorWorkerSpawnProjection
    runtime_finalization: RuntimeFinalizationProjection
    config_warning_count: int
    transport_accept_handle_count: int
    remote_control_enabled: bool


@dataclass
class AppServerRuntimeHooks:
    """Injectable effects for the crate-root async runtime orchestration."""

    parse_cli_overrides: Any = None
    find_codex_home: Any = None
    build_local_runtime_paths: Any = None
    create_environment_manager: Any = None
    create_config_manager: Any = None
    preload_config: Any = None
    load_config: Any = None
    load_default_config: Any = None
    build_telemetry: Any = None
    prepare_unix_socket: Any = None
    init_state_db: Any = None
    maybe_migrate_personality: Any = None
    check_execpolicy: Any = None
    build_feedback: Any = None
    start_log_db: Any = None
    install_logging: Any = None
    resolve_installation_id: Any = None
    start_transport: Any = None
    create_auth_manager: Any = None
    start_remote_control: Any = None
    run_outbound_router: Any = None
    run_processor: Any = None
    finalize_transport: Any = None
    shutdown_otel: Any = None


@dataclass(frozen=True)
class ProcessorLoopUpdateProjection:
    """Rust processor loop shutdown-update projection."""

    action: ShutdownAction
    cancel_transport_shutdown_token: bool
    outbound_event: OutboundControlEvent | None = None
    should_break: bool = False


@dataclass(frozen=True)
class ProcessorShutdownSignalProjection:
    """Rust processor-loop shutdown-signal select arm projection."""

    listen_for_shutdown_signal: bool
    call_shutdown_state_on_signal: bool = False
    continue_loop: bool = False
    signal: ShutdownSignal | None = None
    connection_count: int | None = None
    running_turn_count: int | None = None


@dataclass(frozen=True)
class ProcessorRunningTurnWatcherProjection:
    """Rust processor-loop running-turn watcher select arm projection."""

    listen_for_running_turn_changes: bool
    warn_closed_watcher: bool = False
    continue_loop: bool = False


@dataclass(frozen=True)
class ShutdownSignalWaiters:
    """Injectable waiters for Rust ``shutdown_signal`` selection semantics."""

    ctrl_c: Any
    terminate: Any = None
    hangup: Any = None
    is_unix: bool = os.name != "nt"


@dataclass
class ShutdownState:
    """Mirror Rust's graceful-restart shutdown state machine."""

    _requested: bool = False
    _forced: bool = False
    _last_logged_running_turn_count: int | None = None

    def requested(self) -> bool:
        return self._requested

    def forced(self) -> bool:
        return self._forced

    def on_signal(
        self,
        signal: ShutdownSignal,
        connection_count: int,
        running_turn_count: int,
    ) -> None:
        _ = connection_count, running_turn_count
        if self._requested:
            if signal is ShutdownSignal.FORCEABLE:
                self._forced = True
            return

        self._requested = True
        self._last_logged_running_turn_count = None

    def update(self, running_turn_count: int, connection_count: int) -> ShutdownAction:
        _ = connection_count
        if not self._requested:
            return ShutdownAction.NOOP

        if self._forced or running_turn_count == 0:
            return ShutdownAction.FINISH

        if self._last_logged_running_turn_count != running_turn_count:
            self._last_logged_running_turn_count = running_turn_count

        return ShutdownAction.NOOP

    @property
    def last_logged_running_turn_count(self) -> int | None:
        return self._last_logged_running_turn_count


def app_text_range(value: Any) -> TextRange:
    """Mirror Rust ``app_text_range`` field projection."""

    start = _text_position(getattr(value, "start", None))
    end = _text_position(getattr(value, "end", None))
    return TextRange(start=start, end=end)


def config_warning_from_error(summary: str, err: BaseException) -> ConfigWarningNotification:
    """Mirror Rust ``config_warning_from_error`` shape."""

    location = config_error_location(err)
    path: str | None
    range_: TextRange | None
    if location is None:
        path = None
        range_ = None
    else:
        path, range_ = location
    return ConfigWarningNotification(
        summary=summary,
        details=str(err),
        path=path,
        range=range_,
    )


def config_error_location(err: BaseException) -> tuple[str, TextRange] | None:
    """Extract Rust-like ``ConfigLoadError`` path/range details when present."""

    config_error = _config_error_from_exception(err)
    if config_error is None:
        return None
    return (str(getattr(config_error, "path")), app_text_range(getattr(config_error, "range")))


def exec_policy_warning_location(err: BaseException) -> tuple[str | None, TextRange | None]:
    """Mirror Rust ``exec_policy_warning_location`` for parse-policy errors."""

    location = _call_optional(err, "location")
    if location is not None:
        return (str(getattr(location, "path")), app_text_range(getattr(location, "range")))

    kind = getattr(err, "kind", None)
    path = getattr(err, "path", None)
    if kind == "parse_policy" and path is not None:
        return (str(path), None)

    return (None, None)


def analytics_rpc_transport(transport: Any) -> AppServerRpcTransport:
    """Mirror Rust ``analytics_rpc_transport`` transport bucketing."""

    name = _transport_name(transport)
    if name == "stdio":
        return AppServerRpcTransport.STDIO
    return AppServerRpcTransport.WEBSOCKET


def project_config_warning(config: Any) -> ConfigWarningNotification | None:
    """Mirror Rust ``project_config_warning`` summary construction."""

    disabled_folders: list[tuple[str, str]] = []
    for layer in _config_layers(config):
        name = _attr_or_key(layer, "name")
        if _source_kind(name) != "project":
            continue
        disabled_reason = _attr_or_key(layer, "disabled_reason")
        if disabled_reason is None:
            continue
        dot_codex_folder = _attr_or_key(name, "dot_codex_folder")
        if dot_codex_folder is None:
            continue
        disabled_folders.append((str(dot_codex_folder), str(disabled_reason)))

    if not disabled_folders:
        return None

    message = (
        "Project-local config, hooks, and exec policies are disabled in the "
        "following folders until the project is trusted, but skills still "
        "load.\n"
    )
    for index, (folder, reason) in enumerate(disabled_folders, start=1):
        message += f"    {index}. {folder}\n"
        message += f"       {reason}\n"

    return ConfigWarningNotification(summary=message, details=None, path=None, range=None)


def system_bwrap_warning_projection(
    config: Any,
    *,
    warning_result: str | None,
) -> SystemBwrapWarningProjection:
    """Mirror Rust app-server's ``system_bwrap_warning`` call site."""

    permission_profile = _permission_profile(config)
    notification = None
    if warning_result is not None:
        notification = ConfigWarningNotification(
            summary=warning_result,
            details=None,
            path=None,
            range=None,
        )
    return SystemBwrapWarningProjection(
        call_system_bwrap_warning=True,
        permission_profile=permission_profile,
        append_config_warning=notification is not None,
        notification=notification,
    )


def collect_config_warnings(
    config: Any,
    *,
    initial_warnings: list[ConfigWarningNotification] | None = None,
    exec_policy_error: BaseException | None = None,
    system_bwrap_warning: str | None = None,
) -> list[ConfigWarningNotification]:
    """Mirror Rust app-server config warning accumulation order."""

    warnings = list(initial_warnings or [])
    if exec_policy_error is not None:
        path, range_ = exec_policy_warning_location(exec_policy_error)
        warnings.append(
            ConfigWarningNotification(
                summary="Error parsing rules; custom rules not applied.",
                details=str(exec_policy_error),
                path=path,
                range=range_,
            )
        )

    project_warning = project_config_warning(config)
    if project_warning is not None:
        warnings.append(project_warning)

    for warning in _startup_warnings(config):
        warnings.append(
            ConfigWarningNotification(summary=warning, details=None, path=None, range=None)
        )

    if system_bwrap_warning is not None:
        warnings.append(
            ConfigWarningNotification(
                summary=system_bwrap_warning,
                details=None,
                path=None,
                range=None,
            )
        )

    return warnings


def connection_opened_projection(
    *,
    connection_id: Any,
    origin: Any,
    writer: Any,
    disconnect_sender: Any = None,
    outbound_control_send_ok: bool = True,
) -> ConnectionOpenedProjection:
    """Mirror Rust ``TransportEvent::ConnectionOpened`` local state creation."""

    initialized = False
    experimental_api_enabled = False
    opted_out_notification_methods: frozenset[str] = frozenset()
    outbound_event = OutboundControlEvent.opened(
        connection_id=connection_id,
        writer=writer,
        disconnect_sender=disconnect_sender,
        initialized=initialized,
        experimental_api_enabled=experimental_api_enabled,
        opted_out_notification_methods=opted_out_notification_methods,
    )
    return ConnectionOpenedProjection(
        outbound_event=outbound_event,
        connection_id=connection_id,
        origin=origin,
        initialized=initialized,
        experimental_api_enabled=experimental_api_enabled,
        opted_out_notification_methods=opted_out_notification_methods,
        insert_connection=outbound_control_send_ok,
        should_break=not outbound_control_send_ok,
    )


def connection_closed_projection(
    *,
    connection_id: Any,
    known_connection: bool,
    remaining_connection_count: int,
    shutdown_when_no_connections: bool,
    outbound_control_send_ok: bool = True,
) -> ConnectionClosedProjection:
    """Mirror Rust ``TransportEvent::ConnectionClosed`` local control flow."""

    if not known_connection:
        return ConnectionClosedProjection(
            outbound_event=None,
            notify_processor=False,
            should_break=False,
        )

    outbound_event = OutboundControlEvent.closed(connection_id)
    if not outbound_control_send_ok:
        return ConnectionClosedProjection(
            outbound_event=outbound_event,
            notify_processor=False,
            should_break=True,
        )

    return ConnectionClosedProjection(
        outbound_event=outbound_event,
        notify_processor=True,
        should_break=shutdown_when_no_connections and remaining_connection_count == 0,
    )


def transport_event_channel_closed_projection() -> TransportEventChannelClosedProjection:
    """Mirror Rust ``transport_event_rx.recv()`` closed-channel loop exit."""

    return TransportEventChannelClosedProjection(should_break=True)


def incoming_request_projection(
    *,
    known_connection: bool,
    was_initialized: bool,
    is_initialized: bool,
    experimental_api_enabled: bool,
    opted_out_notification_methods: Any,
    opted_out_update_ok: bool = True,
    request_attestation: Any = None,
) -> IncomingRequestProjection:
    """Mirror Rust post-request connection/outbound state synchronization."""

    if not known_connection:
        return IncomingRequestProjection(
            process_request=False,
            warn_unknown_connection=True,
        )

    initialized_now = not was_initialized and is_initialized
    return IncomingRequestProjection(
        process_request=True,
        update_outbound_opted_out_notification_methods=(
            frozenset(str(item) for item in opted_out_notification_methods)
            if opted_out_update_ok
            else None
        ),
        warn_failed_update_outbound_opted_out_notifications=not opted_out_update_ok,
        update_outbound_experimental_api_enabled=bool(experimental_api_enabled),
        send_initialize_notifications=initialized_now,
        send_remote_control_status=initialized_now,
        notify_connection_initialized=initialized_now,
        connection_initialized_request_attestation=(
            request_attestation if initialized_now else None
        ),
        mark_outbound_initialized=initialized_now,
    )


def incoming_non_request_projection(
    *,
    known_connection: bool,
    message_kind: str,
) -> IncomingNonRequestProjection:
    """Mirror Rust response/notification/error connection gate routing."""

    normalized = message_kind.strip().lower()
    method_by_kind = {
        "response": "process_response",
        "notification": "process_notification",
        "error": "process_error",
    }
    try:
        processor_method = method_by_kind[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported JSON-RPC message kind: {message_kind}") from exc
    if not known_connection:
        return IncomingNonRequestProjection(
            process_message=False,
            warn_unknown_connection=True,
            message_kind=normalized,
        )
    return IncomingNonRequestProjection(
        process_message=True,
        processor_method=processor_method,
        message_kind=normalized,
    )


def remote_control_status_projection(
    *,
    current_status: Any,
    changed_ok: bool,
    observed_status: Any = None,
) -> RemoteControlStatusProjection:
    """Mirror Rust remote-control status watcher update semantics."""

    if not changed_ok:
        return RemoteControlStatusProjection(
            next_status=current_status,
            send_status_notification=False,
        )
    if current_status == observed_status:
        return RemoteControlStatusProjection(
            next_status=current_status,
            send_status_notification=False,
        )
    return RemoteControlStatusProjection(
        next_status=observed_status,
        send_status_notification=True,
    )


def thread_created_projection(
    *,
    recv_result: str,
    thread_id: Any = None,
    connections: Any = (),
) -> ThreadCreatedProjection:
    """Mirror Rust thread-created listener attach branch."""

    normalized = recv_result.strip().lower()
    if normalized == "lagged":
        return ThreadCreatedProjection(
            attach_thread_listener=False,
            listen_for_threads=True,
            warn_lagged_receiver=True,
        )
    if normalized == "closed":
        return ThreadCreatedProjection(
            attach_thread_listener=False,
            listen_for_threads=False,
        )
    if normalized != "ok":
        raise ValueError(f"unsupported thread-created recv result: {recv_result}")

    return ThreadCreatedProjection(
        attach_thread_listener=True,
        listen_for_threads=True,
        thread_id=thread_id,
        initialized_connection_ids=_initialized_connection_ids(connections),
    )


def processor_exit_projection(*, shutdown_forced: bool) -> ProcessorExitProjection:
    """Mirror Rust processor-task exit cleanup gate."""

    graceful_cleanup = not shutdown_forced
    return ProcessorExitProjection(
        shutdown_rpc_gates=graceful_cleanup,
        drain_background_tasks=graceful_cleanup,
        shutdown_threads=graceful_cleanup,
    )


def processor_loop_update_projection(action: ShutdownAction) -> ProcessorLoopUpdateProjection:
    """Mirror Rust processor-loop handling of ``ShutdownState::update``."""

    if action is ShutdownAction.FINISH:
        return ProcessorLoopUpdateProjection(
            action=action,
            cancel_transport_shutdown_token=True,
            outbound_event=OutboundControlEvent.disconnect_all(),
            should_break=True,
        )
    if action is ShutdownAction.NOOP:
        return ProcessorLoopUpdateProjection(
            action=action,
            cancel_transport_shutdown_token=False,
        )
    raise ValueError(f"unsupported shutdown action: {action}")


def processor_shutdown_signal_projection(
    *,
    graceful_signal_restart_enabled: bool,
    shutdown_forced: bool,
    signal_result_ok: bool,
    signal: ShutdownSignal | None = None,
    connection_count: int = 0,
    running_turn_count: int = 0,
) -> ProcessorShutdownSignalProjection:
    """Mirror Rust processor-loop shutdown signal select arm."""

    listen = graceful_signal_restart_enabled and not shutdown_forced
    if not listen:
        return ProcessorShutdownSignalProjection(listen_for_shutdown_signal=False)
    if not signal_result_ok:
        return ProcessorShutdownSignalProjection(
            listen_for_shutdown_signal=True,
            continue_loop=True,
        )
    if signal is None:
        raise ValueError("signal is required when signal_result_ok is true")
    return ProcessorShutdownSignalProjection(
        listen_for_shutdown_signal=True,
        call_shutdown_state_on_signal=True,
        signal=signal,
        connection_count=connection_count,
        running_turn_count=running_turn_count,
    )


def processor_running_turn_watcher_projection(
    *,
    graceful_signal_restart_enabled: bool,
    shutdown_requested: bool,
    changed_ok: bool,
) -> ProcessorRunningTurnWatcherProjection:
    """Mirror Rust running-turn watcher select arm."""

    listen = graceful_signal_restart_enabled and shutdown_requested
    if not listen:
        return ProcessorRunningTurnWatcherProjection(
            listen_for_running_turn_changes=False,
        )
    return ProcessorRunningTurnWatcherProjection(
        listen_for_running_turn_changes=True,
        warn_closed_watcher=not changed_ok,
        continue_loop=True,
    )


def runtime_finalization_projection(
    *,
    transport_accept_handle_count: int,
    has_otel: bool,
) -> RuntimeFinalizationProjection:
    """Mirror Rust run-main finalization sequence decisions."""

    if transport_accept_handle_count < 0:
        raise ValueError("transport_accept_handle_count must be non-negative")
    return RuntimeFinalizationProjection(
        drop_transport_event_sender=True,
        await_processor_handle=True,
        await_outbound_handle=True,
        cancel_transport_shutdown_token=True,
        await_transport_accept_handle_count=transport_accept_handle_count,
        shutdown_otel=bool(has_otel),
    )


def transport_startup_projection(transport: Any) -> TransportStartupProjection:
    """Mirror Rust ``match &transport`` startup branch decisions."""

    name = _transport_name(transport)
    if name == "stdio":
        return TransportStartupProjection(
            create_stdio_client_name_channel=True,
            app_server_client_name_rx_available=True,
            start_stdio_connection=True,
            start_control_socket_acceptor=False,
            start_websocket_acceptor=False,
            push_accept_handle_count=0,
            requires_websocket_auth_policy=False,
            drop_unix_socket_startup_lock=True,
        )
    if name in {"unix_socket", "unixsocket", "unix-socket"}:
        return TransportStartupProjection(
            create_stdio_client_name_channel=False,
            app_server_client_name_rx_available=False,
            start_stdio_connection=False,
            start_control_socket_acceptor=True,
            start_websocket_acceptor=False,
            push_accept_handle_count=1,
            requires_websocket_auth_policy=False,
            drop_unix_socket_startup_lock=True,
        )
    if name in {"websocket", "web_socket", "web-socket"}:
        return TransportStartupProjection(
            create_stdio_client_name_channel=False,
            app_server_client_name_rx_available=False,
            start_stdio_connection=False,
            start_control_socket_acceptor=False,
            start_websocket_acceptor=True,
            push_accept_handle_count=1,
            requires_websocket_auth_policy=True,
            drop_unix_socket_startup_lock=True,
        )
    if name == "off":
        return TransportStartupProjection(
            create_stdio_client_name_channel=False,
            app_server_client_name_rx_available=False,
            start_stdio_connection=False,
            start_control_socket_acceptor=False,
            start_websocket_acceptor=False,
            push_accept_handle_count=0,
            requires_websocket_auth_policy=False,
            drop_unix_socket_startup_lock=True,
        )
    raise ValueError(f"unsupported app-server transport: {transport}")


def transport_acceptor_startup_projection(
    transport: Any,
    *,
    policy_ok: bool = True,
    acceptor_ok: bool = True,
) -> TransportAcceptorStartupProjection:
    """Mirror Rust transport match fallible startup ordering."""

    name = _transport_name(transport)
    if name == "stdio":
        if not acceptor_ok:
            return TransportAcceptorStartupProjection(
                create_stdio_client_name_channel=True,
                set_app_server_client_name_rx=True,
                build_websocket_auth_policy=False,
                start_acceptor="stdio",
                push_accept_handle=False,
                drop_unix_socket_startup_lock=False,
                return_error=True,
                error_stage="start_stdio_connection",
            )
        return TransportAcceptorStartupProjection(
            create_stdio_client_name_channel=True,
            set_app_server_client_name_rx=True,
            build_websocket_auth_policy=False,
            start_acceptor="stdio",
            push_accept_handle=False,
            drop_unix_socket_startup_lock=True,
        )
    if name in {"unix_socket", "unixsocket", "unix-socket"}:
        if not acceptor_ok:
            return TransportAcceptorStartupProjection(
                create_stdio_client_name_channel=False,
                set_app_server_client_name_rx=False,
                build_websocket_auth_policy=False,
                start_acceptor="unix_socket",
                push_accept_handle=False,
                drop_unix_socket_startup_lock=False,
                return_error=True,
                error_stage="start_control_socket_acceptor",
            )
        return TransportAcceptorStartupProjection(
            create_stdio_client_name_channel=False,
            set_app_server_client_name_rx=False,
            build_websocket_auth_policy=False,
            start_acceptor="unix_socket",
            push_accept_handle=True,
            drop_unix_socket_startup_lock=True,
        )
    if name in {"websocket", "web_socket", "web-socket"}:
        if not policy_ok:
            return TransportAcceptorStartupProjection(
                create_stdio_client_name_channel=False,
                set_app_server_client_name_rx=False,
                build_websocket_auth_policy=True,
                start_acceptor=None,
                push_accept_handle=False,
                drop_unix_socket_startup_lock=False,
                return_error=True,
                error_stage="policy_from_settings",
            )
        if not acceptor_ok:
            return TransportAcceptorStartupProjection(
                create_stdio_client_name_channel=False,
                set_app_server_client_name_rx=False,
                build_websocket_auth_policy=True,
                start_acceptor="websocket",
                push_accept_handle=False,
                drop_unix_socket_startup_lock=False,
                return_error=True,
                error_stage="start_websocket_acceptor",
            )
        return TransportAcceptorStartupProjection(
            create_stdio_client_name_channel=False,
            set_app_server_client_name_rx=False,
            build_websocket_auth_policy=True,
            start_acceptor="websocket",
            push_accept_handle=True,
            drop_unix_socket_startup_lock=True,
        )
    if name == "off":
        return TransportAcceptorStartupProjection(
            create_stdio_client_name_channel=False,
            set_app_server_client_name_rx=False,
            build_websocket_auth_policy=False,
            start_acceptor=None,
            push_accept_handle=False,
            drop_unix_socket_startup_lock=True,
        )
    raise ValueError(f"unsupported app-server transport: {transport}")


def unix_socket_startup_lock_projection(
    transport: Any,
    *,
    socket_path: Any = None,
    lock_path_ok: bool = True,
    acquire_lock_ok: bool = True,
    prepare_socket_ok: bool = True,
) -> UnixSocketStartupLockProjection:
    """Mirror Rust's Unix-socket-only startup lock preparation branch."""

    name = _transport_name(transport)
    if name not in {"unix_socket", "unixsocket", "unix-socket"}:
        return UnixSocketStartupLockProjection(
            compute_startup_lock_path=False,
            acquire_startup_lock=False,
            prepare_control_socket_path=False,
            store_startup_lock=False,
        )
    if not lock_path_ok:
        return UnixSocketStartupLockProjection(
            compute_startup_lock_path=True,
            acquire_startup_lock=False,
            prepare_control_socket_path=False,
            store_startup_lock=False,
            socket_path=socket_path,
            return_error=True,
            error_stage="startup_lock_path",
        )
    if not acquire_lock_ok:
        return UnixSocketStartupLockProjection(
            compute_startup_lock_path=True,
            acquire_startup_lock=True,
            prepare_control_socket_path=False,
            store_startup_lock=False,
            socket_path=socket_path,
            return_error=True,
            error_stage="acquire_startup_lock",
        )
    if not prepare_socket_ok:
        return UnixSocketStartupLockProjection(
            compute_startup_lock_path=True,
            acquire_startup_lock=True,
            prepare_control_socket_path=True,
            store_startup_lock=False,
            socket_path=socket_path,
            return_error=True,
            error_stage="prepare_control_socket_path",
        )
    return UnixSocketStartupLockProjection(
        compute_startup_lock_path=True,
        acquire_startup_lock=True,
        prepare_control_socket_path=True,
        store_startup_lock=True,
        socket_path=socket_path,
    )


def remote_control_startup_projection(
    *,
    config: Any,
    installation_id: Any,
    state_db_available: bool,
    auth_manager_available: bool = True,
    app_server_client_name_rx_available: bool = False,
    remote_control_enabled: bool,
    startup_ok: bool = True,
) -> RemoteControlStartupProjection:
    """Mirror Rust ``start_remote_control`` argument projection."""

    if not startup_ok:
        return RemoteControlStartupProjection(
            start_remote_control=True,
            remote_control_url=str(_attr_or_key(config, "chatgpt_base_url")),
            installation_id=str(installation_id),
            pass_state_db=bool(state_db_available),
            pass_auth_manager=bool(auth_manager_available),
            pass_transport_event_sender=True,
            pass_transport_shutdown_token=True,
            pass_app_server_client_name_rx=bool(app_server_client_name_rx_available),
            remote_control_enabled=bool(remote_control_enabled),
            push_accept_handle_count=0,
            keep_remote_control_handle=False,
            return_error=True,
            error_stage="start_remote_control",
        )
    return RemoteControlStartupProjection(
        start_remote_control=True,
        remote_control_url=str(_attr_or_key(config, "chatgpt_base_url")),
        installation_id=str(installation_id),
        pass_state_db=bool(state_db_available),
        pass_auth_manager=bool(auth_manager_available),
        pass_transport_event_sender=True,
        pass_transport_shutdown_token=True,
        pass_app_server_client_name_rx=bool(app_server_client_name_rx_available),
        remote_control_enabled=bool(remote_control_enabled),
        push_accept_handle_count=1,
        keep_remote_control_handle=True,
    )


def outbound_router_control_projection(
    event: OutboundControlEvent | None,
    *,
    outbound_connection_count: int,
) -> OutboundRouterControlProjection:
    """Mirror Rust outbound router control-event branch decisions."""

    if outbound_connection_count < 0:
        raise ValueError("outbound_connection_count must be non-negative")
    if event is None:
        return OutboundRouterControlProjection(
            action="break",
            should_break=True,
            log_outbound_router_task_exited=True,
        )
    if event.kind == "opened":
        return OutboundRouterControlProjection(
            action="opened",
            connection_id=event.connection_id,
            insert_connection=True,
        )
    if event.kind == "closed":
        return OutboundRouterControlProjection(
            action="closed",
            connection_id=event.connection_id,
            remove_connection=True,
        )
    if event.kind == "disconnect_all":
        return OutboundRouterControlProjection(
            action="disconnect_all",
            request_disconnect_count=outbound_connection_count,
            clear_connections=True,
        )
    raise ValueError(f"unsupported outbound control event: {event.kind}")


def outbound_router_outgoing_projection(envelope: Any | None) -> OutboundRouterOutgoingProjection:
    """Mirror Rust outbound router outgoing-envelope branch decisions."""

    if envelope is None:
        return OutboundRouterOutgoingProjection(
            route_outgoing_envelope=False,
            should_break=True,
            log_outbound_router_task_exited=True,
        )
    return OutboundRouterOutgoingProjection(route_outgoing_envelope=True)


def outbound_router_startup_projection() -> OutboundRouterStartupProjection:
    """Mirror Rust outbound router worker initialization and biased select."""

    return OutboundRouterStartupProjection(
        spawn_worker=True,
        initialize_outbound_connections_empty=True,
        select_is_biased=True,
        control_arm_priority=0,
        outgoing_arm_priority=1,
        control_arm_receives_outbound_control=True,
        outgoing_arm_receives_envelopes=True,
        log_task_exited_after_loop=True,
    )


def outgoing_message_runtime_projection() -> OutgoingMessageRuntimeProjection:
    """Mirror Rust analytics client and outgoing sender setup."""

    return OutgoingMessageRuntimeProjection(
        clone_auth_manager_for_analytics=True,
        build_analytics_events_client_from_config=True,
        pass_config_to_analytics_client=True,
        create_outgoing_message_sender=True,
        pass_outgoing_tx=True,
        clone_analytics_client_for_sender=True,
        wrap_sender_in_arc=True,
        clone_initialize_notification_sender=True,
    )


def message_processor_args_projection(
    *,
    transport: Any,
    runtime_options: AppServerRuntimeOptions | None = None,
    config_warnings: Any = (),
    session_source: Any,
    installation_id: Any,
    log_db_available: bool,
    state_db_available: bool,
    remote_control_handle_available: bool = True,
) -> MessageProcessorArgsProjection:
    """Mirror Rust ``MessageProcessorArgs`` assembly in ``src/lib.rs``."""

    options = runtime_options or AppServerRuntimeOptions()
    return MessageProcessorArgsProjection(
        pass_outgoing=True,
        pass_analytics_events_client=True,
        pass_arg0_paths=True,
        wrap_config_in_arc=True,
        pass_config_manager=True,
        pass_environment_manager=True,
        clone_feedback=True,
        has_log_db=bool(log_db_available),
        has_state_db=bool(state_db_available),
        config_warning_count=len(tuple(config_warnings)),
        session_source=session_source,
        pass_auth_manager=True,
        installation_id=str(installation_id),
        rpc_transport=analytics_rpc_transport(transport),
        remote_control_handle_some=bool(remote_control_handle_available),
        plugin_startup_tasks=options.plugin_startup_tasks,
    )


def processor_startup_projection() -> ProcessorStartupProjection:
    """Mirror Rust processor worker local state setup before its loop."""

    return ProcessorStartupProjection(
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


def processor_worker_spawn_projection() -> ProcessorWorkerSpawnProjection:
    """Mirror Rust processor worker spawn/capture boundary."""

    return ProcessorWorkerSpawnProjection(
        spawn_processor_worker=True,
        clone_auth_manager_before_analytics=True,
        move_outbound_control_tx_into_worker=True,
        create_processor_before_async_move=True,
        async_move_captures_processor_state=True,
        processor_handle_awaited_during_finalization=True,
    )


def processor_select_topology_projection() -> ProcessorSelectTopologyProjection:
    """Mirror Rust processor loop ``tokio::select!`` arm order and gates."""

    return ProcessorSelectTopologyProjection(
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


def configured_thread_config_loader(config: Any) -> Any:
    """Mirror Rust ``configured_thread_config_loader`` endpoint selection."""

    endpoint = _attr_or_key(config, "experimental_thread_config_endpoint")
    if endpoint is not None:
        return RemoteThreadConfigLoader.new(str(endpoint))
    return NoopThreadConfigLoader()


def config_preload_projection(*, load_ok: bool) -> ConfigPreloadProjection:
    """Mirror Rust's best-effort cloud requirements config preload branch."""

    if load_ok:
        return ConfigPreloadProjection(
            replace_thread_config_loader=True,
            load_auth_manager_with_codex_api_key_env=False,
            replace_cloud_requirements_loader=True,
            warn_failed_preload_cloud_requirements=False,
        )
    return ConfigPreloadProjection(
        replace_thread_config_loader=False,
        load_auth_manager_with_codex_api_key_env=None,
        replace_cloud_requirements_loader=False,
        warn_failed_preload_cloud_requirements=True,
    )


def config_provider_startup_projection(
    *,
    ignore_user_config: bool,
    parse_overrides_ok: bool = True,
    local_runtime_paths_ok: bool = True,
    environment_manager_ok: bool = True,
) -> ConfigProviderStartupProjection:
    """Mirror Rust config/environment manager assembly before config loads."""

    if not parse_overrides_ok:
        return ConfigProviderStartupProjection(
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
    if not local_runtime_paths_ok:
        return ConfigProviderStartupProjection(
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
    if not environment_manager_ok:
        return ConfigProviderStartupProjection(
            parse_cli_overrides=True,
            find_codex_home=True,
            build_local_runtime_paths=True,
            use_env_environment_manager=ignore_user_config,
            use_codex_home_environment_manager=not ignore_user_config,
            create_config_manager=False,
            config_manager_uses_noop_thread_loader=False,
            pass_loader_overrides=False,
            pass_strict_config=False,
            pass_arg0_paths=False,
            continue_startup=False,
            return_environment_manager_error=True,
        )
    return ConfigProviderStartupProjection(
        parse_cli_overrides=True,
        find_codex_home=True,
        build_local_runtime_paths=True,
        use_env_environment_manager=ignore_user_config,
        use_codex_home_environment_manager=not ignore_user_config,
        create_config_manager=True,
        config_manager_uses_noop_thread_loader=True,
        pass_loader_overrides=True,
        pass_strict_config=True,
        pass_arg0_paths=True,
    )


def runtime_auth_manager_projection() -> RuntimeAuthManagerProjection:
    """Mirror Rust runtime ``AuthManager::shared_from_config`` call site."""

    return RuntimeAuthManagerProjection(
        create_auth_manager=True,
        enable_codex_api_key_env=False,
        after_transport_startup=True,
        after_unix_socket_startup_lock_drop=True,
    )


def main_config_load_projection(
    *,
    load_ok: bool,
    strict_config: bool,
    default_load_ok: bool = True,
) -> MainConfigLoadProjection:
    """Mirror Rust's main config load strict/fallback branch."""

    if load_ok:
        return MainConfigLoadProjection(
            use_loaded_config=True,
            append_invalid_config_warning=False,
            load_default_config=False,
            should_run_personality_migration=True,
        )
    if strict_config:
        return MainConfigLoadProjection(
            use_loaded_config=False,
            append_invalid_config_warning=False,
            load_default_config=False,
            should_run_personality_migration=False,
            return_original_error=True,
        )
    if not default_load_ok:
        return MainConfigLoadProjection(
            use_loaded_config=False,
            append_invalid_config_warning=True,
            load_default_config=True,
            should_run_personality_migration=False,
            return_default_config_error=True,
            default_config_error_prefix="error loading default config after config error:",
        )
    return MainConfigLoadProjection(
        use_loaded_config=False,
        append_invalid_config_warning=True,
        load_default_config=True,
        should_run_personality_migration=False,
    )


def personality_migration_projection(
    *,
    should_run: bool,
    deserialize_ok: bool = True,
    migration_status: str = "skipped_marker",
    reload_ok: bool = True,
) -> PersonalityMigrationProjection:
    """Mirror Rust's personality migration branch after state DB startup."""

    if not should_run:
        return PersonalityMigrationProjection(
            attempt_deserialize_effective_config=False,
            call_maybe_migrate_personality=False,
            pass_state_db_clone=False,
            reload_latest_config=False,
            replace_config_with_reloaded=False,
        )
    if not deserialize_ok:
        return PersonalityMigrationProjection(
            attempt_deserialize_effective_config=True,
            call_maybe_migrate_personality=False,
            pass_state_db_clone=False,
            reload_latest_config=False,
            replace_config_with_reloaded=False,
            warn_deserialize_failed=True,
        )
    if migration_status == "error":
        return PersonalityMigrationProjection(
            attempt_deserialize_effective_config=True,
            call_maybe_migrate_personality=True,
            pass_state_db_clone=True,
            reload_latest_config=False,
            replace_config_with_reloaded=False,
            warn_migration_failed=True,
        )
    if migration_status == "applied":
        if not reload_ok:
            return PersonalityMigrationProjection(
                attempt_deserialize_effective_config=True,
                call_maybe_migrate_personality=True,
                pass_state_db_clone=True,
                reload_latest_config=True,
                replace_config_with_reloaded=False,
                return_reload_error=True,
                reload_error_prefix="error reloading config after personality migration:",
            )
        return PersonalityMigrationProjection(
            attempt_deserialize_effective_config=True,
            call_maybe_migrate_personality=True,
            pass_state_db_clone=True,
            reload_latest_config=True,
            replace_config_with_reloaded=True,
        )
    skipped_statuses = {
        "skipped_marker",
        "skipped_explicit_personality",
        "skipped_no_sessions",
    }
    if migration_status in skipped_statuses:
        return PersonalityMigrationProjection(
            attempt_deserialize_effective_config=True,
            call_maybe_migrate_personality=True,
            pass_state_db_clone=True,
            reload_latest_config=False,
            replace_config_with_reloaded=False,
        )
    raise ValueError(f"unsupported personality migration status: {migration_status}")


def state_db_startup_projection(*, init_ok: bool, sqlite_home: Any) -> StateDbStartupProjection:
    """Mirror Rust's rollout state DB startup success/error branch."""

    if init_ok:
        return StateDbStartupProjection(
            try_init_state_db=True,
            state_db_available=True,
        )
    return StateDbStartupProjection(
        try_init_state_db=True,
        state_db_available=False,
        return_error=True,
        error_prefix=f"failed to initialize sqlite state runtime under {sqlite_home}:",
    )


def telemetry_startup_projection(
    *,
    build_ok: bool,
    package_version: str,
    service_name: str = "codex-app-server",
    default_analytics_enabled: bool,
) -> TelemetryStartupProjection:
    """Mirror Rust's OpenTelemetry provider build/install branch."""

    if build_ok:
        return TelemetryStartupProjection(
            build_provider=True,
            package_version=package_version,
            service_name=service_name,
            default_analytics_enabled=bool(default_analytics_enabled),
            record_process_start=True,
            install_sqlite_telemetry=True,
        )
    return TelemetryStartupProjection(
        build_provider=True,
        package_version=package_version,
        service_name=service_name,
        default_analytics_enabled=bool(default_analytics_enabled),
        record_process_start=False,
        install_sqlite_telemetry=False,
        return_error=True,
        error_prefix="error loading otel config:",
    )


def runtime_resource_startup_projection(
    *,
    state_db_available: bool,
) -> RuntimeResourceStartupProjection:
    """Mirror Rust feedback and optional log DB runtime resource setup."""

    return RuntimeResourceStartupProjection(
        create_feedback=True,
        clone_state_db_for_log_db=True,
        start_log_db=bool(state_db_available),
        log_db_available=bool(state_db_available),
        pass_feedback_to_logging=True,
        pass_feedback_to_message_processor=True,
        pass_log_db_to_logging=bool(state_db_available),
        pass_log_db_to_message_processor=bool(state_db_available),
    )


def logging_subscriber_projection(
    *,
    log_format: LogFormat | str,
    state_db_available: bool,
    otel_available: bool,
    config_warnings: Any = (),
) -> LoggingSubscriberProjection:
    """Mirror Rust's tracing subscriber layer assembly branch."""

    fmt = log_format if isinstance(log_format, LogFormat) else LogFormat.from_env_value(str(log_format))
    warnings = tuple(config_warnings)
    detail_count = sum(
        1
        for warning in warnings
        if _attr_or_key(warning, "details") is not None
    )
    return LoggingSubscriberProjection(
        stderr_json=fmt is LogFormat.JSON,
        stderr_span_events_full=True,
        stderr_uses_env_filter=True,
        include_feedback_logger_layer=True,
        include_feedback_metadata_layer=True,
        start_log_db=bool(state_db_available),
        include_log_db_layer=bool(state_db_available),
        include_otel_logger_layer=bool(otel_available),
        include_otel_tracing_layer=bool(otel_available),
        ignore_try_init_result=True,
        emitted_config_warning_count=len(warnings),
        emitted_warning_detail_count=detail_count,
    )


def runtime_channel_startup_projection() -> RuntimeChannelStartupProjection:
    """Mirror Rust app-server runtime channel creation at startup."""

    return RuntimeChannelStartupProjection(
        transport_event_capacity=APP_SERVER_CHANNEL_CAPACITY,
        outgoing_capacity=APP_SERVER_CHANNEL_CAPACITY,
        outbound_control_capacity=APP_SERVER_CHANNEL_CAPACITY,
        transport_event_payload="TransportEvent",
        outgoing_payload="OutgoingEnvelope",
        outbound_control_payload="OutboundControlEvent",
        creates_transport_event_receiver=True,
        creates_outgoing_receiver=True,
        creates_outbound_control_receiver=True,
    )


def runtime_startup_handles_projection(
    *,
    installation_id_ok: bool,
    installation_id: Any = None,
) -> RuntimeStartupHandlesProjection:
    """Mirror Rust runtime handle initialization before transport match."""

    if not installation_id_ok:
        return RuntimeStartupHandlesProjection(
            resolve_installation_id=True,
            installation_id=None,
            create_transport_shutdown_token=False,
            init_transport_accept_handles_empty=False,
            init_app_server_client_name_rx_none=False,
            return_error=True,
            error_stage="resolve_installation_id",
        )
    return RuntimeStartupHandlesProjection(
        resolve_installation_id=True,
        installation_id=str(installation_id),
        create_transport_shutdown_token=True,
        init_transport_accept_handles_empty=True,
        init_app_server_client_name_rx_none=True,
    )


def runtime_transport_decisions(
    transport: Any,
    runtime_options: AppServerRuntimeOptions | None = None,
) -> RuntimeTransportDecisions:
    """Mirror Rust transport-derived runtime booleans."""

    options = runtime_options or AppServerRuntimeOptions()
    single_client_mode = _transport_name(transport) == "stdio"
    return RuntimeTransportDecisions(
        single_client_mode=single_client_mode,
        shutdown_when_no_connections=single_client_mode,
        graceful_signal_restart_enabled=(
            options.install_shutdown_signal_handler and not single_client_mode
        ),
    )


def remote_control_runtime_decision(
    *,
    runtime_options: AppServerRuntimeOptions | None = None,
    state_db_available: bool,
    transport_accept_handle_count: int,
) -> RemoteControlRuntimeDecision:
    """Mirror Rust remote-control enablement/no-transport validation."""

    options = runtime_options or AppServerRuntimeOptions()
    requested = options.remote_control_enabled
    enabled = requested and state_db_available
    log_disabled_missing_state_db = requested and not state_db_available
    if transport_accept_handle_count == 0 and not enabled:
        if requested and not state_db_available:
            error_message = (
                "no transport configured; remote control disabled because sqlite "
                "state db is unavailable"
            )
        else:
            error_message = "no transport configured; use --listen or enable remote control"
        return RemoteControlRuntimeDecision(
            requested=requested,
            enabled=enabled,
            log_disabled_missing_state_db=log_disabled_missing_state_db,
            error_message=error_message,
        )

    return RemoteControlRuntimeDecision(
        requested=requested,
        enabled=enabled,
        log_disabled_missing_state_db=log_disabled_missing_state_db,
    )


async def shutdown_signal(waiters: ShutdownSignalWaiters | None = None) -> ShutdownSignal:
    """Mirror Rust ``shutdown_signal`` mapping with injectable signal waiters."""

    if waiters is None:
        raise AppServerNotImplementedError(
            "codex-app-server/src/lib.rs shutdown_signal OS listener is not ported yet"
        )

    candidates: list[tuple[str, Any]] = [("ctrl_c", waiters.ctrl_c)]
    if waiters.is_unix:
        if waiters.terminate is not None:
            candidates.append(("terminate", waiters.terminate))
        if waiters.hangup is not None:
            candidates.append(("hangup", waiters.hangup))

    ready: list[tuple[str, BaseException | object]] = []
    for kind, awaitable in candidates:
        result = _awaiter_ready(awaitable)
        if result is not None:
            ready.append((kind, result))
    if ready:
        kind, result = ready[0]
        if isinstance(result, BaseException):
            raise result
        return _shutdown_signal_from_kind(kind)

    tasks = {
        asyncio.create_task(_await_signal(awaitable)): kind
        for kind, awaitable in candidates
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        first = next(iter(done))
        kind = tasks[first]
        await first
        return _shutdown_signal_from_kind(kind)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


def run_main_default_transport_options(
    arg0_paths: Any,
    cli_config_overrides: Any,
    loader_overrides: Any,
    strict_config: bool,
    default_analytics_enabled: bool,
) -> RunMainWithTransportOptionsCall:
    """Mirror Rust ``run_main`` defaults before runtime startup."""

    return RunMainWithTransportOptionsCall(
        arg0_paths=arg0_paths,
        cli_config_overrides=cli_config_overrides,
        loader_overrides=loader_overrides,
        strict_config=strict_config,
        default_analytics_enabled=default_analytics_enabled,
        transport="stdio",
        session_source="vscode",
        auth="default",
        runtime_options=AppServerRuntimeOptions(),
    )


async def run_main(
    arg0_paths: Any,
    cli_config_overrides: Any,
    loader_overrides: Any,
    strict_config: bool,
    default_analytics_enabled: bool,
) -> AppServerRuntimeResult:
    """Rust ``run_main`` delegates to default transport-option startup."""

    call = run_main_default_transport_options(
        arg0_paths=arg0_paths,
        cli_config_overrides=cli_config_overrides,
        loader_overrides=loader_overrides,
        strict_config=strict_config,
        default_analytics_enabled=default_analytics_enabled,
    )
    return await run_main_with_transport_options(
        arg0_paths=call.arg0_paths,
        cli_config_overrides=call.cli_config_overrides,
        loader_overrides=call.loader_overrides,
        strict_config=call.strict_config,
        default_analytics_enabled=call.default_analytics_enabled,
        transport=call.transport,
        session_source=call.session_source,
        auth=call.auth,
        runtime_options=call.runtime_options,
    )


async def run_main_with_transport_options(
    arg0_paths: Any,
    cli_config_overrides: Any,
    loader_overrides: Any,
    strict_config: bool,
    default_analytics_enabled: bool,
    transport: Any,
    session_source: Any,
    auth: Any,
    runtime_options: AppServerRuntimeOptions | None = None,
    *,
    hooks: AppServerRuntimeHooks | None = None,
) -> AppServerRuntimeResult:
    """Run the crate-root app-server startup/finalization orchestration.

    The heavy sibling-owned behaviors remain injectable through hooks, but this
    mirrors the Rust ``src/lib.rs`` ordering and error boundaries instead of
    stopping at a NotImplemented marker.
    """

    options = runtime_options or AppServerRuntimeOptions()
    effects = hooks or AppServerRuntimeHooks()
    transport_name = _transport_name(transport)
    channel_startup = runtime_channel_startup_projection()

    cli_kv_overrides = await _maybe_invoke(
        effects.parse_cli_overrides,
        cli_config_overrides,
        default_factory=lambda: _default_parse_cli_overrides(cli_config_overrides),
    )
    codex_home = await _maybe_invoke(
        effects.find_codex_home,
        default_factory=lambda: _attr_or_key(loader_overrides, "codex_home") or ".codex",
    )
    runtime_paths = await _maybe_invoke(
        effects.build_local_runtime_paths,
        arg0_paths,
        default_factory=lambda: SimpleNamespace(arg0_paths=arg0_paths),
    )
    ignore_user_config = bool(_attr_or_key(loader_overrides, "ignore_user_config"))
    environment_manager = await _maybe_invoke(
        effects.create_environment_manager,
        codex_home,
        runtime_paths,
        ignore_user_config,
        default_factory=lambda: SimpleNamespace(
            codex_home=codex_home,
            runtime_paths=runtime_paths,
            ignore_user_config=ignore_user_config,
        ),
    )
    config_provider = config_provider_startup_projection(
        parse_overrides_ok=True,
        local_runtime_paths_ok=True,
        environment_manager_ok=True,
        ignore_user_config=ignore_user_config,
    )
    config_manager = await _maybe_invoke(
        effects.create_config_manager,
        codex_home,
        cli_kv_overrides,
        loader_overrides,
        strict_config,
        arg0_paths,
        default_factory=lambda: SimpleNamespace(
            codex_home=codex_home,
            cli_kv_overrides=cli_kv_overrides,
            loader_overrides=loader_overrides,
            strict_config=strict_config,
            arg0_paths=arg0_paths,
        ),
    )

    preload_ok = True
    try:
        preload_config = await _maybe_invoke(
            effects.preload_config,
            config_manager,
            default_factory=lambda: _default_config(codex_home),
        )
        _ = configured_thread_config_loader(preload_config)
    except Exception:
        preload_ok = False
    config_preload = config_preload_projection(load_ok=preload_ok)

    config_warnings: list[Any] = []
    should_run_personality_migration = True
    try:
        config = await _maybe_invoke(
            effects.load_config,
            config_manager,
            default_factory=lambda: _default_config(codex_home),
        )
        main_config_load = main_config_load_projection(load_ok=True, strict_config=strict_config)
    except Exception as err:
        if strict_config:
            raise
        config_warnings.append(
            config_warning_from_error("Invalid configuration; using defaults.", err)
        )
        config = await _maybe_invoke(
            effects.load_default_config,
            config_manager,
            default_factory=lambda: _default_config(codex_home),
        )
        should_run_personality_migration = False
        main_config_load = main_config_load_projection(
            load_ok=False,
            strict_config=False,
            default_load_ok=True,
        )

    telemetry = await _maybe_invoke(
        effects.build_telemetry,
        config,
        "codex-app-server",
        default_analytics_enabled,
        default_factory=lambda: SimpleNamespace(shutdown=lambda: None),
    )
    telemetry_startup = telemetry_startup_projection(
        build_ok=True,
        package_version=str(_attr_or_key(config, "package_version") or "0.0.0"),
        default_analytics_enabled=default_analytics_enabled,
    )

    if transport_name == "unix_socket":
        await _maybe_invoke(effects.prepare_unix_socket, transport, codex_home, default_factory=lambda: None)

    state_db = await _maybe_invoke(
        effects.init_state_db,
        config,
        default_factory=lambda: SimpleNamespace(sqlite_home=_attr_or_key(config, "sqlite_home")),
    )
    state_db_available = state_db is not None
    state_db_startup = state_db_startup_projection(
        init_ok=state_db_available,
        sqlite_home=_attr_or_key(config, "sqlite_home"),
    )
    if state_db_startup.return_error:
        raise OSError(state_db_startup.error_prefix)

    if should_run_personality_migration:
        await _maybe_invoke(
            effects.maybe_migrate_personality,
            config,
            state_db,
            default_factory=lambda: "skipped_no_sessions",
        )

    exec_policy_warning = await _maybe_invoke(
        effects.check_execpolicy,
        config,
        default_factory=lambda: None,
    )
    if exec_policy_warning is not None:
        path, range_ = exec_policy_warning_location(exec_policy_warning)
        config_warnings.append(
            ConfigWarningNotification(
                summary="Error parsing rules; custom rules not applied.",
                details=str(exec_policy_warning),
                path=path,
                range=range_,
            )
        )
    if (warning := project_config_warning(config)) is not None:
        config_warnings.append(warning)
    for warning_text in _startup_warnings(config):
        config_warnings.append(
            ConfigWarningNotification(summary=warning_text, details=None, path=None, range=None)
        )

    await _maybe_invoke(effects.build_feedback, default_factory=lambda: SimpleNamespace())
    runtime_resources = runtime_resource_startup_projection(state_db_available=state_db_available)
    if runtime_resources.start_log_db:
        await _maybe_invoke(effects.start_log_db, state_db, default_factory=lambda: SimpleNamespace())
    logging_projection = logging_subscriber_projection(
        log_format=log_format_from_env({}),
        state_db_available=state_db_available,
        otel_available=telemetry is not None,
        config_warnings=config_warnings,
    )
    await _maybe_invoke(effects.install_logging, logging_projection, config_warnings, default_factory=lambda: None)

    installation_id = await _maybe_invoke(
        effects.resolve_installation_id,
        config,
        default_factory=lambda: str(_attr_or_key(config, "installation_id") or "local"),
    )
    startup_handles = runtime_startup_handles_projection(
        installation_id_ok=True,
        installation_id=installation_id,
    )
    transport_projection = transport_startup_projection(transport)
    transport_accept_handle_count = transport_projection.push_accept_handle_count
    await _maybe_invoke(effects.start_transport, transport, transport_projection, default_factory=lambda: None)

    auth_manager = await _maybe_invoke(
        effects.create_auth_manager,
        config,
        default_factory=lambda: SimpleNamespace(config=config),
    )
    remote_decision = remote_control_runtime_decision(
        runtime_options=options,
        state_db_available=state_db_available,
        transport_accept_handle_count=(
            transport_accept_handle_count
            + (1 if transport_projection.start_stdio_connection else 0)
        ),
    )
    if remote_decision.error_message is not None:
        raise OSError(remote_decision.error_message)
    remote_startup = remote_control_startup_projection(
        config=config,
        remote_control_enabled=remote_decision.enabled,
        installation_id=str(installation_id),
        state_db_available=state_db_available,
        auth_manager_available=True,
        app_server_client_name_rx_available=transport_name == "stdio",
        startup_ok=True,
    )
    await _maybe_invoke(
        effects.start_remote_control,
        remote_startup,
        state_db,
        auth_manager,
        default_factory=lambda: SimpleNamespace(),
    )
    transport_accept_handle_count += remote_startup.push_accept_handle_count

    outbound_startup = outbound_router_startup_projection()
    outgoing_runtime = outgoing_message_runtime_projection()
    message_args = message_processor_args_projection(
        transport=transport,
        runtime_options=options,
        config_warnings=config_warnings,
        session_source=session_source,
        installation_id=str(installation_id),
        log_db_available=runtime_resources.log_db_available,
        state_db_available=state_db_available,
        remote_control_handle_available=True,
    )
    processor_startup = processor_startup_projection()
    processor_spawn = processor_worker_spawn_projection()
    await _maybe_invoke(effects.run_outbound_router, outbound_startup, default_factory=lambda: None)
    await _maybe_invoke(effects.run_processor, processor_startup, default_factory=lambda: None)

    finalization = runtime_finalization_projection(
        transport_accept_handle_count=transport_accept_handle_count,
        has_otel=telemetry is not None,
    )
    await _maybe_invoke(effects.finalize_transport, finalization, default_factory=lambda: None)
    if finalization.shutdown_otel:
        await _maybe_invoke(effects.shutdown_otel, telemetry, default_factory=lambda: _shutdown_otel(telemetry))

    return AppServerRuntimeResult(
        transport=transport_name,
        session_source=session_source,
        runtime_options=options,
        channel_startup=channel_startup,
        config_provider_startup=config_provider,
        config_preload=config_preload,
        main_config_load=main_config_load,
        telemetry_startup=telemetry_startup,
        state_db_startup=state_db_startup,
        runtime_resources=runtime_resources,
        logging_subscriber=logging_projection,
        startup_handles=startup_handles,
        transport_startup=transport_projection,
        remote_control_runtime=remote_decision,
        remote_control_startup=remote_startup,
        outbound_router_startup=outbound_startup,
        outgoing_message_runtime=outgoing_runtime,
        message_processor_args=message_args,
        processor_startup=processor_startup,
        processor_worker_spawn=processor_spawn,
        runtime_finalization=finalization,
        config_warning_count=len(config_warnings),
        transport_accept_handle_count=transport_accept_handle_count,
        remote_control_enabled=remote_decision.enabled,
    )


__all__ = [
    "analytics_rpc_transport",
    "app_text_range",
    "AppServerNotImplementedError",
    "AppServerRuntimeHooks",
    "AppServerRuntimeOptions",
    "AppServerRuntimeResult",
    "collect_config_warnings",
    "ConnectionClosedProjection",
    "connection_closed_projection",
    "ConnectionOpenedProjection",
    "connection_opened_projection",
    "config_error_location",
    "ConfigPreloadProjection",
    "config_preload_projection",
    "ConfigProviderStartupProjection",
    "config_provider_startup_projection",
    "config_warning_from_error",
    "configured_thread_config_loader",
    "crate_root_module_inventory_projection",
    "CrateRootModuleInventoryProjection",
    "exec_policy_warning_location",
    "IncomingNonRequestProjection",
    "incoming_non_request_projection",
    "IncomingRequestProjection",
    "incoming_request_projection",
    "LogFormat",
    "LoggingSubscriberProjection",
    "logging_subscriber_projection",
    "MainConfigLoadProjection",
    "main_config_load_projection",
    "MessageProcessorArgsProjection",
    "message_processor_args_projection",
    "OutboundControlEvent",
    "OutboundRouterControlProjection",
    "outbound_router_control_projection",
    "OutboundRouterOutgoingProjection",
    "outbound_router_outgoing_projection",
    "OutboundRouterStartupProjection",
    "outbound_router_startup_projection",
    "OutgoingMessageRuntimeProjection",
    "outgoing_message_runtime_projection",
    "PersonalityMigrationProjection",
    "personality_migration_projection",
    "PluginStartupTasks",
    "ProcessorExitProjection",
    "processor_exit_projection",
    "ProcessorLoopUpdateProjection",
    "processor_loop_update_projection",
    "ProcessorRunningTurnWatcherProjection",
    "processor_running_turn_watcher_projection",
    "ProcessorSelectTopologyProjection",
    "processor_select_topology_projection",
    "ProcessorShutdownSignalProjection",
    "processor_shutdown_signal_projection",
    "ProcessorStartupProjection",
    "processor_startup_projection",
    "ProcessorWorkerSpawnProjection",
    "processor_worker_spawn_projection",
    "project_config_warning",
    "RemoteControlStatusProjection",
    "remote_control_status_projection",
    "RunMainWithTransportOptionsCall",
    "RemoteControlRuntimeDecision",
    "RemoteControlStartupProjection",
    "remote_control_startup_projection",
    "RuntimeChannelStartupProjection",
    "runtime_channel_startup_projection",
    "RuntimeResourceStartupProjection",
    "runtime_resource_startup_projection",
    "RuntimeStartupHandlesProjection",
    "runtime_startup_handles_projection",
    "RuntimeAuthManagerProjection",
    "runtime_auth_manager_projection",
    "RuntimeTransportDecisions",
    "RuntimeFinalizationProjection",
    "runtime_finalization_projection",
    "ShutdownAction",
    "ShutdownSignal",
    "ShutdownSignalWaiters",
    "ShutdownState",
    "StateDbStartupProjection",
    "state_db_startup_projection",
    "SystemBwrapWarningProjection",
    "system_bwrap_warning_projection",
    "TelemetryStartupProjection",
    "telemetry_startup_projection",
    "log_format_from_env",
    "run_main",
    "run_main_default_transport_options",
    "run_main_with_transport_options",
    "remote_control_runtime_decision",
    "runtime_transport_decisions",
    "shutdown_signal",
    "ThreadCreatedProjection",
    "thread_created_projection",
    "TransportAcceptorStartupProjection",
    "transport_acceptor_startup_projection",
    "TransportStartupProjection",
    "transport_startup_projection",
    "TransportEventChannelClosedProjection",
    "transport_event_channel_closed_projection",
    "UnixSocketStartupLockProjection",
    "unix_socket_startup_lock_projection",
]


def _text_position(value: Any) -> TextPosition:
    if isinstance(value, TextPosition):
        return value
    if isinstance(value, dict):
        return TextPosition(line=value["line"], column=value["column"])
    return TextPosition(line=getattr(value, "line"), column=getattr(value, "column"))


def _config_error_from_exception(err: BaseException) -> Any | None:
    current: BaseException | None = err
    while current is not None:
        config_error = _call_optional(current, "config_error")
        if config_error is not None:
            return config_error
        config_error = getattr(current, "config_error", None)
        if config_error is not None and not callable(config_error):
            return config_error
        current = current.__cause__
    return None


def _call_optional(value: Any, name: str) -> Any | None:
    method = getattr(value, name, None)
    if callable(method):
        return method()
    return None


async def _maybe_invoke(func: Any, *args: Any, default_factory: Any = None) -> Any:
    if func is None:
        value = default_factory() if callable(default_factory) else default_factory
    else:
        value = func(*args)
    if hasattr(value, "__await__"):
        return await value
    return value


def _default_parse_cli_overrides(cli_config_overrides: Any) -> Any:
    parse_overrides = getattr(cli_config_overrides, "parse_overrides", None)
    if callable(parse_overrides):
        return parse_overrides()
    if isinstance(cli_config_overrides, dict):
        return dict(cli_config_overrides)
    if cli_config_overrides is None:
        return {}
    if isinstance(cli_config_overrides, (list, tuple)):
        return tuple(cli_config_overrides)
    return cli_config_overrides


def _default_config(codex_home: Any) -> Any:
    return SimpleNamespace(
        codex_home=codex_home,
        sqlite_home=f"{codex_home}/state",
        chatgpt_base_url="",
        package_version="0.0.0",
        config_layer_stack=(),
        startup_warnings=(),
        permissions=SimpleNamespace(permission_profile=lambda: None),
        experimental_thread_config_endpoint=None,
        installation_id="local",
    )


def _shutdown_otel(otel: Any) -> None:
    shutdown = getattr(otel, "shutdown", None)
    if callable(shutdown):
        shutdown()


async def _await_signal(awaitable: Any) -> None:
    result = awaitable() if callable(awaitable) else awaitable
    if hasattr(result, "__await__"):
        await result


def _awaiter_ready(awaitable: Any) -> BaseException | object | None:
    if callable(awaitable) and not hasattr(awaitable, "__await__"):
        return None
    done = getattr(awaitable, "done", None)
    if not callable(done) or not done():
        return None
    exception = getattr(awaitable, "exception", None)
    if callable(exception):
        err = exception()
        if err is not None:
            return err
    result = getattr(awaitable, "result", None)
    if callable(result):
        return result()
    return object()


def _shutdown_signal_from_kind(kind: str) -> ShutdownSignal:
    if kind == "hangup":
        return ShutdownSignal.GRACEFUL_ONLY
    return ShutdownSignal.FORCEABLE


def _transport_name(transport: Any) -> str:
    if isinstance(transport, str):
        return transport.strip().lower()
    value = getattr(transport, "value", None)
    if isinstance(value, str):
        return value.strip().lower()
    name = getattr(transport, "name", None)
    if isinstance(name, str):
        return name.strip().lower()
    kind = getattr(transport, "kind", None)
    if isinstance(kind, str):
        return kind.strip().lower()
    return transport.__class__.__name__.strip().lower()


def _config_layers(config: Any) -> tuple[Any, ...]:
    stack = _attr_or_key(config, "config_layer_stack")
    if stack is None:
        stack = _attr_or_key(config, "config_layers")
    if stack is None:
        return ()
    get_layers = getattr(stack, "get_layers", None)
    if callable(get_layers):
        for args in (
            ("lowest_precedence_first", True),
            ("LowestPrecedenceFirst", True),
            (),
        ):
            try:
                return tuple(get_layers(*args))
            except TypeError:
                continue
    if isinstance(stack, dict):
        layers = stack.get("layers", ())
        return tuple(layers)
    return tuple(stack)


def _startup_warnings(config: Any) -> tuple[str, ...]:
    startup_warnings = _attr_or_key(config, "startup_warnings")
    if startup_warnings is None:
        return ()
    return tuple(str(warning) for warning in startup_warnings)


def _permission_profile(config: Any) -> Any:
    permissions = _attr_or_key(config, "permissions")
    profile = _attr_or_key(permissions, "permission_profile")
    if callable(profile):
        return profile()
    return profile


def _initialized_connection_ids(connections: Any) -> tuple[Any, ...]:
    if isinstance(connections, dict):
        items = connections.items()
    else:
        items = connections

    initialized_ids: list[Any] = []
    for item in items:
        try:
            connection_id, state = item
        except (TypeError, ValueError):
            connection_id = _attr_or_key(item, "connection_id")
            state = _attr_or_key(item, "state")
            if state is None:
                state = item
        if _connection_initialized(state):
            initialized_ids.append(connection_id)
    return tuple(initialized_ids)


def _connection_initialized(state: Any) -> bool:
    if isinstance(state, bool):
        return state
    direct = _call_optional(state, "initialized")
    if direct is not None:
        return bool(direct)
    session = _attr_or_key(state, "session")
    if session is not None:
        session_initialized = _call_optional(session, "initialized")
        if session_initialized is not None:
            return bool(session_initialized)
        value = _attr_or_key(session, "initialized")
        if value is not None:
            return bool(value)
    value = _attr_or_key(state, "initialized")
    if value is not None:
        return bool(value)
    return False


def _source_kind(source: Any) -> str | None:
    kind = _attr_or_key(source, "kind")
    if kind is None:
        kind = _attr_or_key(source, "type")
    if kind is None:
        return None
    value = getattr(kind, "value", kind)
    return str(value).strip().lower()


def _attr_or_key(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        if name in value:
            return value[name]
        camel = _snake_to_camel(name)
        if camel in value:
            return value[camel]
        return None
    return getattr(value, name, None)


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)
