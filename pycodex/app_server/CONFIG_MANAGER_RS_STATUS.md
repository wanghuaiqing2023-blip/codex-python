# codex-app-server/src/config_manager.rs status

Rust source:

- `codex/codex-rs/app-server/src/config_manager.rs`

Python target:

- `pycodex/app_server/config_manager.py`

Status: `complete`

## Covered contract

- `ConfigManager` stores codex home, CLI overrides, loader overrides, strict
  config, cloud requirements loader, arg0 dispatch paths, and thread config
  loader handles.
- Current-handle helpers preserve Rust's local clone/handle behavior.
- Runtime feature enablement can be extended, read back, and applied to a
  config while skipping feature keys protected by config layers or managed
  requirements.
- `replace_cloud_requirements_loader(...)` and
  `replace_thread_config_loader(...)` preserve the app-server side swap points.
- `load_latest_config(...)`, `load_with_overrides(...)`, and
  `load_for_cwd(...)` delegate into `load_with_cli_overrides(...)`.
- `load_with_cli_overrides(...)` preserves the Rust request override merge:
  `bypass_hook_trust` is removed from ad-hoc overrides, must be boolean, and is
  moved into typed overrides before CLI/request overrides are chained.
- `load_latest_config_for_thread(...)` reloads with the thread cwd, calls
  `rebuild_preserving_session_layers(...)`, then applies runtime feature
  enablement and arg0 dispatch paths.
- `load_default_config(...)` applies runtime feature enablement and arg0 paths
  and injects an empty user profile layer when loader overrides specify a user
  config path or profile.
- `load_config_layers(...)` preserves the Rust call-shape into the config layer
  loader: codex home, cwd, current CLI overrides, strict/load options, current
  cloud requirements, and current thread-config loader.

## Deferred boundaries

- Concrete `codex_core::config::ConfigBuilder::build(...)` execution remains a
  runtime dependency injected into the Python manager.
- Concrete `Config::load_default_with_cli_overrides_for_codex_home(...)`
  execution remains injected.
- Concrete `load_config_layers_state(...)` filesystem/config loader execution
  remains injected.
- Real Rust lock poisoning behavior, tracing warnings, exact `std::io::Error`
  identity, AuthManager internals, and default client residency global side
  effects remain runtime/platform details.

## Python parity tests

- `tests/test_app_server_config_manager_rs.py`

- `python -m pytest tests/test_app_server_config_manager_rs.py -q` passed on
  2026-06-19 with 8 tests.
- `python -m py_compile pycodex/app_server/config_manager.py
  tests/test_app_server_config_manager_rs.py` passed on 2026-06-19.
