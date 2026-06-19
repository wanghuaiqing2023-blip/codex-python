# request_processors/apps_processor.rs Status

Rust module: `codex-app-server/src/request_processors/apps_processor.rs`

Python module: `pycodex/app_server/request_processors_apps_processor.py`

Status: `complete`

## Covered Contract

- Processor construction preserves Rust's injected auth/thread/outgoing/config
  manager, workspace settings cache, shutdown token, connector-loader, and
  task-spawn boundaries.
- `apps_list`/`apps_list_inner` preserve optional thread loading, config
  snapshot fallback CWD, latest-config reload error mapping, feature/auth
  gating, workspace plugin gating, immediate empty-list responses, and spawned
  list-task behavior.
- `apps_list_task` and `apps_list_response` preserve cached/interim/final
  app-list update notification behavior, connector merge and enabled-state
  projection, final pagination, `codex_apps_ready` return, and force-refetch
  retry when Codex apps are not ready.
- `merge_loaded_apps`, `should_send_app_list_updated_notification`,
  `paginate_apps`, and cursor parsing mirror the Rust helpers.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/apps_processor.rs`
- Python parity tests staged in
  `tests/test_app_server_request_processors_apps_processor_rs.py`.
- Rust local tests: none in this module; parity is source-contract based.
- Focused validation completed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_apps_processor_rs.py -q`
  -> 8 passed.
- Syntax validation completed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_apps_processor.py tests/test_app_server_request_processors_apps_processor_rs.py`.

## Known Gaps

- Concrete connector discovery, MCP environment-manager loading, workspace
  backend fetch, Tokio task scheduling, channel timeout timing, and concrete
  outgoing transport delivery remain dependency/runtime boundaries.
