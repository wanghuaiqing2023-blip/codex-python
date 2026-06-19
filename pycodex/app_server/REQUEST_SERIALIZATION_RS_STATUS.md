# codex-app-server/src/request_serialization.rs status

Rust source:

- `codex/codex-rs/app-server/src/request_serialization.rs`

Python target:

- `pycodex/app_server/request_serialization.py`

Status: `complete`

## Covered contract

- `RequestSerializationQueueKey.from_scope(...)` maps every Rust
  `ClientRequestSerializationScope` variant to the app-server queue key and
  access mode, including connection-scoped command/process/fs-watch variants.
- `RequestSerializationAccess` preserves exclusive versus shared-read modes.
- `QueuedInitializedRequest.run(...)` delegates through `ConnectionRpcGate` so
  closed gates skip queued requests while live gates run handlers.
- `RequestSerializationQueues.enqueue(...)` creates one drain worker per new
  key and appends later requests to the existing key queue.
- Same-key exclusive requests run FIFO.
- Different keys drain concurrently.
- Closed-gate requests are skipped and later requests for the same key
  continue.
- Gate shutdown skips already-queued requests that have not entered the gate.
- Contiguous shared reads for the same key are drained together.
- Exclusive writes wait behind running shared reads, and later shared reads do
  not jump ahead of a queued exclusive write.

## Deferred boundaries

- Rust `tokio::spawn`, `tracing::debug_span`, `Instrument`, and
  `futures::join_all` are represented with `asyncio` task/gather primitives.
- Exact Tokio scheduler timing and wake ordering remain runtime details.
- The concrete request handlers and JSON-RPC request processor integration
  remain neighboring module/runtime boundaries.

## Python parity tests

- `tests/test_app_server_request_serialization_rs.py`

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_request_serialization_rs.py -q`
  -> 8 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/request_serialization.py tests/test_app_server_request_serialization_rs.py`.
