# pycodex.agent_graph_store

Python alignment target for Rust crate `codex-agent-graph-store`.

Rust coordinates:

- `codex/codex-rs/agent-graph-store/src/types.rs`
- `codex/codex-rs/agent-graph-store/src/error.rs`
- `codex/codex-rs/agent-graph-store/src/store.rs`
- `codex/codex-rs/agent-graph-store/src/local.rs`
- `codex/codex-rs/agent-graph-store/src/lib.rs`

Python mapping:

- `pycodex/agent_graph_store/error.py`
- `pycodex/agent_graph_store/local.py`
- `pycodex/agent_graph_store/store.py`
- `pycodex/agent_graph_store/types.py`
- `pycodex/agent_graph_store/__init__.py`

Current status: complete.

Certified modules:

- `src/types.rs`: complete. `ThreadSpawnEdgeStatus` carries Rust snake_case wire values for open and closed thread-spawn edges.
- `src/error.rs`: complete. Shared error variants preserve Rust display messages.
- `src/store.rs`: complete. `AgentGraphStore` preserves the four async store methods and exposes a runtime async-method validator for injected store implementations.
- `src/local.rs`: complete. `LocalAgentGraphStore` adapts an existing state runtime/thread store, converts status enums, forwards list/upsert/update operations, and wraps state errors as internal graph-store errors.
- `src/lib.rs`: complete. The package root re-exports the Rust crate-root public items from `error`, `local`, `store`, and `types`.

Validation:

- Crate pytest after all modules completed:
  `python -m pytest tests/test_agent_graph_store_types_rs.py tests/test_agent_graph_store_error_rs.py tests/test_agent_graph_store_store_rs.py tests/test_agent_graph_store_local_rs.py tests/test_agent_graph_store_lib_rs.py -q` -> `15 passed`
