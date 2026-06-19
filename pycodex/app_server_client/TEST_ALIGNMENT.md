# codex-app-server-client test alignment

Rust crate: `codex-app-server-client`

Python package: `pycodex/app_server_client`

Status: `complete`

Complete modules:

- `codex/codex-rs/app-server-client/src/lib.rs`
  -> `pycodex/app_server_client/__init__.py`
- `codex/codex-rs/app-server-client/src/remote.rs`
  -> `pycodex/app_server_client/__init__.py`

Remaining Rust modules:

None. All known Rust modules are tracked and focused Python validation passes
for both modules.

Rust tests and fixtures for tracked modules:

- `src/lib.rs`
  - Source-contract coverage identified for `TypedRequestError` display/source
    behavior, lossless event classification, lag marker projection,
    initialize params, request method diagnostics, async request round trips,
    in-process event forwarding, runtime start args, and shutdown behavior.
- `src/remote.rs`
  - Source-contract coverage identified for remote endpoint/connect arguments,
    initialize params, auth-token URL policy, websocket frame/message config,
    UDS handshake URL, JSON-RPC request/notification projection, remote
    initialization, websocket/UDS round trips, server-request handling,
    backpressure, disconnect, and shutdown behavior.

Python parity coverage:

  - `tests/test_app_server_client_lib_rs.py`
  - `test_initialize_params_matches_rust_shape`
  - `test_shutdown_timeout_constant_matches_rust_module_boundary`
  - `test_in_process_runtime_dependency_projection_tracks_app_server_owner`
  - `test_in_process_worker_topology_projection_matches_rust_start_loop`
  - `test_in_process_worker_select_timing_projection_matches_unbiased_select_contract`
  - `test_in_process_worker_command_projection_matches_rust_match_branches`
  - `test_in_process_worker_event_projection_matches_rust_next_event_branch`
  - `test_in_process_command_channel_backpressure_projection_matches_rust_sender_boundary`
  - `test_in_process_command_entrypoint_projection_matches_rust_public_methods`
  - `test_in_process_request_response_projection_matches_rust_request_flow`
  - `test_in_process_worker_request_task_projection_matches_rust_detached_delivery`
  - `test_in_process_request_handle_projection_matches_rust_factory`
  - `test_in_process_next_event_projection_matches_rust_facade`
  - `test_in_process_shutdown_entrypoint_projection_matches_rust_method`
  - `test_in_process_shutdown_projection_returns_prompt_command_result`
  - `test_in_process_shutdown_projection_aborts_worker_after_timeout`
  - `test_in_process_client_command_projection_matches_rust_variants`
  - `test_default_in_process_channel_capacity_matches_rust_reexport`
  - `test_in_process_start_effective_channel_capacity_clamps_to_one`
  - `test_in_process_start_projects_runtime_args_and_effective_capacity`
  - `test_in_process_start_returns_empty_shutdownable_facade`
  - `test_in_process_start_request_uses_runtime_projection_bookkeeping`
  - `test_in_process_request_returns_runtime_projection_immediate_errors`
  - `test_in_process_start_request_handle_uses_runtime_projection_bookkeeping`
  - `test_in_process_start_notify_uses_runtime_projection_bookkeeping`
  - `test_in_process_start_server_request_response_uses_runtime_projection_bookkeeping`
  - `test_in_process_start_push_event_uses_runtime_projection_bookkeeping`
  - `test_legacy_core_reexports_existing_core_boundaries`
  - `test_app_server_control_socket_path_reexports_exec_session_policy`
  - `test_crate_root_reexports_existing_state_and_exec_server_types`
  - `test_runtime_start_args_forward_environment_manager`
  - `test_runtime_start_args_forward_and_clone_startup_fields`
  - `test_runtime_start_args_clone_initialize_opt_out_methods`
  - `test_runtime_start_args_use_noop_thread_config_loader_by_default`
  - `test_runtime_start_args_use_remote_thread_config_loader_when_configured`
  - `test_into_app_server_in_process_start_args_preserves_runtime_handoff_fields`
  - `test_typed_request_error_messages_match_rust_display`
  - `test_typed_request_error_exposes_sources`
  - `test_in_process_event_projection_matches_rust_from_impl`
  - `test_next_event_surfaces_lagged_markers`
  - `test_event_requires_delivery_marks_transcript_and_terminal_events`
  - `test_project_in_process_event_forwarding_preserves_lossless_order`
  - `test_project_in_process_event_forwarding_accumulates_skipped_best_effort_events`
  - `test_project_in_process_event_forwarding_flushes_existing_skipped_before_best_effort`
  - `test_project_in_process_event_forwarding_rejects_dropped_server_requests`
  - `test_project_in_process_event_forwarding_marks_closed_consumer_disabled`
  - `test_in_process_chatgpt_auth_refresh_request_is_rejected_not_delivered`
  - `test_request_method_name_uses_client_request_method`
  - `test_in_process_request_handle_delegates_to_client_request`
  - `test_in_process_request_handles_share_client_channel`
  - `test_in_process_request_handle_observes_client_shutdown`
  - `test_in_process_request_handle_typed_wraps_server_and_decode_errors`
  - `test_in_process_request_observes_client_shutdown`
  - `test_in_process_request_typed_wraps_transport_errors`
  - `test_in_process_request_typed_wraps_server_and_decode_errors`
  - `test_in_process_notify_resolve_reject_next_event_and_shutdown`
  - `test_in_process_closed_command_errors_use_rust_channel_names`
  - `test_shutdown_completes_promptly_without_retained_managers`
  - `test_app_server_client_next_event_converts_in_process_events`
  - `test_app_server_client_and_request_handle_forward_in_process_methods`
  - `test_app_server_client_and_request_handle_forward_remote_methods`
