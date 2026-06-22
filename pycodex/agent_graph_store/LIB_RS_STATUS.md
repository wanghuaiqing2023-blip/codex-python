# codex-agent-graph-store src/lib.rs status

Rust source:

- `codex/codex-rs/agent-graph-store/src/lib.rs`

Python target:

- `pycodex/agent_graph_store/__init__.py`

Status: complete.

Implemented contract:

- The package root documents the crate purpose: storage-neutral parent/child
  topology for thread-spawned agents.
- The Rust module tree is represented by Python modules:
  `error.py`, `local.py`, `store.py`, and `types.py`.
- The Rust public crate-root exports are available from
  `pycodex.agent_graph_store`:
  `AgentGraphStoreError`, `AgentGraphStoreResult`, `LocalAgentGraphStore`,
  `AgentGraphStore`, and `ThreadSpawnEdgeStatus`.

Python adaptation:

- Additional helper exports such as `invalid_request`, `internal`,
  `to_state_status`, and `validate_agent_graph_store` remain public Python
  convenience APIs, but the Rust root export surface is explicitly covered.

Tests:

- `tests/test_agent_graph_store_lib_rs.py`

Validation:

- Crate pytest after all modules completed:
  `python -m pytest tests/test_agent_graph_store_types_rs.py tests/test_agent_graph_store_error_rs.py tests/test_agent_graph_store_store_rs.py tests/test_agent_graph_store_local_rs.py tests/test_agent_graph_store_lib_rs.py -q` -> `15 passed`
