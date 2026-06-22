# codex-api src/sse/responses.rs status

Rust crate: `codex-api`

Rust module: `src/sse/responses.rs`

Python package/module: `pycodex/codex_api/sse/responses.py`

Status: `complete`

Implemented Rust-derived behavior:

- `ResponsesStreamEvent` JSON shape for the event fields used by response SSE
  event decoding.
- `response_model` header extraction, including response-header precedence,
  top-level header fallback, `openai-model` / `x-openai-model` matching, and
  first-array-item string handling.
- `model_verifications` metadata-only extraction for
  `trusted_access_for_cyber`, with unknown/non-array values ignored.
- `process_responses_event` pure event mapping for output item, output text,
  custom tool-call input, reasoning summary text, reasoning text, created,
  completed, output-item added, and reasoning-summary part added events.
- `response.completed` token-usage projection, including cached input tokens,
  reasoning output tokens, `end_turn`, and parse-error mapping to stream
  errors when the completed response shape is invalid.
- `response.failed` classification for context-window, quota, usage-not-
  included, cyber-policy, invalid-prompt, overloaded/slow-down, retryable, and
  malformed failed-response cases.
- `response.incomplete` stream-error message construction.
- `try_parse_retry_after` `rate_limit_exceeded` seconds and milliseconds
  parsing.
- `process_sse` dependency-light stream parsing for SSE `data:` frames,
  response-header server model updates, model verification metadata, completed
  termination, failed-response error retention until stream close, missing
  completed errors, transport errors, and idle timeout errors.
- Server-model extraction ignores bare `response.model` payload fields, and
  model verification extraction ignores response headers as in Rust.
- `spawn_response_stream` header prelude projection for server model,
  rate-limit snapshots, models ETag, reasoning-included markers, upstream
  request id, and turn-state capture.

Runtime adaptation:

- Rust uses Tokio tasks, mpsc channels, `eventsource_stream`, and elapsed-time
  telemetry callbacks. Python keeps the same observable event/error ordering
  through a synchronous iterable `ResponseStream` facade so the port stays
  standard-library-first.
- The telemetry parameter is retained as an interface constraint; elapsed poll
  timing is not modeled by this synchronous facade.

Validation:

- `python -m pytest tests/test_codex_api_sse_responses_rs.py -q --tb=short`
  passed on 2026-06-21 with `22 passed, 7 subtests passed`.
- `python -m py_compile pycodex/codex_api/sse/responses.py tests/test_codex_api_sse_responses_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `240 passed, 71 subtests passed`.