- `tests/test_app_server_client_remote_rs.py`
  - `test_remote_connect_args_initialize_params_match_rust_shape`
  - `test_remote_connect_endpoint_projection_matches_rust_connectors`
  - `test_remote_connect_dispatch_projection_matches_rust_connect`
  - `test_remote_connect_with_stream_projection_matches_rust_lifecycle`
  - `test_remote_client_command_projection_matches_rust_variants`
  - `test_remote_command_entrypoint_projection_matches_rust_public_methods`
  - `test_remote_worker_command_projection_matches_rust_match_branches`
  - `test_remote_worker_select_loop_projection_matches_rust_topology`
  - `test_remote_worker_stream_message_projection_matches_rust_match_branches`
  - `test_remote_worker_command_channel_closed_projection_matches_rust_branch`
  - `test_remote_channel_topology_projection_matches_rust_worker_setup`
  - `test_remote_worker_timing_boundary_projection_matches_current_python_boundary`
  - `test_remote_deliver_event_projection_matches_rust_helper`
  - `test_remote_next_event_projection_matches_rust_pending_event_order`
  - `test_remote_websocket_close_error_projection_matches_rust_helper`
  - `test_remote_write_jsonrpc_message_projection_matches_rust_helper`
  - `test_remote_server_version_from_user_agent_matches_rust_initialize_parse`
  - `test_remote_initialize_close_frame_error_message_matches_rust_branch`
  - `test_remote_initialize_error_message_matches_rust_branches`
  - `test_remote_initialize_handshake_projection_matches_rust_sequence`
  - `test_remote_initialize_frame_projection_matches_rust_loop_branches`
  - `test_remote_runtime_close_frame_disconnected_message_matches_rust_branch`
  - `test_remote_runtime_eof_disconnected_message_matches_rust_branch`
  - `test_remote_runtime_invalid_jsonrpc_disconnected_message_matches_rust_branch`
  - `test_remote_runtime_transport_failure_disconnected_message_matches_rust_branch`
  - `test_remote_websocket_connect_error_message_matches_rust_branches`
  - `test_remote_unsupported_server_request_error_message_matches_rust_branch`
  - `test_remote_write_failed_disconnected_message_matches_rust_branch`
  - `test_remote_shutdown_close_failed_error_message_matches_rust_branch`
  - `test_remote_worker_exit_pending_requests_projection_matches_rust_branch`
  - `test_remote_shutdown_projection_matches_rust_control_flow`
  - `test_remote_duplicate_request_id_error_message_matches_rust_branch`
  - `test_remote_endpoint_shape_validation_and_effective_channel_capacity`
  - `test_remote_auth_token_transport_policy_allows_wss_and_loopback_ws`
  - `test_remote_constants_and_websocket_config_match_rust`
  - `test_jsonrpc_request_projection_matches_client_request`
  - `test_jsonrpc_request_projection_accepts_jsonrpc_mapping`
  - `test_jsonrpc_notification_projection_matches_client_notification`
  - `test_jsonrpc_notification_projection_accepts_jsonrpc_mapping`
  - `test_remote_jsonrpc_projection_panic_message_matches_rust_helpers`
  - `test_remote_app_server_event_from_notification_filters_like_rust`
  - `test_remote_request_handle_projection_matches_rust_factory`
  - `test_remote_request_handle_delegates_and_reports_server_version`
  - `test_remote_notify_resolve_reject_next_event_and_shutdown`
  - `test_remote_shutdown_tolerates_worker_closed_after_command_is_queued`
  - `test_remote_connect_reuses_exec_session_wire_client_for_requests`
  - `test_remote_connect_ignores_malformed_initialize_user_agent_version`
  - `test_remote_connect_ignores_blank_initialize_user_agent_version`
  - `test_remote_connected_request_handle_routes_over_wire_client`
  - `test_remote_connect_preserves_initialize_pending_events`
  - `test_remote_connect_initialize_server_request_resolution_roundtrip`
  - `test_remote_connect_ignores_non_initialize_responses_during_initialize`
  - `test_remote_connect_ignores_non_text_frames_during_initialize`
  - `test_remote_connect_maps_initialize_error_to_os_error`
  - `test_remote_connect_maps_initialize_close_frame_to_os_error`
  - `test_remote_connect_maps_initialize_eof_to_os_error`
  - `test_remote_connect_maps_initialize_transport_failure_to_os_error`
  - `test_remote_connect_maps_initialize_timeout_to_os_error`
  - `test_remote_connect_maps_invalid_initialize_jsonrpc_to_os_error`
  - `test_remote_connect_maps_initialize_write_failure_to_os_error`
  - `test_remote_connect_maps_initialized_notification_write_failure_to_os_error`
  - `test_remote_connect_rejects_unknown_initialize_server_request`
  - `test_remote_connect_unix_socket_uses_uds_handshake_url`
  - `test_remote_unix_socket_typed_request_roundtrip`
  - `test_remote_connect_maps_unix_socket_connector_failure_to_os_error`
  - `test_remote_connect_maps_unix_socket_connector_timeout_to_os_error`
  - `test_remote_connect_maps_unix_socket_connector_invalid_input_to_os_error`
  - `test_remote_unix_socket_connect_error_message_matches_rust_branches`
  - `test_remote_connect_rejects_non_loopback_ws_auth_before_connector`
  - `test_remote_connect_rejects_invalid_websocket_url_before_connector`
  - `test_remote_connect_forwards_safe_websocket_auth_token_to_connector`
  - `test_remote_connect_forwards_loopback_websocket_auth_token_to_connector`
  - `test_remote_connect_rejects_invalid_authorization_header_before_connector`
  - `test_remote_connect_maps_connector_timeout_to_os_error`
  - `test_remote_connect_maps_connector_failure_to_os_error`
  - `test_remote_connect_maps_connector_invalid_input_to_os_error`
  - `test_remote_wire_client_notifies_resolves_rejects_and_streams_events`
  - `test_remote_wire_notify_write_failure_maps_to_os_error`
  - `test_remote_wire_server_request_response_write_failure_maps_to_os_error`
  - `test_remote_wire_ignores_non_text_websocket_frames`
  - `test_remote_wire_invalid_jsonrpc_text_streams_disconnected_event`
  - `test_remote_wire_close_frame_streams_disconnected_event`
  - `test_remote_wire_disconnect_surfaces_as_event_with_default_close_message`
  - `test_remote_wire_eof_streams_closed_connection_event`
  - `test_remote_wire_transport_failure_streams_disconnected_event`
  - `test_remote_wire_unknown_server_notification_is_ignored`
  - `test_remote_wire_account_updated_notification_arrives_over_websocket`
  - `test_remote_wire_transcript_notifications_stream_in_order`
  - `test_remote_wire_supported_server_request_streams_event`
  - `test_remote_wire_server_request_resolution_roundtrip`
  - `test_remote_wire_unknown_server_request_is_rejected`
  - `test_remote_wire_thread_unknown_server_request_is_rejected`
  - `test_remote_wire_unknown_server_request_reject_write_failure_streams_disconnected_event`
  - `test_remote_wire_request_error_maps_to_typed_request_error`
  - `test_remote_wire_request_preserves_interleaved_notification_event`
  - `test_remote_wire_request_ignores_interleaved_unknown_notification`
  - `test_remote_wire_request_preserves_interleaved_server_request_event`
  - `test_remote_wire_request_rejects_interleaved_unknown_server_request`
  - `test_remote_wire_request_typed_decodes_response_or_reports_deserialize_error`
  - `test_remote_wire_typed_request_roundtrip_get_account`
  - `test_remote_wire_request_typed_accepts_large_single_frame_response`
  - `test_remote_wire_request_typed_transport_error_maps_to_typed_error`
  - `test_remote_wire_request_write_failure_maps_to_os_error_and_disconnect_event`
  - `test_remote_wire_duplicate_request_id_maps_to_transport_error`
  - `test_remote_wire_request_disconnect_maps_to_os_error_and_disconnect_event`
  - `test_remote_wire_request_transport_failure_maps_to_os_error_and_disconnect_event`
  - `test_remote_wire_request_close_frame_maps_to_os_error_and_disconnect_event`
  - `test_remote_wire_request_invalid_jsonrpc_maps_to_os_error_and_disconnect_event`
  - `test_remote_shutdown_maps_close_error_to_os_error`
  - `test_remote_shutdown_tolerates_already_closed_close_error`
  - `test_remote_shutdown_tolerates_connection_reset_close_error_from_wire_client`

