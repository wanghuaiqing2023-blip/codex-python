# codex-app-server-client src/remote.rs alignment

Rust module:
`codex/codex-rs/app-server-client/src/remote.rs`

Python module:
`pycodex/app_server_client/__init__.py`

Status: `complete`

## Scope

This module owns remote app-server connection metadata, initialize params,
auth-token transport policy, JSON-RPC request/notification projection, remote
websocket config limits, and the async websocket/UDS remote client lifecycle.

## Python Mapping

- `RemoteAppServerEndpoint` and `RemoteAppServerConnectArgs` mirror Rust's
  endpoint/connect argument shapes, including exclusive endpoint variants and
  effective channel capacity clamping to at least one when bridging into the
  remote runtime.
- `RemoteAppServerConnectArgs.initialize_params()` mirrors Rust initialize
  capability construction.
- `REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS`,
  `REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS`,
  `REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE`, and
  `UDS_WEBSOCKET_HANDSHAKE_URL` mirror Rust constants.
- `websocket_url_supports_auth_token(...)` mirrors Rust's policy by reusing
  the existing `pycodex.exec.session` implementation: auth tokens require
  `wss://` or loopback `ws://` URLs.
- The helper coverage is anchored to Rust's
  `remote_auth_token_transport_policy_allows_wss_and_loopback_ws`, including
  the concrete `wss://example.com:443`, `ws://127.0.0.1:4500`, and
  `ws://example.com:4500` cases.
- `remote_websocket_config()` mirrors the max frame/message size settings.
- `jsonrpc_request_from_client_request(...)`,
  `request_id_from_client_request(...)`, and
  `jsonrpc_notification_from_client_notification(...)` mirror Rust's serde
  projection helpers for already-ported protocol facades, including already
  JSON-RPC-shaped request/notification mappings used by the delegated wire
  bridge.
- `remote_jsonrpc_projection_panic_message(...)` mirrors the Rust panic
  diagnostics for request/notification serialize and JSON-RPC encode failures.
- `remote_app_server_event_from_notification(...)` mirrors Rust's
  `app_server_event_from_notification(...)`: known server notifications become
  `AppServerEvent.server_notification(...)`, while unknown notification methods
  are ignored.
- `remote_deliver_event_projection(...)` mirrors Rust's `deliver_event(...)`
  helper result boundary: open consumers receive the event, and closed
  consumers map to `BrokenPipe` with
  `remote app-server event consumer channel is closed`.
- `remote_next_event_projection(...)` mirrors
  `RemoteAppServerClient::next_event(...)`: initialize-time pending events are
  popped before the runtime event receiver is awaited.
- `remote_write_jsonrpc_message_projection(...)` mirrors Rust's
  `write_jsonrpc_message(...)` helper boundary: messages serialize to compact
  lite JSON-RPC text payloads, and write failures use the endpoint-qualified
  `failed to write websocket message to ...` error text.
- `remote_initialize_close_frame_error_message(...)` mirrors the initialize
  close-frame branch: non-empty close reasons are preserved, while empty or
  missing reasons default to `connection closed during initialize`.
- `remote_initialize_error_message(...)` mirrors non-close
  `initialize_remote_connection(...)` error text: rejected initialize,
  invalid response JSON, transport failure, EOF, and initialize timeout.
- `remote_initialize_handshake_projection(...)` mirrors the successful
  initialize handshake sequence: write `initialize` request id/method, wait for
  the matching response id, then write the `initialized` notification.
- `remote_initialize_frame_projection(...)` mirrors initialize-loop frame
  handling: matching responses/errors complete the handshake, known
  notifications and supported server requests are queued, unknown server
  requests are rejected with `-32601`, and unrelated/non-text frames are ignored.
- `remote_runtime_close_frame_disconnected_message(...)` mirrors the runtime
  websocket close-frame branch: non-empty close reasons are preserved, while
  empty or missing reasons default to `connection closed`.
- `remote_runtime_eof_disconnected_message(...)` mirrors the runtime websocket
  EOF branch's fixed disconnected-event text.
