# Local HTTP exec same-turn tool output grouping

## Upstream graph and source slice

- Graph node: `function:codex-rs/exec/src/lib.rs#run_exec_session`
- Graph node: `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request`
- Graph node: `function:codex-rs/core/tests/suite/tool_parallelism.rs#tool_results_grouped`
- Source: `codex/codex-rs/core/tests/suite/tool_parallelism.rs`

Rust's `tool_results_grouped` coverage verifies a core model-facing contract:
when one model response emits multiple tool calls, the follow-up request keeps
all original `function_call` inputs before generated `function_call_output`
items, and each output remains paired with the matching `call_id` in call
order.

## Python changes

- Added an end-to-end local HTTP exec test for
  `run_exec_user_turn_with_shell_tools_http_sampling`.
- The test simulates one model response with three shell tool calls and a
  second final-answer response.
- It asserts the follow-up request groups the three original calls before the
  three tool outputs, preserves `call_id` pairing, and returns successful tool
  output content before the final assistant answer.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_groups_same_turn_tool_outputs`
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_session_runtime`