Known gaps:

- 2026-06-19 complete-candidate audit: `src/lib.rs` no longer has a tracked
  local facade/source-contract blocker. Concrete MessageProcessor success
  response production and exact live Tokio scheduling/backpressure observations
  are treated as embedded app-server collaboration and crate-level validation
  evidence, not as another client-module implementation gap.
- 2026-06-19 `src/lib.rs` validation: `python -m pytest
  tests/test_app_server_client_lib_rs.py -q` passed (`61 passed`). Combined
  crate validation initially exposed `src/remote.rs` failures; those are now
  corrected.
- 2026-06-19 `src/remote.rs` validation: `python -m pytest
  tests/test_app_server_client_remote_rs.py -q` passed (`127 passed`). Combined
  crate validation also passed with `python -m pytest
  tests/test_app_server_client_lib_rs.py tests/test_app_server_client_remote_rs.py
  -q` (`188 passed`).
- Initialize-params tests cover Rust's `InProcessClientStartArgs::initialize_params`
  client info and capabilities shape, including empty opt-out notification
  methods becoming `None` and non-empty opt-out methods being cloned into the
  initialize params.
- Legacy-core tests cover Rust's crate-root `pub mod legacy_core` bridge by
  re-exporting existing `pycodex.core` symbols and submodules from
  `pycodex.app_server_client.legacy_core`.
- Crate-root path tests cover Rust's `app_server_control_socket_path`
  re-export by delegating to the already-ported `pycodex.exec.session`
  socket-path policy.
- Crate-root type tests cover Rust's re-exported `StateDbHandle`,
  `EnvironmentManager`, and `ExecServerRuntimePaths` boundaries by aliasing the
  existing `pycodex.core.state_db_bridge` and `pycodex.exec_server` types.
- Default channel-capacity tests cover Rust's crate-root
  `DEFAULT_IN_PROCESS_CHANNEL_CAPACITY` re-export and the Python
  `InProcessClientStartArgs` default/runtime-start projection that depends on
  it.
- Shutdown-timeout tests cover Rust's crate-root
  `SHUTDOWN_TIMEOUT = Duration::from_secs(5)` constant boundary without
  claiming the embedded worker timeout path is implemented.
- Shutdown projection tests cover Rust's local
  `InProcessAppServerClient::shutdown` timeout/abort-fallback control flow,
  including dropping the caller-facing event receiver before sending shutdown,
  without claiming exact Tokio worker execution is implemented.
- Client-command projection tests cover the internal Rust `ClientCommand`
  variant shape and the oneshot-response boundary without claiming worker
  scheduling behavior.
- In-process worker command projection tests cover the Rust worker-side
  `ClientCommand` match branch skeleton: request commands clone the request
  sender and spawn a detached request task, notify/resolve/reject commands use
  the corresponding handle methods, shutdown sends the `handle.shutdown()`
  result and breaks, and a closed command channel shuts the handle down before
  breaking. They do not execute the embedded runtime worker.