- `remote_runtime_invalid_jsonrpc_disconnected_message(...)` mirrors the
  runtime invalid JSON-RPC branch's endpoint-qualified disconnected event text.
- `remote_runtime_transport_failure_disconnected_message(...)` mirrors the
  runtime websocket transport-failure branch's endpoint-qualified disconnected
  event text.
- `remote_websocket_connect_error_message(...)` mirrors
  `connect_websocket_endpoint(...)` error text for invalid URLs, unsafe auth
  token URLs, connector timeouts, and connector failures.
- `remote_unix_socket_connect_error_message(...)` mirrors
  `connect_unix_socket_endpoint(...)` error text for invalid UDS handshake URLs,
  Unix socket connect timeouts/failures, and websocket upgrade timeouts/failures.
- `remote_connect_endpoint_projection(...)` mirrors the connector setup shape
  for `connect_websocket_endpoint(...)` and `connect_unix_socket_endpoint(...)`:
  URL/request preparation, auth-token header policy, websocket config usage,
  connect timeout, Unix socket connect, and websocket upgrade function choice.
- `remote_connect_dispatch_projection(...)` mirrors
  `RemoteAppServerClient::connect(...)`: clamp channel capacity, build
  initialize params before endpoint connection, select the websocket or Unix
  connector by endpoint variant, and call `connect_with_stream(...)`.
- `remote_connect_with_stream_projection(...)` mirrors the
  `connect_with_stream(...)` lifecycle: initialize with timeout before channel
  setup, create bounded command and unbounded event channels, store pending
  events/server version, spawn the worker, and return a worker-backed client.
- `remote_unsupported_server_request_error_message(...)` mirrors the runtime
  unknown server-request rejection JSON-RPC error message.
- `remote_write_failed_disconnected_message(...)` mirrors the runtime websocket
  write-failure disconnected-event text used when response/rejection writes
  fail.
- `remote_shutdown_close_failed_error_message(...)` mirrors the shutdown
  websocket close-failure error text used when close errors are not
  already-closed.
- `remote_worker_exit_pending_requests_projection(...)` mirrors the Rust worker
  exit fan-out boundary: all remaining pending request waiters receive the same
  error kind/message, defaulting to BrokenPipe plus
  `remote app-server worker channel is closed` through the Rust
  `unwrap_or_else` branch when the worker exits without a stored transport
  error, while explicit worker-exit errors bypass that default.
- `remote_duplicate_request_id_error_message(...)` mirrors the request-command
  duplicate request-id rejection text.
- `RemoteAppServerClient` now provides a stateful Python facade for request,
  typed request, notify, server-request resolve/reject, queued events,
  request handles, server version, and shutdown when supplied with local
  handlers.
- `RemoteAppServerClient.connect(...)` now reuses
  `pycodex.exec.session.remote_app_server_client_connect(...)` through a thin
  adapter from this crate facade to the already-ported remote websocket client,
  avoiding a duplicate wire state-machine implementation in this package. The
  bridge covers websocket auth rejection, forwarding supported websocket auth
  tokens to the connector, invalid websocket URL rejection before connector
  invocation, invalid authorization header rejection before connector
  invocation, connector timeout, connector invalid-input, and generic
  connector-failure errors, the UDS websocket handshake URL path, and Unix
  socket connector timeout/failure/invalid-input endpoint mapping.
- The bridge forwards `RemoteAppServerConnectArgs.effective_channel_capacity`
  into the shared wire client, preserving Rust's
  `channel_capacity.max(1)` bounded `RemoteClientCommand` channel boundary
  without adding a separate remote event-queue capacity model.
- `remote_channel_topology_projection(...)` mirrors the Rust worker setup shape:
  bounded `mpsc::channel<RemoteClientCommand>`, unbounded
  `mpsc::unbounded_channel<AppServerEvent>`, `VecDeque<AppServerEvent>` pending
  events, and a pending-request `HashMap`.
