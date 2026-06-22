# server/processor.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/server/processor.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Rust anchors

- `ConnectionProcessor::new`
- `ConnectionProcessor::run_connection`
- internal `run_connection`
- request route dispatch through `build_router`
- transport-disconnect race handling while a route future is in flight
- shutdown/detach behavior after processor exit

## Python evidence

- `tests/test_exec_server_transport_rs.py::test_stdio_listen_transport_serves_initialize`
- `tests/test_exec_server_processor_rs.py::test_transport_disconnect_detaches_session_during_in_flight_read`
- `tests/test_exec_server_server_registry_rs.py::test_build_router_dispatches_requests_to_matching_handler_methods`

## Notes

This status covers newline-framed stdio connection processing through the
registered router, typed process route request/response projection, best-effort
outbound drain on shutdown, handler shutdown, and disconnect cancellation of
in-flight route work. Concrete Axum/tungstenite websocket serving remains owned
by `src/server/transport.rs` and is still an explicit runtime boundary.

## Validation

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_handler_rs.py tests\test_exec_server_processor_rs.py
python -m pytest tests/test_exec_server_process_handler_rs.py tests/test_exec_server_processor_rs.py -q --tb=short
python -m pytest tests/test_exec_server_process_handler_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_server_registry_rs.py -q --tb=short
```

Latest result:

```text
2026-06-21 process-handler/processor focused validation: 4 passed
2026-06-21 adjacent handler/session/registry regression: 20 passed
2026-06-21 py_compile passed for pycodex\exec_server\__init__.py, tests\test_exec_server_process_handler_rs.py, and tests\test_exec_server_processor_rs.py
```
