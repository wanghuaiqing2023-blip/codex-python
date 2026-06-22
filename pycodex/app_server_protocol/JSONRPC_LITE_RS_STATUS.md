# jsonrpc_lite.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/jsonrpc_lite.rs`

Python module: `pycodex/app_server_protocol/jsonrpc_lite.py`

Status: complete for the module-scoped lite JSON-RPC protocol data contract.

## Covered

- `JSONRPC_VERSION` constant and `Result` JSON value alias.
- `RequestId` untagged string-or-i64 behavior via the existing
  `pycodex.protocol.RequestId` value type.
- `JSONRPCRequest`, `JSONRPCNotification`, `JSONRPCResponse`, `JSONRPCError`,
  and `JSONRPCErrorError` envelope shapes.
- `JSONRPCMessage` request/notification/response/error classification from
  mappings.
- Optional field omission for request `params`, request `trace`, notification
  `params`, and error `data`.

## Intentional Adaptations

- Python reuses the existing `RequestId` implementation that already mirrors
  Rust's untagged string-or-i64 request id behavior.
- This module does not implement transport encoding, websocket handling, or
  app-server request routing; those are owned by other Rust modules/crates.
- Like Rust, serialized mappings do not include a top-level `jsonrpc` field
  even though `JSONRPC_VERSION` is exposed as `"2.0"`.

## Validation

- `python -m py_compile pycodex/app_server_protocol/jsonrpc_lite.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered request id parsing/display, request/notification/
  response/error serialization, optional field omission, message
  classification, i64 validation, and package exports.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
