# SSE stop-after-completed parity

## Rust sources checked

- `codex/codex-rs/codex-api/src/sse/responses.rs`
- `codex/codex-rs/core/src/client.rs`
- `codex/codex-rs/core/src/session/turn.rs`

## Behavior confirmed

- Rust SSE processing emits `ResponseEvent::Completed` and then returns from the SSE processing task.
- Events after `response.completed` are not processed by the core turn loop.
- The session turn loop treats stream closure before `response.completed` as `stream closed before response.completed`, but completed itself is terminal for that stream.

## Python changes

- Updated `pycodex/core/http_transport.py` so `_parse_responses_sse_stream` stops parsing after a valid `response.completed`.
- Added a focused SSE parser test proving a late `response.failed` and late `response.output_item.done` after completed do not overwrite or fail the completed result.

## Validation

- `python -m py_compile pycodex/core/http_transport.py tests/test_core_http_transport.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_http_transport.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py tests/test_core_client.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_stream_events_utils.py tests/test_core_turn_timing.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`

Final smoke result: `744 passed, 1 skipped, 98 subtests passed`.

## Known gaps

- This slice only aligns SSE terminal event handling. Broader websocket stream transport parity remains ongoing.