- In-process worker event projection tests cover the Rust worker-side
  `handle.next_event()` branch skeleton: runtime event-stream end breaks the
  worker, unsupported `ChatgptAuthTokensRefresh` server requests are rejected
  with JSON-RPC code `-32000` and not forwarded, forwarded events consume the
  existing `forward_in_process_event(...)` contract, and `DisableStream`
  disables the event arm without claiming exact Tokio scheduling.
- In-process command entrypoint projection tests cover the Rust public
  `request`, `notify`, `resolve_server_request`, and `reject_server_request`
  send/response skeleton: each method sends the matching `ClientCommand`,
  owns a response oneshot, shares the worker-send BrokenPipe text, and uses the
  operation-specific response-channel BrokenPipe text.
- In-process command-channel backpressure projection tests cover the Rust
  bounded `mpsc::channel<ClientCommand>` sender contract from
  `InProcessAppServerClient::start(...)`: capacity is
  `channel_capacity.max(1)`, sends wait for receiver progress when the channel
  is full, and only worker receiver closure maps to the shared
  `in-process app-server worker channel is closed` BrokenPipe text. They also
  record that the event channel is separately bounded and event-side
  backpressure is handled by `forward_in_process_event(...)`.
- In-process request-handle projection tests cover
  `InProcessAppServerClient::request_handle()`: the factory clones the command
  sender, handle requests send boxed `ClientCommand::Request` values with a
  response oneshot, and handle typed requests share the direct client
  transport/server/deserialize wrapping semantics.
- In-process next-event projection tests cover
  `InProcessAppServerClient::next_event()`: the facade awaits
  `event_rx.recv()`, returns `Option<InProcessServerEvent>`, preserves
  in-process event variants, and leaves `AppServerEvent` conversion to the
  wrapper facade.
- In-process shutdown entrypoint projection tests cover the Rust public
  `shutdown(self)` skeleton: consume and destructure the client, drop the
  caller-facing event receiver before sending `ClientCommand::Shutdown`, ignore
  worker-send failure and response timeout, and only propagate an in-time
  command result.
- Effective in-process channel-capacity tests cover Rust's
  `InProcessAppServerClient::start` facade rule that clamps queue capacity with
  `channel_capacity.max(1)` while leaving runtime-start argument projection as
  the caller-provided value. The lightweight Python `start(...)` compatibility
  layer also materializes `into_runtime_start_args()` and records the effective
  queue capacity, without claiming the embedded runtime worker is complete.
  On 2026-06-19 the returned facade stopped being a disconnected shell:
  `start(...)` now attaches the app-server-owned `InProcessRuntimeProjection`,
  so notifications, server-request responses/rejections, event injection, and
  request-acceptance bookkeeping are live. Accepted client requests report a
  pending-response JSON-RPC error instead of fabricating a MessageProcessor
  result that this client crate does not own.
- In-process request immediate-error tests cover the Rust raw `RequestResult`
  boundary for runtime-produced errors before concrete response delivery:
  duplicate in-flight request IDs return `INVALID_REQUEST`, full processor
  queues return `OVERLOADED`, and a closed request processor returns
  `INTERNAL_ERROR`. This proves client `request(...)` propagates runtime
  errors without claiming successful MessageProcessor result production.
- In-process worker-topology projection tests cover Rust's
  `InProcessAppServerClient::start(...)` setup shape: bounded command and
  event channels, the runtime handle sender, owned worker handle, initial
  event-stream/skipped-event state, and the two select arms. They do not
  execute Tokio scheduling or the embedded runtime.
- In-process worker select-timing projection tests cover the Rust worker loop's
  unbiased `tokio::select!` ready-set boundary: command input is always
  enabled, the runtime event arm is disabled when `event_stream_enabled` is
  false, single ready enabled arms are deterministic, and simultaneous command
  plus event readiness has no stable branch-order contract. They do not execute
  the Tokio scheduler or embedded runtime.
- `src/lib.rs` named-test audit:
  - Covered at the Python facade/source-contract boundary:
    `typed_request_error_exposes_sources`,
    `next_event_surfaces_lagged_markers`,
    `event_requires_delivery_marks_transcript_and_terminal_events`,
    `runtime_start_args_forward_environment_manager`,
    `runtime_start_args_use_remote_thread_config_loader_when_configured`, and
    `shutdown_completes_promptly_without_retained_managers`.
  - Deferred until embedded runtime/backpressure exists:
    `typed_request_roundtrip_works`,
    `typed_request_reports_json_rpc_errors`,
    `caller_provided_session_source_is_applied`,
    `threads_started_via_app_server_are_visible_through_typed_requests`,
    `tiny_channel_capacity_still_supports_request_roundtrip`, and
    `forward_in_process_event_preserves_transcript_notifications_under_backpressure`.
  - 2026-06-18 residual audit: remaining `src/lib.rs` named-test debt is
    runtime/backpressure-owned; the pure facade/source-contract surface is
    tracked above to avoid repeatedly adding overlapping lightweight tests.
  - 2026-06-18 post-start-facade audit: the lightweight
    `InProcessAppServerClient.start(...)` compatibility surface now covers
    argument/effective-capacity projection, empty lifecycle/shutdown, direct
    request, request-handle, notification, server-request response, and
    event-injection boundaries. Further `src/lib.rs` work should target the
    embedded runtime worker rather than additional start-facade-only tests.
  - 2026-06-19 start runtime-projection test update: the old
    `*_remains_unimplemented_without_runtime` start tests were replaced with
    runtime-projection-backed assertions for direct requests, cloned request
    handles, notifications, server-request responses/rejections, and event
    injection. These tests prove the client crate no longer exposes
    disconnected start shells while still avoiding fabricated MessageProcessor
    responses.
  - 2026-06-19 immediate-error propagation: direct request tests now cover raw
    runtime-projection request errors for duplicate IDs, full processor queues,
    and closed processors. Successful roundtrip response production remains
    owned by the embedded runtime/MessageProcessor path.
  - 2026-06-18 runtime dependency handoff: Rust
    `InProcessAppServerClient::start(...)` obtains true runtime behavior by
    calling `codex_app_server::in_process::start(...)`. Python now has a
    partial `pycodex.app_server` runtime owner plus an explicit
    `InProcessStartArgs` handoff projection, so the deferred startup,
    roundtrip, event-streaming, and backpressure tests should remain blocked on
    that runtime owner or a deliberate compatibility shim, not duplicated in
    `app_server_client`.
  - 2026-06-18 post-public-facade residual audit: all currently identified
    pure `src/lib.rs` facade/source-contract anchors are tracked above,
    including worker topology, worker command/event branches, public command
    entrypoints, request-handle factory, `next_event()`, and shutdown
    entrypoint. Remaining named-test debt continues to require embedded
    runtime/backpressure support.
