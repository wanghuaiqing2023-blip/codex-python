# codex-api/src/endpoint/responses.rs status

Rust module: `codex/codex-rs/codex-api/src/endpoint/responses.rs`

Python module: `pycodex/codex_api/endpoint/responses.py`

Status: `complete`

Implemented behavior:

- `ResponsesOptions` stores session id, thread id, session source, extra
  headers, request compression, and optional turn-state handle.
- `ResponsesClient.new(...)` constructs the shared `EndpointSession`.
- `with_telemetry(...)` threads request telemetry into the session and stores
  SSE telemetry for the response-stream handoff.
- `stream_request(...)` serializes `ResponsesApiRequest`, applies Azure stored
  request item-id reattachment, builds client/session/thread/subagent headers,
  and delegates to `stream(...)`.
- `path()` returns the fixed `responses` endpoint path.
- `stream(...)` maps request compression to `codex-client` compression, adds
  `accept: text/event-stream`, delegates to `EndpointSession.stream_with`, and
  hands off to `spawn_response_stream(...)`.
- `spawn_response_stream(...)` preserves the response stream handoff boundary,
  upstream request id projection, and turn-state response-header side effect.

Runtime boundary:

- Full SSE parsing and event conversion remain owned by `codex-api/src/sse`.
  This module preserves the endpoint-to-SSE handoff shape without duplicating
  sibling module behavior.

Validation:

- `python -m pytest tests/test_codex_api_endpoint_responses_rs.py -q --tb=short`
  passed on 2026-06-20 with `4 passed`.
- `python -m py_compile pycodex/codex_api/endpoint/responses.py tests/test_codex_api_endpoint_responses_rs.py pycodex/codex_api/endpoint/__init__.py pycodex/codex_api/__init__.py`
  passed on 2026-06-20.
