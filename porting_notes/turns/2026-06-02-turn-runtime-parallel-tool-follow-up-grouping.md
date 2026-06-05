# Turn runtime parallel tool follow-up grouping

## Upstream graph and source slice

- Graph node: `class:codex-rs/core/src/tools/parallel.rs#ToolCallRuntime`
- Graph node: `function:codex-rs/core/src/tools/parallel.rs#handle_tool_call`
- Graph node: `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request`
- Graph node: `function:codex-rs/core/tests/suite/tool_parallelism.rs#tool_results_grouped`
- Source: `codex/codex-rs/core/src/tools/parallel.rs`
- Source: `codex/codex-rs/core/tests/suite/tool_parallelism.rs`

Rust starts tool executions from a completed model response as concurrent
runtime futures where each tool supports parallel execution. The follow-up
request still preserves model-visible grouping: all model-emitted
`function_call` items remain before the generated `function_call_output`
items, and outputs are ordered by the original calls.

## Python changes

- Updated `_handle_response_tool_calls` in `pycodex.core.turn_runtime` to
  schedule tool calls concurrently with `asyncio.create_task`.
- Preserved Rust-visible ordering by storing each tool result at the original
  call output index before recording the batch.
- Added cancellation cleanup for already scheduled tool tasks if a fatal tool
  error aborts the turn.
- Added a turn-runtime test proving parallel tool calls enter their handlers
  concurrently and that follow-up input groups all function calls before
  outputs while pairing call IDs in order.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_parallel_tool_calls_concurrently_and_groups_outputs`
- `python -m unittest tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_tool_parallel.ToolParallelTests.test_parallel_dispatches_share_execution_gate tests.test_core_tool_parallel.ToolParallelTests.test_non_parallel_dispatch_waits_for_active_parallel_dispatch tests.test_core_tool_parallel.ToolParallelTests.test_non_parallel_dispatches_are_mutually_exclusive`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_tool_router tests.test_core_tool_registry tests.test_core_turn_prompt tests.test_core_turn_request tests.test_core_session_runtime`

Attempted:

- `python -m unittest tests.test_core_turn_runtime tests.test_core_tool_parallel`

The combined run surfaced multiple failures inside the much larger
`tests.test_core_tool_parallel` suite and did not finish promptly, so it was
terminated. The focused tool-parallel gate tests listed above passed.
