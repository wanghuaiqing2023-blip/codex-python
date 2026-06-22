# pycodex.utils.cache

Python alignment target for Rust crate `codex-utils-cache`.

Rust coordinate:

- `codex/codex-rs/utils/cache/src/lib.rs`

Python mapping:

- `pycodex/utils/cache/__init__.py`

The module preserves Rust's small cache contract:

- `BlockingLruCache` is active only when an async runtime is present.
- outside a runtime, cache operations are no-ops except `with_mut`, which receives a disabled scratch cache.
- inside a runtime, values are stored in LRU order and least-recently-used values are evicted.
- `sha1_digest` returns a 20-byte SHA-1 digest.

