# codex-app-server-client src/lib.rs alignment

Rust module:
`codex/codex-rs/app-server-client/src/lib.rs`

Python module:
`pycodex/app_server_client/__init__.py`

Status: `complete`

## Scope

This module owns the public in-process app-server client facade, request/result
error type, app-server event projection, initialize params, event delivery
classification, and wrapper APIs shared by CLI/TUI surfaces.

## Python Mapping

- Public facade names are exported from `pycodex.app_server_client`.
- `pycodex.app_server_client.legacy_core` mirrors Rust's transitional
  `pub mod legacy_core` by re-exporting already-ported `pycodex.core`
  constants, helpers, and submodules without duplicating implementations.
- `app_server_control_socket_path(...)` mirrors Rust's crate-root re-export by
  delegating to the already-ported `pycodex.exec.session` socket path policy.
- `StateDbHandle`, `EnvironmentManager`, and `ExecServerRuntimePaths` mirror
  Rust crate-root `pub use` exports by aliasing the existing
  `pycodex.core.state_db_bridge` and `pycodex.exec_server` implementations
  instead of local placeholders.
- `DEFAULT_IN_PROCESS_CHANNEL_CAPACITY` mirrors Rust's crate-root re-export of
  the app-server in-process default queue capacity, and
  `InProcessClientStartArgs` uses that value as its Python default before
  projecting it into runtime-start args.
- `SHUTDOWN_TIMEOUT_SECONDS` mirrors Rust's crate-root
  `SHUTDOWN_TIMEOUT = Duration::from_secs(5)` boundary used by graceful
  shutdown fallback logic.
- `in_process_shutdown_projection(...)` mirrors the local
  `InProcessAppServerClient::shutdown` timeout control flow: drop the
  caller-facing event receiver before sending shutdown, wait for the response
  up to `SHUTDOWN_TIMEOUT`, drop the command sender before awaiting the
  worker, and abort the worker when that second timeout elapses.
- `in_process_shutdown_entrypoint_projection(...)` mirrors the Rust public
  shutdown entrypoint: consume and destructure the client, drop the
  caller-facing event receiver before sending `ClientCommand::Shutdown`, ignore
  worker-send failure and response timeout, and only propagate the command
  result when it arrives within `SHUTDOWN_TIMEOUT`.
- `InProcessClientCommandProjection` mirrors the internal Rust
  `ClientCommand` variants and their oneshot response boundary: request,
  notify, resolve server request, reject server request, and shutdown.
- `in_process_worker_command_projection(...)` mirrors the Rust worker-side
  `ClientCommand` match branches: request commands clone `request_sender` and
  run on a detached task, notify/resolve/reject commands forward through the
  matching handle methods, shutdown awaits `handle.shutdown()` and breaks, and
  closed command input shuts the handle down before breaking.
- `in_process_worker_event_projection(...)` mirrors the Rust worker-side
  `handle.next_event()` branch: an ended runtime event stream breaks the
  worker, unsupported `ChatgptAuthTokensRefresh` server requests are rejected
  with code `-32000` and skipped, ordinary events are forwarded through
  `forward_in_process_event(...)`, and `DisableStream` disables only the event
  stream arm.
- `in_process_command_entrypoint_projection(...)` mirrors the Rust public
  in-process command methods (`request`, `notify`, `resolve`, and `reject`):
  each sends the matching `ClientCommand` through the worker channel, owns a
  response oneshot, maps closed worker sends to
  `in-process app-server worker channel is closed`, and maps closed response
  oneshots to the operation-specific channel name.
- `in_process_command_channel_backpressure_projection(...)` mirrors the Rust
  bounded `mpsc::channel<ClientCommand>` sender boundary: command capacity is
  clamped with `channel_capacity.max(1)`, sends wait when the channel is full,
  and sends fail only when the worker receiver is closed, using the shared
  `in-process app-server worker channel is closed` BrokenPipe text. The
  separate in-process event channel is bounded with the same capacity and uses
  `forward_in_process_event(...)` for event-side backpressure handling.
