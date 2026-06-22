# codex-agent-graph-store src/types.rs status

Rust coordinate: `codex/codex-rs/agent-graph-store/src/types.rs`

Python coordinate: `pycodex/agent_graph_store/types.py`

Status: complete.

Ported public API:

- `ThreadSpawnEdgeStatus`

Ported behavior:

- `Open` serializes as `"open"`.
- `Closed` serializes as `"closed"`.
- Deserialization accepts only the Rust snake_case wire values.
- Unknown or non-string values are rejected.

Rust-derived test evidence:

- `tests/test_agent_graph_store_types_rs.py`

Validation:

- Syntax-only this turn because the full `codex-agent-graph-store` crate functional code is not yet complete:
  `python -m py_compile pycodex/agent_graph_store/__init__.py pycodex/agent_graph_store/types.py tests/test_agent_graph_store_types_rs.py`