- Typed request error tests cover Rust's
  `typed_request_error_exposes_sources`: transport and deserialize errors
  expose chained Python causes, while JSON-RPC server errors remain
  method-qualified display errors without an exception cause. Server error
  `data` uses Rust's compact JSON `serde_json::Value` display style.
- In-process typed request tests cover the Rust
  `InProcessAppServerClient::request_typed` transport wrapper boundary:
  request-path `OSError`s and request-channel closure after client shutdown
  become method-qualified `TypedRequestError.transport(...)` errors.
- In-process request-handle tests cover Rust's cloned command-sender boundary:
  request handles forward through the same client channel and observe the same
  request-channel closure after client shutdown. Multiple Python handles from
  one client are covered as the observable equivalent of Rust's cloned
  `InProcessAppServerRequestHandle` values sharing one command sender. Handle
  typed requests also cover the Rust server/decode wrapper boundary.
- In-process typed request tests also cover the Rust server/decode wrapper
  boundary: JSON-RPC error results become method-qualified
  `TypedRequestError.server(...)` errors, and optional Python decoder failures
  stand in for Rust `serde_json::from_value(...)` failures as
  `TypedRequestError.deserialize(...)`.
- In-process command-channel tests cover Rust's closed-channel error text for
  `notify`, `resolve_server_request`, and `reject_server_request`, including
  the shorter Rust channel names `notify`, `resolve`, and `reject`.
- In-process request response projection tests cover the Rust
  `InProcessAppServerClient::request(...)` raw response boundary: boxed
  `ClientCommand::Request`, response oneshot creation/waiting, raw
  `RequestResult` return, worker-channel closure, request-response-channel
  closure, and the typed wrapper split for transport/server/deserialize
  layers.
- In-process worker request task projection tests cover the Rust worker-side
  detached task that clones `request_sender`, moves the boxed request, awaits
  `request_sender.request(*request).await`, sends the raw `RequestResult` into
  the response oneshot, ignores dropped response receivers, and allows the
  worker loop to keep draining runtime events while the request waits. They do
  not claim concrete MessageProcessor result production.
- In-process command-channel backpressure tests cover bounded sender capacity
  and failure semantics without claiming concrete Tokio wakeup scheduling under
  live runtime load.
- In-process worker select-timing tests cover the pure local `tokio::select!`
  guard and ready-set semantics without claiming concrete worker scheduling,
  bounded-channel wakeup timing, or MessageProcessor response delivery.
- In-process unsupported server-request tests cover Rust's worker branch that
  rejects `ChatgptAuthTokensRefresh` requests with JSON-RPC code `-32000`
  instead of delivering them to in-process clients.
- In-process event-forwarding projection tests cover the non-Tokio observable
  contract from Rust's
  `forward_in_process_event_preserves_transcript_notifications_under_backpressure`:
  best-effort events dropped while full become skipped counts, the next
  lossless transcript/completion notification is preceded by a `Lagged` marker,
  repeated best-effort drops accumulate into a single `Lagged { skipped: N }`
  marker, an existing skipped counter is flushed before a later best-effort
  event when capacity is available, dropped server requests are rejected with
  JSON-RPC code `-32001`, healthy forwarding is projected as Rust
  `ForwardEventResult::Continue`, and closed consumer channels are projected as
  Rust `ForwardEventResult::DisableStream`.
- Request-method diagnostics cover Rust's `request_method_name(...)` helper:
  known JSON-RPC method shapes are preserved and unrecognized request shapes
  fall back to `"<unknown>"`.
- Wrapper facade tests cover Rust's `AppServerClient` and
  `AppServerRequestHandle` enum-dispatch boundary for in-process request,
  typed request with decode, notify, resolve, reject, next-event conversion,
  request-handle forwarding, and shutdown forwarding. They also cover the
  crate-root remote variant dispatch at the wrapper boundary without expanding
  this module's scope into `src/remote.rs` transport internals.
- Runtime start-argument tests cover Rust's
  `runtime_start_args_forward_environment_manager` projection boundary for the
  currently ported fields, including preserving supplied config and
  environment-manager objects, generated initialize params, and channel
  capacity.
- Runtime dependency projection tests cover the Rust
  `InProcessAppServerClient::start(...)` ownership boundary: the client crate
  projects arguments and hands true embedded behavior to `codex-app-server`;
  the Python runtime owner is `pycodex.app_server`, which remains partial.
- Runtime start-argument tests also cover Rust's broader
  `InProcessClientStartArgs::into_runtime_start_args` field projection for
  arg0 paths, CLI overrides, loader overrides, strict config, cloud
  requirements, feedback, log DB, state DB, config warnings, session source,
  and `CODEX_API_KEY` env opt-in. Python list-backed startup fields are cloned
  into runtime args so later caller mutation does not rewrite the projected
  payload. The initialize params embedded in runtime args also carry cloned
  opt-out notification method lists.
