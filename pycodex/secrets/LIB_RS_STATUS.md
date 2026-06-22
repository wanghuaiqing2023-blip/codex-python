# codex-secrets src/lib.rs Status

Rust source:

- `codex/codex-rs/secrets/src/lib.rs`

Python mapping:

- `pycodex/secrets/__init__.py`

Status: `complete_candidate`

Implemented behavior:

- `SecretName` trimming, validation, ordering, and display value.
- `SecretScope` global/environment construction and canonical key formatting.
- `SecretListEntry`.
- `SecretsBackendKind` local backend enum value/default.
- `SecretsBackend` protocol shape.
- `SecretsManager` backend delegation methods.
- `environment_id_from_cwd(...)` git-root basename preference and SHA-256
  cwd fallback.
- `compute_keyring_account(...)` and `keyring_service()`.
- Re-export of `redact_secrets`.

Dependency boundary:

- `SecretsManager.new(...)` and `new_with_keyring_store(...)` now construct the
  Python `LocalSecretsBackend` mapped from `codex-secrets/src/local.rs`.

Validation:

- `python -m py_compile pycodex/secrets/__init__.py pycodex/secrets/sanitizer.py pycodex/secrets/local.py tests/test_secrets_sanitizer_rs.py tests/test_secrets_lib_rs.py tests/test_secrets_local_rs.py`
  passed on 2026-06-19.
- `python -m pytest tests/test_secrets_sanitizer_rs.py tests/test_secrets_lib_rs.py tests/test_secrets_local_rs.py -q`
  passed with 18 tests on 2026-06-19.
