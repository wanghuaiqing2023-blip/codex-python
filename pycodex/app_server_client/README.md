# pycodex.app_server_client

Rust crate: `codex-app-server-client`

Rust anchor: `codex/codex-rs/app-server-client`

This package mirrors the public app-server client facade used by CLI/TUI
surfaces. The current Python implementation keeps transport methods as
compatibility stubs, but the crate-root API boundary now carries the pure
`src/lib.rs` behavior that other Python modules can safely depend on.

## 2026-06-19 lib.rs runtime-projection alignment

`src/lib.rs` is tracked in `TEST_ALIGNMENT.md` and `LIB_RS_STATUS.md`. Python
now covers the crate-root constants, event/request handle facades,
`InProcessClientStartArgs.initialize_params()`, the in-process runtime-start
argument projection boundary including remote thread-config loader selection
and default noop loader selection, channel-capacity forwarding, startup field
projection, and list cloning for CLI overrides/config warnings and initialize
opt-out notification methods, plus the Rust
`DEFAULT_IN_PROCESS_CHANNEL_CAPACITY` re-export/default-start-args boundary and
the in-process start-layer `channel_capacity.max(1)` effective-capacity rule,
and the `InProcessAppServerClient.start(...)` compatibility layer now
materializes the app-server-owned `InProcessRuntimeProjection` from
`into_app_server_in_process_start_args(...)`. Start-created clients are no
longer disconnected shells: notification, server-request response, rejection,
event injection, and runtime bookkeeping use the app-server in-process
projection. Direct requests enter that projection and surface a pending-response
JSON-RPC error instead of fabricating a MessageProcessor result that this client
crate does not own,
`TypedRequestError` display semantics and source exposure,
`request_method_name(...)`, in-process event projection to
`AppServerEvent`, the Rust lossless notification classification used by
backpressure handling including the concrete transcript/terminal event marker
test and non-lossless lagged markers, a deterministic
`forward_in_process_event` ordering projection for skipped best-effort events,
accumulated and pre-existing `Lagged` markers, lossless transcript/completion
delivery, and dropped server-request rejection, plus closed-consumer
stream-disable projection,
direct lagged-marker delivery through `next_event()`,
prompt shutdown completion at the lightweight facade boundary,
and a stateful in-process facade for injected
request/notification handlers, server-request resolution records, queued
events, request handles, direct request-channel shutdown closure,
method-qualified typed-request transport wrapping, server/decode error
wrapping through an optional Python decoder, and shutdown.
Request handles now also cover Rust's cloned command-sender closure boundary:
multiple handles from one client share the same request path, and after client
shutdown, handle requests observe the same request-channel `BrokenPipeError`
and typed requests wrap it as `TypedRequestError.transport`; handle typed
requests also mirror the direct client server/decode error wrappers.
The lightweight in-process facade also mirrors Rust's unsupported
`ChatgptAuthTokensRefresh` server-request branch by recording a JSON-RPC
`-32000` rejection instead of delivering that request to callers.
The 2026-06-18 residual audit found no further tracked pure `src/lib.rs`
facade/source-contract branches outside the documented embedded runtime and
backpressure debt.
The 2026-06-19 start-facade update replaces the disconnected lightweight shell
with app-server-owned runtime projection bookkeeping. The remaining
MessageProcessor success-response path and concrete Tokio worker/backpressure
execution are now treated as embedded app-server collaboration and crate-level
validation evidence, not local `src/lib.rs` facade plumbing or another pure
worker select ready-set contract.
The 2026-06-19 start test update also replaces the old
`*_remains_unimplemented_without_runtime` assertions with runtime-projection
bookkeeping assertions for direct requests, request handles, notifications,
server-request responses/rejections, and event injection.
The 2026-06-19 immediate-error propagation update also checks that
`InProcessAppServerClient.request(...)` returns raw runtime-projection
`RequestResult` errors for duplicate request IDs, full processor queues, and
closed request processors, without pretending that successful MessageProcessor
responses are locally available.
The 2026-06-19 request-response projection also makes the client-owned
`request(...)` oneshot contract explicit: `ClientCommand::Request` is boxed and
sent through the worker channel, the response oneshot is awaited, raw
`RequestResult` is returned, and worker/request response channel closures keep
Rust's exact BrokenPipe messages.
The 2026-06-19 in-process command-channel backpressure projection records the
bounded `mpsc::channel<ClientCommand>` sender contract too:
`channel_capacity.max(1)`, full-channel sends waiting for worker receiver
progress, worker receiver closure as the only send-error condition, and the
shared `in-process app-server worker channel is closed` BrokenPipe text. The
event channel remains a separate bounded channel whose event-side saturation is
handled by `forward_in_process_event(...)`.
The 2026-06-19 worker request-task projection records the worker-side detached
delivery path too: the worker clones `request_sender`, moves the boxed request
into a spawned task, awaits `request_sender.request(*request).await`, forwards
the raw `RequestResult` to the response oneshot, ignores dropped receivers, and
keeps draining runtime events while a request waits.
The 2026-06-19 worker select-timing projection also records the local
`tokio::select!` boundary: command input is always enabled, runtime events are
guarded by `event_stream_enabled`, disabled event arms cannot win, and
simultaneous command/event readiness has no stable branch order because Rust
does not use `biased;`.
Closed in-process command errors use the same Rust channel names for
`notify`, `resolve`, and `reject` paths. The crate-root wrapper facades also
cover Rust-style inner-client dispatch for request handles, typed requests,
notifications, server-request resolution/rejection, next events, and shutdown
for both in-process and remote wrapper variants; the remote coverage here is
only the `src/lib.rs` enum-dispatch boundary, not remote transport internals.
Public `AppServerEvent` shape coverage includes lagged, notification,
request, and disconnected-message variants.
Request-method diagnostics now use Rust's `"<unknown>"` fallback for
unrecognized request shapes.
Initialize params now cover both Rust opt-out notification branches: empty
lists become `None`, and non-empty lists are cloned into the params payload.
The Rust `legacy_core` compatibility bridge is mirrored as
`pycodex.app_server_client.legacy_core`, re-exporting already-ported
`pycodex.core` symbols and submodules without duplicating implementations.
The crate-root `app_server_control_socket_path(...)` re-export now delegates
to the existing `pycodex.exec.session` socket path policy.
Crate-root `StateDbHandle`, `EnvironmentManager`, and
`ExecServerRuntimePaths` now alias the existing Python core/exec-server
implementations instead of local placeholders.
Typed request server-error data now uses compact JSON formatting, matching
Rust `serde_json::Value` display output.

