# app-server-protocol `protocol/v2/remote_control.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/remote_control.rs`

Python target: `pycodex/app_server_protocol/remote_control.py`

Status: implemented module contract.

## Covered Rust items

- `RemoteControlStatusChangedNotification`
- `RemoteControlEnableResponse`
- `RemoteControlDisableResponse`
- `RemoteControlStatusReadResponse`
- `RemoteControlConnectionStatus`
- `From<RemoteControlStatusChangedNotification> for
  RemoteControlEnableResponse` via `to_enable_response()` and
  `RemoteControlEnableResponse.from_notification()`
- `From<RemoteControlStatusChangedNotification> for
  RemoteControlDisableResponse` via `to_disable_response()` and
  `RemoteControlDisableResponse.from_notification()`

## Notes

- Enum wire values mirror Rust `serde(rename_all = "camelCase")`:
  `disabled`, `connecting`, `connected`, and `errored`.
- Mapping helpers accept Rust camelCase and Python snake_case field names.
- The response conversion helpers move the same four fields as the Rust
  `From` implementations.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/remote_control.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed enum values, round-tripped camelCase mappings, and
  converted a status-changed notification into enable/disable responses.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
