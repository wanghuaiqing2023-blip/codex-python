# codex-login `src/auth/revoke.rs` alignment status

Status: `complete_candidate`

Rust module: `codex/codex-rs/login/src/auth/revoke.rs`

Python module: `pycodex/login/auth/revoke.py`

## Behavior Contract

This module owns best-effort OAuth token revocation for managed ChatGPT auth
cleanup:

- Select the revocable token from `AuthDotJson`, preferring refresh token over
  access token.
- Treat only resolved ChatGPT auth as managed token auth.
- Decide whether previous auth should be revoked when replacement auth is
  written.
- Build OAuth revoke request payloads, including `client_id` only for refresh
  token revocation.
- Resolve the revoke endpoint from explicit revoke override, derived refresh
  endpoint override, or the production default.
- Report failed revoke responses with parsed OpenAI error messages.

## Python Mapping

- `RevokeTokenKind` mirrors the Rust enum and helper methods.
- `revocable_token`, `managed_chatgpt_tokens`, `resolved_auth_mode`, and
  `should_revoke_auth_tokens` mirror Rust's private helper contracts.
- `revoke_oauth_token` uses a dependency-light standard-library HTTP transport
  by default and accepts an injectable client for parity tests.
- `revoke_auth_tokens` preserves Rust's no-op behavior when no managed token is
  revocable.

## Rust Evidence

Rust tests mirrored in `tests/test_login_auth_revoke.py`:

- `derives_revoke_url_from_refresh_token_override`
- `revoke_request_times_out` is represented by the injectable-client timeout
  and error propagation contract instead of a networked wiremock server.

Additional Python parity tests cover source-level helper contracts from
`src/auth/revoke.rs`:

- resolved auth mode fallback rules.
- managed ChatGPT token filtering.
- refresh-before-access token selection.
- replacement auth revoke decisions.
- endpoint override precedence.
- access vs refresh revoke payload JSON.
- failed response error-message formatting.

## Known Adaptations

- Rust uses `CodexHttpClient`/`reqwest`; Python uses the standard library
  `urllib` in a small async wrapper to avoid adding third-party dependencies.
- `manager.rs` still owns the canonical constants in Rust. Python keeps the
  compatible constants here without expanding the heartbeat scope to the manager
  module.
- Actual test execution is deferred by the active crate automation policy until
  `codex-login` functional code is complete.
