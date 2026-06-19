# auth/external_bearer.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/auth/external_bearer.rs`

Python module: `pycodex/login/auth/external_bearer.py`

Status: `complete`

Aligned behavior:

- `BearerTokenRefresher.new()` stores provider auth config and exposes API-key
  auth mode.
- `resolve()` returns cached access-token-only credentials while the configured
  refresh interval is still valid, and otherwise runs the provider auth command.
- `refresh()` always re-runs the provider auth command and updates the cache.
- `run_provider_auth_command()` resolves the command path, runs it with null
  stdin and captured stdout/stderr, applies timeout handling, reports start
  failure, non-zero exit plus stderr, non-UTF-8 stdout, and empty token errors,
  and trims stdout for the access token.
- `resolve_provider_auth_program()` mirrors Rust path handling for absolute
  paths, relative paths with components, and bare command names.

Python parity coverage:

- `tests/test_login_external_bearer.py::test_resolve_provider_auth_program_matches_rust_path_rules`
- `tests/test_login_external_bearer.py::test_run_provider_auth_command_trims_stdout`
- `tests/test_login_external_bearer.py::test_run_provider_auth_command_rejects_empty_token`
- `tests/test_login_external_bearer.py::test_run_provider_auth_command_reports_stderr_for_nonzero_exit`
- `tests/test_login_external_bearer.py::test_run_provider_auth_command_reports_non_utf8_stdout`
- `tests/test_login_external_bearer.py::test_run_provider_auth_command_times_out`
- `tests/test_login_external_bearer.py::test_bearer_token_refresher_caches_and_refresh_forces_command`
- `tests/test_login_external_bearer.py::test_bearer_token_refresher_zero_refresh_interval_never_expires_cache`
- `tests/test_login_external_bearer.py::test_bearer_token_refresher_expired_cache_refetches`

Validation:

- Not run in this turn; current automation defers actual test execution until the crate functional code is complete.
