# app-server-protocol `protocol/v2/hook.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/hook.rs`

Python target: `pycodex/app_server_protocol/hook.py`

Status: implemented module contract.

## Covered Rust items

- `HookEventName`
- `HookHandlerType`
- `HookExecutionMode`
- `HookScope`
- `HookSource`
- `HookTrustStatus`
- `HookRunStatus`
- `HookOutputEntryKind`
- `HookOutputEntry`
- `HookRunSummary`
- `HookStartedNotification`
- `HookCompletedNotification`

## Notes

- Enum wire values mirror Rust `v2_enum_from_core!` camelCase serde values.
- `HookRunSummary.source` defaults to `HookSource.UNKNOWN`, matching Rust
  `default_hook_source()`.
- `source_path` enforces the Rust `AbsolutePathBuf` absolute-path invariant.
- Notification payloads accept Rust camelCase keys and emit Rust wire names
  through `to_camel_mapping()`.

## Validation

- Compile check: `python -m py_compile pycodex/app_server_protocol/hook.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed output entry, run summary defaults, started/completed
  notifications, and representative enum wire values.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
