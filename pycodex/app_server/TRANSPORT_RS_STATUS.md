# codex-app-server src/transport.rs alignment

Rust module:

`codex/codex-rs/app-server/src/transport.rs`

Python target:

`pycodex/app_server/transport.py`

Status: `complete`

## Covered

- `TRANSPORT_PUBLIC_REEXPORTS`, `TRANSPORT_CRATE_REEXPORTS`, and
  `transport_reexport_surface_projection(...)` mirror the module's
  `pub use`/`pub(crate) use` surface from `codex_app_server_transport`,
  including transport type, connection/message/event types, path helpers,
  acceptor startup functions, and remote-control items.
- `ConnectionStateProjection` and `connection_state_projection(...)` mirror
  `ConnectionState::new(...)`: the origin argument is intentionally ignored,
  the outbound initialized/experimental/opt-out shared state is retained, and
  a fresh `ConnectionSessionState` is created.
- `OutboundConnectionStateProjection` mirrors the local outbound routing fields
  used by `OutboundConnectionState`: initialized state, experimental API
  capability, opted-out notification method set, writer queue state, writer
  closed state, and optional disconnect token presence.
- `disconnect_connection_projection(...)` mirrors the local helper that removes
  a known outbound connection, requests disconnect only when a disconnect token
  exists, and returns false without side effects for unknown connection IDs.
- `should_skip_notification_for_connection(...)` mirrors Rust's outbound
  notification filtering: non-notifications are never skipped, unreadable
  opted-out state warns and does not skip, experimental notifications are
  dropped when the connection lacks experimental capability, and opted-out
  notification methods are dropped by their wire method string.
- `filter_outgoing_message_for_connection(...)` mirrors Rust's
  `CommandExecutionRequestApproval` compatibility filter: when experimental API
  is disabled, `additionalPermissions`/`additional_permissions` are stripped
  from approval params; experimental-capable connections receive the original
  message.
- `route_outgoing_envelope_projection(...)` mirrors the pure routing decisions
  in `route_outgoing_envelope(...)`: direct sends drop unknown connections,
  broadcasts target initialized and unfiltered connections, disconnectable
  full/closed writers are removed, non-disconnectable full writers wait rather
  than disconnect, write-complete senders stay scoped to direct sends, and
  remaining connection IDs are reported after routing.

## Deferred dependency/runtime boundaries

- Real `mpsc::Sender<QueuedOutgoingMessage>` behavior is represented only as a
  queue-state projection; no async channel, websocket writer, or oneshot
  completion is executed in this module-scoped contract.
- Transport acceptor functions are recorded as re-exported names here, but
  their real async acceptor implementations remain in the
  `codex-app-server-transport` crate and are not executed by this module.
- Exact protocol enum classes are not required here; the projection accepts
  mapping/object messages with Rust-aligned `kind`, `method`, `request`, and
  `params` fields.
- No further local `src/transport.rs` item/function is currently tracked as a
  module-scoped gap.

## Evidence

- Rust source:
  `codex/codex-rs/app-server/src/transport.rs`
- Rust tests:
  `codex/codex-rs/app-server/src/transport_tests.rs`
- Rust protocol source for the hard-coded approval filter:
  `codex/codex-rs/app-server-protocol/src/protocol/v2/item.rs`
- Python tests:
  `tests/test_app_server_transport_rs.py`

## Validation

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_transport_rs.py -q` -> 13 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/transport.py tests/test_app_server_transport_rs.py`.
