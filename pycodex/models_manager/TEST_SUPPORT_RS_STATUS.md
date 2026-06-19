# codex-models-manager src/test_support.rs status

Status: `complete`

Rust module: `codex/codex-rs/models-manager/src/test_support.rs`

Python module: `pycodex/models_manager/test_support.py`

Behavior covered:

- `get_model_offline_for_tests` returns an explicitly requested model without
  consulting cache or remote state.
- Without an explicit model, bundled models are sorted by priority and converted
  to presets; the first picker-visible preset is selected, falling back to the
  first preset, and then to an empty string for an empty catalog.
- `construct_model_info_offline_for_tests` builds model metadata only from the
  optional `ModelsManagerConfig.model_catalog` candidates and delegates matching
  plus override semantics to the manager/model-info interface.

Dependency handling:

- `manager::construct_model_info_from_candidates` is treated as an interface
  constraint for this module. The broader `manager.rs` behavior remains pending
  for its own module turn.

Prepared tests:

- `tests/test_models_manager_test_support.py`

Validation:

- `python -m py_compile pycodex/models_manager/test_support.py tests/test_models_manager_test_support.py`
  (passed)
- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)




