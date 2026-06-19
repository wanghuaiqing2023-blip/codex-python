# codex-utils-cache src/lib.rs Status

Status: complete

Rust source:

- `codex/codex-rs/utils/cache/src/lib.rs`

Python target:

- `pycodex/utils/cache/__init__.py`

Behavior contract covered:

- runtime-gated LRU cache operations
- no-op cache behavior outside an async runtime
- LRU eviction after capacity is exceeded
- insert/get/remove/clear helpers
- disabled scratch cache for `with_mut`
- SHA-1 digest helper

Tests:

- `tests/test_utils_cache.py`

Last validation:

- 2026-06-17: `python -m pytest tests\test_utils_cache.py -q` -> `6 passed`
- 2026-06-17: `python -m py_compile pycodex\utils\cache\__init__.py tests\test_utils_cache.py` -> passed

