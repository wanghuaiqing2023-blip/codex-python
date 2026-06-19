# codex-utils-rustls-provider test alignment

Rust crate: `codex-utils-rustls-provider`

Rust module: `codex/codex-rs/utils/rustls-provider/src/lib.rs`

Python module: `pycodex/utils/rustls_provider/__init__.py`

Status: `complete`

Validation:

- `python -m pytest tests/test_utils_rustls_provider.py -q`
- `python -m py_compile pycodex/utils/rustls_provider/__init__.py tests/test_utils_rustls_provider.py`

Rust-derived coverage:

- No Rust unit tests are present in this crate.
- Python tests are source-contract tests derived from `src/lib.rs`.

Covered contracts:

- process-wide provider initialization starts uninstalled in the Python facade.
- `ensure_rustls_crypto_provider` marks the provider installed.
- an injected installer is called once, mirroring Rust `Once::call_once`.
- repeated calls after initialization are no-ops.

Known gaps: none for `src/lib.rs`. Python cannot install rustls' native `ring` provider without a rustls binding, so the standard-library port keeps the idempotent initialization boundary and optional installer hook.
