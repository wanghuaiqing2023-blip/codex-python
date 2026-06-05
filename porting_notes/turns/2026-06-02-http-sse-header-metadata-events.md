# HTTP SSE header metadata ResponseEvents

## Upstream Rust slice

- `codex/codex-rs/codex-api/src/sse/responses.rs` emits header-derived metadata before processing the SSE body:
  `ResponseEvent::ServerModel`, `ResponseEvent::RateLimits`, `ResponseEvent::ModelsEtag`, and
  `ResponseEvent::ServerReasoningIncluded`.
- `codex/codex-rs/core/src/session/turn.rs` applies those events through the same runtime event path used by body
  stream metadata.

## Python port progress

- `pycodex/core/http_transport.py` now projects SSE response headers into `PreparedSamplingResult.stream_events`
  in the Rust order: server model, rate limits, models etag, server reasoning included, then body stream events.
- SSE body metadata is now appended before the parsed body event for the same SSE record, matching Rust
  `process_sse` behavior.
- `pycodex/core/turn_runtime.py` now lets stream metadata events own the side effects when equivalent raw
  metadata also exists on the sampling result. This avoids raw metadata applying before the Rust-style stream
  event order for server reasoning, models etag, and rate limits.

## Validation

- `python -m py_compile pycodex/core/http_transport.py pycodex/core/turn_runtime.py tests/test_core_http_transport.py tests/test_core_turn_runtime.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_http_transport.py -q`
  - `48 passed, 9 subtests passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py -q`
  - `70 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`
