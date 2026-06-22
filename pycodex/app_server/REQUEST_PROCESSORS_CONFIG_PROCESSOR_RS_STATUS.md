# request_processors/config_processor.rs Status

Rust module: `codex-app-server/src/request_processors/config_processor.rs`

Python module: `pycodex/app_server/request_processors_config_processor.py`

Status: `complete`

## Covered Contract

- Processor construction preserves Rust's injected outgoing sender,
  config/auth/thread managers, analytics client, and runtime-only extension
  refresh boundaries.
- `read` delegates config reads through the config manager, reloads the latest
  config with the request CWD fallback, and normalizes `config.additional`
  `features` into an object populated with Rust's supported experimental
  feature enablement keys.
- `config_requirements_read` maps the Rust TOML requirements model into the
  app-server protocol, including approval policy/reviewer, sandbox mode,
  web-search disabled fallback, permissions, appshots, computer-use, hook,
  residency, feature, and network requirement projections.
- `value_write`, `batch_write`, runtime feature enablement, reload-user-config,
  cache clearing, write-error data, and plugin-toggle analytics event
  collection preserve the Rust control-flow boundaries.
- Experimental feature enablement validation preserves canonical-only support,
  legacy alias rejection with canonical-key guidance, empty-response behavior,
  runtime enablement extension, user-config refresh, response sending, and
  app-list refresh triggering for `apps: true`.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/config_processor.rs`
- Python parity tests staged in
  `tests/test_app_server_request_processors_config_processor_rs.py`.
- Rust local tests covered:
  `requirements_api_includes_allow_managed_hooks_only`,
  `requirements_api_includes_allow_appshots`, and
  `requirements_api_includes_computer_use_requirements`.
- Focused validation completed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_config_processor_rs.py -q`
  -> 10 passed.
- Syntax validation completed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_config_processor.py tests/test_app_server_request_processors_config_processor_rs.py`.

## Known Gaps

- Concrete connector directory refresh, app-enabled-state merging, installed
  plugin telemetry metadata loading, real thread-manager runtime refresh, and
  model-provider construction remain injected dependency/runtime boundaries.