- `RemoteClientCommandProjection` mirrors the internal Rust
  `RemoteClientCommand` variants and their oneshot response boundary: request,
  notify, resolve server request, reject server request, and shutdown.
- `remote_command_entrypoint_projection(...)` mirrors the public
  request/notify/resolve/reject entrypoint skeleton: create a response oneshot,
  send the matching command variant, map command-channel send failure to
  `remote app-server worker channel is closed`, and map response-channel
  closure to the operation-specific channel name.
- `remote_worker_command_projection(...)` mirrors the worker-side
  `RemoteClientCommand` match branches: request pending-registration and
  duplicate-id rejection, request write-failure disconnect/fan-out behavior,
  notify/resolve/reject write-result responses, and shutdown close/break
  behavior with already-closed tolerance.
- `remote_worker_stream_message_projection(...)` mirrors the worker-side
  websocket `stream.next()` branches: response/error pending-request completion,
  notification and supported server-request event delivery, unsupported
  server-request rejection, invalid JSON-RPC/close/transport/EOF disconnected
  exits, and ignored binary/ping/pong/frame inputs.
- `remote_worker_command_channel_closed_projection(...)` mirrors the
  `command_rx.recv()` closed branch: attempt to close the websocket stream,
  ignore that close result, break the worker loop, then fan out the default
  `remote app-server worker channel is closed` error to remaining pending
  requests.
- `remote_worker_select_loop_projection(...)` mirrors the worker loop topology:
  an unbiased `tokio::select!` over `command_rx.recv()` and `stream.next()`,
  `HashMap<RequestId, oneshot::Sender<IoResult<RequestResult>>>` pending
  requests, optional worker-exit error storage, and post-loop pending-request
  fan-out.
- `remote_worker_timing_boundary_projection(...)` records the remaining
  compatibility boundary: Rust owns bounded command-channel backpressure and
  branch wakeup timing through Tokio, while Python delegates the websocket wire
  state machine to `pycodex.exec.session`; remote events remain unbounded and
  do not synthesize `Lagged`.
- `remote_worker_select_timing_projection(...)` records the observable timing
  contract for the Rust worker's unbiased `tokio::select!`: no ready branch
  awaits progress, exactly one ready branch is deterministic, and simultaneous
  command/stream readiness has no stable branch-order guarantee.
- `remote_command_channel_backpressure_projection(...)` narrows the bounded
  command-channel portion of that boundary: Rust's
  `mpsc::channel<RemoteClientCommand>` capacity is clamped to at least one,
  sends wait for receiver capacity when the channel is full, and send errors
  are reserved for the worker receiver being closed. The remote event channel
  remains `mpsc::unbounded_channel<AppServerEvent>` with no remote `Lagged`
  synthesis.
- The Rust `remote_connect_includes_auth_header_when_configured` loopback
  websocket case is mirrored by forwarding auth tokens for `ws://127.0.0.1`
  endpoints, not only `wss://` endpoints.
- The Rust `remote_connect_rejects_non_loopback_ws_when_auth_configured` case
  is mirrored by rejecting non-loopback `ws://` auth-token endpoints before
  invoking the websocket connector.
- The Rust `remote_unix_socket_typed_request_roundtrip_works` case is mirrored:
  Unix socket connections use the delegated UDS websocket path and can issue a
  typed `account/read` request.
- The Rust `remote_typed_request_roundtrip_works` websocket case is mirrored:
  initialize `userAgent` sets `server_version()`, and a typed `account/read`
  request decodes the account response.
- Large single-frame typed responses follow Rust's websocket configuration and
  typed decoding path: the `remote_typed_request_accepts_large_single_frame_response`
  case accepts a response with padding above 16 MiB and decodes the account
  payload while ignoring extra fields.
- Connected `RemoteAppServerRequestHandle` instances route requests through the
  same delegated wire client path, mirroring Rust's cloned command sender
  handle.
- Connected `RemoteAppServerRequestHandle` values preserve the same request
  closure error behavior as the client path, including worker-channel-closed
  request errors and typed transport wrapping for request response-channel
  closure.
