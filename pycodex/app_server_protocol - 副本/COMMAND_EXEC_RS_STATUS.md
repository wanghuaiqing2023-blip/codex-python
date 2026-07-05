# app-server-protocol `protocol/v2/command_exec.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/command_exec.rs`

Python target: `pycodex/app_server_protocol/command_exec.py`

Status: implemented module contract.

## Covered Rust items

- `CommandExecTerminalSize`
- `CommandExecParams`
- `CommandExecResponse`
- `CommandExecWriteParams`
- `CommandExecWriteResponse`
- `CommandExecTerminateParams`
- `CommandExecTerminateResponse`
- `CommandExecResizeParams`
- `CommandExecResizeResponse`
- `CommandExecOutputStream`
- `CommandExecOutputDeltaNotification`

## Notes

- `cwd` follows Rust's plain `PathBuf` contract and therefore accepts relative
  or absolute path strings.
- Boolean defaults with Rust `skip_serializing_if` are omitted from serialized
  mappings when false.
- `CommandExecOutputStream` mirrors Rust camelCase serde values: `stdout` and
  `stderr`.
- `sandbox_policy` is represented as a SandboxPolicy-compatible mapping/object
  because `SandboxPolicy` is owned by a neighboring protocol module and is
  outside this module's implementation boundary.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/command_exec.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed terminal size, command exec params with default omitted
  booleans and optional nullable fields, sandbox policy mapping preservation,
  response payloads, stdin write defaults, terminate, resize, and output delta
  notifications.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