- `in_process_request_response_projection(...)` mirrors the Rust
  `InProcessAppServerClient::request(...)` raw response boundary: create a
  response oneshot, send a boxed `ClientCommand::Request`, await the response
  oneshot, return raw `RequestResult`, map closed worker sends to
  `in-process app-server worker channel is closed`, and map closed response
  oneshots to `in-process app-server request channel is closed`.
- `in_process_worker_request_task_projection(...)` mirrors the Rust worker's
  detached request task: the request branch clones `request_sender`, moves the
  boxed request into a spawned task, awaits
  `request_sender.request(*request).await`, sends that raw `RequestResult` to
  the response oneshot, ignores dropped response receivers, and keeps the
  worker loop free to drain runtime events while the request waits.
- `in_process_request_handle_projection(...)` mirrors
  `InProcessAppServerClient::request_handle()`: the factory clones the command
  sender, handle requests send boxed `ClientCommand::Request` values with a
  response oneshot, and handle typed requests share the same
  transport/server/deserialize wrapping contract as direct client requests.
- `in_process_next_event_projection(...)` mirrors
  `InProcessAppServerClient::next_event()`: the facade awaits
  `self.event_rx.recv()`, returns `Option<InProcessServerEvent>`, preserves
  in-process event variants, and leaves conversion to `AppServerEvent` to the
  wrapper facade.
- `RequestResult`, request handle wrappers, and app-server client wrapper
  classes map the Rust public API boundary.
- `InProcessClientStartArgs.initialize_params()` mirrors Rust client info and
  capability construction, including `None` for empty opt-out notification
  methods and cloned non-empty opt-out method lists.
- `InProcessClientStartArgs.into_runtime_start_args()` mirrors the Rust
  runtime-start argument projection boundary for currently ported fields,
  including preserving the supplied config and environment manager objects, and
  forwarding channel capacity, selecting the remote thread-config loader when
  `experimental_thread_config_endpoint` is configured, and selecting the noop
  thread-config loader by default. Startup list fields such as CLI overrides
  and config warnings are copied into runtime args so caller mutation after
  projection does not rewrite the runtime payload; initialize opt-out
  notification methods are cloned into the projected initialize params too.
- `into_app_server_in_process_start_args(...)` bridges the client-owned start
  args into the app-server-owned `InProcessStartArgs` projection, preserving
  the Rust handoff from `args.into_runtime_start_args()` into
  `codex_app_server::in_process::start(...)` without duplicating the embedded
  runtime in this crate.
- `InProcessClientStartArgs.effective_channel_capacity()` mirrors the Rust
  `InProcessAppServerClient::start` facade rule that clamps worker queue
  capacity with `channel_capacity.max(1)` before channel creation.
- `in_process_runtime_dependency_projection(...)` mirrors the
  `InProcessAppServerClient::start(...)` runtime ownership boundary: this
  client module hands true embedded runtime behavior to `codex-app-server`
  (`pycodex.app_server`), and must not fabricate a second runtime locally.
- `in_process_worker_topology_projection(...)` mirrors the Rust
  `InProcessAppServerClient::start(...)` worker setup: start the embedded
  handle, take `handle.sender()`, create bounded command/event channels using
  `channel_capacity.max(1)`, spawn a worker with
  `event_stream_enabled = true` and `skipped_events = 0`, and select over
  command input plus `handle.next_event()` while the event stream remains
  enabled.
- `in_process_worker_select_timing_projection(...)` mirrors the Rust worker
  loop's local `tokio::select!` ready-set contract without running Tokio:
  command input is always an enabled arm, runtime events are guarded by
  `event_stream_enabled`, a disabled event arm cannot win even when an event is
  ready, exactly one ready enabled arm has a deterministic branch, and
  simultaneous command/event readiness has no stable branch-order guarantee
  because the Rust macro is not marked `biased;`.
