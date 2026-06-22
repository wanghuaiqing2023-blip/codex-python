# codex-exec-server src/client/reqwest_http_client.rs Status

Rust source: `codex/codex-rs/exec-server/src/client/reqwest_http_client.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Scope

This module owns the local HTTP client runtime used by `http/request`:

- `ReqwestHttpRequestRunner.run(...)` validates method, URL scheme, and headers,
  sends a real standard-library HTTP request, and returns status, response
  headers, and buffered body bytes.
- `ReqwestHttpClient.http_request(...)` forces buffered response mode and maps
  JSON-RPC runner errors into `ExecServerError.http_request(...)`.
- `ReqwestHttpClient.http_request_stream(...)` returns an empty buffered body
  plus a local `HttpResponseBodyStream`.
- `ReqwestHttpRequestRunner.stream_body(...)` forwards local pending response
  chunks as ordered `http/request/bodyDelta` notifications with a terminal
  empty done frame.

The Python implementation intentionally uses `urllib` from the standard library
instead of adding a third-party HTTP dependency.

## Evidence

- Rust source:
  - `src/client/reqwest_http_client.rs`
  - `src/client/http_response_body_stream.rs`
- Rust integration tests:
  - `tests/http_request.rs::exec_server_http_request_buffers_response_body`
  - `tests/http_request.rs::exec_server_http_request_streams_response_body_notifications`
- Python tests:
  - `tests/test_exec_server_reqwest_http_client_rs.py`

## Validation

```powershell
python -m pytest tests/test_exec_server_reqwest_http_client_rs.py -q --tb=short
python -m pytest tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_rpc_http_client_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_reqwest_http_client_rs.py
```

Non-blocking runtime notes: exact `reqwest` custom-CA/TLS behavior, redirect
policy nuances, and immediate header-before-body streaming timing are not
claimed by this dependency-light slice and remain optional operational checks.

## Completion validation

2026-06-21:

```text
python -m pytest tests/test_exec_server_reqwest_http_client_rs.py -q --tb=short
8 passed

python -m pytest tests/test_exec_server_reqwest_http_client_rs.py tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_rpc_http_client_rs.py -q --tb=short
21 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_reqwest_http_client_rs.py
passed
```