`src/lib.rs` is now complete: the client-owned in-process facade, worker
topology/projection, command/event boundaries, request response forwarding,
runtime handoff, and wrapper dispatch contract pass focused Python validation
(`tests/test_app_server_client_lib_rs.py`, 61 tests). `src/remote.rs` is also
complete after correcting the delegated wire bridge's method-string
request/notification passthrough, initialize `clientInfo.title = None`
preservation, Unix socket connector path shape, and quiet EOF drain behavior
after ignored or unknown remote frames. The full package-focused validation now
passes (`tests/test_app_server_client_lib_rs.py` plus
`tests/test_app_server_client_remote_rs.py`, 188 tests).
`TEST_ALIGNMENT.md` now records the `src/lib.rs` named-test audit: pure
facade/source-contract tests are anchored, while app-server startup,
session-source, typed runtime roundtrip, and exact backpressure tests are
explicitly deferred until the embedded runtime is implemented.
The 2026-06-18 runtime dependency handoff confirms that Rust
`InProcessAppServerClient::start(...)` calls into
`codex_app_server::in_process::start(...)`; Python now exposes the
app-server-owned `pycodex.app_server.in_process.InProcessStartArgs` projection,
so this client package materializes that handoff with
`into_app_server_in_process_start_args(...)` and now attaches the app-server
in-process runtime projection to the start-created facade, while leaving true
MessageProcessor execution owned by `pycodex.app_server`.

## 2026-06-18 remote.rs partial alignment

`src/remote.rs` is now tracked in `TEST_ALIGNMENT.md` and
`REMOTE_RS_STATUS.md`. Python covers the remote endpoint/connect argument
shapes, initialize params, auth-token URL policy, websocket config constants,
UDS handshake URL, JSON-RPC request/notification projection helpers including
already-shaped mappings, and a Rust-compatible
`remote_app_server_event_from_notification(...)` helper for known/unknown
server notification filtering. It also provides a stateful remote
facade for injected request/notification handlers, server request resolution
records, queued events, server version, request handles, and shutdown.