- `TypedRequestError` mirrors Rust display strings for transport, server, and
  deserialize errors, and mirrors Rust `Error::source()` exposure by chaining
  Python causes for transport/deserialize sources while leaving server
  JSON-RPC errors unchained. JSON-RPC server error `data` is formatted with
  compact JSON to match Rust `serde_json::Value` display output.
- `AppServerEvent.from_in_process(...)` mirrors the Rust `From` conversion for
  lagged markers, server notifications, and server requests.
- `AppServerEvent.disconnected(...)` carries the Rust disconnected-message
  event shape used by remote and wrapper paths.
- `server_notification_requires_delivery(...)` and
  `event_requires_delivery(...)` mirror the Rust lossless notification tier for
  transcript and completion events, while leaving lagged markers and command
  output deltas outside that delivery-required tier.
- `project_in_process_event_forwarding(...)` mirrors the pure observable
  ordering contract of Rust's `forward_in_process_event(...)`: dropped
  best-effort events increment and accumulate skipped counts, the following
  lossless transcript/completion event is preceded by a single `Lagged` marker
  carrying that count, existing skipped counts can flush before a later
  best-effort event when capacity is available, and dropped server requests
  receive the Rust `-32001` queue-full rejection. The
  `ForwardEventResult` enum and projection result field now record Rust's
  `Continue` branch for healthy streams and `DisableStream` branch when the
  consumer channel is closed.
- `request_method_name(...)` maps Python `ClientRequest` instances and
  method-shaped mappings to JSON-RPC method names for diagnostics, falling back
  to Rust's `"<unknown>"` marker for unrecognized request shapes.
- `InProcessAppServerClient` now provides a stateful Python facade for
  request, typed request, notify, server-request resolve/reject, queued events,
  request handles, and shutdown when supplied with local handlers.
- `InProcessAppServerClient.start(...)` now implements the Rust start-layer
  argument boundary by projecting `into_runtime_start_args()`, materializing
  `into_app_server_in_process_start_args(...)`, recording the
  `channel_capacity.max(1)` effective queue capacity, and attaching the
  app-server-owned `InProcessRuntimeProjection` to the Python facade. The
  returned facade supports prompt shutdown plus runtime-projection bookkeeping
  for notifications, server-request responses, server-request rejections, event
  injection, accepted client requests, and immediate runtime-projection request
  errors such as duplicate request IDs, full processor queues, and closed
  request processors. It deliberately reports accepted client requests as
  pending JSON-RPC errors instead of fabricating a MessageProcessor result that
  this client crate does not own.
- `InProcessAppServerRequestHandle` mirrors Rust's cloned command-sender
  boundary by forwarding through the same client and observing the same
  request-channel closure after client shutdown. Multiple Python handles from
  the same client share that request path, matching Rust cloned handles sharing
  one command sender, and handle typed requests share the same server/decode
  error wrapper semantics as direct client typed requests.
- `InProcessAppServerClient.request_typed(...)` mirrors the Rust transport
  wrapper boundary for request-path `OSError`s, JSON-RPC server error wrapping,
  request-channel closure after client shutdown, and optional Python decoder
  failures as deserialize errors.
- Closed in-process command methods use Rust's channel error names for
  notification and server-request response paths (`notify`, `resolve`, and
  `reject`).
- `in_process_unsupported_server_request_error(...)` and the lightweight
  `push_event(...)` facade mirror Rust's in-process worker branch that rejects
  `ChatgptAuthTokensRefresh` server requests with JSON-RPC code `-32000`
  instead of delivering them to callers.
- `InProcessAppServerClient.next_event()` surfaces queued lagged markers,
  matching Rust's `next_event_surfaces_lagged_markers` behavior at the facade
  boundary.
- `AppServerClient.next_event()` maps in-process events through
  `AppServerEvent.from_in_process(...)`, matching Rust's wrapper behavior.
