# codex-login src/auth/mod.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/auth/mod.rs`

Python module: `pycodex/login/auth/__init__.py`

Status: `complete_slice`

## Behavior Contract

`src/auth/mod.rs` is the Rust auth subtree aggregation boundary. It declares
the internal auth modules and exposes:

- public submodules: `default_client`, `error`
- private implementation modules: `agent_identity`, `storage`, `util`,
  `external_bearer`, `manager`, `revoke`
- public re-exports from `error`
- public re-exports from `manager::*`
- crate-internal re-exports of `revoke_auth_tokens` and
  `should_revoke_auth_tokens`

The Python package maps that aggregation boundary to
`pycodex.login.auth.__init__`. Completed child-module exports are surfaced
there so callers can use the auth package as the canonical import surface while
`src/auth/manager.rs` remains a separate pending module.

## Python Mapping

- `RefreshTokenFailedError` and `RefreshTokenFailedReason` are re-exported from
  `pycodex.login.auth.error`.
- `default_client` is exposed as a public submodule.
- Completed auth child contracts are re-exported from
  `agent_identity`, `external_bearer`, `storage`, `revoke`, and `util`.
- `revoke_auth_tokens` and `should_revoke_auth_tokens` are intentionally
  available from the Python package despite Rust's `pub(crate)` visibility,
  because Python has no crate-private namespace and the functions are already
  used as compatibility helpers in this package.

## Deferred Neighbor

`src/auth/manager.rs` is not implemented by this module slice. Its broad auth
manager types and login/logout flows remain tracked separately, and this slice
does not claim that `manager::*` is complete.

## Validation

Actual test execution is deferred by the current crate automation rule until
`codex-login` functional code is complete.
