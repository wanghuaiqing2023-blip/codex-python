# 2026-06-02 HTTP SSE metadata stream events

## Upstream behavior

- Rust's core response stream treats server model and model verification data as
  stream events consumed by `try_run_sampling_request`.
- `ResponseEvent::ServerModel` can trigger a server-model mismatch warning.
- `ResponseEvent::ModelVerifications` can emit model verification information
  while the response stream is being handled.

## Python port progress

- The Python HTTP/SSE transport already parsed server model headers and
  `response.metadata` verification recommendations into the final sampling
  result metadata.
- Added core stream-event projection for this metadata in
  `pycodex.core.http_transport`:
  - new server model values now add `{"type": "server_model", ...}`;
  - new verification recommendations now add
    `{"type": "model_verifications", ...}`;
  - duplicate model verification recommendations remain deduplicated.
- This connects the HTTP transport to the stream metadata side-effect path added
  in the core runtime.

## Validation

- `python -m py_compile pycodex/core/http_transport.py tests/test_core_http_transport.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_http_transport.py::HttpTransportTests::test_run_user_turn_http_sampling_records_sse_metadata_model_verification_once tests/test_core_http_transport.py::HttpTransportTests::test_send_prepared_http_sampling_request_records_rust_style_sse_stream_events tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_applies_stream_server_model_and_verification_metadata -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_http_transport.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
