# pycodex.login

This package contains the Python public import surface for the Rust `codex-login`
crate.

## Rust Counterpart

```text
Rust crate: codex-login
Rust path: codex/codex-rs/login
```

## Alignment Role

`pycodex.login` should own authentication/account persistence behavior that is
not merely a CLI command surface.

The current implementation is still provided by `pycodex.cli.login`, and this
package currently re-exports that implementation to preserve the public import
shape while the tree is being reorganized.

## Rust Module Areas

Typical Rust sources to inspect before changing this package:

```text
codex/codex-rs/login/src/lib.rs
codex/codex-rs/login/src/**/*.rs
```

Related CLI command behavior may also involve:

```text
codex/codex-rs/cli/src/main.rs
```

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
login.auth_file
login.auth_mode_resolution
login.chatgpt_oauth_flow
login.account_display
```

## Test Source Policy

Prefer Rust login tests and Rust source behavior before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-login
# Rust module: src/lib.rs
# Rust test: tests::example_test_name
# Contract: login.auth_file
```

## Current Movement Status

The former root module `pycodex/login.py` has been moved to this package as
`pycodex/login/__init__.py`.

The concrete implementation still lives in `pycodex.cli.login`; future work may
move non-CLI authentication logic from `pycodex.cli.login` into this package and
leave CLI-only command handling under `pycodex.cli`.

## Certified Modules

- `codex/codex-rs/login/src/lib.rs` is mapped to
  `pycodex/login/__init__.py`; see `pycodex/login/LIB_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/mod.rs` is mapped to
  `pycodex/login/auth/__init__.py`; see
  `pycodex/login/AUTH_MOD_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/manager.rs` is mapped to
  `pycodex/login/auth/manager.py`; see
  `pycodex/login/AUTH_MANAGER_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth_env_telemetry.rs` is mapped to
  `pycodex/login/auth_env_telemetry.py`; see
  `pycodex/login/AUTH_ENV_TELEMETRY_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/agent_identity.rs` is mapped to
  `pycodex/login/auth/agent_identity.py`; see
  `pycodex/login/AUTH_AGENT_IDENTITY_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/default_client.rs` is mapped to
  `pycodex/login/auth/default_client.py`; see
  `pycodex/login/AUTH_DEFAULT_CLIENT_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/error.rs` is mapped to
  `pycodex/login/auth/error.py`; see `pycodex/login/AUTH_ERROR_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/external_bearer.rs` is mapped to
  `pycodex/login/auth/external_bearer.py`; see
  `pycodex/login/AUTH_EXTERNAL_BEARER_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/revoke.rs` is mapped to
  `pycodex/login/auth/revoke.py`; see
  `pycodex/login/AUTH_REVOKE_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/storage.rs` is mapped to
  `pycodex/login/auth/storage.py`; see
  `pycodex/login/AUTH_STORAGE_RS_STATUS.md`.
- `codex/codex-rs/login/src/auth/util.rs` is mapped to
  `pycodex/login/auth/util.py`; see `pycodex/login/AUTH_UTIL_RS_STATUS.md`.
- `codex/codex-rs/login/src/device_code_auth.rs` is mapped to
  `pycodex/login/device_code_auth.py`; see
  `pycodex/login/DEVICE_CODE_AUTH_RS_STATUS.md`.
- `codex/codex-rs/login/src/pkce.rs` is mapped to
  `pycodex/login/pkce.py`; see `pycodex/login/PKCE_RS_STATUS.md`.
- `codex/codex-rs/login/src/server.rs` is mapped to
  `pycodex/login/server.py`; see `pycodex/login/SERVER_RS_STATUS.md`.
- `codex/codex-rs/login/src/token_data.rs` is mapped to
  `pycodex/login/token_data.py`; see `pycodex/login/TOKEN_DATA_RS_STATUS.md`.
