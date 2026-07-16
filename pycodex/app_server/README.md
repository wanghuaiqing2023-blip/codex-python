# pycodex.app_server

Python alignment package for Rust crate `codex-app-server`.

## Crate status

`codex-app-server` is complete for the current Python porting scope. All
module status files and README module-map rows are complete.

2026-06-19 crate validation used the app-server-only test set: 60
`tests/test_app_server*.py` files excluding sibling crates
`test_app_server_client*` and `test_app_server_protocol_common.py`. That run
passed with 584 tests, and `python -m compileall -q pycodex/app_server @($tests)`
also passed for the same app-server-only test selection.

## Module map

| Rust module | Python module | Status |
| --- | --- | --- |
| `src/analytics_utils.rs` | `pycodex/app_server/analytics_utils.py` | complete |
| `src/app_server_tracing.rs` | `pycodex/app_server/app_server_tracing.py` | complete |
| `src/attestation.rs` | `pycodex/app_server/attestation.py` | complete |
| `src/bespoke_event_handling.rs` | `pycodex/app_server/bespoke_event_handling.py` | complete |
| `src/bin/notify_capture.rs` | `pycodex/app_server/bin/notify_capture.py` | complete |
| `src/bin/test_notify_capture.rs` | `pycodex/app_server/bin/test_notify_capture.py` | complete |
| `src/command_exec.rs` | `pycodex/app_server/command_exec.py` | complete |
| `src/config/mod.rs` | `pycodex/app_server/config/__init__.py` | complete |
| `src/config/external_agent_config.rs` | `pycodex/app_server/config/external_agent_config.py` | complete |
| `src/connection_rpc_gate.rs` | `pycodex/app_server/connection_rpc_gate.py` | complete |
| `src/config_manager.rs` | `pycodex/app_server/config_manager.py` | complete |
| `src/config_manager_service.rs` | `pycodex/app_server/config_manager_service.py` | complete |
| `src/dynamic_tools.rs` | `pycodex/app_server/dynamic_tools.py` | complete |
| `src/error_code.rs` | `pycodex/app_server/error_code.py` | complete |
| `src/extensions.rs` | `pycodex/app_server/extensions.py` | complete |
| `src/filters.rs` | `pycodex/app_server/filters.py` | complete |
| `src/fs_watch.rs` | `pycodex/app_server/fs_watch.py` | complete |
| `src/fuzzy_file_search.rs` | `pycodex/app_server/fuzzy_file_search.py` | complete |
| `src/in_process.rs` | `pycodex/app_server/in_process.py` | complete |
| `src/lib.rs` | `pycodex/app_server/__init__.py` | complete |
| `src/main.rs` | `pycodex/app_server/main.py` | complete |
| `src/message_processor.rs` | `pycodex/app_server/message_processor.py` | complete |
| `src/mcp_refresh.rs` | `pycodex/app_server/mcp_refresh.py` | complete |
| `src/models.rs` | `pycodex/app_server/models.py` | complete |
| `src/outgoing_message.rs` | `pycodex/app_server/outgoing_message.py` | complete |
| `src/request_processors.rs` | `pycodex/app_server/request_processors.py` | complete |
| `src/request_processors/account_processor.rs` | `pycodex/app_server/request_processors_account_processor.py` | complete |
| `src/request_processors/apps_processor.rs` | `pycodex/app_server/request_processors_apps_processor.py` | complete |
| `src/request_processors/catalog_processor.rs` | `pycodex/app_server/request_processors_catalog_processor.py` | complete |
| `src/request_processors/command_exec_processor.rs` | `pycodex/app_server/request_processors_command_exec_processor.py` | complete |
| `src/request_processors/config_processor.rs` | `pycodex/app_server/request_processors_config_processor.py` | complete |
| `src/request_processors/config_errors.rs` | `pycodex/app_server/request_processors_config_errors.py` | complete |
| `src/request_processors/environment_processor.rs` | `pycodex/app_server/request_processors_environment_processor.py` | complete |
| `src/request_processors/external_agent_config_processor.rs` | `pycodex/app_server/request_processors_external_agent_config_processor.py` | complete |
| `src/request_processors/feedback_doctor_report.rs` | `pycodex/app_server/request_processors_feedback_doctor_report.py` | complete |
| `src/request_processors/feedback_processor.rs` | `pycodex/app_server/request_processors_feedback_processor.py` | complete |
| `src/request_processors/fs_processor.rs` | `pycodex/app_server/request_processors_fs_processor.py` | complete |
| `src/request_processors/git_processor.rs` | `pycodex/app_server/request_processors_git_processor.py` | complete |
| `src/request_processors/initialize_processor.rs` | `pycodex/app_server/request_processors_initialize_processor.py` | complete |
| `src/request_processors/marketplace_processor.rs` | `pycodex/app_server/request_processors_marketplace_processor.py` | complete |
| `src/request_processors/mcp_processor.rs` | `pycodex/app_server/request_processors_mcp_processor.py` | complete |
| `src/request_processors/plugins.rs` | `pycodex/app_server/request_processors_plugins.py` | complete |
| `src/request_processors/process_exec_processor.rs` | `pycodex/app_server/request_processors_process_exec_processor.py` | complete |
| `src/request_processors/remote_control_processor.rs` | `pycodex/app_server/request_processors_remote_control_processor.py` | complete |
| `src/request_processors/request_errors.rs` | `pycodex/app_server/request_processors_request_errors.py` | complete |
| `src/request_processors/search.rs` | `pycodex/app_server/request_processors_search.py` | complete |
| `src/request_processors/thread_goal_processor.rs` | `pycodex/app_server/request_processors_thread_goal_processor.py` | complete |
| `src/request_processors/thread_lifecycle.rs` | `pycodex/app_server/request_processors_thread_lifecycle.py` | complete |
| `src/request_processors/thread_processor.rs` | `pycodex/app_server/request_processors_thread_processor.py` | complete |
| `src/request_processors/turn_processor.rs` | `pycodex/app_server/request_processors_turn_processor.py` | complete |
| `src/request_processors/thread_summary.rs` | `pycodex/app_server/request_processors_thread_summary.py` | complete |
| `src/request_processors/thread_resume_redaction.rs` | `pycodex/app_server/request_processors_thread_resume_redaction.py` | complete |
| `src/request_processors/token_usage_replay.rs` | `pycodex/app_server/request_processors_token_usage_replay.py` | complete |
| `src/request_processors/windows_sandbox_processor.rs` | `pycodex/app_server/request_processors_windows_sandbox_processor.py` | complete |
| `src/request_serialization.rs` | `pycodex/app_server/request_serialization.py` | complete |
| `src/server_request_error.rs` | `pycodex/app_server/server_request_error.py` | complete |
| `src/skills_watcher.rs` | `pycodex/app_server/skills_watcher.py` | complete |
| `src/thread_state.rs` | `pycodex/app_server/thread_state.py` | complete |
| `src/thread_status.rs` | `pycodex/app_server/thread_status.py` | complete |
| `src/transport.rs` | `pycodex/app_server/transport.py` | complete |

