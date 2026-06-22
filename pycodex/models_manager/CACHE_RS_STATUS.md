# codex-models-manager src/cache.rs status

Status: `complete`

Rust module: `codex/codex-rs/models-manager/src/cache.rs`

Python module: `pycodex/models_manager/cache.py`

Behavior covered:

- `ModelsCache` serializes and deserializes `fetched_at`, optional `etag`,
  optional `client_version`, and cached `ModelInfo` entries.
- Cache freshness rejects zero TTL and entries older than the configured TTL.
- `ModelsCacheManager.load_fresh` returns `None` for missing, stale,
  version-mismatched, or invalid cache data, matching Rust's logged-load-error
  fallback behavior.
- `persist_cache` writes a timestamped cache snapshot and creates parent
  directories.
- `renew_cache_ttl` updates `fetched_at` and reports missing cache as not found.
- Test-only helper behavior is mirrored by `set_ttl`,
  `manipulate_cache_for_test`, and `mutate_cache_for_test`.

Prepared tests:

- `tests/test_models_manager_cache.py`

Validation:

- `python -m py_compile pycodex/models_manager/cache.py tests/test_models_manager_cache.py`
  (passed)
- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)




