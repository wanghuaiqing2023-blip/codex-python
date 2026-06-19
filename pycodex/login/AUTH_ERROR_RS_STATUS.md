# auth/error.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/auth/error.rs`

Python module: `pycodex/login/auth/error.py`

Status: `complete`

Aligned behavior:

- Re-exports `RefreshTokenFailedError` from `pycodex.protocol.auth`, matching
  Rust's `pub use codex_protocol::auth::RefreshTokenFailedError`.
- Re-exports `RefreshTokenFailedReason` from `pycodex.protocol.auth`, matching
  Rust's `pub use codex_protocol::auth::RefreshTokenFailedReason`.
- The same protocol error classes are also surfaced through `pycodex.login.auth`
  and `pycodex.login` compatibility imports.

Python parity coverage:

- `tests/test_login_auth_error.py::test_login_auth_error_reexports_protocol_refresh_failure_types`
- `tests/test_login_auth_error.py::test_login_auth_error_preserves_protocol_error_behavior`

Validation:

- Not run in this turn; current automation defers actual test execution until the crate functional code is complete.
