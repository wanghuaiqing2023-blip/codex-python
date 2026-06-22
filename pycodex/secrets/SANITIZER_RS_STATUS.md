# codex-secrets src/sanitizer.rs Status

Rust source:

- `codex/codex-rs/secrets/src/sanitizer.rs`

Python mapping:

- `pycodex/secrets/sanitizer.py`

Status: `complete_candidate`

Implemented behavior:

- OpenAI API key pattern redaction.
- AWS access key id pattern redaction.
- case-insensitive bearer token redaction, normalized to `Bearer [REDACTED_SECRET]`.
- secret assignment redaction for `api_key`, `apikey`, `api-key`,
  `token`, `secret`, and `password`, preserving the matched key, separator,
  and optional quote prefix.

Validation:

- `python -m py_compile pycodex/secrets/__init__.py pycodex/secrets/sanitizer.py pycodex/secrets/local.py tests/test_secrets_sanitizer_rs.py tests/test_secrets_lib_rs.py tests/test_secrets_local_rs.py`
  passed on 2026-06-19.
- `python -m pytest tests/test_secrets_sanitizer_rs.py tests/test_secrets_lib_rs.py tests/test_secrets_local_rs.py -q`
  passed with 18 tests on 2026-06-19.
