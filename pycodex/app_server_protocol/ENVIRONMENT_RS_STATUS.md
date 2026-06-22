# app-server-protocol `protocol/v2/environment.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/environment.rs`

Python target: `pycodex/app_server_protocol/environment.py`

Status: implemented module contract.

## Covered Rust items

- `EnvironmentAddParams`
- `EnvironmentAddResponse`

## Notes

- `EnvironmentAddParams.from_mapping()` accepts Rust serde camelCase keys
  (`environmentId`, `execServerUrl`) and Python snake_case keys.
- `to_mapping()` preserves Python snake_case compatibility.
- `to_camel_mapping()` emits the Rust protocol wire names.
- `EnvironmentAddResponse` is an empty response object, matching the Rust
  empty struct.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/environment.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: constructed params from camelCase input, checked snake/camel
  output, and constructed the empty response.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
