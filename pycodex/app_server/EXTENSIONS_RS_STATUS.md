# codex-app-server src/extensions.rs status

Rust module: `codex/codex-rs/app-server/src/extensions.rs`

Python module: `pycodex/app_server/extensions.py`

Status: `complete`

## Covered

- `thread_extensions_projection(...)` records Rust's extension registry
  install order: guardian, memories, then web search, with the global
  OpenTelemetry provider marker.
- `app_server_extension_event_sink_projection(...)` mirrors
  `AppServerExtensionEventSink::emit(...)`: `ThreadGoalUpdated` events are
  forwarded as app-server `ThreadGoalUpdated` notifications, while unsupported
  extension events are dropped with debug metadata.
- `app_server_thread_goal_from_core(...)` mirrors the core `ThreadGoal` to
  app-server `ThreadGoal` conversion used by the event sink.
- `guardian_agent_spawn_projection(...)` mirrors the weak `ThreadManager`
  upgrade boundary and delegates to `spawn_subagent(...)` when available, or
  returns the Rust unsupported-operation message when dropped.

## Deferred

- Real `ExtensionRegistryBuilder`, guardian/memories/web-search extension
  installation, AuthManager use, OpenTelemetry provider values, and concrete
  async subagent spawning remain runtime/extension dependencies.

## Python parity tests

- `tests/test_app_server_extensions_rs.py`

- `python -m pytest tests/test_app_server_extensions_rs.py -q` passed on
  2026-06-19 with 6 tests.
- `python -m py_compile pycodex/app_server/extensions.py
  tests/test_app_server_extensions_rs.py` passed on 2026-06-19.
