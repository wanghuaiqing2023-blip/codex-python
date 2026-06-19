# codex-models-manager src/model_presets.rs status

Status: `complete`

Rust module: `codex/codex-rs/models-manager/src/model_presets.rs`

Python module: `pycodex/models_manager/model_presets.py`

Behavior covered:

- `HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG` matches the Rust legacy notice key.
- `HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG` matches the Rust legacy
  notice key.
- The Python module documents the Rust source note that hardcoded model
  presets were removed and active listings are derived from catalog metadata.

Python-local support:

- `model_presets_from_models` is retained as a Python helper for adjacent
  `manager.rs`/`cache.rs` behavior; it is not a separate public item in Rust
  `src/model_presets.rs`.

Prepared tests:

- `tests/test_models_manager_model_presets.py`

Validation:

- `python -m py_compile pycodex/models_manager/model_presets.py tests/test_models_manager_model_presets.py`
  (passed)
- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)




