# SSE pending error until close parity

## Rust sources checked

- `codex/codex-rs/codex-api/src/sse/responses.rs`
- `codex/codex-rs/core/src/session/turn.rs`

## Behavior confirmed

- Rust `process_sse` stores errors returned by `process_responses_event` in `response_error`.
- A stored `response.failed` or `response.incomplete` error is sent only when the SSE stream closes before `response.completed`.
- If a valid `response.completed` arrives after a stored error, Rust emits `Completed` and returns, so the earlier pending error does not fail the turn.
- `response.completed` remains terminal for the stream.

## Python changes

- Updated `pycodex/core/http_transport.py` so `_parse_responses_sse_stream` keeps a pending `CodexErr` for `response.failed` and `response.incomplete` instead of raising immediately.
- If the stream ends without completed, the pending error is raised.
- If completed arrives later, completed wins and parsing stops.

## Validation

- `python -m py_compile pycodex/core/http_transport.py tests/test_core_http_transport.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_http_transport.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py tests/test_core_client.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_stream_events_utils.py tests/test_core_turn_timing.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`

Final smoke result: `744 passed, 1 skipped, 98 subtests passed`.

## Known gaps

- This slice aligns stdlib HTTP/SSE parsing. Websocket transport error sequencing still needs separate parity review.
