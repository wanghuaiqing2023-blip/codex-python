# codex-models-manager src/model_info.rs status

Status: `complete`

Rust module: `codex/codex-rs/models-manager/src/model_info.rs`

Python module: `pycodex/models_manager/model_info.py`

Behavior covered:

- `BASE_INSTRUCTIONS` is loaded from the Rust `prompt.md` fixture.
- `model_info_from_slug` mirrors Rust fallback model metadata for unknown
  slugs, including visibility, priority, truncation policy, context window,
  input modalities, and fallback marker fields.
- `local_personality_messages_for_slug` enables local personality templates
  only for the Rust-matched slugs.
- `with_config_overrides` mirrors Rust override semantics for reasoning
  summaries, context window clamping, auto-compact token limit, tool-output
  truncation policy mode, base instructions, and personality disabling.

Prepared tests:

- `tests/test_models_manager_model_info.py`

Validation:

- `python -m py_compile pycodex/models_manager/model_info.py tests/test_models_manager_model_info.py`
  (passed)
- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)




