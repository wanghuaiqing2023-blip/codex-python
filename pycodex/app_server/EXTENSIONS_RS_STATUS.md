# codex-app-server src/extensions.rs status

Rust module: `codex/codex-rs/app-server/src/extensions.rs`

Python module: `pycodex/app_server/extensions.py`

Status: `complete`

## Covered

- `thread_extensions(...)` builds a real `ExtensionRegistry` in Rust install
  order: guardian, memories, then web search, using the global OpenTelemetry
  provider.
- `app_server_extension_event_sink(...)` returns a real `ExtensionEventSink`
  and mirrors
  `AppServerExtensionEventSink::emit(...)`: `ThreadGoalUpdated` events are
  forwarded as app-server `ThreadGoalUpdated` notifications, while unsupported
  extension events are dropped with debug metadata.
- The event sink mirrors the core `ThreadGoal` to
  app-server `ThreadGoal` conversion used by the event sink.
- `guardian_agent_spawner(...)` returns an `AgentSpawner`, mirrors the weak
  `ThreadManager` upgrade boundary, delegates to `spawn_subagent(...)`, and
  raises the Rust unsupported-operation error when the manager was dropped.

## Neighboring dependency boundaries

- Guardian, memories, and web-search extension internals remain owned by their
  sibling crates; this module verifies their registry installation boundary.

## Python parity tests

- `tests/test_app_server_extensions_rs.py`

- `python -B -m pytest -q tests/test_app_server_extensions_rs.py` passed on
  2026-07-23 with 5 tests.
