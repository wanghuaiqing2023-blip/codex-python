# codex-app-server/src/message_processor.rs alignment

Status: `complete`

Rust module: `codex/codex-rs/app-server/src/message_processor.rs`

Python module: `pycodex/app_server/message_processor.py`

Python tests: `tests/test_app_server_message_processor_rs.py`

## Behavior contract

This module owns the app-server message processing shell:

- `ConnectionSessionState` defaults, initialized-state queries, and one-time
  initialization semantics.
- `ExternalAuthRefreshBridge` ChatGPT auth mode, Unauthorized reason mapping,
  refresh request payload projection, timeout cancellation, and response/error
  mapping.
- `MessageProcessorArgs` dependency inventory and `MessageProcessor.new(...)`
  external-auth bridge installation boundary.
- JSON-RPC request deserialization into `ClientRequest`, request-context
  registration, initialize-first routing, invalid request error projection, and
  typed in-process request handling.
- Initialized-request gate, experimental API gate, initialized-request tracking,
  injectable child-processor dispatch, `Ok(Some(_))` response emission,
  `Ok(None)` no-response behavior, and child error emission.
- JSON-RPC response/error callback forwarding.
- Runtime cleanup ordering for `clear_runtime_references(...)` and
  `connection_closed(...)`.

Full construction of every concrete child request processor, async queue
execution, tracing spans, and Tokio task scheduling remain runtime boundaries
owned by neighboring modules or the crate root.

## Evidence

- Rust source: `codex/codex-rs/app-server/src/message_processor.rs`
- Python parity tests: `tests/test_app_server_message_processor_rs.py`

- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_message_processor_rs.py -q` -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/message_processor.py tests/test_app_server_message_processor_rs.py`.