- `AppServerClient` and `AppServerRequestHandle` forward request,
  typed-request, notify, resolve/reject, request-handle, next-event, and
  shutdown calls to their inner in-process or remote client variants, matching
  the Rust enum-dispatch facade boundary. The remote branch is covered here as
  wrapper dispatch only; remote transport behavior remains owned by
  `src/remote.rs`.

## Known Gaps

- 2026-06-19 complete-candidate audit: no remaining tracked
  `src/lib.rs`-owned public API, local facade branch, command/event/request
  projection, shutdown boundary, wrapper dispatch path, or Rust test-derived
  source-contract gap is open. The remaining concrete MessageProcessor
  success response and exact live Tokio scheduling/backpressure observations
  are owned by the embedded `codex-app-server` runtime collaboration and
  crate-level validation, not by another local client-module shim.
- 2026-06-18 post-public-facade residual audit: after adding explicit
  projections for in-process worker topology, worker command branches, worker
  event branches, public command entrypoints, request-handle factory,
  `next_event()`, and shutdown entrypoint, no additional pure `src/lib.rs`
  public facade branch is currently tracked. Remaining progress for this
  module is runtime/backpressure-owned rather than another lightweight facade
  projection.
- 2026-06-18 residual audit: no additional pure crate-root facade or
  source-contract branch is currently tracked for `src/lib.rs` outside the
  runtime items below. The start-layer argument/effective-capacity boundary is
  now covered; further `src/lib.rs` progress should focus on the embedded
  runtime worker/backpressure contract rather than adding duplicate
  lightweight facade shims.
- 2026-06-19 post-start-facade audit: the disconnected lightweight start shell
  was replaced with app-server-owned runtime projection bookkeeping. The local
  `src/lib.rs` facade now covers argument projection, effective capacity,
  lifecycle/shutdown, notification, server-request response/rejection,
  event-injection, and request-acceptance bookkeeping. The true
  MessageProcessor response path and exact Tokio worker/backpressure timing
  remain integration-validation concerns for the app-server runtime owner, not
  additional local facade plumbing.
- 2026-06-19 start runtime-projection test update: Python parity tests now
  assert the runtime-projection-backed start facade directly for request,
  request-handle, notification, server-request response/rejection, and event
  injection behavior. The previous disconnected-start-shell tests are no
  longer part of the status contract.
- 2026-06-19 request immediate-error propagation: Python parity tests now
  assert `InProcessAppServerClient.request(...)` returns raw runtime-projection
  `RequestResult` errors for duplicate request IDs, full processor queues, and
  closed request processors. Successful concrete MessageProcessor result
  production is delegated to the embedded app-server runtime owner.
- 2026-06-19 request response projection: the client-owned raw request/oneshot
  response flow is now explicit, so remaining MessageProcessor debt is limited
  to producing concrete responses in the app-server runtime owner.
- 2026-06-19 worker request task projection: the client-owned detached request
  wait/response-oneshot delivery boundary is now explicit. Remaining request
  debt is concrete runtime result production, not the worker's response_tx
  forwarding shape.
- 2026-06-19 in-process command-channel backpressure projection: the bounded
  command sender capacity and full-channel wait/error boundary is now explicit.
  Remaining backpressure debt is true Tokio wakeup scheduling plus runtime
  event forwarding under live saturation, not the command sender contract.
- 2026-06-19 worker select timing projection: the pure local
  `tokio::select!` ready-set contract is now explicit for the in-process
  worker. Remaining worker debt is concrete Tokio scheduling, event forwarding
  under real saturation, and MessageProcessor response delivery.