- Connected `RemoteAppServerRequestHandle.request_typed(...)` also mirrors
  Rust's typed wrapper split for server JSON-RPC errors and deserialize
  failures.
- Wire request responses preserve Rust's `RequestResult` split:
  `request_typed(...)` maps transport failures to
  `TypedRequestError.transport(...)`, JSON-RPC error responses to
  `TypedRequestError.server(...)`, and decoder failures to
  `TypedRequestError.deserialize(...)`.
- Request, notification, and server-request response write failures from the
  wire runtime surface to callers as `OSError`, preserving Rust's command
  response error path.
- Remote request write failures also enqueue Rust's companion
  `AppServerEvent.disconnected(...)` write-failed event before surfacing the
  request error to the caller.
- Duplicate pending remote request ids mirror Rust's
  `remote_duplicate_request_id_keeps_original_waiter` typed `account/read`
  path: the duplicate is rejected before writing a second request and maps to a
  typed transport error, while preserving the original pending waiter for its
  eventual response.
- Remote shutdown delegates to the shared wire client's close handling and
  surfaces non-already-closed close errors as `OSError`.
- `remote_shutdown_projection(...)` mirrors Rust's shutdown control-flow order:
  drop the event receiver, send the shutdown command, optionally propagate a
  close result received before `SHUTDOWN_TIMEOUT`, then wait for the worker and
  abort it on timeout.
- Remote shutdown treats already-closed websocket close errors as successful
  close by delegating to the Rust-aligned `pycodex.exec.session`
  `websocket_close_error_is_already_closed(...)` helper, including the
  `ConnectionReset`/not-connected style branches.
- `remote_websocket_close_error_is_already_closed(...)` exposes that same Rust
  helper boundary directly for this module: `ConnectionClosed`/`AlreadyClosed`
  tokens and `BrokenPipe`/`ConnectionReset`/not-connected I/O errors are
  treated as successful close states, while unrelated transport errors remain
  failures.
- Remote shutdown also mirrors Rust's worker-exit tolerance: if the worker
  channel is already closed after a shutdown command is queued, shutdown still
  completes successfully.
- Remote command entrypoints preserve Rust's worker-channel-closed error
  mapping: request, notify, resolve, and reject all surface
  `remote app-server worker channel is closed` as an I/O-style error when the
  shared wire client reports the worker send failure.
- Remote command response-channel closures preserve Rust's operation-specific
  mappings: request, notify, resolve, and reject surface their corresponding
  `remote app-server {request,notify,resolve,reject} channel is closed`
  I/O-style errors when the shared wire client reports a closed response
  channel.
- Incoming remote JSON-RPC requests preserve Rust's worker behavior: supported
  server requests stream as `AppServerEvent.server_request(...)`, while
  unsupported methods are rejected with JSON-RPC `-32601` and streaming
  continues.
- The concrete Rust `remote_unknown_server_request_is_rejected` case is
  mirrored for `thread/unknown`, including the unsupported-method message
  shape.
- The Rust `remote_server_request_resolution_roundtrip_works` path is mirrored:
  a supported websocket server request can be consumed as an event and resolved
  with a matching JSON-RPC response id.
- If the unsupported-request rejection write fails, the facade now preserves
  Rust's companion `AppServerEvent.disconnected(...)` write-failed event.
- Incoming remote JSON-RPC notifications are filtered through the
  app-server-protocol `ServerNotification` registry, so unknown notification
  methods are ignored like Rust's `ServerNotification::try_from(...)` branch
  and later events continue to stream.
- The Rust `remote_notifications_arrive_over_websocket` account-updated
  notification case is mirrored: after initialize, an incoming
  `account/updated` JSON-RPC notification is delivered as
  `AppServerEvent.server_notification(...)`.
