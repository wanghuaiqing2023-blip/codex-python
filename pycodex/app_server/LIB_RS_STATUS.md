# codex-app-server src/lib.rs alignment

Rust module:

`codex/codex-rs/app-server/src/lib.rs`

Python target:

`pycodex/app_server/__init__.py`

Status: `complete`

## Covered

- `LogFormat::from_env_value(...)` is mirrored by
  `LogFormat.from_env_value(...)`, including trimming, ASCII-like lowercase
  exact matching for `json`, and defaulting all other values, including
  JSON-like non-`json` strings.
- `log_format_from_env(...)` reads the `LOG_FORMAT` key and delegates to the
  same parser.
- `crate_root_module_inventory_projection(...)` mirrors the crate-root
  `mod`, `pub mod`, and `pub use` namespace boundary, including the 26 private
  sibling modules, public `in_process` module, and transport/error-code public
  re-export surface declared in Rust `src/lib.rs`.
- `logging_subscriber_projection(...)` mirrors the local tracing subscriber
  layer assembly: stderr JSON/default formatting, full span events, EnvFilter,
  feedback logger/metadata layers, optional log DB and OpenTelemetry layers,
  ignored `try_init` result, and config-warning error emission shape.
- `runtime_startup_handles_projection(...)` mirrors the local pre-transport
  setup after logging: installation ID resolution, shutdown token creation,
  empty accept-handle vector initialization, and initial absent stdio
  client-name receiver.
- `PluginStartupTasks` and `AppServerRuntimeOptions` mirror the crate-root
  enum/default boundary: startup tasks default to `Start`, remote control is
  disabled, and shutdown signal handling is enabled.
- `OutboundControlEvent` mirrors the crate-root outbound router coordination
  message shape for opened, closed, and disconnect-all control events.
- `outbound_router_startup_projection(...)` mirrors the outbound router worker
  setup: `tokio::spawn`, an initially empty outbound connection map, biased
  select ordering with the control branch before the outgoing-envelope branch,
  and the task-exited info log after the loop.
- `outbound_router_control_projection(...)` mirrors the local outbound router
  control-event branch: opened inserts outbound connection state, closed
  removes it, disconnect-all requests disconnect for all current outbound
  connections and clears the map, and a closed control channel breaks the loop
  before the outbound-router-exited info log.
- `outbound_router_outgoing_projection(...)` mirrors the local outbound router
  outgoing-envelope branch: present envelopes delegate to
  `route_outgoing_envelope(...)`, while a closed outgoing channel breaks the
  loop before the outbound-router-exited info log. The concrete
  `route_outgoing_envelope(...)` routing contract belongs to the sibling
  Rust `transport` module and is tracked there rather than under `src/lib.rs`.
- `outgoing_message_runtime_projection(...)` mirrors the local processor-worker
  setup for analytics and outgoing messages: clone auth manager for
  `analytics_events_client_from_config(...)`, pass config, build
  `Arc<OutgoingMessageSender>` from `outgoing_tx`, clone the analytics client
  into it, and clone the initialize-notification sender.
- `message_processor_args_projection(...)` mirrors the local
  `MessageProcessorArgs` assembly: outgoing and analytics handles, dispatch
  paths, config/session/auth/environment/feedback handles, optional log/state
  DB handles, config warnings, installation ID, analytics RPC transport bucket,
  remote-control handle, and plugin startup task propagation.
- `processor_startup_projection(...)` mirrors the local processor worker setup:
  `Arc<MessageProcessor>` creation, thread-created and running-turn
  subscriptions, empty connection map, remote-control status receiver and
  initial status clone, transport shutdown token clone, `listen_for_threads =
  true`, and default shutdown state.
- `processor_worker_spawn_projection(...)` mirrors the local processor worker
  spawn/capture boundary: clone auth manager before analytics setup, move
  `outbound_control_tx`, create the `Arc<MessageProcessor>` before `async
  move`, and await the processor handle during runtime finalization.
- `processor_select_topology_projection(...)` mirrors the processor loop
  `tokio::select!` topology: shutdown signal, running-turn watcher, transport
  event, remote-control status watcher, and thread-created watcher arms, plus
  the local gate expressions for the gated arms.
