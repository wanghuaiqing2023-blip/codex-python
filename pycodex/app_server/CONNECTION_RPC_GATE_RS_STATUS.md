# codex-app-server src/connection_rpc_gate.rs status

Rust module: `codex/codex-rs/app-server/src/connection_rpc_gate.rs`

Python module: `pycodex/app_server/connection_rpc_gate.py`

Status: `complete`

## Covered

- `ConnectionRpcGate.new()` mirrors Rust's default open gate construction.
- `ConnectionRpcGate.run(...)` mirrors the accepting check, token acquisition
  before handler execution, handler await, token drop, and rejected late-run
  path after shutdown.
- `ConnectionRpcGate.shutdown()` mirrors closing acceptance and waiting for
  already-started handlers to finish.
- Test-only inspection helpers `is_accepting()` and `inflight_count()` mirror
  the Rust test helpers.

## Deferred

- Rust `tokio_util::task::TaskTracker` internals and exact scheduling fairness
  are represented with `asyncio.Condition`; no external app-server runtime
  integration is attempted in this module.

## Python parity tests

- `tests/test_app_server_connection_rpc_gate_rs.py`

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_connection_rpc_gate_rs.py -q`
  -> 5 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/connection_rpc_gate.py tests/test_app_server_connection_rpc_gate_rs.py`.