- The transcript notification set used by Rust's
  `remote_backpressure_preserves_transcript_notifications` test is recognized
  and streamed in order over the delegated websocket path. The `src/remote.rs`
  runtime uses a bounded `RemoteClientCommand` channel but an unbounded
  `AppServerEvent` channel, so this module's remaining backpressure debt is
  command-channel worker timing rather than remote event-queue `Lagged`
  synthesis.
- Notifications received while a remote request is awaiting its response are
  preserved as events for `next_event()` while the request continues waiting for
  its matching response; unknown notifications in the same window are ignored
  without blocking the response.
- Supported server requests received while a remote request is awaiting its
  response are preserved as events for `next_event()` while the request
  continues waiting for its matching response.
- Unknown server requests received while a remote request is awaiting its
  response are rejected with JSON-RPC `-32601` while the request continues
  waiting for its matching response.
- Remote websocket non-text frames are ignored through the delegated wire
  runtime, preserving Rust's Binary/Ping/Pong/Frame skip branch while continuing
  to stream later JSON-RPC events.
- Invalid runtime JSON-RPC text frames surface as
  `AppServerEvent.disconnected(...)`, matching Rust's invalid-message worker
  branch.
- Remote requests that observe invalid JSON-RPC while awaiting a response
  preserve Rust's split behavior: the caller receives the request I/O error and
  the companion invalid-message disconnected event remains available through
  `next_event()`.
- Runtime websocket close frames surface as `AppServerEvent.disconnected(...)`
  with Rust's endpoint/reason message shape. The default no-reason close case
  is anchored to Rust's `remote_disconnect_surfaces_as_event` and uses the
  `connection closed` reason.
- Remote requests that observe a websocket close frame while awaiting a response
  preserve Rust's split behavior: the caller receives the request I/O error and
  the companion close-frame disconnected event remains available through
  `next_event()`.
- Runtime websocket EOF surfaces as `AppServerEvent.disconnected(...)` with
  Rust's closed-connection message shape.
- Remote requests that observe websocket EOF while awaiting a response preserve
  Rust's split behavior: the caller receives the request I/O error and the
  companion closed-connection disconnected event remains available through
  `next_event()`.
- Runtime websocket transport failures surface as
  `AppServerEvent.disconnected(...)` with Rust's transport-failed message shape.
- Remote requests that observe websocket transport failure while awaiting a
  response preserve Rust's split behavior: the caller receives the request I/O
  error and the companion transport-failed disconnected event remains available
  through `next_event()`.
- Remote initialize preserves Rust's pending-event behavior: notifications and
  supported server requests received before the initialize response are queued,
  and unknown initialize-time server requests are rejected with JSON-RPC
  `-32601`.
- Supported server requests received during initialize can be resolved after
  connect with a matching JSON-RPC response id, mirroring Rust's
  `remote_server_request_received_during_initialize_is_delivered` test.
- Remote initialize also preserves Rust's non-matching response/error
  behavior: JSON-RPC response or error frames whose id is not the initialize
  request id are ignored while the client continues waiting for the initialize
  response.
- Remote initialize ignores non-text websocket frames while waiting for the
  initialize response, matching Rust's Binary/Ping/Pong/Frame skip branch.
- Remote initialize maps a matching JSON-RPC initialize error into an
  I/O-style connect failure with Rust's endpoint-qualified rejected-initialize
  message.
- Remote initialize maps websocket close frames into I/O-style connect
  failures with Rust's endpoint-qualified closed-during-initialize message and
  close reason handling.
- Remote initialize maps websocket EOF into an I/O-style connect failure with
  Rust's endpoint-qualified closed-during-initialize message.
- Remote initialize maps websocket transport failures into I/O-style connect
  failures with Rust's endpoint-qualified transport-failed-during-initialize
  message.
- Remote initialize maps initialize response timeouts into I/O-style connect
  failures with Rust's endpoint-qualified timeout message.
- Remote initialize maps invalid JSON-RPC text frames into I/O-style connect
  failures with Rust's endpoint-qualified invalid-initialize-response message.
- Remote initialize maps failures while writing the initialize request into
  I/O-style connect failures with Rust's endpoint-qualified websocket
  write-failed message.
