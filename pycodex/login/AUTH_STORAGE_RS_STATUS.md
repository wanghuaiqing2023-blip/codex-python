# codex-login `src/auth/storage.rs` alignment status

Status: `complete_candidate`

Rust module: `codex/codex-rs/login/src/auth/storage.rs`

Python module: `pycodex/login/auth/storage.py`

## Behavior Contract

This module owns the auth persistence backends for `codex-login`:

- `AuthDotJson` JSON shape, including Rust's `OPENAI_API_KEY` rename,
  optional `tokens`, `last_refresh`, and `agent_identity` fields.
- `AgentIdentityAuthRecord` construction from an agent identity JWT payload.
- `auth.json` path resolution, file load/save/delete behavior, and missing-file
  handling.
- keyring store key derivation, keyring load/save/delete behavior, and
  keyring error message wrapping.
- automatic storage fallback from keyring to file.
- ephemeral in-memory storage keyed by the same store key.
- `create_auth_storage` mode dispatch.

## Python Mapping

- `AuthDotJson` mirrors Rust serde defaults and skip-none behavior through
  `from_mapping()` and `to_json_dict()`.
- `FileAuthStorage` mirrors `FileAuthStorage::{load,save,delete}` with
  dependency-light standard-library JSON and filesystem APIs.
- `KeyringAuthStorage` reuses the existing `pycodex.keyring_store` port for
  the Rust `codex-keyring-store` dependency.
- `AutoAuthStorage` preserves Rust's keyring-first, file-fallback load/save
  policy.
- `EphemeralAuthStorage` uses a process-local in-memory map keyed by
  `compute_store_key()`.

## Rust Evidence

Rust tests mirrored in `tests/test_login_auth_storage.py`:

- `file_storage_load_returns_auth_dot_json`
- `file_storage_save_persists_auth_dot_json`
- `file_storage_round_trips_agent_identity_auth`
- `file_storage_loads_agent_identity_as_jwt`
- `file_storage_delete_removes_auth_file`
- `ephemeral_storage_save_load_delete_is_in_memory_only`
- `keyring_auth_storage_load_returns_deserialized_auth`
- `keyring_auth_storage_compute_store_key_for_home_directory`
- `keyring_auth_storage_save_persists_and_removes_fallback_file`
- `keyring_auth_storage_delete_removes_keyring_and_file`
- `auto_auth_storage_load_prefers_keyring_value`
- `auto_auth_storage_load_uses_file_when_keyring_empty`
- `auto_auth_storage_load_falls_back_when_keyring_errors`
- `auto_auth_storage_save_prefers_keyring`
- `auto_auth_storage_save_falls_back_when_keyring_errors`
- `auto_auth_storage_delete_removes_keyring_and_file`

## Known Adaptations

- The Rust module is private under `auth/mod.rs`; Python exposes this module for
  direct parity testing while the crate remains partially ported.
- Agent identity JWT verification with JWKS remains owned by the
  `codex-agent-identity` crate. This module mirrors the Rust `None`/payload
  decode path needed by `AgentIdentityAuthRecord::from_agent_identity_jwt`.
- Actual test execution is deferred by the active crate automation policy until
  `codex-login` functional code is complete.