- 2026-06-18 runtime dependency handoff: Rust
  `InProcessAppServerClient::start(...)` delegates real embedded behavior to
  `codex_app_server::run_app_server(...)`. Python now has a partial
  `pycodex.app_server` runtime owner that exposes the explicit full-runtime
  boundary, so `src/lib.rs` should not fabricate app-server runtime behavior
  inside the client crate. True request/notification/server-request roundtrips
  and event streaming still depend on that owning app-server runtime module or
  an approved compatibility runtime shim.
- `InProcessAppServerClient.start(...)` now attaches the app-server-owned
  runtime projection but still does not execute a concrete MessageProcessor.
- The Tokio worker task's concrete scheduling, bounded channel backpressure
  execution under live runtime load, lossless event forwarding under real
  saturation, and concrete MessageProcessor response delivery remain
  crate-integration validation debt.
- The Python event-forwarding projection is deterministic parity evidence for
  ordering/rejection only; it is not a substitute for exact async
  bounded-channel timing.
- Rust named tests that require that embedded runtime remain explicit debt:
  `typed_request_roundtrip_works`,
  `typed_request_reports_json_rpc_errors`,
  `caller_provided_session_source_is_applied`,
  `threads_started_via_app_server_are_visible_through_typed_requests`,
  `tiny_channel_capacity_still_supports_request_roundtrip`, and
  `forward_in_process_event_preserves_transcript_notifications_under_backpressure`.
- Full remote transport behavior remains owned by `src/remote.rs`.

## Evidence

- Rust source:
  `codex/codex-rs/app-server-client/src/lib.rs`
- Python validation:
  `python -m py_compile pycodex/app_server_client/__init__.py tests/test_app_server_client_lib_rs.py`
  and `python -m pytest tests/test_app_server_client_lib_rs.py -q`
  passed on 2026-06-19 (`61 passed`).
- Rust tests in this module cover typed request errors, event delivery
  classification, next-event lag markers, initialize/runtime argument mapping,
  and async request/transport behavior.
- Python parity tests in `tests/test_app_server_client_lib_rs.py` cover the
  currently mapped pure and stateful facade behavior, including Rust's
  `legacy_core`, `app_server_control_socket_path`, and crate-root type
  re-export bridges, the `DEFAULT_IN_PROCESS_CHANNEL_CAPACITY` re-export and
  `SHUTDOWN_TIMEOUT` constant boundary,
  the shutdown entrypoint projection,
  the shutdown timeout/abort-fallback projection,
  internal `ClientCommand` variant shape,
  in-process command entrypoint projection,
  in-process command-channel backpressure projection,
  in-process request response projection,
  in-process worker detached request task projection,
  in-process next-event facade projection,
  in-process request-handle factory projection,
  in-process worker command match-branch projection,
  in-process worker event branch projection,
  in-process worker select timing projection,
  runtime dependency handoff projection,
  in-process worker topology projection,
  internal `ForwardEventResult` continue/disable-stream projection,
  default runtime-start projection, the in-process start-layer effective
  channel-capacity clamp, runtime-projection-backed start argument projection,
  runtime-projection immediate request error propagation,
  `runtime_start_args_forward_environment_manager` runtime-argument projection
  and `runtime_start_args_use_remote_thread_config_loader_when_configured`
  remote-loader selection, `typed_request_error_exposes_sources` pure
  error-source contract, in-process typed-request transport/server/decode
  wrapping, direct request-channel shutdown closure, cloned runtime initialize
  opt-out methods, cloned request-handle shared-channel behavior, request-handle
  typed server/decode wrapping, request-method fallback diagnostics, closed
  command-channel error names, public app-server event shapes, wrapper facade
  dispatch,
  `next_event_surfaces_lagged_markers`, and
  `event_requires_delivery_marks_transcript_and_terminal_events`, plus
  `shutdown_completes_promptly_without_retained_managers` at the lightweight
  facade boundary, but are not run yet because the crate functional code is not
  complete.
- `TEST_ALIGNMENT.md` records the `src/lib.rs` named-test audit so deferred
  embedded-runtime tests are not accidentally counted as completed facade
  parity.
