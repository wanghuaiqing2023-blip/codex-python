# codex-agent-graph-store src/local.rs status

Rust source:

- `codex/codex-rs/agent-graph-store/src/local.rs`

Python target:

- `pycodex/agent_graph_store/local.py`

Status: complete.

Implemented contract:

- `LocalAgentGraphStore.new(...)` and constructor retain an existing state
  runtime/thread-store adapter rather than owning database initialization.
- The four async `AgentGraphStore` methods forward to the state runtime graph
  methods.
- `to_state_status(...)` maps `ThreadSpawnEdgeStatus.Open/Closed` to
  `DirectionalThreadSpawnEdgeStatus.OPEN/CLOSED`.
- State-runtime failures are wrapped as `AgentGraphStoreError.Internal` display
  messages, matching Rust `internal_error`.
- `repr(...)` exposes the runtime `codex_home` value in the same spirit as the
  Rust debug formatter.

Python adaptation:

- Current Python `StateRuntime` keeps thread graph methods under `.threads`;
  `LocalAgentGraphStore` also accepts objects that expose the methods directly
  to preserve the Rust-facing boundary.

Tests:

- `tests/test_agent_graph_store_local_rs.py`

Validation:

- Syntax-only while the crate remains partial:
  `python -m py_compile pycodex/agent_graph_store/__init__.py pycodex/agent_graph_store/types.py pycodex/agent_graph_store/error.py pycodex/agent_graph_store/store.py pycodex/agent_graph_store/local.py tests/test_agent_graph_store_types_rs.py tests/test_agent_graph_store_error_rs.py tests/test_agent_graph_store_store_rs.py tests/test_agent_graph_store_local_rs.py`
