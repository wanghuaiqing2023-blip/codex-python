# codex-models-manager src/manager.rs status

Status: `complete`

Rust module: `codex/codex-rs/models-manager/src/manager.rs`

Python module: `pycodex/models_manager/manager.py`

Behavior covered:

- `RefreshStrategy` string values match Rust display values.
- `ModelsEndpointClient`/`OpenAiModelsManager` endpoint handoff passes the
  whole client version and accepts optional ETags.
- `CachedModelsManager` and `StaticModelsManager` expose the Rust manager
  surface for raw catalogs, current remote models, model listing, default model
  selection, collaboration modes, model-info lookup, and ETag refresh.
- Available-model construction sorts by priority, filters by auth mode, and
  marks the first picker-visible model as default.
- Refresh policy mirrors Rust: offline uses cache only, online fetches when
  refresh auth is available, online-if-uncached prefers fresh cache, and missing
  refresh auth avoids network fetches.
- Remote model application mirrors Rust ChatGPT-vs-API behavior: visible
  ChatGPT remote catalogs become authoritative, empty/hidden-only remotes merge
  with bundled models, and API auth keeps bundled models plus remote overlays.
- Cache hits are applied through the same remote-model merge/replace path as
  fresh endpoint results.
- Model-info construction uses longest-prefix matching, narrowly scoped
  namespaced-suffix matching, fallback metadata, and config overrides.
- Same-ETag refresh renews cache TTL when possible and ignores renewal errors,
  matching Rust's logged-error behavior.

Prepared tests:

- `tests/test_models_manager_manager.py`
- manager-level override coverage also delegates to
  `tests/test_models_manager_model_info.py`.

Validation:

- `python -m py_compile pycodex/models_manager/manager.py tests/test_models_manager_manager.py`
  (passed)
- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)




