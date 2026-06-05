# Unified Exec Original Token Count

- Upstream graph slice: `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs` and `codex-rs/core/src/unified_exec/process_manager.rs`.
- Confirmed Rust behavior: process-manager unified exec responses compute `original_token_count` from the collected raw output before model-facing truncation. Sandbox-denied terminal responses do the same; apply-patch interception keeps the count absent.
- Python change: `ExecCommandHandler.handle` now computes `original_token_count` for the local subprocess fallback from decoded raw output and passes it into `ExecCommandToolOutput`.
- Added coverage that local `exec_command` responses include `Original token count:` when output is truncated by `max_output_tokens`.
- Validation:
  - `python -m unittest tests.test_core_unified_exec_handler`
  - `python -m unittest tests.test_core_unified_exec_handler tests.test_core_tool_context tests.test_exec_local_runtime tests.test_exec_run`
  - `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport tests.test_exec_local_runtime tests.test_exec_run tests.test_exec_event_processor tests.test_core_tool_router tests.test_core_unified_exec_handler tests.test_core_view_image_handler tests.test_core_turn_request tests.test_core_session_runtime tests.test_core_tool_events tests.test_core_user_shell_command`

Known gaps:

- The Python count uses the existing stdlib approximate tokenizer, not Rust's exact helper crate implementation.
