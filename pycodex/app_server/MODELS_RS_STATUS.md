# codex-app-server src/models.rs status

Rust module: `codex/codex-rs/app-server/src/models.rs`

Python module: `pycodex/app_server/models.py`

Status: `complete`

## Covered

- `model_from_preset(...)` mirrors Rust's conversion from
  `codex_protocol::openai_models::ModelPreset` into app-server protocol
  `Model`, including upgrade metadata, availability NUX, hidden flag,
  reasoning effort options, input modalities, personality support, speed
  tiers, service tiers, default service tier, and default marker.
- `reasoning_efforts_from_preset(...)` mirrors the local effort/description
  mapping.
- `supported_models_from_presets(...)` mirrors the `include_hidden ||
  preset.show_in_picker` filter before conversion.
- `supported_models(...)` preserves the call shape to
  `list_models(RefreshStrategy::OnlineIfUncached)` while allowing a sync or
  async Python manager facade.

## Deferred

- Concrete `ThreadManager` ownership, model-manager caching, and real online
  refresh behavior remain owned by runtime/model-manager modules.

## Python parity tests

- `tests/test_app_server_models_rs.py`

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_models_rs.py -q`
  -> `5 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/models.py
  tests/test_app_server_models_rs.py`.
