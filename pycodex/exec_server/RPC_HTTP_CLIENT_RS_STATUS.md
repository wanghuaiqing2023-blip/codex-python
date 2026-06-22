# codex-exec-server src/client/rpc_http_client.rs Status

Rust source: `codex/codex-rs/exec-server/src/client/rpc_http_client.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Scope

This module adapts `ExecServerClient` to the environment-owned HTTP client
capability by forwarding requests over JSON-RPC:

- `ExecServerClient.http_request(...)` forces `stream_response=false` and calls
  `http/request`.
- `ExecServerClient.http_request_stream(...)` allocates a connection-local
  `http-N` request id, overwrites caller-supplied request ids, registers a
  body-delta route before issuing `http/request`, removes the route if the
  header request fails, and returns `HttpResponseBodyStream.remote(...)` on
  success.
- `HTTP_BODY_DELTA_CHANNEL_CAPACITY` mirrors the Rust queue capacity.

The actual JSON-RPC transport call remains injectable in Python through
`ExecServerClient.call(...)`; full transport response matching is owned by
`src/rpc.rs` and `src/client.rs` connection orchestration.

## Evidence

- Rust source:
  - `src/client/rpc_http_client.rs`
  - `src/client/http_response_body_stream.rs`
- Python tests:
  - `tests/test_exec_server_rpc_http_client_rs.py`

## Validation

```powershell
python -m pytest tests/test_exec_server_rpc_http_client_rs.py -q --tb=short
python -m pytest tests/test_exec_server_rpc_http_client_rs.py tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_server_remote_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_rpc_http_client_rs.py
```

Remaining HTTP runtime boundaries: concrete reqwest request execution,
transport-level response matching for `ExecServerClient.call`, and local
streamed HTTP body conversion.

## Completion validation

2026-06-21:

```text
python -m pytest tests/test_exec_server_rpc_http_client_rs.py -q --tb=short
5 passed

python -m pytest tests/test_exec_server_rpc_http_client_rs.py tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_server_remote_rs.py -q --tb=short
31 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_rpc_http_client_rs.py
passed
```
