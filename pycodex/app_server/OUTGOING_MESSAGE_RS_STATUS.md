# src/outgoing_message.rs alignment

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/outgoing_message.rs`

Python mapping:

- `pycodex/app_server/outgoing_message.py`
- `tests/test_app_server_outgoing_message_rs.py`

Covered behavior:

- `ConnectionRequestId`, `RequestContext`, `OutgoingEnvelope`,
  `OutgoingMessage`, `OutgoingResponse`, and `OutgoingError` local shapes.
- `OutgoingMessageSender` request ID allocation, pending callback storage,
  broadcast request sending, targeted request sending, and send-failure callback
  cleanup projection.
- Request-context registration, connection-close cleanup, trace lookup, and
  turn-id recording hook.
- Client response/error callback notification and request cancellation.
- Pending requests for a thread returned in request-id order.
- Thread-scoped request sending, server notification targeting, global
  notification forwarding, and turn-transition abort error shaping.
- Response/error routing to the target connection and server-notification
  broadcast/targeted/wait-for-write-complete envelopes.

Deferred boundaries:

- Concrete `codex-app-server-transport` writer behavior remains owned by the
  transport module.
- Exact `tokio::mpsc` backpressure, oneshot close errors, tracing span
  instrumentation, and warning text are represented as Python queue/future
  behavior.
- Full typed `ServerRequest::response_from_result(...)` decoding and
  notification JSON method serialization remain owned by
  `codex-app-server-protocol`.
- Analytics calls are preserved as optional hook calls, but real
  `AnalyticsEventsClient` event payloads remain an integration boundary.
- `python -m pytest tests/test_app_server_outgoing_message_rs.py -q` passed on
  2026-06-19 with 10 tests.
- `python -m py_compile pycodex/app_server/outgoing_message.py
  tests/test_app_server_outgoing_message_rs.py` passed on 2026-06-19.
