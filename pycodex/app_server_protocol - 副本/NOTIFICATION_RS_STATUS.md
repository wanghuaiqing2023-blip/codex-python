# app-server-protocol `protocol/v2/notification.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/notification.rs`

Python target: `pycodex/app_server_protocol/notification.py`

Status: implemented module contract.

## Covered Rust items

- `DeprecationNoticeNotification`
- `WarningNotification`
- `GuardianWarningNotification`
- `ErrorNotification`
- `ServerRequestResolvedNotification`

## Notes

- Notification structs accept Rust serde camelCase keys and emit Rust wire
  names through `to_camel_mapping()`.
- `ServerRequestResolvedNotification` reuses `pycodex.protocol.RequestId` to
  preserve Rust's untagged string-or-integer request id behavior.
- `ErrorNotification.error` is treated as a TurnError-compatible
  mapping/object. The owning `TurnError` type lives in `protocol/v2/thread_data.rs`
  and remains a separate module boundary.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/notification.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed deprecation, warning, guardian warning, error, and
  server request resolution notifications, including integer and string
  request ids.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