- `connection_opened_projection(...)` mirrors the local
  `TransportEvent::ConnectionOpened` projection into an opened outbound-control
  event plus connection-state initial values, including the break-before-insert
  path when sending the opened event to the outbound router fails.
- `connection_closed_projection(...)` mirrors the local
  `TransportEvent::ConnectionClosed` control flow for unknown connections,
  outbound closed events, outbound send-failure loop exit, processor
  notification, and single-client loop exit.
- `transport_event_channel_closed_projection(...)` mirrors the local
  `transport_event_rx.recv()` closed-channel branch: a closed receiver breaks
  the processor loop.
- `incoming_request_projection(...)` mirrors the local
  `JSONRPCMessage::Request` post-processing projection for unknown-connection
  warning/drop behavior, outbound session flag synchronization, and
  first-initialization side effects, including the warning-only path when
  updating outbound opted-out notification methods fails and the
  `session.request_attestation()` argument passed to `connection_initialized`.
- `incoming_non_request_projection(...)` mirrors the local connection gate and
  processor-method routing for `JSONRPCMessage::Response`,
  `JSONRPCMessage::Notification`, and `JSONRPCMessage::Error`, including
  unknown-connection warning/drop behavior by message kind.
- `remote_control_status_projection(...)` mirrors the local remote-control
  status watcher branch: watcher errors continue without notification,
  unchanged statuses are ignored, changed statuses update local state and
  broadcast a status notification, and every branch continues the processor
  loop.
- `thread_created_projection(...)` mirrors the local thread-created watcher
  branch: successful thread creation attaches listeners only to initialized
  connections, lagged receivers continue without resyncing, and closed
  receivers stop future listening; all handled branches continue the processor
  loop, and lagged receivers expose the warning path.
- `processor_exit_projection(...)` mirrors the local processor task exit
  cleanup gate: non-forced shutdown closes connection RPC gates, drains
  background tasks, and shuts down threads, while forced shutdown skips the
  graceful cleanup block; both paths emit the processor task exited info log.
- `processor_loop_update_projection(...)` mirrors the local top-of-loop
  shutdown update handling: `Finish` cancels the transport shutdown token,
  sends outbound `DisconnectAll`, and breaks the processor loop; `Noop`
  continues into the select block.
- `processor_shutdown_signal_projection(...)` mirrors the local shutdown signal
  select arm: graceful restart must be enabled, forced shutdown disables the
  arm, listener errors continue the loop, and successful signals call
  `ShutdownState::on_signal` with live connection and running-turn counts.
- `processor_running_turn_watcher_projection(...)` mirrors the local
  running-turn watcher select arm: listening is enabled only when graceful
  restart is enabled and shutdown has been requested, successful changes wake
  the loop, and a closed watcher warns while continuing the loop.
- `runtime_finalization_projection(...)` mirrors the local runtime finalization
  sequence after worker shutdown: transport event sender drop, processor and
  outbound worker awaits, transport shutdown token cancellation, accept-handle
  awaits, ignored join results via Rust's `let _ = ...await`, and conditional
  OpenTelemetry shutdown.
- `ShutdownSignal`, `ShutdownAction`, and `ShutdownState` mirror the local
  graceful-restart drain state machine: first signal requests shutdown, a
  second forceable signal forces shutdown, repeated signals preserve the
  existing wait-log running-turn count, and zero running turns finishes the
  drain.
- `shutdown_signal(...)` mirrors the local signal mapping contract with
  injectable waiters: Ctrl-C and Unix SIGTERM map to `Forceable`, Unix SIGHUP
  maps to `GracefulOnly`, and non-Unix mode waits only for Ctrl-C.
- `runtime_transport_decisions(...)` mirrors the local runtime mode flags:
  stdio is single-client mode, stdio shuts down when connections drain, and
  graceful signal restart is enabled only when the runtime option is enabled
  and the transport is not stdio.
- `transport_startup_projection(...)` mirrors the local `match &transport`
  branch: stdio creates the client-name receiver and calls stdio startup, Unix
  socket and websocket transports push one accept handle, websocket requires
  auth-policy construction, and off starts no acceptor.
- `transport_acceptor_startup_projection(...)` mirrors the fallible ordering
  inside the transport match: stdio startup after client-name channel setup,
  Unix socket acceptor error before handle push, websocket auth policy before
  websocket acceptor startup, and startup-lock drop only after the match
  completes.