- Remote initialize maps failures while writing the post-response `initialized`
  notification into I/O-style connect failures with the same Rust
  endpoint-qualified websocket write-failed message.
- Remote connect now observes the initialize response `userAgent` and exposes
  the Rust-compatible parsed server version through
  `RemoteAppServerClient.server_version()`.
- Remote connect leaves `server_version()` unset when the initialize
  `userAgent` value does not contain a non-empty version segment after `/`,
  including whitespace-only version segments, matching Rust's `split_once('/')`
  plus first-whitespace-token parsing.
- `remote_server_version_from_user_agent(...)` exposes that Rust initialize
  parse boundary directly for this module: the substring after the first `/` is
  split on whitespace and the first token becomes the version.

## Known Gaps

- 2026-06-19 validation closeout: focused remote-module validation now passes.
  The previous validation failures were closed by accepting already-shaped
  method-string request/notification inputs, preserving initialize
  `clientInfo.title = None` on the delegated wire bridge, normalizing Unix
  socket connector paths, and matching Rust's quiet drain behavior after
  ignored/unknown remote frames. No tracked `src/remote.rs` blocker remains.
- `RemoteAppServerClient.connect(...)` depends on the existing stdlib
  websocket connector in `pycodex.exec.session`; this crate does not own a
  second transport implementation.
- 2026-06-18 residual audit: no additional `src/remote.rs` named Rust test or
  helper/facade branch is currently tracked outside the compatibility debt
  below. The 2026-06-19 select-timing projection records the remaining Tokio
  branch-order contract without duplicating the already delegated
  `pycodex.exec.session` websocket state machine.
- 2026-06-18 command/handle closure audit: after adding command-capacity,
  worker-closed command, response-channel closure, request-handle closure, and
  request-handle typed-wrapper anchors, no further `src/remote.rs`
  request/notification/server-request facade branch is currently tracked
  outside the real worker timing debt below.
- 2026-06-18 post-wire-bridge residual audit: after reconciling the delegated
  `pycodex.exec.session` wire bridge, connect/connect-with-stream setup,
  initialize, request/response, notification, server-request, disconnect,
  shutdown, request-handle, worker-command, worker-stream, and worker-exit
  projections, no additional pure `src/remote.rs` helper/facade branch is
  currently tracked except the bounded sender helper added on 2026-06-19.
  The select-timing helper added on 2026-06-19 closes the final tracked timing
  boundary by documenting Rust's lack of stable branch-order guarantees.
- No tracked `src/remote.rs` helper/facade branch remains open. Python still
  delegates the concrete websocket scheduler/state machine to
  `pycodex.exec.session`, which is this module's intended transport boundary.
  Remote event delivery is unbounded in `src/remote.rs`; `Lagged` marker
  synthesis belongs to the crate-root in-process event forwarding/backpressure
  contract, not this remote module.

## Evidence

- Rust source:
  `codex/codex-rs/app-server-client/src/remote.rs`
- Python validation:
  `python -m py_compile pycodex/app_server_client/__init__.py tests/test_app_server_client_remote_rs.py`
  and `python -m pytest tests/test_app_server_client_remote_rs.py -q`
  passed on 2026-06-19 (`127 passed`).
- Rust tests in this crate cover auth policy, JSON-RPC projection, large frame
  config, remote initialization, websocket/UDS round trips, server requests,
  backpressure, disconnect, and shutdown.
- Named Rust remote tests are now accounted for in Python parity coverage or
  status debt: `shutdown_tolerates_worker_exit_after_command_is_queued`,
  `remote_typed_request_roundtrip_works`,
  `remote_unix_socket_typed_request_roundtrip_works`,
  `remote_typed_request_accepts_large_single_frame_response`,
  `remote_connect_includes_auth_header_when_configured`,
  `remote_connect_rejects_non_loopback_ws_when_auth_configured`,
  `remote_auth_token_transport_policy_allows_wss_and_loopback_ws`,
  `remote_duplicate_request_id_keeps_original_waiter`,
  `remote_notifications_arrive_over_websocket`,
  `remote_backpressure_preserves_transcript_notifications`,
  `remote_server_request_resolution_roundtrip_works`,
  `remote_server_request_received_during_initialize_is_delivered`,
  `remote_unknown_server_request_is_rejected`, and
  `remote_disconnect_surfaces_as_event`.