`RemoteAppServerClient.connect(...)` now delegates to the already-ported
`pycodex.exec.session.remote_app_server_client_connect(...)` wire runtime via a
thin adapter. This keeps `pycodex.app_server_client` as the crate-owned public
facade while avoiding a second implementation of the remote websocket
state-machine. The remote auth-token URL policy also delegates to the same
`pycodex.exec.session` helper, so loopback and `wss://` handling is kept in one
place; its helper coverage is anchored to Rust's
`remote_auth_token_transport_policy_allows_wss_and_loopback_ws`. Remote
endpoint variants now validate their mutually exclusive fields,
and connect args expose Rust's effective `channel_capacity.max(1)` behavior
when bridging into the runtime's bounded command channel, without adding a
separate remote event-queue capacity model. Connected request handles route
over the same delegated wire path as direct requests, including request-path
closure error propagation and typed server/deserialize wrapping. Wire request handling preserves the Rust
`RequestResult` split: raw requests keep transport failures as I/O-style
`OSError`s, while `request_typed(...)` wraps transport failures as
`TypedRequestError.transport(...)`, JSON-RPC errors as
`TypedRequestError.server(...)`, and optional decoder failures as
`TypedRequestError.deserialize(...)`. Request, notification, and server-request
response write failures also surface as I/O-style `OSError`s. The bridge
preserves Rust's request write-failure side effect by queuing the companion
`AppServerEvent.disconnected(...)` write-failed event before surfacing the
request error. It also preserves the Rust remote connect boundaries for unsafe
auth-token URL rejection, including rejecting non-loopback `ws://` auth-token
endpoints before connector invocation, invalid websocket URL rejection before
connector invocation, supported auth-token forwarding to the websocket
connector for `wss://` and loopback `ws://` endpoints, invalid authorization
header rejection before connector invocation, connector timeouts,
connector invalid-input errors, generic connector failures, and Unix socket
connections using the fixed UDS websocket handshake URL,
including Unix socket typed request roundtrips, connector timeout/failure
endpoint context, and connector invalid-input errors. Incoming remote JSON-RPC requests
follow the Rust worker split:
supported server requests become `AppServerEvent.server_request(...)`, and
unknown methods are rejected with JSON-RPC `-32601` while later events continue
to stream. If that rejection write fails, the facade surfaces Rust's companion
write-failed disconnected event. Incoming notifications are filtered through
the app-server-protocol `ServerNotification` registry so known notifications
such as `account/updated` are delivered to `next_event()` and unknown
notification methods are ignored while later events continue to stream. Non-text websocket
frames are skipped while later JSON-RPC events continue to stream, and invalid
runtime JSON-RPC text frames surface as disconnected events. If invalid JSON-RPC
is observed while a request is awaiting its response, the request reports the
I/O error and the companion disconnected event remains queued for
`next_event()`. Notifications received while a request is awaiting its response
are preserved for `next_event()` while the request continues waiting for its
matching response, and unknown notifications in that window are ignored.
The transcript notification sequence from Rust's remote backpressure coverage
is recognized and streamed in order. The remaining `src/remote.rs`
backpressure gap has been narrowed: the bounded `RemoteClientCommand` channel
capacity and sender semantics are represented by
`remote_command_channel_backpressure_projection(...)`, including waiting for
receiver capacity when full and failing only when the worker receiver is
closed. The remaining remote-module runtime gap is exact Tokio worker
select-loop wakeup/timing; remote event delivery itself is unbounded in Rust,
so remote event-queue `Lagged` synthesis is not a separate target for this
module.
Supported server requests received in the same window are preserved the same
way, while unknown server requests are rejected with JSON-RPC `-32601` without
blocking the pending response. Supported server requests can also be resolved
back to the server with a matching JSON-RPC response id. The concrete
`thread/unknown` rejection path mirrors Rust's unsupported-method error
message. Runtime websocket close frames also surface as disconnected
events with the Rust endpoint/reason message shape, including the default
`connection closed` reason. The default close event is anchored to Rust's
`remote_disconnect_surfaces_as_event`.
If a close frame is observed while a request is awaiting its response, the
request reports the I/O error and the companion disconnected event remains
queued for `next_event()`.
Runtime websocket EOF surfaces as a closed-connection disconnected event.
If EOF is observed while a request is awaiting its response, the request reports
the I/O error and the companion disconnected event remains queued for
`next_event()`.
Runtime websocket transport failures surface as transport-failed disconnected
events. If a transport failure is observed while a request is awaiting its
response, the request reports the I/O error and the companion disconnected event
remains queued for `next_event()`.
Large single-frame typed responses also use the Rust-aligned websocket message
limits and decode successfully while ignoring extra result fields.
The normal websocket typed `account/read` roundtrip also mirrors Rust's
`remote_typed_request_roundtrip_works`: initialize `userAgent` populates
`server_version()`, and the typed account response is decoded through
`request_typed(...)`.
Duplicate pending request ids mirror Rust's typed `account/read` duplicate
case: a second request is rejected before another frame is written and maps to
a typed transport error, while the original pending request remains active and
can still receive its matching response.
Shutdown uses the shared wire client close path, surfaces non-already-closed
close failures as `OSError`, tolerates already-closed close errors, and
tolerates Rust's worker-already-closed shutdown race. The facade shutdown
fallback delegates close-error classification to the same Rust-aligned
`pycodex.exec.session.websocket_close_error_is_already_closed(...)` helper, so
direct wire-client `ConnectionResetError` and related already-closed cases are
also treated as successful close.
Request, notification, and server-request response commands also preserve
Rust's worker-channel-closed mapping by surfacing the shared wire client's
`remote app-server worker channel is closed` error as an `OSError`.
They also preserve Rust's operation-specific response-channel closure errors:
request, notify, resolve, and reject report their own remote app-server channel
closed messages as `OSError`s.
Initialize-time notifications and supported server requests are preserved as
pending events, non-matching response/error frames are ignored while waiting
for the initialize response, non-text websocket frames are ignored in the same
initialize window, unknown initialize-time server requests are rejected, and
queued initialize-time server requests can be resolved after connect with a
matching JSON-RPC response id.
matching initialize JSON-RPC errors surface as endpoint-qualified connect
failures. Initialize-time websocket close frames also surface as
endpoint-qualified closed-during-initialize connect failures, as does
initialize-time websocket EOF. Initialize-time websocket transport failures
surface as endpoint-qualified transport-failed-during-initialize connect
failures, and initialize response timeouts surface as endpoint-qualified
timeout connect failures. Invalid initialize JSON-RPC text frames surface as
endpoint-qualified invalid-initialize-response connect failures. Initialize
request write failures surface as endpoint-qualified websocket write-failed
connect failures, and so do post-response `initialized` notification write
failures. The initialize response `userAgent` is parsed into
`server_version()` with the same `codex/<version>` extraction shape used by
Rust; malformed or whitespace-only values without a non-empty version segment
leave `server_version()` unset.

No tracked `src/remote.rs` helper/facade gap remains open. The bounded remote
command-channel capacity and sender backpressure semantics are tracked by the
`remote_command_channel_backpressure_projection(...)` helper, and the unbiased
`tokio::select!` branch-order contract is tracked by
`remote_worker_select_timing_projection(...)`: simultaneous command and
websocket readiness has no stable priority guarantee in Rust. The deeper
embedded in-process runtime behavior remains outside this remote facade.
The named Rust remote tests are now explicitly anchored in the package test
alignment/status files; the remaining remote work is the documented
compatibility debt above rather than an untracked named Rust remote test.
After the 2026-06-18 command/handle closure audit, request/notification and
server-request facade closure behavior is also explicitly tracked; future
`src/remote.rs` work should move to true worker timing instead of adding more
duplicate facade-level closure tests.
The 2026-06-19 command-channel backpressure and select-timing updates leave no
further tracked `src/remote.rs` helper/facade branch, so future remote work
should avoid duplicating the delegated `pycodex.exec.session` websocket state
machine or adding a remote event-queue backpressure layer that Rust
`src/remote.rs` does not have.
