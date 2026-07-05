# app-server-protocol `protocol/v2/feedback.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/feedback.rs`

Python target: `pycodex/app_server_protocol/feedback.py`

Status: implemented module contract.

## Covered Rust items

- `FeedbackUploadParams`
- `FeedbackUploadResponse`

## Notes

- `FeedbackUploadParams.from_mapping()` accepts Rust serde camelCase keys
  (`threadId`, `includeLogs`, `extraLogFiles`) and Python snake_case keys.
- `include_logs` defaults to `False`; `to_mapping()` and `to_camel_mapping()`
  omit it when false, matching Rust's `skip_serializing_if`.
- `extra_log_files` accepts path strings or `pathlib.Path` values and emits
  JSON path strings, matching Rust `PathBuf` JSON behavior.
- `tags` preserves Rust's string-to-string map contract.

## Validation

- Compile check: `python -m py_compile pycodex/app_server_protocol/feedback.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: constructed params from camelCase input, checked
  `include_logs` omission/default behavior, path serialization, and response
  thread-id mapping.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
