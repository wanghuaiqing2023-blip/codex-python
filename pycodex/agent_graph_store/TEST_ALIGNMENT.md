# codex-agent-graph-store test alignment

Rust crate: `codex-agent-graph-store`

Python package: `pycodex/agent_graph_store`

Status: `complete`

Module mapping:

- `codex/codex-rs/agent-graph-store/src/types.rs` -> `pycodex/agent_graph_store/types.py` (`complete`)
- `codex/codex-rs/agent-graph-store/src/error.rs` -> `pycodex/agent_graph_store/error.py` (`complete`)
- `codex/codex-rs/agent-graph-store/src/store.rs` -> `pycodex/agent_graph_store/store.py` (`complete`)
- `codex/codex-rs/agent-graph-store/src/local.rs` -> `pycodex/agent_graph_store/local.py` (`complete`)
- `codex/codex-rs/agent-graph-store/src/lib.rs` -> `pycodex/agent_graph_store/__init__.py` (`complete`)

Rust-derived coverage for `src/types.rs`:

- `thread_spawn_edge_status_serializes_as_snake_case`

Additional source-contract coverage:

- Unknown and non-string status values are rejected.
- `src/error.rs` invalid-request/internal display messages, constructors, base type, variants, and message validation.
- `src/store.rs` exposes the four async trait methods in Rust order and validates injected implementations for async callability.
- `src/local.rs` covers local-store status conversion, direct child status filtering, edge status updates, descendant listing with status filters, and state-error wrapping.
- `src/lib.rs` covers crate-root public re-exports for the Rust `pub use` surface.

Validation:

- Crate pytest after all modules completed:
  `python -m pytest tests/test_agent_graph_store_types_rs.py tests/test_agent_graph_store_error_rs.py tests/test_agent_graph_store_store_rs.py tests/test_agent_graph_store_local_rs.py tests/test_agent_graph_store_lib_rs.py -q` -> `15 passed`
