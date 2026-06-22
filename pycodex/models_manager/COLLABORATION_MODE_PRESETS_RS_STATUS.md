# codex-models-manager src/collaboration_mode_presets.rs status

Status: `complete`

Rust module: `codex/codex-rs/models-manager/src/collaboration_mode_presets.rs`

Python module: `pycodex/models_manager/collaboration_mode_presets.py`

Behavior covered:

- `builtin_collaboration_mode_presets` returns the Plan and Default
  collaboration mode presets in Rust order.
- Plan preset fields mirror Rust: display-name `name`, `ModeKind::Plan`,
  no model override, medium reasoning effort, and plan developer
  instructions.
- Default preset fields mirror Rust: display-name `name`,
  `ModeKind::Default`, no model override, no reasoning-effort override, and
  rendered default developer instructions.
- `default_mode_instructions` renders the known-mode-names placeholder using
  `TUI_VISIBLE_COLLABORATION_MODES`.
- `format_mode_names` mirrors the Rust private helper for zero, one, two, and
  three-or-more modes.

Prepared tests:

- `tests/test_models_manager_collaboration_mode_presets.py`

Validation:

- `python -m py_compile pycodex/models_manager/collaboration_mode_presets.py tests/test_models_manager_collaboration_mode_presets.py`
  (passed)
- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)




