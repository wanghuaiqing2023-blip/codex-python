# codex-models-manager src/config.rs status

Status: `complete`

Rust module: `codex/codex-rs/models-manager/src/config.rs`

Python module: `pycodex/models_manager/config.py`

Behavior covered:

- `ModelsManagerConfig` carries the Rust fields:
  `model_context_window`, `model_auto_compact_token_limit`,
  `tool_output_token_limit`, `base_instructions`, `personality_enabled`,
  `model_supports_reasoning_summaries`, and `model_catalog`.
- The derived Rust `Default` contract is mirrored by the Python constructor:
  optional fields default to `None`, and `personality_enabled` defaults to
  `False`.
- Mapping construction accepts only the Rust field names and converts
  `model_catalog` mappings into `ModelsResponse`.
- The Python helper rejects non-Rust field shapes at the public boundary.

Prepared tests:

- `tests/test_models_manager_config.py`

Validation:

- `python -m py_compile pycodex/models_manager/config.py tests/test_models_manager_config.py`
  (passed)
- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)