- Runtime start-argument tests also cover Rust's
  `runtime_start_args_use_remote_thread_config_loader_when_configured` by
  selecting a `RemoteThreadConfigLoader` when the config carries
  `experimental_thread_config_endpoint`, and observing the expected
  `RequestFailed` load error from the lightweight remote loader shim.
- Runtime start-argument tests also cover the default
  `configured_thread_config_loader(...)` branch: configs without
  `experimental_thread_config_endpoint` use `NoopThreadConfigLoader` and
  produce no thread config sources.
- In-process event tests cover Rust's `next_event_surfaces_lagged_markers`:
  queued lagged markers are returned intact by the stateful facade.
- App-server event shape tests cover Rust's public `AppServerEvent` variants:
  lagged markers, server notifications, server requests, and disconnected
  message events.
- In-process shutdown tests cover Rust's
  `shutdown_completes_promptly_without_retained_managers`: the lightweight
  Python facade shutdown completes under a short timeout and subsequent event
  reads observe the closed channel state.
- `RemoteAppServerClient.connect(...)` now bridges to the existing
  `pycodex.exec.session` remote wire client instead of duplicating the
  websocket state machine in this package.
- Remote auth-token URL policy now reuses the existing `pycodex.exec.session`
  Rust-aligned helper instead of carrying a second loopback implementation.
  The helper coverage is anchored to Rust's
  `remote_auth_token_transport_policy_allows_wss_and_loopback_ws`, with a few
  additional URL-shape regressions.
- Remote endpoint variants validate mutually exclusive fields, and connect args
  expose the Rust `channel_capacity.max(1)` effective-capacity behavior.
- Remote client-command projection tests cover the internal Rust
  `RemoteClientCommand` variant shape and the oneshot-response boundary without
  claiming worker scheduling behavior.
- Remote JSON-RPC projection panic-message tests cover the Rust serde helper
  diagnostics for request/notification serialize and JSON-RPC encode failures.
- Remote event-delivery projection tests cover Rust's `deliver_event(...)`
  helper: open consumers receive the event, while closed consumers map to
  `BrokenPipe` with the fixed remote event consumer channel error.
- Remote next-event projection tests cover
  `RemoteAppServerClient::next_event(...)`: `pending_events.pop_front()` wins
  before the runtime event receiver is awaited.
- Remote websocket close-error helper tests cover Rust's
  `websocket_close_error_is_already_closed(...)` branches for already-closed
  tokens and BrokenPipe/ConnectionReset/not-connected I/O errors, plus the
  unrelated transport-error negative case.
- Remote JSON-RPC write helper tests cover Rust's `write_jsonrpc_message(...)`
  boundary: compact lite JSON-RPC text serialization and endpoint-qualified
  websocket write-failure error text.
- Remote server-version parsing tests cover Rust's initialize `userAgent`
  helper boundary: split after `/`, take the first whitespace-delimited token,
  and ignore missing or blank versions.
- Remote initialize close-frame helper tests cover Rust's close branch reason
  mapping: non-empty close reasons are preserved and empty/missing reasons
  default to `connection closed during initialize`.
- Remote wire request tests cover Rust's `RequestResult` split: JSON-RPC errors
  become typed server errors, `request_typed(...)` transport failures become
  typed transport errors, decoder failures become typed deserialize errors,
  Rust's `remote_typed_request_roundtrip_works` websocket `account/read`
  roundtrip decodes the account response and preserves initialize
  `userAgent` server-version extraction, and large single-frame typed
  responses can be decoded while ignoring extra fields.
- Remote request/notification/server-request response tests cover write
  failures surfacing as transport errors, including the request write-failure
  companion disconnected event.
- Duplicate pending request id tests cover Rust's
  `remote_duplicate_request_id_keeps_original_waiter` typed `account/read`
  path: the pre-write `InvalidInput` guard maps to a typed transport error,
  no duplicate frame is written, and the original pending waiter is preserved.
  The pure duplicate request-id helper test separately locks the
  request-id-qualified error message without exercising the worker.
- Remote shutdown tests cover non-already-closed websocket close errors
  surfacing as transport errors, already-closed websocket close errors being
  tolerated, direct wire-client `ConnectionResetError` close failures being
  tolerated through the Rust-aligned close-error helper, and the Rust
  worker-exit-after-shutdown-command tolerance path. The pure shutdown
  close-failure helper test separately locks the endpoint-qualified
  `failed to close websocket app server ...` text without exercising the worker.
  The shutdown projection test separately locks Rust's control-flow ordering:
  drop event receiver, send shutdown command, optionally propagate an in-time
  close result, then wait for/abort the worker.
- Remote worker-exit projection tests cover the Rust loop tail that fans the
  stored worker exit error out to all remaining pending request waiters, including
  the default BrokenPipe/`remote app-server worker channel is closed`
  `unwrap_or_else` fallback and the explicit stored-error branch.
- Remote command-closure tests cover Rust's `command_tx.send(...)` failure
  mapping for request, notify, resolve, and reject entrypoints, preserving the
  `remote app-server worker channel is closed` I/O-style error.
- Remote command response-channel closure tests cover Rust's `response_rx.await`
  failure mappings for request, notify, resolve, and reject entrypoints,
  preserving the operation-specific channel-closed I/O-style errors.
- Remote connect bridge tests cover Unix socket handshake URL forwarding,
  `remote_unix_socket_typed_request_roundtrip_works` typed request behavior,
  Unix socket connector timeout/failure/invalid-input mapping, unsafe
  auth-token URL rejection via Rust's
  `remote_connect_rejects_non_loopback_ws_when_auth_configured` pre-connector
  boundary, invalid websocket URL rejection, supported `wss://` and loopback
  `ws://` auth-token connector forwarding, invalid
  authorization header rejection, connector timeout error mapping, connector
  invalid-input mapping, generic connector-failure error mapping, and
  forwarding `channel_capacity.max(1)` as the shared wire client's command
  channel capacity.
