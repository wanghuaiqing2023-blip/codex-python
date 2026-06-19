# codex-utils-rustls-provider src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/rustls-provider/src/lib.rs`

Python coordinate: `pycodex/utils/rustls_provider/__init__.py`

Status: `complete`

Behavior contract:

- `ensure_rustls_crypto_provider` is process-wide and idempotent.
- the install closure runs once.
- subsequent calls return without invoking another install.
- Python exposes reset/test-observation helpers without changing the production idempotent boundary.

Evidence:

- `tests/test_utils_rustls_provider.py` covers the Rust source contract because the Rust crate has no unit tests.
- `python -m pytest tests/test_utils_rustls_provider.py -q` passed.
- `python -m py_compile pycodex/utils/rustls_provider/__init__.py tests/test_utils_rustls_provider.py` passed.
