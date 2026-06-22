# pycodex.utils.rustls_provider

Python alignment target for Rust crate `codex-utils-rustls-provider`.

Rust coordinate:

- `codex/codex-rs/utils/rustls-provider/src/lib.rs`

Python mapping:

- `pycodex/utils/rustls_provider/__init__.py`

The Rust module installs the `ring` rustls crypto provider through a process-wide `Once`. Python has no rustls global provider in the standard library, so this module preserves the observable boundary:

- `ensure_rustls_crypto_provider` is idempotent.
- an injected installer runs at most once.
- later calls are no-ops after installation.
- focused tests can reset the facade with `reset_rustls_crypto_provider_for_tests`.
