# codex-secrets test alignment

Rust crate: `codex-secrets`

Python package: `pycodex/secrets`

Status: `complete`

Module mapping:

- `codex/codex-rs/secrets/src/sanitizer.rs` ->
  `pycodex/secrets/sanitizer.py` (`complete_candidate`)
- `codex/codex-rs/secrets/src/lib.rs` ->
  `pycodex/secrets/__init__.py` (`complete_candidate`)
- `codex/codex-rs/secrets/src/local.rs` ->
  `pycodex/secrets/local.py` (`complete_candidate`)

Rust behavior prepared in `tests/test_secrets_sanitizer_rs.py`:

- `load_regex`
- OpenAI key redaction via `sk-[A-Za-z0-9]{20,}`
- AWS access key id redaction via `AKIA[0-9A-Z]{16}`
- case-insensitive bearer token redaction
- secret assignment redaction preserving key, separator, and optional quote

Rust behavior prepared in `tests/test_secrets_lib_rs.py`:

- `SecretName::new` trimming and validation
- `SecretScope::environment` validation and `canonical_key`
- `environment_id_fallback_has_cwd_prefix`
- git-root basename preference in `environment_id_from_cwd`
- `compute_keyring_account` and `keyring_service`
- `SecretsManager` backend method delegation
- `SecretsManager::new*` local backend construction

Rust behavior covered in `tests/test_secrets_local_rs.py`:

- `load_file_rejects_newer_schema_versions`
- `set_fails_when_keyring_is_unavailable`
- `save_file_does_not_leave_temp_files`
- local backend set/get/delete/list and scope filtering
- `manager_round_trips_local_backend`
- canonical key parsing for global/env scopes
- decrypt failure with the wrong passphrase

Validation:

- `python -m py_compile pycodex/secrets/__init__.py pycodex/secrets/sanitizer.py pycodex/secrets/local.py tests/test_secrets_sanitizer_rs.py tests/test_secrets_lib_rs.py tests/test_secrets_local_rs.py`
  (passed)
- `python -m pytest tests/test_secrets_sanitizer_rs.py tests/test_secrets_lib_rs.py tests/test_secrets_local_rs.py -q`
  (18 passed)
