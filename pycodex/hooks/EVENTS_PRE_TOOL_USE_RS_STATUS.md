# codex-hooks src/events/pre_tool_use.rs Status

Rust crate: `codex-hooks`

Rust module: `src/events/pre_tool_use.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `PreToolUseCommandInput` serialization keeps the request `tool_name`,
  `tool_input`, `tool_use_id`, and optional subagent fields in Rust's
  snake_case command-input shape.
- Completed hook output parsing mirrors Rust's supported hook-specific
  `permissionDecision` contract: deny blocks with feedback, allow rewrites
  input only when `updatedInput` is present, ask/unsupported allow fail open,
  and invalid deny reasons fail.
- Legacy top-level `decision:block` blocks, `decision:approve` fails open, and
  additional context is recorded before feedback when valid.
- Plain stdout is ignored, JSON-looking invalid stdout fails, exit code 2
  blocks only with non-empty stderr, and command errors/non-zero/no-status
  branches produce Rust-compatible failures.
- Competing updated inputs are resolved by latest completion order, and
  tool-use hook run ids append the `tool_use_id`.

## Rust Evidence

- `codex/codex-rs/hooks/src/events/pre_tool_use.rs`
- Rust tests:
  - `command_input_uses_request_tool_name`
  - `permission_decision_deny_blocks_processing`
  - `permission_decision_allow_can_update_input`
  - `last_completed_updated_input_wins`
  - `permission_decision_allow_without_updated_input_fails_open`
  - `deprecated_block_decision_blocks_processing`
  - `deprecated_block_decision_with_additional_context_blocks_processing`
  - `unsupported_permission_decision_fails_open`
  - `deprecated_approve_decision_fails_open`
  - `additional_context_is_recorded`
  - `plain_stdout_is_ignored`
  - `invalid_json_like_stdout_fails_instead_of_becoming_noop`
  - `exit_code_two_blocks_processing`
  - `preview_and_completed_run_ids_include_tool_use_id`
  - `serialization_failure_run_ids_include_tool_use_id`

## Python Evidence

- `tests/test_hooks_events_pre_tool_use_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_events_pre_tool_use_rs.py -q --tb=short
```

Passed on 2026-06-21 with `16 passed`.

Related hooks validation also passed with:

```text
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py -q --tb=short
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short
```

Results: `78 passed` and `101 passed`.
