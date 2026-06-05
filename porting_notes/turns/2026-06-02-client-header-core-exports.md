# Client Header Core Exports

## Upstream graph/source slice

- Used `codex/.understand-anything/knowledge-graph.json` to navigate the client side of the core path:
  - `codex-rs/core/src/client.rs#ModelClientSession`
  - `codex-rs/core/src/client.rs#build_responses_request`
  - `codex-rs/core/src/client.rs#stream_responses_websocket`
  - `codex-rs/core/src/client.rs#stream`
- Confirmed from Rust source that Responses/WebSocket request construction carries Codex identity and turn metadata through shared header/client-metadata helpers.

## Python changes

- `pycodex/core/__init__.py`
  - Re-exported `WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY`.
  - Re-exported `WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY`.
  - Re-exported `build_session_headers`.
- `pycodex/core/client.py`
  - Added `x-codex-installation-id` to the shared WebSocket/realtime header base, matching the identity header behavior already expected by the core client tests.

## Validation

- `python -m py_compile pycodex\core\client.py pycodex\core\__init__.py tests\test_core_client.py`
- Ran targeted `tests.test_core_client` header/metadata functions with an in-memory pytest `raises` shim because the active Python environment does not have pytest installed.
- `python -m unittest tests.test_core_http_transport tests.test_exec_config_plan tests.test_exec_run`
- `python -m compileall -q pycodex`

## Known gaps

- The full `tests.test_core_client` module still cannot be run through the normal pytest runner in this environment because pytest is not installed.
- A later sync function in `tests.test_core_client` currently fails on a large runtime state summary assertion; that appears separate from this header/export slice and should be handled as its own graph-guided client runtime state pass.
