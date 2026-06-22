# pycodex.models_manager

Rust counterpart:

```text
Primary Rust crate: codex-models-manager
Primary Rust path: codex/codex-rs/models-manager
```

This package carries Python interfaces for the Rust `codex-models-manager`
crate. The `test_support.py` module is anchored to
`codex/codex-rs/models-manager/src/test_support.rs` and the adjacent
models-manager helper modules it delegates to.

Module map:

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