- `unix_socket_startup_lock_projection(...)` mirrors the earlier Unix-socket
  pre-acceptor setup branch: compute startup lock path, acquire startup lock,
  prepare control socket path, and store the lock only when all fallible steps
  succeed.
- `remote_control_runtime_decision(...)` mirrors local remote-control
  enablement and no-transport validation: remote control requires both a
  request and an available state DB, missing state DB records Rust's disabled
  error log, and no configured transport yields Rust's `InvalidInput` messages.
- `remote_control_startup_projection(...)` mirrors the local
  `start_remote_control(...)` call assembly: base URL, installation ID, state
  DB, auth manager, transport event sender, shutdown token, optional stdio
  client-name receiver, enabled flag, accept-handle push, and retained remote
  control handle, including the await-error path before accept-handle push.
- `app_text_range(...)`, `config_error_location(...)`,
  `config_warning_from_error(...)`, and `exec_policy_warning_location(...)`
  mirror the crate-root warning/location projection helpers for local config
  and exec-policy diagnostics, including the `config_warning_from_error`
  no-location branch that preserves summary/details while omitting path/range.
- `analytics_rpc_transport(...)` mirrors Rust's app-server RPC transport
  bucket: stdio stays stdio, while Unix socket, websocket, and off transports
  are classified as websocket for analytics.
- `project_config_warning(...)` mirrors the crate-root project-trust warning
  projection by listing disabled project `.codex` folders in layer order and
  returning no warning when no disabled project layers are present.
- `collect_config_warnings(...)` mirrors the local warning accumulation order:
  existing config-load warnings, exec-policy parse warnings, project-trust
  warnings, config startup warnings, and system bwrap warnings.
- `system_bwrap_warning_projection(...)` mirrors the local call site that
  passes `config.permissions.permission_profile()` into the core helper and
  appends a summary-only `ConfigWarningNotification` when a warning is
  returned.
- `configured_thread_config_loader(...)` mirrors the crate-root config loader
  selection: missing endpoints use `NoopThreadConfigLoader`, and configured
  endpoints use `RemoteThreadConfigLoader`.
- `config_provider_startup_projection(...)` mirrors the early
  config-provider setup before config loads: CLI override parsing, codex-home
  lookup, local runtime path construction, `EnvironmentManager` source
  selection from `ignore_user_config`, fallible setup stops including runtime
  path errors before environment manager creation, and
  `ConfigManager::new(...)` construction with an initial
  `NoopThreadConfigLoader`.
- `config_preload_projection(...)` mirrors the best-effort startup preload
  branch for cloud requirements: successful `load_latest_config(None)` replaces
  the thread-config loader and cloud requirements loader using an auth manager
  created with `enable_codex_api_key_env = false`; failures warn and continue.
- `runtime_auth_manager_projection(...)` mirrors the second runtime
  `AuthManager::shared_from_config(...)` call site after transport startup and
  startup-lock drop, also with `enable_codex_api_key_env = false`.
- `main_config_load_projection(...)` mirrors the main config-load branch:
  successful `load_latest_config(None)` enables personality migration, strict
  failures return the original config error, and non-strict failures append the
  invalid-config warning before loading default config with migration disabled.
- `personality_migration_projection(...)` mirrors the local personality
  migration control flow after state DB startup: disabled migration bypass,
  deserialize warning, migration warning, skipped statuses, Applied reload, and
  reload error mapping.
- `state_db_startup_projection(...)` mirrors the local
  `rollout_state_db::try_init(&config)` branch: success makes state DB
  available and failure returns an error mentioning `config.sqlite_home`.
- `telemetry_startup_projection(...)` mirrors the local OpenTelemetry provider
  startup branch: successful provider build records process start and installs
  sqlite telemetry, while build failures return the Rust `error loading otel
  config:` prefix before side effects.
- `runtime_resource_startup_projection(...)` mirrors the local feedback/log DB
  resource setup: `CodexFeedback::new()` is unconditional, `state_db` is cloned
  for `log_db::start`, and the resulting feedback/log DB handles are shared
  with tracing setup and `MessageProcessorArgs`.
