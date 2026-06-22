# codex-login src/lib.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/lib.rs`

Python module: `pycodex/login/__init__.py`

Status: `complete_slice`

## Behavior Contract

`src/lib.rs` is the crate-root import surface for `codex-login`. It declares
the crate modules and re-exports the public auth, device-code, server,
telemetry, and token-data symbols used by sibling crates.

This Python slice maps the root surface to `pycodex.login` and exposes the
completed child-module contracts from:

- `auth`
- `auth_env_telemetry`
- `token_data`
- `device_code_auth`
- `server`

## Python Mapping

- Rust `pub mod auth` maps to the `pycodex.login.auth` package and the root
  `auth` export.
- Rust `pub mod auth_env_telemetry` maps to
  `pycodex.login.auth_env_telemetry` exports.
- Rust `pub mod token_data` maps to `pycodex.login.TokenData`.
- Rust private `device_code_auth` with public crate-root re-exports maps to
  `DeviceCode`, `request_device_code`, `complete_device_code_login`, and
  `run_device_code_login`.
- Rust private `server` with public crate-root re-exports maps to
  `LoginServer`, `ServerOptions`, `ShutdownHandle`, and `run_login_server`.
- Rust `BuildLoginHttpClientError` is represented as Python `OSError`, matching
  the standard-library network/client error shape used by this port.
- Existing compatibility exports backed by `pycodex.cli.login` remain available
  while the broad `src/auth/manager.rs` login/logout API is still pending.

## Deferred Neighbors

This slice does not implement `src/auth/manager.rs`. Crate-root names owned by
that module remain tracked as follow-up debt until the owning module is ported.

## Validation

Actual test execution is deferred by the current crate automation rule until
`codex-login` functional code is complete.
