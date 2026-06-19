# auth/util.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/auth/util.rs`

Python module: `pycodex/login/auth/util.py`

Status: `complete`

Aligned behavior:

- `try_parse_error_message()` parses JSON server responses and extracts
  `error.message` only when the nested value is a string.
- Invalid JSON falls back to raw text, matching Rust's `unwrap_or_default()`
  behavior.
- JSON without a nested string `error.message` falls back to raw text.
- Empty text returns `"Unknown error"`.

Rust tests and Python parity coverage:

- Rust `try_parse_error_message_extracts_openai_error_message` ->
  `tests/test_login_auth_util.py::test_try_parse_error_message_extracts_openai_error_message`
- Rust `try_parse_error_message_falls_back_to_raw_text` ->
  `tests/test_login_auth_util.py::test_try_parse_error_message_falls_back_to_raw_text`
- Additional source-contract coverage for invalid JSON, empty text, and
  non-string nested messages is in `tests/test_login_auth_util.py`.

Validation:

- Not run in this turn; current automation defers actual test execution until the crate functional code is complete.
