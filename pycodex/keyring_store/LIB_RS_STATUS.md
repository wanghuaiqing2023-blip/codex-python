# codex-keyring-store src/lib.rs status

Rust coordinate: `codex/codex-rs/keyring-store/src/lib.rs`

Python coordinate: `pycodex/keyring_store/__init__.py`

Status: `complete`

Behavior contract:

- expose `CredentialStoreError` with `new`, `message`, display text, and
  `into_error` behavior around the underlying keyring error.
- expose the `KeyringStore` load/save/delete protocol.
- provide `DefaultKeyringStore` backed by the platform keyring abstraction,
  mapping missing entries to `None`/`False` and other backend errors to
  `CredentialStoreError`.
- provide public test-support `MockKeyringStore` with account-scoped
  credentials, saved-value inspection, error injection, contains checks, and
  Rust-like `NoEntry` handling for load/delete.

Evidence:

- `CredentialStoreError` mirrors the Rust enum wrapper methods.
- `DefaultKeyringStore` mirrors the default keyring-backed implementation using
  an optional Python `keyring` backend.
- `MockKeyringStore` mirrors the public Rust `tests` module helper and keeps
  `NoEntry` as a success-like missing-entry condition for load/delete.

Validation:

- `tests/test_keyring_store_lib_rs.py` covers the source-contract behaviors.
