# `src/in_process.rs` Alignment Status

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/in_process.rs`

Python mapping:

- `pycodex/app_server/in_process.py`
- `tests/test_app_server_in_process_rs.py`

Mapped behavior contract:

- `IN_PROCESS_CONNECTION_ID`, `SHUTDOWN_TIMEOUT`, and
  `DEFAULT_IN_PROCESS_CHANNEL_CAPACITY` local constants.
- `InProcessStartArgs` state shape and `channel_capacity.max(1)` behavior.
- `InProcessServerEvent`, `InProcessClientMessage`, and `ProcessorCommand`
  local variant shapes.
- `InProcessClientSender::try_send_client_message` queue-full and closed-runtime
  error mapping.
- `start(...)` initialize/initialized handshake projection, including
  initialize-error shutdown and `InvalidData` error prefix.
- Runtime loop request bookkeeping for duplicate request IDs, full/closed
  processor queues, notification queue saturation, server-request event
  backpressure, guaranteed terminal notification delivery, shutdown request ack,
  and pending request error fan-out.

Rust local tests mirrored:

- `in_process_start_initializes_and_handles_typed_v2_request`
- `in_process_start_uses_requested_session_source_for_thread_start`
- `in_process_start_clamps_zero_channel_capacity`
- `guaranteed_delivery_helpers_cover_terminal_server_notifications`

Deferred dependency/runtime boundaries:

- Real Tokio task spawning, `mpsc`/`oneshot` timing, `MessageProcessor`
  execution, real initialize/config/thread-start handlers, outbound routing
  execution, auth/config/state DB construction, and concrete queue scheduling.
- The Python module is a deterministic projection of the module-owned runtime
  control contract, not a live embedded app-server runtime.

Validation:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_in_process_rs.py -q` -> 11 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/in_process.py tests/test_app_server_in_process_rs.py`.
