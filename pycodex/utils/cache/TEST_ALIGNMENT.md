# codex-utils-cache Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/utils/cache/src/lib.rs`

Python module:

- `pycodex/utils/cache/__init__.py`

Parity evidence:

- `tests/test_utils_cache.py`

Rust-derived coverage:

- `stores_and_retrieves_values`
- `evicts_least_recently_used`
- `disabled_without_runtime`

Additional Python boundary coverage:

- `try_with_capacity(0)` returns `None`
- `sha1_digest` returns the standard SHA-1 bytes
- `get_or_insert_with` and `get_or_try_insert_with` reuse cached values inside an async runtime

Validation:

- `python -m pytest tests\test_utils_cache.py -q` -> `6 passed`
- `python -m py_compile pycodex\utils\cache\__init__.py tests\test_utils_cache.py` -> passed

Known adaptations:

- Rust uses Tokio runtime detection and `lru::LruCache`; Python uses `asyncio.get_running_loop` and `OrderedDict` to preserve the same observable behavior for this module.

