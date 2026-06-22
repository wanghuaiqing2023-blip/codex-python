# codex-keyring-store

Rust crate: `codex-keyring-store`

Rust anchor: `codex/codex-rs/keyring-store/src/lib.rs`

Current certified modules:

- `keyring-store/src/lib.rs`

This package mirrors the crate's keyring-backed credential-store abstraction:
`CredentialStoreError`, the `KeyringStore` protocol, `DefaultKeyringStore`,
and the public test-support `MockKeyringStore`. The default store uses an
optional Python `keyring` backend when present; the mock store is dependency
free and preserves the Rust `NoEntry` load/delete semantics for local tests.

Remaining Rust modules: none.
