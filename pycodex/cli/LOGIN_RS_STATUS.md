# codex-cli src/login.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/cli/src/login.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/login.rs` |
| Python module | `pycodex/cli/login.py` |
| Python parser integration | `pycodex/cli/parser.py` login/logout/status dispatch |
| Python tests | `tests/test_cli_login.py` |
| Status | `complete_candidate` |

`src/login.rs` owns the direct CLI login/logout/status command surfaces:
config-load failure messages, forced-login-method guards, stdin secret
handling, browser/device-code flow result messages, local login server startup
messaging, login status/logout output, API-key masking, and direct-login log
file setup decisions.

The module is now a `complete_candidate`: module-owned behavior contracts are
mirrored by Python helpers and Rust-derived Python tests. Actual pytest
validation is deferred until `codex-cli` functional code is complete, per the
current crate automation rule.

## Completed Behavior Areas

- `print_login_server_start` stderr shape is mirrored by
  `print_login_server_start`.
- Forced login method guards for ChatGPT/device-code, API key, and access token
  flows are mirrored by `login_disabled_message`.
- `read_api_key_from_stdin`, `read_access_token_from_stdin`, and
  `read_stdin_secret` user-facing messages, trimming, empty-input guard, and
  read-error message are mirrored by `stdin_secret_messages`,
  `api_key_from_stdin_text`, `access_token_from_stdin_text`, and
  `stdin_secret_read_error_message`.
- `run_login_status` auth-mode messages, API-key retrieval error, and
  auth-status error branches are mirrored by `login_status_message` and
  `login_status_error_message`.
- `run_logout` success, not-logged-in, and error messages are mirrored by
  `logout_status_message`.
- `run_login_with_chatgpt`, `run_login_with_api_key`,
  `run_login_with_access_token`, `run_login_with_device_code`, and
  `run_login_with_device_code_fallback_to_browser` success/error prefixes and
  device-code unsupported fallback message are mirrored by
  `login_result_message` and `device_code_fallback_message`.
- `load_config_or_exit` parse/load error prefixes are mirrored by
  `login_config_error_message`.
- `init_login_file_logging` log file path, warning text, default filter, Unix
  `0o600` mode, and `OpenOptions::create(true).append(true)` contract are
  mirrored by the `login_log_*` helpers.
- `safe_format_key` is mirrored by `safe_format_key`.

## Rust Test Inventory

The Rust module currently contains two local tests:

- `tests::formats_long_key`
- `tests::short_key_returns_stars`

They are covered by:

- `tests/test_cli_login.py::LoginCallbackHandlerTests::test_safe_format_key_matches_rust_login_status_masking`

Additional source-contract coverage is recorded in the same file for the
public command helpers and important internal message/logging helpers listed
above.

## Intentional Adaptation

The Rust `login.rs` module delegates OAuth server, device-code, token storage,
logout revoke, and auth-storage details to the sibling `codex-login` crate and
related auth/config crates. This status file does not claim those sibling crate
internals as complete. Python keeps a pragmatic local browser-login
implementation in `pycodex/cli/login.py`, but this module closeout only claims
the `codex-cli/src/login.rs` command-surface behavior and direct-user
observability contract.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
