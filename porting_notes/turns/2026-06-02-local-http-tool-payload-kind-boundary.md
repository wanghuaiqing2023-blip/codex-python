# Local HTTP tool payload kind boundary

## Source slice

- Checked Rust runtime handlers:
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
  - `codex-rs/core/src/tools/handlers/shell/shell_command.rs`
  - `codex-rs/core/src/tools/handlers/apply_patch.rs`
  - `codex-rs/core/src/tools/registry.rs`
- Rust `exec_command` and `shell_command` only accept function payloads.
- Rust `apply_patch` only accepts custom/freeform payloads.
- The registry treats wrong payload kinds as incompatible instead of executing them.

## Python changes

- Local HTTP shell-tool output handling now rejects custom payloads for function-only tools such as `exec_command`, `shell_command`, `write_stdin`, `request_permissions`, and `view_image`.
- Local HTTP `apply_patch` now rejects function payloads instead of applying a `patch` argument from JSON.
- Timeline reconstruction now treats only function shell calls as `command_execution`, so custom `exec_command` payloads are not rendered as shell executions.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_custom_exec_command_payload_is_not_executed tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_function_apply_patch_payload_is_not_executed tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_maps_function_call_json_event_without_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_nonzero_exit_marks_timeline_failed tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_tool_events tests.test_core_apply_patch tests.test_core_spec_plan`