- Python parity tests in `tests/test_app_server_client_remote_rs.py` cover the
  currently mapped helper, stateful facade, `exec.session` wire-client bridge,
  connected request handles, initialize pending events, initialize-time
  server-request resolution roundtrip, initialize-time
  non-matching response/error ignoring, initialize-time non-text websocket
  frame ignoring, initialize rejection error mapping, initialize close-frame
  error mapping, initialize non-close error-text projection, initialize EOF error mapping, initialize transport-failure
  error mapping, initialize timeout error mapping, initialize invalid-response
  error mapping, initialize handshake write/wait sequence projection,
  initialize frame-handling projection, initialize request write-failure error mapping,
  initialized-notification write-failure error mapping, initialize `userAgent`
  server-version parsing including malformed/blank user-agent omission,
  Unix socket handshake and typed request roundtrip, Unix socket connector and
  upgrade error-text projection, Unix socket connector
  timeout/failure/invalid-input mapping, websocket typed `account/read`
  roundtrip, non-loopback `ws://` auth rejection before connector invocation,
  WebSocket connector error-text projection, websocket/Unix connector setup
  projection, remote connect dispatch projection, connect-with-stream lifecycle
  projection, invalid websocket URL rejection, supported
  `wss://` and loopback `ws://` auth-token forwarding, invalid authorization
  header rejection, timeout mapping, connector invalid-input mapping, generic
  connector-failure mapping,
  known/unknown
  notification helper behavior,
  account-updated notification delivery,
  transcript notification stream ordering,
  notification stream filtering, non-text
  websocket frame ignoring, invalid runtime JSON-RPC disconnect events,
  websocket close-frame disconnected events including Rust's
  `remote_disconnect_surfaces_as_event`, websocket EOF closed-connection
  events, websocket transport-failure disconnected events, supported server
  requests, server-request resolution roundtrip, unknown server-request
  rejection including `thread/unknown`, duplicate request-id behavior
  including typed `account/read` transport-error mapping and original-waiter
  preservation,
  large single-frame typed response decoding,
  typed request transport/server/deserialize error mapping,
  request write-failure disconnected event delivery,
  request-response close/disconnect error plus companion disconnected event
  delivery,
  request-response invalid-message error plus companion disconnected event
  delivery,
  request-response transport-failure error plus companion disconnected event
  delivery,
  interleaved request/notification event preservation and unknown notification
  ignoring,
  interleaved request/server-request event preservation,
  interleaved request/unknown-server-request rejection,
  unsupported server-request rejection write-failure disconnected event
  delivery,
  request/notification/server-request response write-failure mapping, remote
  command entrypoint send/response-channel projection, remote worker command
  match-branch projection, remote worker stream-message match projection, remote
  command-channel-closed projection, remote worker channel
  topology projection, remote next-event pending-event drain projection,
  worker exit pending-request error fan-out projection, shutdown
  control-flow projection, shutdown close-error mapping including
  endpoint-qualified close-failure helper projection, shutdown
  already-closed close-error tolerance including direct wire-client
  `ConnectionResetError`, and shutdown
  worker-closed tolerance, plus the bridge projection of effective command
  channel capacity, worker-closed command error mapping, and operation-specific
  command response-channel closure mapping, plus request-handle closure error
  propagation and request-handle typed server/deserialize wrapping, but are not
  run yet because the crate functional code is not complete.
- `remote_request_handle_projection(...)` mirrors
  `RemoteAppServerClient::request_handle(...)`: clone the command sender into a
  handle, without owning the event receiver or server version, and reuse the
  request/request_typed command path.
