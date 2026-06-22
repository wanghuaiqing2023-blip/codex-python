# codex-exec-server src/client/http_response_body_stream.rs Status

Rust source: `codex/codex-rs/exec-server/src/client/http_response_body_stream.rs`

Python surface: `pycodex.exec_server`

Status: `complete` for remote streamed-body routing

## Scope

This slice covers the dependency-light remote response-body stream behavior:

- `HttpResponseBodyStream.remote(...)` receives
  `HttpRequestBodyDeltaNotification` values from a request-local queue.
- `recv()` enforces contiguous sequence numbers, returns chunks, translates
  terminal `done` to EOF, and converts stream errors/failures to protocol
  errors.
- Dropping a remote stream schedules route removal when an event loop is active.
- `ExecServerClient` owns the request-id routing table:
  `next_http_body_stream_request_id`, `insert_http_body_stream`,
  `remove_http_body_stream`, `handle_http_body_delta_notification`, and
  `fail_all_http_body_streams`.
- Unknown request ids are ignored intentionally, matching the Rust EOF/drop
  race contract.

## Evidence

- Rust source:
  - `src/client/http_response_body_stream.rs`
  - `src/client/rpc_http_client.rs`
- Python tests:
  - `tests/test_exec_server_http_response_body_stream_rs.py`

## Validation

```powershell
python -m pytest tests/test_exec_server_http_response_body_stream_rs.py -q --tb=short
python -m pytest tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_server_remote_rs.py tests/test_exec_server_environment_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_http_response_body_stream_rs.py
```

Remaining HTTP client runtime boundaries: concrete reqwest execution,
buffered/streamed local response conversion, JSON-RPC `http/request` call
integration, and full cancellation/drop races around in-flight header requests.

## Completion validation

2026-06-21:

```text
python -m pytest tests/test_exec_server_http_response_body_stream_rs.py -q --tb=short
8 passed

python -m pytest tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_server_remote_rs.py tests/test_exec_server_environment_rs.py -q --tb=short
37 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_http_response_body_stream_rs.py
passed
```
