# app-server-protocol `protocol/v2/process.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/process.rs`

Python target: `pycodex/app_server_protocol/process.py`

Status: implemented module contract.

## Covered Rust items

- `ProcessTerminalSize`
- `ProcessSpawnParams`
- `ProcessSpawnResponse`
- `ProcessWriteStdinParams`
- `ProcessWriteStdinResponse`
- `ProcessKillParams`
- `ProcessKillResponse`
- `ProcessResizePtyParams`
- `ProcessResizePtyResponse`
- `ProcessOutputStream`
- `ProcessOutputDeltaNotification`
- `ProcessExitedNotification`

## Notes

- `cwd` follows Rust's `AbsolutePathBuf` contract and must be absolute.
- `output_bytes_cap` and `timeout_ms` preserve Rust's
  `Option<Option<T>>` serde behavior with an `UNSET` sentinel for omitted
  fields, `None` for explicit JSON `null`, and integers for concrete values.
- Boolean defaults with Rust `skip_serializing_if` are omitted from serialized
  mappings when false.
- `ProcessOutputStream` mirrors Rust camelCase serde values: `stdout` and
  `stderr`.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/process.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed terminal size, spawn params with omitted/null/concrete
  double-option fields, empty responses, stdin write defaults, kill, resize,
  output delta, and exit notifications.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
