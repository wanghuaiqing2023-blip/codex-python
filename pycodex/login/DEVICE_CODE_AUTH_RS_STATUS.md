# codex-login `src/device_code_auth.rs` alignment status

Status: `complete_candidate`

Rust module: `codex/codex-rs/login/src/device_code_auth.rs`

Python module: `pycodex/login/device_code_auth.py`

## Behavior Contract

This module owns the device-code login flow around the Codex auth server:

- request a device authorization code from `/deviceauth/usercode`.
- accept both `user_code` and `usercode` response fields.
- parse the polling interval.
- present the verification URL and one-time code to the user.
- poll `/deviceauth/token` until authorization succeeds or the 15-minute window
  expires.
- retry pending `403`/`404` token responses.
- construct the PKCE record and callback URL for the final token exchange.

## Python Mapping

- `DeviceCode`, `UserCodeResp`, and `CodeSuccessResp` mirror the Rust data
  structures owned by this module; `ServerOptions` is imported from the
  server-owned `pycodex.login.server` mapping.
- `request_user_code`, `poll_for_token`, `print_device_code_prompt`, and
  `request_device_code` mirror the Rust local behavior with standard-library
  HTTP primitives.
- `complete_device_code_login` uses the server-owned exchange, workspace
  validation, and token persistence callbacks by default while still allowing
  explicit injection for focused tests.
- Existing `pycodex.cli.parser` device-auth HTTP helpers now delegate to this
  module to avoid duplicated device-code request and polling logic.

## Rust Evidence

`src/device_code_auth.rs` has no local unit test module. Python parity coverage
in `tests/test_login_device_code_auth.py` is derived from the Rust source
contract:

- `test_deserialize_interval_matches_rust_string_parser`
- `test_request_user_code_posts_client_id_and_accepts_usercode_alias`
- `test_request_user_code_404_is_not_enabled`
- `test_request_user_code_rejects_missing_user_code`
- `test_poll_for_token_returns_authorization_code_and_pkce`
- `test_poll_for_token_retries_on_forbidden_then_succeeds`
- `test_poll_for_token_times_out_after_max_wait`
- `test_print_device_code_prompt_contains_url_code_and_warning`
- `test_request_device_code_derives_api_base_and_verification_url`

## Known Adaptations

- Rust uses async `reqwest`; Python uses standard-library `urllib` plus
  injectable open/sleep/clock call sites for focused parity tests.
- The Python parser wrapper keeps legacy return dictionaries and exception types
  for current CLI tests while the owned behavior lives under `pycodex.login`.
- Actual test execution is deferred by the active crate automation policy until
  `codex-login` functional code is complete.