- `runtime_channel_startup_projection(...)` mirrors the local runtime channel
  setup at entry: bounded `TransportEvent`, `OutgoingEnvelope`, and
  `OutboundControlEvent` channels all use `CHANNEL_CAPACITY = 128` and expose
  their receivers to the transport, outbound, and processor workers.
- `run_main_default_transport_options(...)` and
  `RunMainWithTransportOptionsCall` mirror the crate-root `run_main(...)`
  default handoff into `run_main_with_transport_options(...)`: stdio transport,
  VSCode session source, default websocket auth settings, and default runtime
  options.
- `run_main(...)` delegates through the same default handoff and then reaches
  the runtime-owned `run_main_with_transport_options(...)` orchestration.
- `AppServerRuntimeHooks`, `AppServerRuntimeResult`, and
  `run_main_with_transport_options(...)` mirror the crate-root startup and
  finalization ordering with injectable effects: CLI override parsing,
  codex-home/runtime-path/environment/config-manager setup, config preload and
  strict/default load handling, telemetry/state DB/personality migration,
  config-warning accumulation, feedback/logging/log DB setup, installation ID,
  transport and remote-control startup, outbound/router/message-processor
  assembly, processor/outbound worker startup, and final transport/OpenTelemetry
  shutdown sequencing.

## Known gaps

- Concrete sibling-owned effects behind `AppServerRuntimeHooks` remain
  dependency/runtime integration work: real config manager IO, telemetry
  provider installation, state DB startup, transport acceptors, remote-control
  server startup, outbound routing, `MessageProcessor` execution, and Tokio
  scheduling are not duplicated in this crate-root module.
- The default real OS listener for `shutdown_signal(...)` remains unimplemented;
  only the Rust signal-selection mapping is covered through injected waiters.
- Transport acceptor startup and remote-control server startup remain
  unimplemented; only local startup/enablement decisions and error text are
  covered.
- Async config loading, exec-policy checking, and concrete system bwrap warning
  rule computation remain unimplemented; only the app-server call site and
  warning accumulation from available inputs are covered.
- Transport event-loop processing remains unimplemented; only the
  connection-opened, connection-closed, transport-event channel-closed, and
  incoming request post-processing projections, non-request message routing
  decisions, outbound router control-event/outgoing-envelope decisions,
  processor-loop shutdown-update and shutdown-signal/running-turn watcher
  gates, and processor-exit cleanup gate are covered.
- Concrete outgoing envelope routing is not a `src/lib.rs` behavior contract:
  this module delegates it to sibling `transport::route_outgoing_envelope`.
- MessageProcessor execution and concrete JSON-RPC routing remain
  unimplemented; only local `MessageProcessorArgs` assembly is covered.
- Remote-control server/watch channel implementation remains unimplemented;
  only startup argument projection plus the local status-change and
  thread-created projections are covered.
- This crate now owns the embedded runtime dependency recorded by
  `codex-app-server-client/src/lib.rs`; the client crate should not duplicate
  this behavior.

## Evidence

- Rust source:
  `codex/codex-rs/app-server/src/lib.rs`
- Rust local tests:
  `log_format_from_env_value_matches_json_values_case_insensitively` and
  `log_format_from_env_value_defaults_for_non_json_values`.
- Rust source-contract tracing subscriber setup:
  local stderr/feedback/log DB/OpenTelemetry layer assembly and config-warning
  error emission.
- Rust source-contract runtime startup handles:
  local installation ID resolution and pre-transport handle initialization.
- Rust source-contract helpers:
  `app_text_range`, `config_error_location`, `config_warning_from_error`,
  `exec_policy_warning_location`, `analytics_rpc_transport`,
  `project_config_warning`, and config warning accumulation.
- Rust source-contract loader helper:
  `configured_thread_config_loader`.
- Rust source-contract config provider setup:
  pre-load CLI override parsing, codex-home/runtime-path discovery,
  environment manager selection, and initial `ConfigManager::new(...)`.
- Rust source-contract config preload branch:
  best-effort cloud requirements preload before the main config load.
- Rust source-contract runtime auth manager:
  post-transport `AuthManager::shared_from_config(..., false)` call site.
- Rust source-contract main config-load branch:
  strict/non-strict `load_latest_config(None)` handling and default-config
  fallback before telemetry setup.
