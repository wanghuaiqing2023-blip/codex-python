# codex-app-server src/main.rs alignment

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/main.rs`

Python module:

- `pycodex/app_server/main.py`

## Covered contract

- `AppServerArgs` startup field shape is represented by
  `AppServerArgsProjection`, including listen URL, session source, auth,
  strict config, debug plugin-startup skip, and remote-control flags.
- `disable_managed_config_from_debug_env(...)` mirrors Rust's exact debug env
  truth table for `CODEX_APP_SERVER_DISABLE_MANAGED_CONFIG`.
- `managed_config_path_from_debug_env(...)` mirrors Rust's absent/empty/path
  handling for `CODEX_APP_SERVER_MANAGED_CONFIG_PATH`.
- `loader_overrides_from_debug_env(...)` preserves Rust's selection order:
  disable managed config wins, otherwise managed path override wins, otherwise
  default loader overrides.
- `main_runtime_call_projection(...)` mirrors the Rust `main` setup before
  runtime startup: empty `CliConfigOverrides`, `strict_config`, default
  analytics disabled, parsed listen transport, parsed session source object,
  auth settings conversion boundary, debug-only plugin startup skip, and
  remote-control runtime option forwarding.

## Deferred

- Actual `clap::Parser` execution and arg0 dispatch are outside this pure
  projection.
- Concrete websocket auth validation belongs to `codex-app-server-transport`;
  this module only preserves the `try_into_settings()` call boundary.
- Real `run_main_with_transport_options(...)` runtime startup remains owned by
  `src/lib.rs`, which is tracked separately and now complete at module scope.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_main_rs.py -q` -> `8 passed`.
  Syntax validation also passed with `python -m py_compile
  pycodex/app_server/main.py tests/test_app_server_main_rs.py`.
