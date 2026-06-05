# 2026-06-01 Tool Error And Lifecycle Boundaries

## Graph-selected slice

- Upstream graph nodes used as navigation:
  - `codex-rs/core/src/function_tool.rs`
  - `codex-rs/tools/src/function_call_error.rs`
  - `codex-rs/core/src/tools/router.rs`
  - `codex-rs/core/src/tools/registry.rs`
  - `codex-rs/core/src/tools/parallel.rs`
- The slice advances the common `stream handling -> tool dispatch -> lifecycle notification -> tool result/error` path.

## Rust source checked

- `codex/codex-rs/tools/src/function_call_error.rs`
- `codex/codex-rs/core/src/tools/registry.rs`

## Python changes

- Made `FunctionCallError` a normal mutable Python exception instead of a frozen dataclass. This preserves Rust-shaped `RespondToModel`/`Fatal` behavior while allowing Python traceback machinery to assign `__traceback__`.
- Updated the multi-agent v1 full-history fork override test to assert the current shared validation message.
- Filtered tool lifecycle notification kwargs so extension lifecycle payloads receive only `session_store`, `thread_store`, `turn_store`, and `turn_id`; router-internal stores such as telemetry recorders and dispatch traces no longer leak into lifecycle payload constructors.
- Let invalid post-tool-use payload trait shapes raise `TypeError` directly, matching the pre-tool-use payload validation boundary.
- Updated the missing-tool telemetry assertion to Rust's `unsupported call: {tool_name}` wording from `tools/registry.rs`.

## Validation

- `python -m unittest tests.test_core_tool_router`
  - Passed: 52 tests.
- `python -m unittest tests.test_core_function_tool tests.test_core_multi_agents_v1_handler.CoreMultiAgentsV1HandlerTests.test_v1_spawn_args_reject_invalid_input_and_full_fork_overrides`
  - Passed the unittest-discovered multi-agent v1 test; `tests.test_core_function_tool` contains pytest-style functions and is not collected by unittest.
- Manual traceback check:
  - Raised `FunctionCallError.respond_to_model("visible")` and assigned its `__traceback__` without `FrozenInstanceError`.
- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_exec_local_runtime tests.test_core_turn_runtime`
  - Passed: 198 tests.

## Follow-up debt

- Full unittest discovery still reports many unrelated failures and some hangs in broader tool/stream/multi-agent areas. Relevant core-path candidates visible after this slice include missing `ResponseItem.reasoning`/`TurnItem.reasoning` compatibility constructors and several multi-agent v1/v2 assertion mismatches.
- `PORTING_STATUS.md` is currently deleted in the worktree; this turn intentionally did not recreate it.
