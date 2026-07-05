# app-server-protocol `protocol/v2/windows_sandbox.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/windows_sandbox.rs`

Python target: `pycodex/app_server_protocol/windows_sandbox.py`

Status: implemented module contract.

## Covered Rust items

- `WindowsWorldWritableWarningNotification`
- `WindowsSandboxSetupMode`
- `WindowsSandboxReadiness`
- `WindowsSandboxSetupStartParams`
- `WindowsSandboxSetupStartResponse`
- `WindowsSandboxReadinessResponse`
- `WindowsSandboxSetupCompletedNotification`

## Notes

- Enum wire values mirror Rust `serde(rename_all = "camelCase")`:
  `elevated`, `unelevated`, `ready`, `notConfigured`, and `updateRequired`.
- `WindowsSandboxSetupStartParams.cwd` accepts a path string or `Path` and
  enforces an absolute path when present, matching Rust `AbsolutePathBuf`.
- Struct mapping helpers accept Python snake_case and Rust camelCase for fields
  whose names differ.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/windows_sandbox.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed enums, round-tripped warning fields, setup params,
  readiness response, and setup-completed notification.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