- Remote websocket connect error helper tests cover Rust
  `connect_websocket_endpoint(...)` message shapes for invalid URLs, unsafe
  auth-token URLs, connector timeouts, and generic connector failures without
  invoking a connector.
- Remote Unix socket connect error helper tests cover Rust
  `connect_unix_socket_endpoint(...)` message shapes for invalid UDS handshake
  URLs, Unix socket connect timeouts/failures, and websocket upgrade
  timeouts/failures without opening a socket.
- Remote connector setup projection tests cover Rust's websocket and Unix
  connector control-flow shape: request construction, auth header insertion,
  rustls provider setup for websocket connections, shared websocket config,
  connect timeouts, Unix socket connect, and upgrade function selection without
  opening a socket.
- Remote connect dispatch projection tests cover
  `RemoteAppServerClient::connect(...)`: endpoint-variant connector selection,
  `channel_capacity.max(1)`, initialize-param construction before connecting,
  and forwarding into `connect_with_stream(...)`.
- Remote connect-with-stream lifecycle projection tests cover the Rust private
  setup order: initialize the stream first, then create command/event channels,
  convert pending events to `VecDeque`, store server version, spawn the worker,
  and return the worker-backed client without executing Tokio scheduling.
- Remote channel topology projection tests cover the Rust `connect_with_stream`
  worker setup shape: bounded `RemoteClientCommand` command channel, unbounded
  `AppServerEvent` event channel, `VecDeque` pending-event storage, and
  pending-request `HashMap`, without claiming Tokio wakeup timing.
- Remote worker timing-boundary projection tests record the current Python
  boundary for Rust's remaining worker semantics: bounded command-channel
  backpressure and branch wakeup timing remain Tokio-owned, the Python client
  delegates websocket wire state to `pycodex.exec.session`, and remote events
  remain unbounded with no remote `Lagged` synthesis.
- Remote worker select-timing projection tests cover the Rust worker's
  unbiased `tokio::select!` timing contract: no ready branch awaits progress,
  a single ready branch is selected deterministically, and simultaneous
  command/websocket readiness has no stable branch-order guarantee.
- Remote command-channel backpressure projection coverage now anchors the
  Rust `mpsc::channel<RemoteClientCommand>` capacity shape separately from
  Tokio scheduling: `channel_capacity.max(1)`, already-queued command count,
  full-channel sends waiting for receiver capacity, worker-receiver closure as
  the send-error condition, and the separate unbounded remote event channel.
- Remote request-handle tests cover connected handles routing requests through
  the delegated wire client path and preserving request-path closure errors.
  Projection coverage anchors `RemoteAppServerClient::request_handle(...)` as a
  cloned command-sender factory that does not own event receiver or server
  version state. The same request-handle area also covers typed transport
  wrapping for request response-channel closure and the handle
  `request_typed(...)` server and deserialize error wrappers.
- Remote initialize tests cover pre-response pending notification/server-request
  queueing, non-matching response/error ignoring while waiting for initialize,
  non-text websocket frame ignoring, matching initialize-error rejection
  mapping, initialize close-frame error mapping, initialize non-close error-text
  projection, initialize EOF error mapping, initialize transport-failure error
  mapping, initialize timeout error mapping, initialize invalid-response error
  mapping, initialize handshake write/wait sequence projection,
  initialize frame-handling projection,
  initialize request write-failure error mapping,
  initialized-notification write-failure error mapping, and
  unknown initialize-time server-request rejection. They also cover the Rust
  `remote_server_request_received_during_initialize_is_delivered` roundtrip:
  a queued initialize-time server request can be resolved after connect with a
  matching JSON-RPC response id.
- Remote connect tests cover initialize `userAgent` parsing into
  `RemoteAppServerClient.server_version()`, including leaving it unset for
  malformed or whitespace-only user-agent values without a non-empty version
  segment.
- Remote incoming request tests cover supported server-request event streaming
  and unsupported method rejection with JSON-RPC `-32601`, including the reject
  write-failure disconnected event, while later events continue to stream.
  They include Rust's concrete `remote_unknown_server_request_is_rejected`
  `thread/unknown` method and message shape.
- Remote server-request roundtrip tests cover the Rust
  `remote_server_request_resolution_roundtrip_works` path: a supported request
  arriving over the websocket is surfaced as an event, and
  `resolve_server_request(...)` writes a matching JSON-RPC response id.
- Remote interleaving tests cover supported server-request events arriving
  while a request is pending before its response arrives, plus unknown
  server-request rejection in the same pending window. The pure unsupported
  server-request helper test separately locks the method-qualified JSON-RPC
  error message.
- Remote incoming notification tests cover the Rust
  `remote_notifications_arrive_over_websocket` account-updated delivery case,
  known notification event streaming, the transcript notification sequence used
  by Rust's remote backpressure test, and unknown notification ignoring via the
  app-server-protocol registry, both through the helper boundary, while later
  events continue to stream, and while a request is pending before its response
  arrives. Exact Tokio bounded command-channel worker timing remains a known
  gap; `src/remote.rs` uses an unbounded event channel, so remote `Lagged`
  synthesis is not a separate module target here.
- Remote websocket frame tests cover Rust's Binary/Ping/Pong/Frame skip branch
  by confirming non-text frames do not block later JSON-RPC events.
- Remote invalid JSON-RPC tests cover Rust's runtime invalid-message branch by
  surfacing a disconnected event, including the pending-request split where the
  request reports an I/O error and the companion event remains queued. The pure
  invalid-message helper test separately locks the endpoint-qualified
  disconnected-event text without exercising the worker.
