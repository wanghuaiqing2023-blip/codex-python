# Tool Emitter Model Output Format

- Upstream graph slice: `codex-rs/core/src/tools/mod.rs` and `codex-rs/core/src/tools/events.rs`.
- Confirmed Rust behavior: `ToolEmitter::finish` returns `format_exec_output_for_model` to the model, including `Exit code`, one-decimal `Wall time`, optional `Total output lines`, and `Output`, while emitted `ExecCommandEndEvent.formatted_output` continues to use `format_exec_output_str`.
- Python change: added `format_exec_output_for_model` and switched `ToolEmitter.finish` to use it for success, nonzero exit, timeout/denied output-bearing failures, and other output failures.
- Kept event formatting on `format_exec_output_str`, matching the Rust split between model-facing tool response and event history formatting.
- Validation:
  - `python -m unittest tests.test_core_user_shell_command tests.test_core_tool_events tests.test_core_tool_context`
  - `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport tests.test_exec_local_runtime tests.test_exec_run tests.test_exec_event_processor tests.test_core_tool_router tests.test_core_unified_exec_handler tests.test_core_view_image_handler tests.test_core_turn_request tests.test_core_session_runtime tests.test_core_tool_events tests.test_core_user_shell_command`

Known gaps:

- This preserves the existing stdlib approximation for token/byte truncation. The broader output-truncation utility still remains an approximation of Rust's helper crate.
