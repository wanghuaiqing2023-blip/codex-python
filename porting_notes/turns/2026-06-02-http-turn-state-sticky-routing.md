# HTTP turn-state sticky routing

## Upstream source

- `codex/codex-rs/core/src/client.rs`
- `codex/codex-rs/codex-api/src/sse/responses.rs`
- `codex/codex-rs/codex-api/src/endpoint/responses.rs`
- `codex/codex-rs/codex-api/src/endpoint/responses_websocket.rs`

Rust captures the `x-codex-turn-state` response header into the per-turn `OnceLock<String>` and replays that value as the `x-codex-turn-state` request header for later requests in the same model-client session. This supports server-side sticky routing across streaming requests and tool follow-ups.

## Python changes

- Extended `HttpTransportConfig` with an optional `turn_state` reference.
- `model_client_http_sampler` now attaches `ModelClientSession.turn_state` to the transport config.
- `send_prepared_http_sampling_request` now:
  - injects the latest turn-state value into request headers at send time, so follow-up requests see newly captured state;
  - records `x-codex-turn-state` from response headers with OnceLock-style semantics.
- Added HTTP transport coverage proving the second request replays the first response's sticky token and later response headers do not overwrite it.

## Validation

- `python -m py_compile pycodex\core\http_transport.py tests\test_core_http_transport.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_http_transport.py -q -k "turn_state or transport_config"`
  - 4 passed, 48 deselected
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_client.py -q -k "turn_state or responses_headers or websocket_headers"`
  - 8 passed, 123 deselected, 1 pre-existing warning
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_http_transport.py -q`
  - 52 passed, 9 subtests passed
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_turn_runtime.py tests\test_core_client.py -q`
  - 201 passed, 1 pre-existing warning
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 744 passed, 1 skipped, 98 subtests passed

## Follow-up

Keep sticky-routing work scoped to the core HTTP/SSE path. WebSocket turn-state capture is already represented by the Rust source and Python client header machinery, but deeper WebSocket runtime parity remains outside the active HTTP-first slice unless the main exec path starts using it.
