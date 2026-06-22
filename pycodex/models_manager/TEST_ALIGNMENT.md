# codex-models-manager test alignment

Rust crate: `codex-models-manager`

Python package: `pycodex/models_manager`

Status: `complete`

Module mapping:

- `codex/codex-rs/models-manager/src/config.rs` ->
  `pycodex/models_manager/config.py` (`complete`)
- `codex/codex-rs/models-manager/src/cache.rs` ->
  `pycodex/models_manager/cache.py` (`complete`)
- `codex/codex-rs/models-manager/src/collaboration_mode_presets.rs` ->
  `pycodex/models_manager/collaboration_mode_presets.py`
  (`complete`)
- `codex/codex-rs/models-manager/src/lib.rs` ->
  `pycodex/models_manager/__init__.py` (`complete`)
- `codex/codex-rs/models-manager/src/manager.rs` ->
  `pycodex/models_manager/manager.py` (`complete`)
- `codex/codex-rs/models-manager/src/model_info.rs` ->
  `pycodex/models_manager/model_info.py` (`complete`)
- `codex/codex-rs/models-manager/src/model_presets.rs` ->
  `pycodex/models_manager/model_presets.py` (`complete`)
- `codex/codex-rs/models-manager/src/test_support.rs` ->
  `pycodex/models_manager/test_support.py` (`complete`)

Rust behavior prepared in `tests/test_models_manager_config.py`:

- derived default field values
- supported mapping fields and `ModelsResponse` catalog conversion
- rejection of unsupported field names and non-Rust field shapes
- integration edge consumed by `model_info::with_config_overrides`

Rust behavior prepared in `tests/test_models_manager_cache.py`:

- cache snapshot serialization and timestamp parsing/formatting
- missing, stale, version-mismatched, zero-TTL, and invalid cache handling
- parent directory creation, TTL renewal, and test-only TTL/timestamp helpers

Rust behavior prepared in `tests/test_models_manager_lib_rs.py`:

- top-level `AuthMode` and `ModelsManagerConfig` re-exports
- canonical manager facade re-exports
- bundled `models.json` loading
- whole-version helper behavior

Rust behavior prepared in
`tests/test_models_manager_collaboration_mode_presets.py`:

- built-in Plan/Default preset field shape
- Default-mode template rendering with known mode names
- `format_mode_names` zero/one/two/many edge cases

Rust behavior prepared in `tests/test_models_manager_model_presets.py`:

- legacy notice-key constants match Rust
- Python helper derives active presets from catalog metadata for adjacent
  manager/cache behavior after Rust removed hardcoded model presets

Rust behavior prepared in `tests/test_models_manager_model_info.py`:

- fallback model metadata built by `model_info_from_slug`
- local personality template gating for Rust-matched slugs
- config override semantics for reasoning summaries, context window clamping,
  auto-compact token limit, tool-output truncation policy, base instructions,
  and personality disabling

Rust behavior prepared in `tests/test_models_manager_manager.py`:

- refresh strategy display values and endpoint client handoff
- available-model sorting, auth filtering, and default selection
- static and cached manager catalog/list/default/model-info surfaces
- offline/online/online-if-uncached refresh behavior
- remote-only ChatGPT catalogs, hidden/empty remote merging, API auth merging,
  cache-hit merging, and skipped network refresh without refresh auth
- ETag refresh and cache TTL renewal behavior
- longest-prefix and namespaced-suffix model metadata matching

Rust behavior prepared in `tests/test_models_manager_test_support.py`:

- explicit offline model selection without cache or remote lookup
- bundled-model fallback selection by priority and picker visibility
- offline model-info construction from config-provided catalog candidates

Validation:

- `python -m py_compile pycodex/models_manager/config.py tests/test_models_manager_config.py`
  (passed)
- `python -m py_compile pycodex/models_manager/cache.py tests/test_models_manager_cache.py`
  (passed)
- `python -m py_compile pycodex/models_manager/__init__.py tests/test_models_manager_lib_rs.py`
  (passed)
- `python -m py_compile pycodex/models_manager/collaboration_mode_presets.py tests/test_models_manager_collaboration_mode_presets.py`
  (passed)
- `python -m py_compile pycodex/models_manager/model_presets.py tests/test_models_manager_model_presets.py`
  (passed)
- `python -m py_compile pycodex/models_manager/model_info.py tests/test_models_manager_model_info.py`
  (passed)
- `python -m py_compile pycodex/models_manager/manager.py tests/test_models_manager_manager.py`
  (passed)
- `python -m py_compile pycodex/models_manager/test_support.py tests/test_models_manager_test_support.py`
  (passed)
- `python -m pytest tests/test_models_manager_config.py tests/test_models_manager_cache.py tests/test_models_manager_collaboration_mode_presets.py tests/test_models_manager_manager.py tests/test_models_manager_model_info.py tests/test_models_manager_model_presets.py tests/test_models_manager_test_support.py tests/test_models_manager_lib_rs.py -q`
  (passed: 60 passed)
