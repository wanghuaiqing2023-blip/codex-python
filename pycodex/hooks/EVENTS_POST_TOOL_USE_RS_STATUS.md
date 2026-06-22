# codex-hooks src/events/post_tool_use.rs Status

Rust crate: `codex-hooks`

Rust module: `src/events/post_tool_use.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `PostToolUseCommandInput` serialization keeps request `tool_name`,
  `tool_input`, `tool_response`, `tool_use_id`, and optional subagent fields
  in Rust's command-input shape.
- Completed hook output parsing records additional context, block feedback,
  `continue:false` stop feedback, unsupported `updatedMCPToolOutput` failures,
  invalid block reasons, invalid JSON-looking stdout, process errors, other
  non-zero exits, and missing status failures.
- Exit code 2 surfaces stderr feedback to the model while leaving the hook run
  completed; missing stderr feedback fails.
- Plain stdout is ignored, and post-tool-use feedback chunks join in
  declaration order with blank lines.
- Tool-use hook run ids append the `tool_use_id`.

## Rust Evidence

- `codex/codex-rs/hooks/src/events/post_tool_use.rs`
- Rust tests:
  - `command_input_uses_request_tool_name`
  - `block_decision_stops_normal_processing`
  - `additional_context_is_recorded`
  - `unsupported_updated_mcp_tool_output_fails_open`
  - `exit_two_surfaces_feedback_to_model_without_blocking`
  - `continue_false_stops_with_reason`
  - `plain_stdout_is_ignored_for_post_tool_use`
  - `preview_and_completed_run_ids_include_tool_use_id`
  - `serialization_failure_run_ids_include_tool_use_id`

## Python Evidence

- `tests/test_hooks_events_post_tool_use_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_events_post_tool_use_rs.py -q --tb=short
```

Passed on 2026-06-21 with `11 passed`.

Related hooks validation also passed with:

```text
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py -q --tb=short
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short
```

Results: `89 passed` and `112 passed`.
