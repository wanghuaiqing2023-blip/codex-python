# codex-exec-server src/protocol.rs Status

Rust source: `codex/codex-rs/exec-server/src/protocol.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Covered Contract

- Protocol method constants mirror the Rust JSON-RPC names for initialize,
  process, filesystem, and HTTP request/body-delta routes.
- `ByteChunk` mirrors the Rust transparent base64 byte wrapper.
- Invalid `ByteChunk` base64 values are rejected instead of silently accepted.
- Initialize, process, filesystem, HTTP, and notification dataclasses preserve
  Rust camelCase wire names where Python needs typed protocol helpers.
- Process request decoders and response encoders preserve transparent
  `ProcessId`, base64 chunks, optional integer fields, `WriteStatus`
  camelCase variants, and Rust defaults for omitted optional fields.
- HTTP request decoding preserves ordered headers, optional `bodyBase64`,
  `timeoutMs` omitted/null semantics, caller `requestId`, and
  `streamResponse` defaulting.
- HTTP response and streamed body-delta notification encoders preserve
  `bodyBase64`/`deltaBase64` names and terminal `done`/`error` shape.
- Exec output/exited/closed notification encoders preserve Rust camelCase
  field names and base64 output chunks.
- `server/registry.rs` now uses the typed `HttpRequestParams` decoder for
  `http/request`, matching the Rust `request_with_id` registration.

## Evidence

- Rust unit test:
  `http_request_timeout_treats_omitted_and_null_as_no_timeout`
- Python parity tests:
  `tests/test_exec_server_protocol_rs.py`
- Registry integration check:
  `tests/test_exec_server_server_registry_rs.py::test_build_router_dispatches_http_request_with_request_id`

Focused validation:

```text
python -m pytest tests/test_exec_server_protocol_rs.py tests/test_exec_server_server_registry_rs.py -q --tb=short
```

Result on 2026-06-21: `10 passed`.

Adjacent exec-server focused regression:

```text
python -m pytest tests/test_exec_server_client_transport_rs.py tests/test_exec_server_connection_rs.py tests/test_exec_server_local_process_rs.py tests/test_exec_server_process_handler_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short
```

Result on 2026-06-21: `306 passed, 1 skipped`.

Completion validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_protocol_rs.py tests/test_exec_server_server_registry_rs.py -q --tb=short
10 passed

python -m pytest tests/test_exec_server_protocol_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short
29 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_protocol_rs.py tests\test_exec_server_server_registry_rs.py
passed
```

## Remaining Boundaries

`src/protocol.rs` is complete as a protocol data-shape module. Crate-level
gaps remain in runtime modules: PTY/terminal process execution, exact
OS-specific process-tree termination, concrete Axum/tungstenite websocket
serving, relay/harness transport, concrete remote environment transport, and
remaining websocket/server orchestration.