- Rust source-contract personality migration branch:
  post-state-DB `maybe_migrate_personality(...)` control flow and Applied
  config reload behavior.
- Rust source-contract state DB startup:
  local `rollout_state_db::try_init(&config)` success/error handling.
- Rust source-contract telemetry startup:
  local `codex_core::otel_init::build_provider(...)` success/error handling
  before socket/state DB setup.
- Rust source-contract runtime resources:
  local `CodexFeedback::new()` and `state_db.clone().map(log_db::start)`
  handle creation before tracing subscriber setup.
- Rust source-contract runtime channels:
  local bounded `mpsc::channel` setup for transport events, outgoing
  envelopes, and outbound control events using `CHANNEL_CAPACITY`.
- Rust source-contract default runtime handoff:
  `run_main` default call to `run_main_with_transport_options`.
- Rust source-contract outbound router coordination shape:
  `OutboundControlEvent`, outbound worker startup biased select shape, the
  outbound control-event branch, and the local outgoing-envelope delegation
  branch to sibling `transport::route_outgoing_envelope`, plus `ConnectionOpened`/
  `ConnectionClosed` projections, the `ConnectionOpened` opened-event send
  failure branch, the `ConnectionClosed` closed-event send failure branch, and
  the transport event receiver closed branch, including the outbound-router
  task exited info log.
- Rust source-contract request post-processing:
  local `JSONRPCMessage::Request` state synchronization after
  `process_request`, including the unknown-connection warning/drop branch, the
  failed outbound opted-out notification methods write branch, and the
  first-initialization `session.request_attestation()` forwarding.
- Rust source-contract message processor setup:
  local analytics/outgoing sender setup, `MessageProcessorArgs` assembly,
  processor worker spawn boundary, watcher/connection/shutdown state
  initialization, plus processor loop select arm topology, in
  `run_main_with_transport_options`.
- Rust source-contract non-request routing:
  local `JSONRPCMessage::Response`, `JSONRPCMessage::Notification`, and
  `JSONRPCMessage::Error` connection gating, including unknown-connection
  warning/drop branches.
- Rust source-contract remote-control watcher projection:
  local `remote_control_status_rx.changed()` branch, including continue-loop
  control flow.
- Rust source-contract thread-created watcher projection:
  local `thread_created_rx.recv()` branch, including lagged warning and
  continue-loop control flow.
- Rust source-contract processor exit cleanup:
  local post-loop `if !shutdown_state.forced()` block and unconditional
  processor-task-exited info log.
- Rust source-contract processor loop shutdown update:
  local `ShutdownState::update(...)` top-of-loop action handling.
- Rust source-contract processor loop shutdown signal:
  local `shutdown_signal()` select arm handling.
- Rust source-contract processor loop running-turn watcher:
  local `running_turn_count_rx.changed()` select arm.
- Rust source-contract runtime finalization:
  local post-worker `drop(transport_event_tx)`, worker awaits,
  ignored join results, `transport_shutdown_token.cancel()`,
  accept-handle awaits, and optional OpenTelemetry shutdown.
- Rust source-contract state machine:
  `ShutdownState::requested`, `ShutdownState::forced`,
  `ShutdownState::on_signal`, repeated-signal preservation of
  `last_logged_running_turn_count`, and `ShutdownState::update`.
- Rust source-contract signal selection:
  `shutdown_signal`.
- Rust source-contract runtime decisions:
  `single_client_mode`, `shutdown_when_no_connections`,
  `graceful_signal_restart_enabled`, `remote_control_enabled`, missing-state-DB
  disabled logging, and no-transport error text.
- Rust source-contract transport startup branch:
  local `match &transport` in `run_main_with_transport_options`.
- Rust source-contract transport acceptor fallible ordering:
  stdio/unix-socket/websocket/off branches and websocket auth policy ordering.
- Rust source-contract Unix socket startup lock:
  local `match &transport` pre-acceptor branch for startup-lock acquisition and
  control-socket path preparation.
- Rust source-contract remote-control startup:
  local `start_remote_control(...)` call, await-error boundary, and
  accept-handle push.
- Python tests:
  `tests/test_app_server_lib_rs.py`

## Validation

Actual pytest is deferred by the crate automation rule until
`codex-app-server` functional runtime code is complete.