## 2026-06-19 src/lib.rs complete alignment

The package now owns the crate-root app-server runtime namespace that
`codex-app-server-client` depends on for embedded startup. Python covers the
local `LogFormat::from_env_value` behavior, `log_format_from_env`, and the
`AppServerRuntimeOptions::default()` surface, including exact rejection of
JSON-like non-`json` log format values.
The crate-root module inventory is also explicit: `src/lib.rs` declares 26
private sibling modules, public `in_process`, and the transport/error-code
re-export surface now projected by `crate_root_module_inventory_projection(...)`.
It also covers crate-root diagnostic projection helpers for config warnings,
exec-policy warning locations, app text ranges, and analytics RPC transport
classification, including the no-location config warning branch.
Logging subscriber projection covers Rust's local tracing layer assembly:
stderr JSON/default formatting, feedback logger/metadata layers, optional log
DB and OpenTelemetry layers, ignored `try_init` result, and config-warning
error emission counts.
Runtime startup handles projection covers the local pre-transport setup after
logging: installation ID resolution, transport shutdown token creation, empty
accept-handle vector initialization, and the initial absent stdio client-name
receiver.
Project-trust startup warning projection is covered for disabled project
`.codex` layers.
Config warning accumulation preserves Rust's order across existing config-load
warnings, exec-policy parse warnings, project-trust warnings, config startup
warnings, and system bwrap warnings. The system bwrap warning call-site is
also projected: app-server passes the config permission profile into the core
helper and appends a summary-only warning when one is returned.
Thread-config loader selection is covered for default/noop and remote endpoint
configs.
`src/command_exec.rs` is complete after focused parity validation for its
control-plane contract. Python covers process id generation and JSON-string
error rendering, duplicate active process id rejection, streaming/client
process-id validation, Windows restricted-token sandbox streaming and custom
output-cap rejection, unsupported Windows sandbox control errors, actionable
write validation, base64 decoding, stdin-streaming guard, terminate/resize
control recording, connection-close session cleanup, not-running error text,
and terminal-size validation. Real PTY/pipe spawning, sandbox execution, output
streaming/capping, expiration select-loop timing, IO drain timeout, and concrete
outgoing response delivery remain runtime/dependency boundaries. Focused
validation passed on 2026-06-19 with
`tests/test_app_server_command_exec_rs.py` (13 passed) plus `py_compile` for
the Python module and parity test.
`src/config/mod.rs` is complete after focused parity validation. Python mirrors
the parent namespace contract: the crate-private `external_agent_config` child
module declaration, intended Python child path, and `pub(crate)` visibility,
without pulling in the child module's migration/config behavior. Focused
validation passed on 2026-06-19 with `tests/test_app_server_config_mod_rs.py`
(1 passed) plus `py_compile` for the Python module and parity test.
`src/config/external_agent_config.rs` is complete after focused parity
validation for the dependency-light external-agent config migration contract.
Python covers migration constants and data shapes, default external-agent home
selection, recursive settings merge, enabled plugin and marketplace-source
collection with official marketplace fallback and relative local source
resolution, case-insensitive term rewriting with ASCII word-boundary checks,
supported settings projection into Codex config tables, environment value
stringification, missing-only TOML table merge behavior, migrated MCP server
name extraction, metric tag construction, and external session source path
canonicalization. Full filesystem migration, real session replay, MCP/hook/
subagent/command import execution, marketplace install policy, and async plugin
installation remain documented runtime boundaries. Focused validation passed on
2026-06-19 with `tests/test_app_server_config_external_agent_config_rs.py` (14
passed) plus `py_compile` for the Python module and parity test.
`src/bin/notify_capture.rs` is complete after focused parity validation for the
registered `codex-app-server-test-notify-capture` helper binary. Python mirrors
the Rust argument contract after skipping the program name, exact missing/extra
argument error strings, lossy payload text conversion, display-based
`"{output_path}.tmp"` temp path construction, synced temp-file writes, and final
move into the requested output path. Focused validation passed on 2026-06-19
with `tests/test_app_server_bin_notify_capture_rs.py` (7 passed) plus
`py_compile` for the Python module and parity test.
`src/bin/test_notify_capture.rs` is complete after focused parity validation
for the standalone Rust helper. Python mirrors skipping the program argument,
missing output/payload error strings, strict UTF-8 payload conversion with the
Rust `payload must be valid UTF-8` error, `with_extension("json.tmp")` temp path
construction, temp-file writes, final move into the requested output path, and
ignored extra arguments after payload. The Python helper keeps its Rust-aligned
export names while marking pytest-looking helper names as non-tests for Python
collection hygiene. Focused validation passed on 2026-06-19 with
`tests/test_app_server_bin_test_notify_capture_rs.py` (6 passed) plus
`py_compile` for the Python module and parity test.
`src/bespoke_event_handling.rs` is complete after focused parity validation for
its module-local conversion and fallback helpers. Python mirrors turn
diff/plan/completion notification shaping, hook prompt completion payload
filtering, MCP elicitation and permissions client-response fallback behavior,
review output rendering, file-change approval decision mapping, and millisecond
timestamp projection. Full `apply_bespoke_event_handling` async dispatch,
concrete Codex thread submission, watcher/permit lifetimes, outgoing transport
emission, thread-state mutation, command-execution approval side effects,
rollback store loading, and concrete permission-profile intersection remain
runtime boundaries. Focused validation passed on 2026-06-19 with
`tests/test_app_server_bespoke_event_handling_rs.py` (8 passed) plus
`py_compile` for the Python module and parity test.
Config provider startup projection covers Rust's early setup before config
loads: CLI override parsing, codex-home/runtime-path discovery, environment
manager selection for `ignore_user_config`, and ConfigManager construction with
the initial Noop thread-config loader, including the runtime-path error stop
before environment manager creation.
Runtime channel startup projection covers the three bounded mpsc channels
created at runtime entry: `TransportEvent`, `OutgoingEnvelope`, and
`OutboundControlEvent`, all using `CHANNEL_CAPACITY = 128`.
Config preload projection covers Rust's best-effort cloud requirements preload:
successful preload replaces the thread-config loader and cloud requirements
loader with an auth manager created without `CODEX_API_KEY` env support, while
failure warns and continues startup.
Main config-load projection covers Rust's strict/non-strict branch: successful
loads enable personality migration, strict failures return the original error,
and non-strict failures append the invalid-config warning before loading default
config with migration disabled.
Telemetry startup projection covers Rust's OpenTelemetry provider build branch:
success records process start and installs sqlite telemetry, while build
failure returns the `error loading otel config:` error prefix before side
effects.
Personality migration projection covers Rust's post-state-DB migration control
flow: disabled migration bypass, effective config deserialize warnings,
warning-only migration errors, skipped statuses, Applied reload, and reload
error mapping.
State DB startup projection covers Rust's `rollout_state_db::try_init` branch:
success stores `Some(state_db)`, while failure returns an error whose message
includes `config.sqlite_home`.
Runtime resource startup projection covers Rust's feedback/log DB setup:
`CodexFeedback` is always created and shared, while `log_db::start` runs only
when state DB is available and is then passed to logging and
`MessageProcessorArgs`.
Outbound router control event shapes are represented for opened, closed, and
disconnect-all coordination messages.
Outbound router startup projection covers the worker setup shape: empty
outbound connection map, biased select loop with control events before
outgoing envelopes, and the task-exited info log after the loop.
Outbound router control projection covers Rust's local control branch:
opened inserts outbound state, closed removes it, disconnect-all requests
disconnect on every outbound connection and clears the map, and a closed
control channel exits the router loop before the outbound-router-exited log.
Outbound router outgoing projection covers Rust's local outgoing-envelope
branch: present envelopes delegate to `route_outgoing_envelope`, while a closed
outgoing channel exits the router loop before the outbound-router-exited log.
`src/transport.rs` now owns that concrete outgoing routing projection:
its re-export surface records the app-server-transport types, path helpers,
acceptor startup functions, and remote-control names used by this module.
`ConnectionState::new` ignores origin while creating a fresh session,
`disconnect_connection` removes/cancels known connections, direct sends drop
unknown connections, broadcasts target initialized and unfiltered connections,
opted-out/experimental notification filters are preserved,
`CommandExecutionRequestApproval` strips `additionalPermissions` without
experimental capability, disconnectable full writers are removed, and
stdio-like non-disconnectable full writers wait rather than disconnect.
Focused validation passed on 2026-06-19 with
`tests/test_app_server_transport_rs.py` (13 passed) plus `py_compile` for the
module and tests.
Outgoing message runtime projection covers Rust's processor-worker setup for
analytics and outgoing notifications: clone auth manager for analytics, build
`OutgoingMessageSender` from `outgoing_tx`, and clone the initialize
notification sender.
Message-processor args projection covers Rust's local
`MessageProcessorArgs` assembly, including outgoing/analytics/config/session
handles, log/state DB optionality, config warnings, analytics transport bucket,
remote-control handle, and plugin startup task propagation.
Processor startup projection covers Rust's local processor worker setup:
watch subscriptions, empty connection map, initial remote-control status clone,
transport shutdown token clone, `listen_for_threads = true`, and default
shutdown state.
Processor worker spawn projection records the Rust spawn/capture boundary:
auth manager clone before analytics setup, moving `outbound_control_tx`,
constructing `MessageProcessor` before `async move`, and finalization awaiting
the processor handle.
Processor select topology projection records the processor loop's five
`tokio::select!` arms, their Rust order, and the local gates for shutdown
signals, running-turn changes, and thread-created events.
Connection-opened projection now records Rust's paired outbound-control event
and connection-state initial values, including the local break path when
sending the opened event to the outbound router fails before insertion.
Connection-closed projection records Rust's local behavior for unknown
connections, outbound closed events, outbound send-failure loop exit,
processor notification, and single-client loop exit.
Transport-event channel-closed projection records Rust's local receiver
shutdown branch: a closed `transport_event_rx` exits the processor loop.
Incoming request projection records Rust's local post-processing state sync:
unknown-connection warning/drop behavior, outbound opt-out/API flag updates,
and first initialize side effects, including the warning-only path when
updating outbound opt-out notification methods fails and the request-attestation
argument passed to `connection_initialized`.
Incoming non-request projection covers Rust's connection gate and processor
method routing for response, notification, and error JSON-RPC messages,
including unknown-connection warning/drop behavior per message kind.
Remote-control status projection covers Rust's watcher behavior for ignored
errors, unchanged statuses, changed-status notifications, and the fact that
each watcher branch continues the processor loop.
Thread-created projection covers Rust's watcher behavior for attaching new
threads only to initialized connections, ignoring lagged receivers without
resync with a warning, disabling future listening once the receiver closes, and
continuing the processor loop for every handled recv result.
Processor-exit projection covers Rust's forced-shutdown cleanup gate: graceful
exits shut down RPC gates, drain background tasks, and shut down threads, while
forced exits skip that block; both paths record the processor task exit log.
Processor-loop update projection covers Rust's top-of-loop shutdown action:
`Finish` cancels the transport shutdown token, sends disconnect-all to outbound
connections, and exits the loop; `Noop` continues into the select block.
Processor shutdown-signal projection covers Rust's select arm gating and
handling: graceful restart must be enabled, forced shutdown disables the arm,
listener errors continue the loop, and successful signals call
`ShutdownState::on_signal` with the current connection/running-turn counts.
Processor running-turn watcher projection covers Rust's graceful-restart drain
watcher: it listens only after shutdown is requested, successful changes wake
the loop, and closed watcher warnings keep the loop alive.
Runtime-finalization projection covers Rust's post-worker shutdown sequence:
drop the transport event sender, await processor/outbound workers, cancel the
transport shutdown token, await transport accept handles, and conditionally
shutdown OpenTelemetry; it also records Rust's `let _ = ...await` behavior for
ignored join results.
The local graceful-restart `ShutdownState` state machine is now represented:
first signal enters drain, a second forceable signal forces completion, and zero
running turns finishes the drain. Repeated signals preserve the existing
wait-log running-turn count after shutdown has already been requested.
`shutdown_signal(...)` covers Rust's signal-to-shutdown-action mapping through
injectable waiters: Ctrl-C and SIGTERM are forceable, while Unix SIGHUP is
graceful-only.
Runtime transport decision helpers cover Rust's local mode flags: stdio enters
single-client/no-connection shutdown mode, non-stdio transports may enable
graceful signal restart, and remote control is enabled only when requested with
an available state DB, with a disabled log recorded when remote control is
requested without state DB.
Transport-startup projection covers Rust's local `match &transport` branch:
stdio creates the client-name receiver and starts stdio transport, Unix socket
and websocket transports push one accept handle, websocket requires auth policy
construction, and off starts no acceptor.
Transport acceptor startup projection covers the fallible ordering inside that
match: stdio channel setup before stdio startup, Unix socket acceptor errors
before handle push, websocket auth policy before websocket acceptor startup,
and dropping the startup lock only after the match completes.
Runtime auth manager projection covers the second
`AuthManager::shared_from_config` call site after transport startup and startup
lock drop, with `CODEX_API_KEY` env opt-in disabled.
`src/dynamic_tools.rs` is now complete. Python covers the dynamic tool response
decode path, invalid-response fallback, request-failed fallback,
turn-transition early return, app-server to core dynamic tool response
conversion, and the shaped `Op::DynamicToolResponse` submit payload. The real
Tokio oneshot await, `CodexThread::submit(...)` execution, and tracing side
effects remain runtime integration boundaries. Focused parity validation passed
with 8 tests plus py_compile.
`src/models.rs` is now mapped as a complete module. Python covers
Rust's `ModelPreset` to app-server `Model` conversion, reasoning effort option
mapping, `include_hidden || show_in_picker` filtering, and the
`RefreshStrategy::OnlineIfUncached` model-list call shape. Concrete
`ThreadManager` model-manager refresh/cache behavior remains a runtime
dependency. Focused validation passed with
`python -m pytest tests/test_app_server_models_rs.py -q` -> `5 passed`.
`src/skills_watcher.rs` is now mapped as a complete module. Python
covers watcher setup/fallback projection, shutdown cancellation, thread-config
registration decisions for absent, unknown, remote, and local environments,
`SkillsLoadInput` shaping, recursive skill-root watch paths, and the listener
iteration action that clears the skills cache and sends `SkillsChanged`.
Focused validation passed on 2026-06-19 with
`tests/test_app_server_skills_watcher_rs.py` (11 passed) plus `py_compile` for
the module and tests.
Concrete file watcher integration, throttled receiver timing, Tokio task
spawning, cancellation-token mechanics, and outgoing async delivery remain
runtime dependencies.
`src/extensions.rs` is complete after focused parity validation. Python covers
the thread extension install order, app-server extension event sink forwarding
for `ThreadGoalUpdated`, unsupported extension event dropping, core-to-app
thread-goal conversion, and the guardian agent spawner weak-manager dropped and
delegate branches. Real extension registry installation,
AuthManager/OpenTelemetry integration, and concrete async subagent spawning
remain runtime dependencies. Focused validation passed on 2026-06-19 with
`tests/test_app_server_extensions_rs.py` (6 passed) plus `py_compile` for the
Python module and parity test.
`src/connection_rpc_gate.rs` is now complete. Python covers the
per-connection RPC gate: open construction, accepting check, inflight token
accounting before handler execution, shutdown closing new work, late-run
dropping without polling the handler, and shutdown waiting for already-started
work. Exact Tokio `TaskTracker` internals and scheduler fairness remain runtime
details. Focused parity validation passed with 5 tests plus py_compile.
`src/fuzzy_file_search.rs` is complete after focused parity validation. Python
covers the app-server-owned fuzzy file search bridge: one-shot empty-root
early return, search option shaping, failure-to-empty behavior, result
projection and score/path ordering, session latest-query updates, cancellation
gates, stale snapshot filtering, empty-query update payloads, update
notifications, and completion notifications. Concrete file walking/matching and
session runtime remain owned by `codex-file-search`. Focused validation passed
on 2026-06-19 with `tests/test_app_server_fuzzy_file_search_rs.py` (7 passed)
plus `py_compile` for the Python module and parity test.
`src/mcp_refresh.rs` is complete after focused parity validation. Python covers
strict refresh loading latest global config first, planning all
per-thread refresh configs before queueing, thread-load error wrapping,
best-effort per-thread skip behavior, refresh-config serialization through the
thread manager MCP manager, `mcp_oauth_credentials_store_mode` forwarding, and
submit error wrapping. Concrete `ConfigManager`, `ThreadManager`, `CodexThread`,
and MCP manager implementations remain dependency/runtime boundaries. Focused
validation passed on 2026-06-19 with `tests/test_app_server_mcp_refresh_rs.py`
(6 passed) plus `py_compile` for the Python module and parity test.
`src/config_manager.rs` is complete after focused parity validation. Python
covers the app-server-owned config-manager coordination contract: stored
loader/config handles, CLI/request override merging, `bypass_hook_trust`
typed-override extraction, runtime feature enablement with protected-feature
skips, thread-config rebuild handoff, default-config user-profile injection,
arg0 dispatch path application, and config-layer loader call shaping. Concrete
core config builder execution, default config loading, config-layer filesystem
loading, AuthManager/cloud internals, lock poisoning, tracing, and global
residency side effects remain runtime dependency boundaries. Focused validation
passed on 2026-06-19 with `tests/test_app_server_config_manager_rs.py`
(8 passed) plus `py_compile` for the Python module and parity test.
`src/config_manager_service.rs` is now complete. Python covers the
app-server-owned config service helper contract: keyPath parsing including
quoted and escaped segments, JSON null clear semantics, replace/upsert table
merge behavior, missing-clear no-op behavior, table/array path lookup,
user-config path restriction, expected-version conflicts, legacy `profile` and
`profiles.*` write rejection, read origins/layer projection, and override
metadata detection for effective higher-precedence layers. Rust's
comment/order-preserving TOML document edits and exact edit span metadata remain
deferred, while Python now reloads the latest user layer and persists changed
values through the core atomic config editor. Core config validation, feature
requirement validation, managed policy validation, and selected-profile loading
remain dependency/runtime boundaries. Focused validation covers both the
service and the Rust-shaped TUI request-handle -> config-processor ->
config-manager-service path, including process-restart persistence.
`src/fs_watch.rs` is now complete. Python covers the app-server-owned
filesystem watch bookkeeping: `(connection_id, watch_id)` scoped entries,
non-recursive watch-path registration shape, duplicate watch ID rejection
within a connection, connection-scoped unwatch, connection-close cleanup,
debounce accumulation projection, and sorted `FsChanged` notification payload
shaping. Concrete `codex-file-watcher`, Tokio task spawning/select timing,
oneshot termination ordering, and outgoing transport delivery remain runtime
dependency boundaries. Focused parity validation passed with 8 tests plus
py_compile.
`src/request_serialization.rs` is now complete. Python covers the app-server
request serialization queues: every `ClientRequestSerializationScope`
key/access mapping, FIFO exclusive execution per key, concurrent draining for
different keys, closed-gate skip behavior, shared-read batch draining,
exclusive-write barriers behind running reads, and the rule that later shared
reads do not jump ahead of an already queued write. Exact Tokio
spawn/scheduler/tracing behavior and concrete request processors remain runtime
dependency boundaries. Focused parity validation passed with 8 tests plus
py_compile.
`src/request_processors.rs` is now mapped as a complete parent module.
Python records the Rust child-module declarations, processor
re-export surface, thread helper re-export surface, and the
`build_api_turns_from_rollout_items(...)` contract that filters rollout items
through `EventPersistenceMode::Limited` before replaying them through
`ThreadHistoryBuilder`. Concrete child request processors remain separate
module boundaries. Focused parity validation passed with 4 tests plus
py_compile.
`src/request_processors/account_processor.rs` is now mapped as a
complete-candidate child module. Python preserves the module-owned account
request state machine: active login replacement/cancellation, forced login
method validation, external-auth checks, login/logout result and notification
projection, get-account response projection, rate-limit primary/by-id
selection, add-credits nudge status mapping, and Rust's invalid/internal error
messages for local request failures. Real credential persistence,
browser/device-code login, backend HTTP, and plugin-cache refresh remain
injectable dependency/runtime boundaries.
`src/request_processors/initialize_processor.rs` is now mapped as a
complete-candidate child module. Python preserves duplicate initialize
rejection, client-name header validation before session mutation, initialized
session capability state, non-originating client-name behavior, analytics
tracking, residency/user-agent metadata side effects through injectable
call-sites, initialize response construction, outbound-ready marking, config
warning notification replay, and initialized-request analytics forwarding.
Concrete transport routing and process-global default-client mutation remain
runtime dependency boundaries.
`src/request_processors/marketplace_processor.rs` is now mapped as a complete
child module after focused validation. Python preserves constructor dependency
storage, add/remove/upgrade facade parameter parsing and response projection,
marketplace add sparse-path defaults, remove installed-root remapping,
InvalidRequest/Internal JSON-RPC error mapping for add/remove, latest-config
reload behavior, plugins-manager lookup, plugins-config input forwarding,
selected marketplace forwarding, upgrade response/error projection, and
upgrade failure invalid-request mapping. Concrete marketplace repository IO,
git/network behavior, plugin runtime upgrade implementation, and Tokio
spawn-blocking scheduling remain injected runtime or extension-area
boundaries. Focused parity validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_marketplace_processor_rs.py` (9
passed) plus `py_compile` for the Python module and parity test.
`src/request_processors/mcp_processor.rs` is now mapped as a complete child
module after focused validation. Python preserves constructor dependency
storage, refresh queue delegation and internal-error text, latest-config and
thread-load error mapping, OAuth login validation for missing/non-HTTP
servers, scope resolution precedence, status-list server-name union/sort,
cursor validation and pagination, unsupported auth defaults, resource-read
thread/threadless response projection and deserialize errors, tool-call thread
loading, `threadId` metadata injection, core tool-result conversion, and
already-mapped JSON-RPC error forwarding. Real MCP status collection,
threadless resource runtime, OAuth browser login, concrete MCP tool execution,
and Tokio task scheduling remain injected runtime or extension-area
boundaries. Focused parity validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_mcp_processor_rs.py` (10 passed)
plus `py_compile` for the Python module and parity test.
`src/request_processors/plugins.rs` is now mapped as a complete child module
after focused validation. Python preserves constructor dependency storage,
public facade delegation for list/read/share/install/uninstall surfaces,
effective-plugin cache clearing and best-effort refresh boundaries,
latest-config reload and workspace-plugin fallback behavior, skill/interface
summary conversion, local/git marketplace source conversion, local share
context lookup, configured marketplace plugin summary conversion, remote
visible-scope calculation, share discoverability/update/target/principal
conversion, and client share-target workspace-principal invalid-request
mapping. Concrete plugin discovery, marketplace sync, remote plugin
install/uninstall, OAuth login, app-auth probing, and share-service calls
remain injected runtime or extension-area boundaries. Focused parity
validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_plugins_rs.py` (12 passed) plus
`py_compile` for the Python module and parity test.
`src/request_processors/catalog_processor.rs` is now mapped as a complete
child module after focused validation. Python preserves catalog construction
boundaries, Rust-style pagination and cursor errors, model and collaboration
mode listing through injected thread-manager methods, permission-profile
built-in/configured ordering, experimental feature stage/enablement projection
with workspace plugin gating, skill/hook/error metadata projection, skills
config write selector validation/cache clearing, and the mock experimental
echo helper. Real plugin discovery, hook loading, skill discovery, and config
edit persistence remain injected runtime or extension-area boundaries. Focused
parity validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_catalog_processor_rs.py` (10 passed)
plus `py_compile` for the Python module and parity test.
`src/request_processors/apps_processor.rs` is now mapped as a complete child
module after focused validation. Python preserves app/list construction
dependencies, thread config-snapshot fallback CWD loading, feature/auth and
workspace plugin gating with immediate empty-list responses, spawned list-task
boundary, shutdown cancellation hook, cached/interim/final app-list update
notifications, connector merge and enabled-state projection, cursor parsing,
pagination, codex-apps-readiness retry, and JSON-RPC error mapping. Concrete
connector discovery, MCP environment-manager loading, workspace backend fetch,
Tokio task scheduling, and timeout timing remain injected dependency/runtime
boundaries. Focused parity validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_apps_processor_rs.py` (8 passed) plus
`py_compile` for the Python module and parity test.
`src/request_processors/command_exec_processor.rs` is now mapped as a complete
child module after focused validation. Python preserves local-environment gating,
one-off command validation and Rust error text, cwd/env assembly,
output-cap/timeout/capture-policy projection, permission-profile config reload
and disallowed-warning mapping, legacy sandbox policy validation, managed
network proxy and exec-request error mapping, and write/resize/terminate/
connection-close delegation to `CommandExecManager`. Concrete exec request
construction, sandbox setup, process spawning, and network proxy runtime
lifetimes remain injected runtime boundaries. Focused parity validation passed
on 2026-06-19 with
`tests/test_app_server_request_processors_command_exec_processor_rs.py`
(13 passed) plus `py_compile` for the Python module and parity test.
`src/request_processors/config_processor.rs` is now mapped as a complete child
module after focused validation. Python preserves config read delegation plus
feature enablement injection, requirements TOML-to-protocol mapping, config
value/batch write mutation boundaries, write-error data, runtime feature
enablement validation, user-config refresh fan-out, plugin-toggle analytics
hooks, model-provider capability projection, and apps-list refresh trigger
boundaries. Concrete connector directory refresh, app-enabled-state merging,
installed plugin telemetry metadata loading, real thread-manager runtime
refresh, and model-provider construction remain injected dependency/runtime
boundaries. Focused parity validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_config_processor_rs.py` (10 passed)
plus `py_compile` for the Python module and parity test.
`src/request_processors/config_errors.rs` is now mapped as a
complete-candidate child module. Python preserves config-load invalid-request
error construction and structured `cloudRequirements` data for wrapped cloud
requirements failures, including Debug-style `errorCode`, optional
`statusCode`, Auth-only `action: relogin`, and unset data for non-cloud
failures.
`src/request_processors/request_errors.rs` is now mapped as a
complete-candidate child module. Python preserves the helper that returns raw
`CodexErr::InvalidRequest` messages for environment-selection failures while
falling back to display strings for all other errors. The flattened Python
filename avoids colliding with the parent `request_processors.py` module.
`src/request_processors/search.rs` is now mapped as a complete child module
after focused validation. Python preserves one-shot fuzzy-search
cancellation-token replacement, empty-query short-circuiting, guarded cleanup
of the current cancellation flag, session start validation/error mapping,
update missing-session errors, and stop removal semantics. Filesystem search
and reporter behavior remain owned by sibling module
`src/fuzzy_file_search.rs`. Focused parity validation passed on 2026-06-19
with `tests/test_app_server_request_processors_search_rs.py` (6 passed) plus
`py_compile` for the Python module and parity test.
`src/request_processors/environment_processor.rs` is now mapped as a
complete-candidate child module. Python stores the environment manager,
delegates `environment_add` to `upsert_environment(environment_id,
exec_server_url)`, maps upsert failures through `invalid_request`, and returns
an empty `EnvironmentAddResponse` on success. MessageProcessor dispatch and
response-envelope wrapping remain runtime boundaries.
`src/request_processors/external_agent_config_processor.rs` is now complete
after focused validation. Python preserves detect option projection,
core-to-protocol migration item/detail mapping, import validation, runtime
refresh gating for config/skills/MCP/hooks/commands/plugins,
response-before-background ordering, immediate completion notifications,
background session/plugin completion scheduling, session source-path dedupe,
cache-clear hooks after plugin imports, and JSON-RPC error mapping. Full
external session replay, thread startup, plugin installation,
imported-session ledger persistence, and Tokio scheduling remain injected
runtime boundaries. Focused validation passed with 8 tests plus py_compile.
`src/request_processors/feedback_doctor_report.rs` is now mapped as a complete
child module after focused validation. Python preserves current-executable
fallback, best-effort doctor JSON extraction from stdout, pretty
`codex-doctor-report.json` attachment construction, object/array check
iteration, ok/warning/fail tag counts, failed/warning check id tags, missing
check ids as `unknown`, and 256-character tag truncation. Focused parity
validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_feedback_doctor_report_rs.py` (6
passed) plus `py_compile` for the Python module and parity test.
`src/request_processors/feedback_processor.rs` is now mapped as a complete
child module after focused validation. Python preserves feedback upload gating,
thread-id parsing, cached auth feedback tag hook names, snapshot upload
dispatch, no-log upload options, include-log flush/subtree/state-DB fallback,
sqlite log override lookup, rollout/guardian/Windows sandbox/explicit
attachment collection with path dedupe, doctor-report attachment and tag
merging, session-source propagation, and JSON-RPC error mapping. Concrete
feedback backend upload, live thread runtime, and Windows sandbox log path
discovery remain injected runtime boundaries. Focused parity validation passed
on 2026-06-19 with
`tests/test_app_server_request_processors_feedback_processor_rs.py` (8 passed)
plus `py_compile` for the Python module and parity test.
`src/request_processors/fs_processor.rs` is now mapped as a complete child
module after focused validation. Python preserves local filesystem lookup
through the environment manager, base64 read/write behavior, create/remove
default options, metadata/directory entry projection, copy option forwarding,
invalid-input filesystem error mapping, and watch/unwatch/connection-close
delegation through `FsWatchManager`. Concrete filesystem access, sandbox
enforcement, and file watching remain injected runtime boundaries. Focused
parity validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_fs_processor_rs.py` (7 passed) plus
`py_compile` for the Python module and parity test.
`src/request_processors/git_processor.rs` is now mapped as a complete child
module after focused validation. Python preserves the stateless processor
constructor, diff-to-origin delegation, successful `sha`/`diff` response
projection, and invalid-request error mapping when no remote diff can be
computed. Actual git diff discovery remains owned by `codex-git-utils`.
Focused parity validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_git_processor_rs.py` (4 passed) plus
`py_compile` for the Python module and parity test.
`src/request_processors/process_exec_processor.rs` is now complete after
focused validation. Python preserves process/spawn local environment gating,
request validation, environment override projection, timeout/output-cap/
terminal-size projection, connection/process-handle session bookkeeping,
duplicate-handle rejection, stdin/resize/kill control routing,
close-triggered kill controls, and output capture/delta projection. Real
PTY/pipe spawning, Tokio task scheduling, expiration waiting, stdio drain
timing, and process-exit notification delivery remain runtime boundaries.
Focused validation passed with 9 tests plus py_compile.
`src/request_processors/remote_control_processor.rs` is now mapped as a
complete child module after focused validation. Python preserves optional
handle storage, missing-handle internal error mapping, enable unavailable
invalid-request mapping, and enable/disable/status-read projection of
remote-control status fields into protocol response payloads. Remote-control
startup and status watching remain transport/runtime boundaries. Focused parity
validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_remote_control_processor_rs.py` (4
passed) plus `py_compile` for the Python module and parity test.
`src/request_processors/windows_sandbox_processor.rs` is now mapped as a
complete child module after focused validation. Python preserves dependency
storage, non-Windows not-configured readiness,
disabled/restricted/elevated readiness state mapping, the immediate
`started: true` setup response, command-cwd/config reload projection,
setup-request assembly, and completion notification shape for success and
failure. Concrete Windows setup execution and exact Tokio spawn scheduling
remain runtime dependency boundaries. Focused parity validation passed on
2026-06-19 with
`tests/test_app_server_request_processors_windows_sandbox_processor_rs.py` (6
passed) plus `py_compile` for the Python module and parity test.
`src/request_processors/thread_summary.rs` is now complete after focused
validation. Python preserves thread-spawn agent metadata overlay, active
permission profile and sandbox policy projection, thread settings projection
from config/core snapshots, thread-started notification turn clearing,
conversation-summary preview extraction, git-info mapping, and
summary-to-thread materialization. Full rollout file IO and thread-processor
JSON-RPC dispatch remain runtime/dependency boundaries. Focused validation
passed with 7 tests plus py_compile.
`src/request_processors/thread_resume_redaction.rs` is now complete. Python
preserves the exact ChatGPT Android/iOS remote-client allowlist, response-only
MCP argument/result/error redaction, and image-generation item removal used by
`thread/resume`. Because protocol thread values are frozen dataclasses in
Python, the helper returns a redacted copy rather than mutating persisted
history inputs. Focused parity validation passed with 3 tests plus py_compile.
`src/request_processors/thread_goal_processor.rs` is now complete after focused
parity validation. Python preserves Goals feature gating, thread
id parsing, materialized-thread state DB lookup, ephemeral-thread rejection,
goal status/budget/objective validation, state-goal to protocol-goal
projection, set/get/clear response ordering, listener-command preferred
update/clear/snapshot delivery, fallback server notifications, preview update,
and running-thread external-goal mutation hooks. Concrete rollout
reconciliation, sqlite state persistence, and thread continuation execution
remain injected runtime boundaries.
Focused parity validation passed with 10 tests plus py_compile.
`src/request_processors/token_usage_replay.rs` is now mapped as a complete
child module after focused validation. Python preserves latest token-count
attribution through pre-replay active-turn snapshots, loaded-id preference
with rebuilt-position fallback, fallback turn-id selection, core
`TokenUsageInfo` to app-server v2 `ThreadTokenUsage` mapping, and
single-connection replay notification delivery. Conversation storage and
concrete outgoing transport remain injected dependency boundaries. Focused
parity validation passed on 2026-06-19 with
`tests/test_app_server_request_processors_token_usage_replay_rs.py` (8 passed)
plus `py_compile` for the Python module and parity test.
`src/request_processors/thread_lifecycle.rs` is now complete after focused
parity validation. Python preserves unload-delay timing,
listener attach result and shutdown result enums, missing-thread and
closing-thread invalid-request branches, closed-connection return, raw-event
subscription opt-in, listener replacement setup, request cancellation and
thread-state cleanup before unload, `ThreadClosed` notification delivery,
listener-command dispatch for resume, goal update/clear/snapshot, and
server-request resolution, plus active-turn merge and stale in-progress turn
interruption. The concrete Tokio listener select loop, bespoke event handling,
token usage replay, rollout IO, and live thread execution remain injected
runtime boundaries.
Focused parity validation passed with 7 tests plus py_compile.
`src/request_processors/thread_processor.rs` is now complete after focused
parity validation for its local helper/facade contract. Python
preserves the constructor dependency surface, resume override mismatch and
persisted metadata helpers, CWD filter normalization, dynamic tool
name/namespace validation, turns-list cursor serialization/parsing and
pagination, stale turn status normalization, active-turn merge, unsupported
thread-store operation errors, title-to-name updates, and project-trust
permission checks. Concrete thread creation/resume/fork/list/read/archive
execution, thread-store persistence, rollout IO, listener orchestration,
telemetry, and dynamic tool schema internals remain runtime/dependency
boundaries.
Focused parity validation passed with 9 tests plus py_compile.
`src/request_processors/turn_processor.rs` is now complete after focused
parity validation. Python preserves runtime workspace-root
resolution and dedupe, additional-context sorting and core-kind projection,
the constructor dependency surface, public request wrapper delegation, thread
load invalid-request errors, realtime builtin voice-list response, analytics
error forwarding, listener-task context projection, and the Xcode 26.4 MCP
elicitation auto-deny compatibility predicate. Concrete turn startup,
settings override construction, live thread execution, realtime session
control, review orchestration, and listener setup remain injected runtime
boundaries owned by neighboring modules.
Focused parity validation passed with 9 tests plus py_compile.
`src/thread_status.rs` is now complete. Python covers the app-server thread
watch manager state machine: loaded/not-loaded, active, idle, system-error,
pending approval/user-input active flags, running turn count, status
subscriptions, silent upsert behavior, status-changed notifications, and
`resolve_thread_status(...)` in-progress turn override. Exact Tokio
watch-channel receiver pruning, Drop-spawn guard release timing, and concrete
outgoing envelope/channel delivery remain runtime dependency boundaries.
Focused parity validation passed with 12 tests plus py_compile.
`src/thread_state.rs` is now complete after focused parity validation. Python
covers the app-server per-thread listener state, command queue shape,
generation/cancellation replacement behavior, active-turn history tracking,
thread-settings delta reporting, server-request resolution handoff,
connection subscription indexes, has-connection watcher notifications,
experimental raw-event flags, and first attestation-capable connection
selection. Exact Tokio channel scheduling, weak `Arc` pointer identity, concrete
`CodexThread` execution, and outgoing transport delivery remain dependency
boundaries.
Focused parity validation passed with 9 tests plus py_compile.
`src/in_process.rs` is now complete after focused parity validation. Python covers
the in-process app-server host's local control contract: start args and capacity
clamping, server-event/client-message/processor-command shapes, client queue
full/closed error mapping, initialize/initialized handshake projection,
duplicate request-id rejection, full/closed processor request handling,
server-request backpressure errors, guaranteed terminal notification delivery,
shutdown ack, and pending request error fan-out. Real Tokio task scheduling,
`MessageProcessor` execution, auth/config/state DB construction, outbound
routing execution, and concrete embedded runtime behavior remain dependency
boundaries.
Focused parity validation passed with 11 tests plus py_compile.
`src/outgoing_message.rs` is complete after focused parity validation. Python
covers the app-server outgoing coordinator's local memory contract: connection
request IDs, request context storage/cleanup, request ID allocation, pending
callback futures, broadcast and targeted request envelopes, client
response/error delivery to waiters, request cancellation, thread-scoped pending
request ordering, response/error routing to one connection, server notification
broadcast/targeted envelopes, and write-completion wait projection. Exact Tokio
channel/backpressure/tracing behavior, transport writer execution, protocol
serde decoding, and real analytics payloads remain dependency boundaries.
Focused validation passed on 2026-06-19 with
`tests/test_app_server_outgoing_message_rs.py` (10 passed) plus `py_compile`
for the Python module and parity test.
Unix socket startup-lock projection covers Rust's earlier pre-acceptor branch:
non-Unix transports skip it, while Unix socket computes and acquires the
app-server startup lock, prepares the control socket path, and stores the lock
only after every fallible step succeeds.
Remote-control startup projection covers Rust's local `start_remote_control`
argument assembly: ChatGPT base URL and installation ID config, state DB/auth
manager/transport token forwarding, optional stdio client-name receiver, enabled
flag propagation, accept-handle push, retained remote-control handle, and the
error path that returns before pushing the remote-control accept handle.
`run_main(...)` now mirrors Rust's default delegation projection into
`run_main_with_transport_options(...)`: stdio transport, VSCode session source,
default websocket auth settings, and default runtime options.
`run_main_with_transport_options(...)` now executes a crate-root
startup/finalization orchestration with injectable runtime hooks. The Python
projection preserves the Rust ordering for CLI override parsing, codex-home and
runtime-path setup, config manager/preload/load fallback, telemetry/state DB,
personality migration, warning accumulation, feedback/logging/log DB,
installation ID, transport and remote-control startup, outbound router and
message processor setup, and final transport/OpenTelemetry shutdown.
`src/server_request_error.rs` is now mapped to
`pycodex/app_server/server_request_error.py`: the `turnTransition` reason
constant and JSON-RPC error `data.reason` detector are represented for the
turn-state-transition server-request cancellation boundary used by outgoing
message handling.
`src/error_code.rs` is now mapped to `pycodex/app_server/error_code.py`:
the app-server JSON-RPC error code constants and fixed-code helper
constructors produce `JSONRPCErrorError` values with no data payload, matching
the local Rust utility contract consumed by command execution, request
processors, in-process handling, and outgoing-message paths.
`src/filters.rs` is now mapped to `pycodex/app_server/filters.py`: source-kind
filters are split into rollout-query allowed session sources versus app-server
post-filtering, and `ThreadSourceKind` matching is preserved for CLI, VSCode,
exec, app-server/MCP, sub-agent variants, and unknown sources.
`src/analytics_utils.rs` is now mapped to
`pycodex/app_server/analytics_utils.py`: app-server-owned analytics client
argument shaping preserves the auth manager handle, trims trailing slashes from
`chatgpt_base_url`, and forwards the `analytics_enabled` flag while leaving
analytics queue/runtime behavior to the `codex-analytics` crate.
`src/main.rs` is now mapped to `pycodex/app_server/main.py`: the app-server
binary startup wrapper preserves the CLI/env projection into
`run_main_with_transport_options(...)`, including the managed-config debug env
hooks, default empty CLI overrides, default analytics disabled, strict-config
forwarding, listen/session/auth/runtime option shaping, and the debug-only
plugin startup skip flag.
Focused validation passed on 2026-06-19:
`python -m pytest tests/test_app_server_main_rs.py -q` -> `8 passed`.
`src/attestation.rs` is now mapped to `pycodex/app_server/attestation.py`:
the module preserves Rust's attestation status wire codes, compact header
envelope shape, 100 ms timeout constant, and local request-result status
mapping while leaving the concrete provider, outgoing sender, thread-state
lookup, async timeout, JSON-RPC delivery, and HTTP header validation to runtime
dependencies.
`src/app_server_tracing.rs` is now mapped to
`pycodex/app_server/app_server_tracing.py`: request span projections preserve
Rust's `app_server.request` metadata fields, transport labels, initialize
client-info precedence, request-trace-before-env fallback behavior, and the
typed in-process request span shape while leaving real `tracing::Span` and
OpenTelemetry parent attachment to telemetry/runtime dependencies.

Concrete sibling-owned runtime effects behind `AppServerRuntimeHooks` remain
integration boundaries and are not duplicated in `pycodex.app_server_client`.
The real OS signal listener remains unimplemented unless waiters are injected.

Focused module validation passed on 2026-06-19:
`python -m pytest tests/test_app_server_lib_rs.py -q` -> `134 passed`.
