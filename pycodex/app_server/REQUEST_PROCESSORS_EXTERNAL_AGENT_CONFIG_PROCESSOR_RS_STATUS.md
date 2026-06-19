# request_processors/external_agent_config_processor.rs Status

Rust module: `codex-app-server/src/request_processors/external_agent_config_processor.rs`

Python module: `pycodex/app_server/request_processors_external_agent_config_processor.py`

Status: `complete`

## Covered Contract

- Processor construction preserves Rust's outgoing sender, codex-home,
  thread/config manager, config processor, arg0 path, migration service, and
  task-spawn/session-import permit boundaries.
- `detect` preserves Rust's detect-option projection and maps core migration
  item/details shapes into protocol `ExternalAgentConfigMigrationItem`
  responses.
- `import_` preserves Rust's request flow: validate pending session imports,
  import config items, refresh runtime sources when required, send the RPC
  response before background work, send immediate completion for foreground-only
  imports, and schedule background session/plugin completion when needed.
- Session validation preserves source-path lookup, invalid-params errors for
  undetected sessions, and first-seen dedupe by detected source path.
- Helper behavior mirrors Rust's runtime-refresh item classifier and session
  not-detected JSON-RPC error text.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/external_agent_config_processor.rs`
- Rust local test:
  `migration_items_that_update_runtime_sources_trigger_refresh`
- Python parity tests staged in
  `tests/test_app_server_request_processors_external_agent_config_processor_rs.py`.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_external_agent_config_processor_rs.py -q`
  -> 8 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_external_agent_config_processor.py tests/test_app_server_request_processors_external_agent_config_processor_rs.py`.

## Known Gaps

- Full external session replay, thread startup, plugin installation, cache
  internals, imported-session ledger persistence, and Tokio scheduling remain
  injected dependency/runtime boundaries.
