# codex-app-server src/dynamic_tools.rs status

Rust module: `codex/codex-rs/app-server/src/dynamic_tools.rs`

Python module: `pycodex/app_server/dynamic_tools.py`

Status: `complete`

## Covered

- `decode_response(...)` mirrors the Rust `serde_json::from_value`
  branch for `DynamicToolCallResponse`, including the invalid-response
  fallback message.
- `fallback_response(...)` mirrors Rust's failed response shape: one
  `inputText` content item and `success = false`.
- `core_response_from_app_server_response(...)` mirrors the app-server
  protocol item conversion into core `codex_protocol::dynamic_tools`
  response items.
- `on_call_response_projection(...)` records Rust's local handler
  decision tree for success, turn-transition server request errors,
  non-turn-transition client errors, and canceled receiver errors, plus
  the shaped `Op.dynamic_tool_response(...)` submission.

## Deferred

- Real Tokio `oneshot::Receiver` awaiting and `CodexThread::submit(...)`
  execution remain runtime integration work.
- Tracing side effects are represented as projected log categories rather
  than emitted through a Rust-compatible tracing subscriber.

## Python parity tests

- `tests/test_app_server_dynamic_tools_rs.py`

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_dynamic_tools_rs.py -q`
  -> 8 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/dynamic_tools.py tests/test_app_server_dynamic_tools_rs.py`.
