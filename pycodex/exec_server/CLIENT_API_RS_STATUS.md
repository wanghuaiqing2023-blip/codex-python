# client_api.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/client_api.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Rust anchors

- `DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT`
- `DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT`
- `ExecServerClientConnectOptions`
- `RemoteExecServerConnectArgs`
- `StdioExecServerCommand`
- `StdioExecServerConnectArgs`
- `ExecServerTransportParams::{WebSocketUrl, StdioCommand}`
- `ExecServerTransportParams::websocket_url`
- `HttpClient::{http_request, http_request_stream}`
- `src/client.rs` default and conversion impls for client connect options

## Python evidence

- `tests/test_exec_server_client_api_rs.py::test_remote_timeout_constants_match_rust_durations`
- `tests/test_exec_server_client_api_rs.py::test_client_connect_options_default_matches_client_impl`
- `tests/test_exec_server_client_api_rs.py::test_remote_connect_args_new_and_into_options`
- `tests/test_exec_server_client_api_rs.py::test_stdio_connect_args_into_options_and_command_normalization`
- `tests/test_exec_server_client_api_rs.py::test_transport_params_websocket_constructor_matches_rust_helper`
- `tests/test_exec_server_client_api_rs.py::test_transport_params_reject_wrong_variant_fields`
- `tests/test_exec_server_client_api_rs.py::test_http_client_trait_boundary_is_explicitly_unported`

## Notes

Python represents Rust `Duration::from_secs(10)` values as integer seconds,
matching the existing app-server-client timeout convention. The concrete
WebSocket/stdio/http transport runtime remains unported; this module only owns
the connection parameter and trait boundary shapes.

## Completion validation

2026-06-21:

```text
python -m pytest tests/test_exec_server_client_api_rs.py -q --tb=short
7 passed

python -m pytest tests/test_exec_server_client_api_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short
25 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_client_api_rs.py
passed
```
