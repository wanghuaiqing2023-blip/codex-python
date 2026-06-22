# codex-agent-graph-store src/store.rs status

Rust source:

- `codex/codex-rs/agent-graph-store/src/store.rs`

Python target:

- `pycodex/agent_graph_store/store.py`

Status: complete.

Implemented contract:

- `AgentGraphStore` preserves the Rust trait's four async methods:
  `upsert_thread_spawn_edge`, `set_thread_spawn_edge_status`,
  `list_thread_spawn_children`, and `list_thread_spawn_descendants`.
- `REQUIRED_AGENT_GRAPH_STORE_METHODS` records the trait surface in Rust order.
- `validate_agent_graph_store(...)` provides a small runtime guard for injected
  Python store implementations, including async-method validation.

Intentionally outside this module:

- Concrete persistence, ordering queries, recursive traversal, and SQLite/local
  error conversion belong to `src/local.rs`.
- Crate-level re-exports belong to `src/lib.rs`.

Tests:

- `tests/test_agent_graph_store_store_rs.py`

Validation:

- Syntax-only while the crate remains partial:
  `python -m py_compile pycodex/agent_graph_store/__init__.py pycodex/agent_graph_store/types.py pycodex/agent_graph_store/error.py pycodex/agent_graph_store/store.py tests/test_agent_graph_store_types_rs.py tests/test_agent_graph_store_error_rs.py tests/test_agent_graph_store_store_rs.py`
