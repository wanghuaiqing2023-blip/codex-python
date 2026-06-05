# Unified exec request contract fields

## Upstream graph/source slice

- Graph-selected core path:
  - `codex-rs/core/src/unified_exec/mod.rs#ExecCommandRequest`
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#handle`
  - `codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs#handle`
- Confirmed Rust behavior:
  - `ExecCommandRequest` includes the manager-allocated `process_id`.
  - `ExecCommandRequest` carries `additional_permissions_preapproved` into the unified exec manager.
  - `exec_command` releases an allocated process id before returning on early error paths.

## Python changes

- Added `process_id` and `additional_permissions_preapproved` to `pycodex.core.unified_exec_handler.ExecCommandRequest`.
- When delegating `exec_command` to a provided unified exec manager, Python now calls `allocate_process_id()` when available and passes that id into the request.
- On manager execution errors, Python calls `release_process_id(process_id)` when available before returning the model-facing error.
- Added focused coverage for request field forwarding and release-on-error behavior.

## Validation

- `python -m py_compile pycodex/core/unified_exec_handler.py tests/test_core_unified_exec_handler.py`
- `python -m unittest tests.test_core_unified_exec_handler.CoreUnifiedExecHandlerTests.test_exec_command_handler_forwards_request_to_unified_exec_manager tests.test_core_unified_exec_handler.CoreUnifiedExecHandlerTests.test_exec_command_handler_releases_allocated_process_id_on_manager_error`
- `python -m unittest tests.test_core_unified_exec_handler`
- `python -m unittest tests.test_core_unified_exec_handler tests.test_core_tool_events`
- `python -m unittest tests.test_core_tool_router tests.test_exec_local_runtime`

Known gaps:

- The actual Python unified exec process manager remains lightweight; this slice aligns the handler-manager request contract needed by the core path.
