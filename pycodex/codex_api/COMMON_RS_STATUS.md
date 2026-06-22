# codex-api/src/common.rs status

Rust module: `codex/codex-rs/codex-api/src/common.rs`

Python module: `pycodex/codex_api/common.py`

Status: `complete`

Ported contract:

- Websocket request metadata constants and
  `response_create_client_metadata(...)` traceparent/tracestate merge behavior.
- `Reasoning`, `TextFormatType`, `TextFormat`, `TextControls`, and
  `OpenAiVerbosity` wire-shape helpers.
- `create_text_param_for_request(...)` verbosity/schema branching and
  `codex_output_schema` JSON-schema format construction.
- `CompactionInput`, `MemorySummarizeInput`, `RawMemory`,
  `RawMemoryMetadata`, and `MemorySummarizeOutput` serde rename/skip behavior.
- `MemorySummarizeOutput` rejects payloads missing both `trace_summary` and
  `raw_memory`, matching Rust required-field deserialization.
- `ResponsesApiRequest` to `ResponseCreateWsRequest` conversion, including
  cloned shared fields, empty `client_metadata` preservation, and
  `previous_response_id`/`generate` defaults.
- `ResponseProcessedWsRequest` and tagged `ResponsesWsRequest` wire shapes.
- Lightweight `ResponseStream` event/upstream-request-id boundary.

Intentional adaptation:

- Rust uses protocol crate structs, `tokio::mpsc::Receiver`, and implements
  `futures::Stream`. Python uses dependency-light dataclasses plus a small
  iterator-backed `ResponseStream` because async endpoint execution belongs to
  later endpoint/SSE module slices.

Validation:

- `tests/test_codex_api_common_rs.py`
- Focused validation command:
  `python -m pytest tests/test_codex_api_common_rs.py -q --tb=short`
  (`8 passed`)
- Syntax validation:
  `python -m py_compile pycodex\codex_api\common.py tests\test_codex_api_common_rs.py`
- Codex API focused validation:
  `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` (`212 passed, 47 subtests passed`)
