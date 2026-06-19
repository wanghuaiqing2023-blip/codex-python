# codex-login src/server.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/server.rs`

Python module: `pycodex/login/server.py`

Status: `complete_slice`

## Behavior Contract

`src/server.rs` owns the local OAuth callback server and helper behavior around
interactive ChatGPT login:

- default issuer and callback port selection
- server option, login-server, and shutdown-handle types
- authorization URL construction with PKCE, state, scope, originator, and
  optional workspace constraints
- callback path handling for success, cancellation, state mismatch, OAuth
  errors, and missing authorization codes
- authorization-code token exchange
- token persistence and best-effort revoke of superseded managed ChatGPT tokens
- workspace restriction checks based on ID token claims
- success URL composition, token endpoint error parsing, HTML escaping, and
  sensitive URL/query redaction

The Python module mirrors these interfaces with standard-library HTTP and
urllib primitives. Long-running server behavior is intentionally lightweight but
keeps the Rust callback and helper semantics available for the CLI/core runtime.

## Python Mapping

- `ServerOptions`, `LoginServer`, and `ShutdownHandle` map the Rust public
  structs.
- `run_login_server` starts a short-lived localhost callback server and returns
  a `LoginServer` with an auth URL and cancel handle.
- `exchange_code_for_tokens`, `persist_tokens_async`,
  `ensure_workspace_allowed`, and `obtain_api_key` map the Rust crate-internal
  helper APIs used by `device_code_auth.rs`.
- `build_authorize_url`, `compose_success_url`,
  `parse_token_endpoint_error`, `render_login_error_page`,
  `sanitize_url_for_logging`, and related helpers cover the pure behavior tested
  in Rust.
- `pycodex.login.device_code_auth` now imports `ServerOptions` and default
  callbacks from this module, avoiding a duplicate server-owned type.

## Deferred Neighbor

`src/auth/manager.rs` remains the only pending `codex-login` module. This slice
uses the existing storage/revoke child-module APIs directly and does not claim
the manager-owned login/logout/auth-refresh surface.

## Validation

Actual test execution is deferred by the current crate automation rule until
`codex-login` functional code is complete.