- Remote close-frame tests cover Rust's runtime websocket close branch by
  surfacing a disconnected event with explicit close reasons and the default
  `connection closed` reason. The default-close case is anchored to Rust's
  `remote_disconnect_surfaces_as_event`; pending-request split coverage
  verifies the request reports an I/O error and the companion event remains
  queued. The pure close-frame helper test separately locks the runtime branch
  reason/default message without exercising the worker.
- Remote EOF tests cover Rust's runtime closed-connection branch by surfacing a
  disconnected event, including the pending-request split where the request
  reports an I/O error and the companion event remains queued. The pure EOF
  helper test separately locks the fixed disconnected-event text without
  exercising the worker.
- Remote transport-failure tests cover Rust's runtime transport error branch by
  surfacing a disconnected event, including the pending-request split where the
  request reports an I/O error and the companion event remains queued. The pure
  transport-failure helper test separately locks the endpoint-qualified
  disconnected-event text without exercising the worker.
- Remote write-failure tests cover Rust's response/rejection write failure
  branch by surfacing a disconnected event. The pure write-failure helper test
  separately locks the endpoint-qualified disconnected-event text without
  exercising the worker.
- Remote command entrypoint projection tests cover the shared public method
  skeleton for request/notify/resolve/reject: command variant, oneshot response
  boundary, worker-channel send error, and operation-specific response-channel
  closure text.
- Remote worker command projection tests cover the Rust worker-side
  `RemoteClientCommand` match branch skeleton: request pending registration and
  duplicate-id rejection, request write-failure disconnect/error fan-out,
  notify/resolve/reject write-result response paths, and shutdown close/break
  behavior.
- Remote worker select-loop projection tests cover the Rust worker topology:
  an unbiased `tokio::select!` over the command receiver and websocket stream,
  pending-request `HashMap` ownership, optional worker-exit error storage, and
  post-loop pending-request fan-out without executing Tokio scheduling.
- Remote worker stream-message projection tests cover the Rust worker-side
  websocket `stream.next()` match branch skeleton: response/error waiter
  completion, notification/server-request event delivery, unsupported request
  rejection, disconnecting invalid/close/transport/EOF exits, and ignored
  control/binary frames.
- Remote worker command-channel-closed projection tests cover the Rust
  `command_rx.recv()` closed branch: close the stream, ignore close errors,
  break the worker loop, and fan out the default BrokenPipe worker-closed error
  to pending request waiters.
- Exact Rust Tokio branch-order execution is not duplicated in this module.
  The select-loop topology, bounded command-channel capacity/backpressure
  shape, and unbiased select timing contract are now tracked as Python
  projections, while concrete websocket scheduling remains delegated to
  `pycodex.exec.session`.
- Audit note: named Rust remote tests from `src/remote.rs` and the crate-root
  remote test block in `src/lib.rs` are now explicitly anchored in Python
  tests or documented as bounded debt; remaining open work is compatibility
  behavior rather than an untracked named Rust remote test.
- 2026-06-18 residual audit plus 2026-06-19 timing closeout: remaining
  `src/remote.rs` timing debt has been converted into an explicit projection of
  Rust's unbiased `tokio::select!` contract. Helper,
  initialize, request/response, server-request, notification, disconnect, and
  shutdown branches are already tracked above or delegated to the existing
  `pycodex.exec.session` wire client. The pending-request exit fan-out helper
  covers only the loop-tail error broadcast shape, the channel-topology helper
  covers only setup structure, the next-event helper covers only pending-event
  drain order, and the shutdown projection covers only the control-flow order,
  not Tokio scheduling.
- 2026-06-18 command/handle closure audit: request/notification/server-request
  facade closure behavior is now explicitly tracked through command-capacity,
  worker-closed command, response-channel closure, request-handle closure, and
  request-handle typed-wrapper anchors; further `src/remote.rs` work should
  target real worker timing rather than additional duplicate facade tests.
- 2026-06-18 post-wire-bridge residual audit: all currently identified pure
  `src/remote.rs` helper/facade anchors are tracked above or delegated to the
  existing `pycodex.exec.session` wire client, with the bounded command sender
  shape and select-timing contract added on 2026-06-19. No additional
  remote-module helper/facade work is currently tracked.
- 2026-06-18 command entrypoint projection: the helper covers the public
  method skeleton and error text mapping only; it does not model Tokio worker
  scheduling or bounded-channel timing.
- 2026-06-18 worker command projection: the helper covers the worker match
  branch outcomes only; it does not execute the select loop, stream IO, or Tokio
  channel scheduling.
- 2026-06-18 stream-message projection: the helper covers the worker
  `stream.next()` branch routing only; it does not execute websocket reads,
  JSON-RPC serde, or concurrent select-loop timing.
- 2026-06-18 command-channel-closed projection: the helper covers the
  command receiver closed branch only; it does not execute the actual stream
  close future or worker join handle.
- 2026-06-18 precision correction: Rust `src/remote.rs` constructs
  `mpsc::channel::<RemoteClientCommand>(channel_capacity)` but
  `mpsc::unbounded_channel::<AppServerEvent>()`; do not implement duplicate
  remote event-queue backpressure or remote `Lagged` synthesis in this module.
- `test_remote_connect_bridge_forwards_effective_command_channel_capacity`
  anchors the Python bridge projection for that bounded command-channel
  capacity without starting a remote runtime.
- 2026-06-19 command-channel backpressure projection: the helper fixes Rust's
  bounded sender semantics without starting the async worker. Full-channel
  sends wait for receiver progress rather than producing a queue-full error;
  only a closed worker receiver maps to
  `remote app-server worker channel is closed`.
- 2026-06-19 select-timing projection: the helper fixes the final timing
  boundary without running Tokio. The Rust worker has no `biased;` arm, so
  simultaneous command and stream readiness intentionally has no stable
  branch-order contract.

Validation:

- Not run in this turn; current automation defers actual test execution until
  the crate functional code is complete.
