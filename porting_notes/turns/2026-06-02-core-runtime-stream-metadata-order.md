# 2026-06-02 Core runtime stream metadata order

## Upstream behavior

- Rust handles `ResponseEvent::ServerModel` and
  `ResponseEvent::ModelVerifications` as stream events inside
  `try_run_sampling_request`.
- Their side effects happen according to stream order instead of being applied
  eagerly from the final response metadata before streamed assistant/tool
  events are processed.

## Python port progress

- `pycodex.core.http_transport` now projects SSE metadata into core
  `stream_events`.
- Updated `pycodex.core.turn_runtime` so raw sampling metadata does not eagerly
  apply server-model or model-verification side effects when equivalent stream
  events are present.
- Header/final-result metadata that does not have stream events, such as
  `server_reasoning_included`, `models_etag`, rate limits, and non-stream
  JSON responses, keeps the existing path.
- Added coverage proving streamed assistant deltas are emitted before model
  verification when the stream orders them that way, even if raw result
  metadata also contains the verification.

## Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_prefers_stream_metadata_order_over_raw_metadata tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_applies_stream_server_model_and_verification_metadata tests/test_core_http_transport.py::HttpTransportTests::test_run_user_turn_http_sampling_records_sse_metadata_model_verification_once -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_http_transport.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
