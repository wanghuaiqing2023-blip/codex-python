# 2026-06-01 Core Exec Import And Startup Fixes

## Graph-selected slice

- Upstream graph nodes used as the planning map:
  - `codex-rs/exec/src/lib.rs#run_main`
  - `codex-rs/exec/src/lib.rs#run_exec_session`
  - `codex-rs/core/src/session/turn.rs#run_turn`
  - `codex-rs/core/src/client.rs#stream`
  - `codex-rs/core/src/exec.rs#process_exec_tool_call`
- The slice advances the common `exec -> request setup -> turn start -> tool dispatch` path.

## Rust source checked

- `codex/codex-rs/exec/src/lib.rs`
- `codex/codex-rs/exec/src/cli.rs`
- `codex/codex-rs/core/src/session/turn.rs`
- `codex/codex-rs/core/src/session/mod.rs`
- `codex/codex-rs/core/src/context_manager/history.rs`
- `codex/codex-rs/core/src/state/additional_context.rs`
- `codex/codex-rs/core/src/client.rs`

## Python changes

- Broke two import cycles that prevented core exec/turn tests from loading:
  - `memory_usage -> unified_exec_handler -> tool_router -> memory_usage`
  - `network_approval -> network_policy_decision -> exec_policy -> tool_sandboxing -> network_approval`
- Preserved behavior by moving the cyclic imports to the narrow call sites that need them.
- Added `CancellationToken.cancelled()` so Python tool dispatch can wait on cancellation like the Rust select loop.
- Accepted `codex exec review -` as a stdin-backed custom review prompt.
- Accepted `thread/turn/start` as an app-server-compatible alias for the initial user turn response.
- Fixed a Python 3.13 syntax error in a turn-runtime test assertion.
- Let rollout thread summaries derive preview/first-user-message from persisted Responses `response_item` records, so local HTTP exec rollouts can be listed and resumed even when they do not contain app-server `event_msg` records.
- Tightened local HTTP auth precedence so an explicit auth object wins over ambient `os.environ` when no explicit `env` mapping is supplied, while explicit `env` mappings still win in tests and callers.
- Moved AGENTS/user-instruction rendering into initial session context assembly instead of injecting it during prompt construction, matching Rust `Session::build_initial_context` plus `turn.rs::build_prompt`.
- Kept `build_turn_prompt` and prompt-debug custom builders order-preserving; `ContextManager::for_prompt` in Rust normalizes call/output and image support, but does not drop contextual user/developer messages.
- Updated local HTTP resume/additional-context tests to preserve Rust-visible ordering: context updates may sit between restored history and current user input, and clearing `additional_context` resets the store without removing old history items already sent to the model.
- Made trusted-directory gate tests independent of the host machine's ancestor `.git` directories by patching the Python `get_git_repo_root` boundary in no-repo scenarios. Product behavior still matches Rust's ancestor walk.

## Validation

- `python -m pytest tests/test_exec_run.py tests/test_exec_config_plan.py tests/test_exec_local_runtime.py tests/test_core_turn_runtime.py -q`
  - Not run: `pytest` is not installed in the current environment.
- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_exec_local_runtime tests.test_core_turn_runtime`
  - Passed: 198 tests.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_can_preload_resume_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_reads_history_and_appends_result_to_same_rollout tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_resolves_named_session_through_index tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_additional_context_removes_one_value_while_adding_another tests.test_core_turn_runtime.TurnRuntimeTests.test_additional_context_empty_map_clears_store_then_readds_values tests.test_core_turn_runtime.TurnRuntimeTests.test_build_user_input_op_request_clears_additional_context_when_absent tests.test_core_turn_prompt`
  - Passed: 12 tests.
- Focused checks passed:
  - `tests.test_exec_run.ExecRunPreparationTests.test_build_review_request_reads_dash_prompt_from_stdin_and_trims`
  - `tests.test_exec_config_plan.ExecRuntimeRequestSequenceShutdownActionsTest.test_runtime_request_sequence_shutdown_actions_unsubscribes_and_breaks`
  - `tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_and_records_tool_outputs`
  - `tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_can_limit_tool_followups`
  - `tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_runtime_materializes_rollout_unless_ephemeral`
  - `tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_uses_auth_openai_api_key_value`
  - related local HTTP auth precedence checks

## Follow-up debt

- `PORTING_STATUS.md` is currently deleted in the worktree; this turn intentionally did not recreate it.
