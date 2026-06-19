# codex-agent-graph-store src/error.rs status

Rust coordinate: `codex/codex-rs/agent-graph-store/src/error.rs`

Python coordinate: `pycodex/agent_graph_store/error.py`

Status: complete.

Ported public API:

- `AgentGraphStoreError`
- `AgentGraphStoreResult`
- `InvalidRequest`
- `Internal`

Ported behavior:

- Invalid request errors display as `invalid agent graph store request: {message}`.
- Internal errors display as `agent graph store internal error: {message}`.
- Error instances preserve their user-facing message and expose variant identity.

Rust-derived/source-contract test evidence:

- `tests/test_agent_graph_store_error_rs.py`

Validation:

- Syntax-only this turn because the full `codex-agent-graph-store` crate functional code is not yet complete:
  `python -m py_compile pycodex/agent_graph_store/__init__.py pycodex/agent_graph_store/error.py tests/test_agent_graph_store_error_rs.py`
