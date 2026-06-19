# auth/default_client.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/auth/default_client.rs`

Python module: `pycodex/login/auth/default_client.py`

Status: `complete`

Aligned behavior:

- Default originator constants and `CODEX_INTERNAL_ORIGINATOR_OVERRIDE` handling
  are mirrored with cached originator selection.
- `set_default_originator()` validates header values and rejects a second
  initialization.
- First-party originator and first-party chat originator predicates match Rust's
  known-value checks.
- User-Agent construction includes originator prefix, package version,
  OS/architecture information, terminal hint, optional suffix, and sanitization.
- `default_headers()` emits `originator`, valid `user-agent`, and the US
  residency header when configured.
- `create_client()` and request-builder shims preserve the observable default
  header and sandbox no-proxy policy without introducing a third-party HTTP
  client dependency.

Rust tests and Python parity coverage:

- Rust `test_get_codex_user_agent` ->
  `tests/test_login_default_client.py::test_get_codex_user_agent_starts_with_originator_prefix`
- Rust `is_first_party_originator_matches_known_values` ->
  `tests/test_login_default_client.py::test_is_first_party_originator_matches_known_values`
- Rust `is_first_party_chat_originator_matches_known_values` ->
  `tests/test_login_default_client.py::test_is_first_party_chat_originator_matches_known_values`
- Rust `test_invalid_suffix_is_sanitized` and `test_invalid_suffix_is_sanitized2` ->
  `tests/test_login_default_client.py::test_invalid_suffix_is_sanitized`
- Source-contract coverage for originator override, residency headers, client
  shims, and sandbox proxy policy is in `tests/test_login_default_client.py`.

Validation:

- Not run in this turn; current automation defers actual test execution until the crate functional code is complete.
