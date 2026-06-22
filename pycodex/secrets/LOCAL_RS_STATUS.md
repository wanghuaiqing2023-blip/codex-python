# codex-secrets src/local.rs Status

Rust source:

- `codex/codex-rs/secrets/src/local.rs`

Python mapping:

- `pycodex/secrets/local.py`

Status: `complete_candidate`

Implemented behavior:

- `SecretsFile` versioned map model.
- `LocalSecretsBackend.new`, `set`, `get`, `delete`, `list`.
- local `secrets/local.age` path handling.
- keyring-backed passphrase load/create behavior through
  `pycodex.keyring_store`.
- schema version normalization/rejection.
- atomic file replacement without leaving temp files.
- generated base64 passphrases.
- authenticated reversible local file encryption using standard-library
  primitives.
- canonical key parsing for global and environment scopes.
- `SecretsManager.new*` construction path through `LocalSecretsBackend`.

Intentional adaptation:

- Rust uses the `age` crate with scrypt recipients. The Python port avoids a
  new third-party dependency and uses a standard-library authenticated stream
  wrapper around JSON payloads while preserving the module contract and tests'
  observable behavior.

Validation:

- `python -m pytest tests/test_secrets_sanitizer_rs.py tests/test_secrets_lib_rs.py tests/test_secrets_local_rs.py -q`
  passed with 18 tests on 2026-06-19.
- `python -m py_compile pycodex/secrets/__init__.py pycodex/secrets/sanitizer.py pycodex/secrets/local.py tests/test_secrets_sanitizer_rs.py tests/test_secrets_lib_rs.py tests/test_secrets_local_rs.py`
  passed.
