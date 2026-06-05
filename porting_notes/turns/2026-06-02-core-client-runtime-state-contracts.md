# Core Client Runtime State Contracts

Date: 2026-06-02

## Scope

Continued the graph-guided core runtime slice around:

`exec -> context/model request -> websocket/session request preparation -> stream event application -> final runtime state`

This stayed on the common client/runtime path and did not expand MCP, plugin, marketplace, cloud, or daemon work.

## Python Changes

- Exported websocket trace metadata constants and `build_session_headers` from `pycodex.core`.
- Included `x-codex-installation-id` in the shared websocket/realtime header base.
- Aligned `tests/test_core_client.py` with the current Python runtime-state contract:
  - runtime summaries include metadata/follow-up state and `completed_output_items` counts;
  - assistant/raw text delta state records include emitted stream events;
  - output item done state records expose whether a completed response item was carried;
  - websocket request payload assertions use the current flattened `response.create` shape;
  - session lifecycle tests now distinguish reused, new, blocked, ready, and warmup paths explicitly.

## Validation

- `python -m py_compile pycodex\core\client.py pycodex\core\__init__.py tests\test_core_client.py`
- `python -m compileall -q pycodex`
- `python -m unittest tests.test_core_http_transport tests.test_exec_config_plan tests.test_exec_run`
  - 141 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 184 tests passed.
- Ran 128 synchronous `tests.test_core_client` functions with a minimal in-memory `pytest` shim.
  - All synchronous functions passed.
  - The shim emits one coroutine warning for an async-style websocket header test because real pytest is not installed in this environment.

## Known Gaps

- Normal pytest execution is still unavailable in this environment because `pytest` is not installed.
- The async pytest-marked client test is only import-covered by the shim; it should be run under real pytest later.
