# codex-login src/auth/manager.rs alignment

Rust module: `codex/codex-rs/login/src/auth/manager.rs`

Python module: `pycodex/login/auth/manager.py`

Status: `complete_candidate`

## Scope

This module owns the login authentication manager contract: auth mode records,
environment credential lookup, persisted auth loading/saving, login/logout
helpers, forced-login restrictions, refresh-token failure classification,
external ChatGPT token conversion, and the cached `AuthManager` state machine.

## Python Mapping

- `CodexAuth`, `ApiKeyAuth`, `ChatgptAuth`, `ChatgptAuthTokens`, and
  `AgentIdentityAuth`-backed records mirror the Rust auth variants and expose
  mode, token, account, plan, workspace, and backend-use helpers.
- `read_openai_api_key_from_env`, `read_codex_api_key_from_env`, and
  `read_codex_access_token_from_env` preserve Rust's trim-and-ignore-empty
  environment behavior.
- `login_with_api_key`, `login_with_access_token`,
  `login_with_chatgpt_auth_tokens`, `save_auth`, `load_auth_dot_json`,
  `logout`, and `logout_with_revoke` use the completed storage and revoke
  module facades.
- `AuthConfig`, `AuthManagerConfig`, `enforce_login_restrictions`, `load_auth`,
  and `AuthManager` preserve the manager-facing login restriction and cached
  auth reload contracts.
- `classify_refresh_token_failure`, `extract_refresh_token_error_code`, and
  `refresh_token_endpoint` preserve the stable refresh error and endpoint
  selection behavior.
- `UnauthorizedRecovery` mirrors the Rust recovery step surface for managed
  reload/refresh and external-auth refresh paths.

## Intentional Python Adaptations

- Network token refresh remains a lightweight compatibility seam. The module
  preserves Rust's classification, state, and external-token refresh contracts,
  but does not implement a new HTTP OAuth client here because the active porting
  priority is core authentication state and common CLI behavior.
- Agent identity auth loaded from persisted JWT is represented directly from the
  decoded record with an empty process task id. Full registration is owned by
  `src/auth/agent_identity.rs` and requires an injected registrar backend.
- Existing `external_bearer.ExternalAuthTokens` is kept as its module-local API;
  manager-owned ChatGPT metadata tokens are exposed as
  `ManagerExternalAuthTokens` to avoid a duplicate Python class name.

## Evidence

- Rust source: `codex/codex-rs/login/src/auth/manager.rs`
- Rust tests: `codex/codex-rs/login/src/auth_tests.rs`
- Python parity tests: `tests/test_login_auth_manager.py`
