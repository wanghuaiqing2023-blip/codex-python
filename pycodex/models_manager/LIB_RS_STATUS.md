# codex-models-manager src/lib.rs status

Status: `complete`

Rust module: `codex/codex-rs/models-manager/src/lib.rs`

Python module: `pycodex/models_manager/__init__.py`

Behavior covered:

- Top-level facade exposes the Rust crate module graph through Python package
  imports for cache, collaboration mode presets, config, manager, model info,
  model presets, and test support.
- `AuthMode` is re-exported from the app-server protocol package, matching the
  Rust `pub use codex_app_server_protocol::AuthMode`.
- `ModelsManagerConfig` is re-exported from the config module.
- `bundled_models_response` loads and parses the bundled Rust `models.json`.
- `client_version_to_whole` preserves Rust's whole-version concept and accepts
  explicit version strings for Python tests/provider shims.
- The old package-local compatibility `CachedModelsManager`/`RefreshStrategy`
  definitions were removed so the top-level package re-exports the canonical
  manager module implementations.

Prepared tests:

- `tests/test_models_manager_lib_rs.py`

Validation:

- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)

