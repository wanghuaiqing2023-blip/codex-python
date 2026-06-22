# codex-hooks Test Alignment

Rust crate: `codex-hooks`

Rust path: `codex/codex-rs/hooks`

Python package: `pycodex/hooks`

## Covered Rust Tests

| Rust module | Rust test/contract | Python test |
|---|---|---|
| `src/config_rules.rs` | `tests::hook_states_from_stack_respects_layer_precedence` | `tests/test_hooks_config_rules_rs.py::test_hook_states_from_stack_respects_layer_precedence` |
| `src/config_rules.rs` | `tests::hook_states_from_stack_merges_fields_across_layers` | `tests/test_hooks_config_rules_rs.py::test_hook_states_from_stack_merges_fields_across_layers` |
| `src/config_rules.rs` | `tests::hook_states_from_stack_ignores_malformed_hook_events` | `tests/test_hooks_config_rules_rs.py::test_hook_states_from_stack_ignores_malformed_hook_events` |
| `src/config_rules.rs` | `tests::hook_states_from_stack_ignores_malformed_state_entries` | `tests/test_hooks_config_rules_rs.py::test_hook_states_from_stack_ignores_malformed_state_entries` |
| `src/declarations.rs` | `tests::lists_declared_plugin_handlers_with_persisted_hook_keys` | `tests/test_hooks_declarations_rs.py::HooksDeclarationsRsTests::test_lists_declared_plugin_handlers_with_persisted_hook_keys` |
| `src/events/common.rs` | matcher helper tests in `#[cfg(test)] mod tests` | `tests/test_hooks_events_common_rs.py` |
| `src/events/common.rs` | context, serialization failure, and tool-use helper source contracts | `tests/test_hooks_events_common_rs.py` |
| `src/events/permission_request.rs` | `permission_request_deny_overrides_earlier_allow` | `tests/test_hooks_events_permission_request_rs.py::test_permission_request_deny_overrides_earlier_allow` |
| `src/events/permission_request.rs` | `permission_request_returns_allow_when_no_handler_denies` | `tests/test_hooks_events_permission_request_rs.py::test_permission_request_returns_allow_when_no_handler_denies` |
| `src/events/permission_request.rs` | `permission_request_returns_none_when_no_handler_decides` | `tests/test_hooks_events_permission_request_rs.py::test_permission_request_returns_none_when_no_handler_decides` |
| `src/events/permission_request.rs` | command input serialization, allow/deny parsing, reserved field failures, unsupported universal output, exit-code 2, process failure, and run-id suffix source contracts | `tests/test_hooks_events_permission_request_rs.py` |
| `src/events/compact.rs` | `pre_compact_input_includes_lifecycle_metadata` | `tests/test_hooks_events_compact_rs.py::test_pre_compact_input_includes_lifecycle_metadata` |
| `src/events/compact.rs` | `post_compact_input_includes_lifecycle_metadata` | `tests/test_hooks_events_compact_rs.py::test_post_compact_input_includes_lifecycle_metadata` |
| `src/events/compact.rs` | `block_decision_is_not_supported_for_pre_compact` | `tests/test_hooks_events_compact_rs.py::test_block_decision_is_not_supported_for_pre_compact` |
| `src/events/compact.rs` | `continue_false_stops_before_compaction` | `tests/test_hooks_events_compact_rs.py::test_continue_false_stops_before_compaction` |
| `src/events/compact.rs` | `post_compact_continue_false_stops_after_compaction` | `tests/test_hooks_events_compact_rs.py::test_post_compact_continue_false_stops_after_compaction` |
| `src/events/compact.rs` | `pre_compact_ignores_plain_stdout` and `post_compact_ignores_plain_stdout` | `tests/test_hooks_events_compact_rs.py::test_plain_stdout_is_ignored_for_pre_and_post_compact` |
| `src/events/compact.rs` | subagent command fields, default stop reason, warning/suppress output, invalid JSON-like stdout, process error, nonzero, and missing-status source contracts | `tests/test_hooks_events_compact_rs.py` |
| `src/events/pre_tool_use.rs` | `command_input_uses_request_tool_name` | `tests/test_hooks_events_pre_tool_use_rs.py::test_command_input_uses_request_tool_name_and_subagent_fields` |
| `src/events/pre_tool_use.rs` | `permission_decision_deny_blocks_processing` | `tests/test_hooks_events_pre_tool_use_rs.py::test_permission_decision_deny_blocks_processing` |
| `src/events/pre_tool_use.rs` | `permission_decision_allow_can_update_input` | `tests/test_hooks_events_pre_tool_use_rs.py::test_permission_decision_allow_can_update_input` |
| `src/events/pre_tool_use.rs` | `last_completed_updated_input_wins` | `tests/test_hooks_events_pre_tool_use_rs.py::test_last_completed_updated_input_wins` |
| `src/events/pre_tool_use.rs` | `permission_decision_allow_without_updated_input_fails_open` | `tests/test_hooks_events_pre_tool_use_rs.py::test_permission_decision_allow_without_updated_input_fails_open` |
| `src/events/pre_tool_use.rs` | `deprecated_block_decision_blocks_processing` | `tests/test_hooks_events_pre_tool_use_rs.py::test_deprecated_block_decision_blocks_processing` |
| `src/events/pre_tool_use.rs` | `deprecated_block_decision_with_additional_context_blocks_processing` | `tests/test_hooks_events_pre_tool_use_rs.py::test_deprecated_block_decision_with_additional_context_blocks_processing` |
| `src/events/pre_tool_use.rs` | `unsupported_permission_decision_fails_open` | `tests/test_hooks_events_pre_tool_use_rs.py::test_unsupported_permission_decision_fails_open` |
| `src/events/pre_tool_use.rs` | `deprecated_approve_decision_fails_open` | `tests/test_hooks_events_pre_tool_use_rs.py::test_deprecated_approve_decision_fails_open` |
| `src/events/pre_tool_use.rs` | `additional_context_is_recorded` | `tests/test_hooks_events_pre_tool_use_rs.py::test_additional_context_is_recorded` |
| `src/events/pre_tool_use.rs` | `plain_stdout_is_ignored` | `tests/test_hooks_events_pre_tool_use_rs.py::test_plain_stdout_is_ignored` |
| `src/events/pre_tool_use.rs` | `invalid_json_like_stdout_fails_instead_of_becoming_noop` | `tests/test_hooks_events_pre_tool_use_rs.py::test_invalid_json_like_stdout_fails_instead_of_becoming_noop` |
| `src/events/pre_tool_use.rs` | `exit_code_two_blocks_processing` | `tests/test_hooks_events_pre_tool_use_rs.py::test_exit_code_two_blocks_processing` |
| `src/events/pre_tool_use.rs` | `preview_and_completed_run_ids_include_tool_use_id` | `tests/test_hooks_events_pre_tool_use_rs.py::test_preview_and_completed_run_ids_include_tool_use_id` |
| `src/events/pre_tool_use.rs` | `serialization_failure_run_ids_include_tool_use_id` | `tests/test_hooks_events_pre_tool_use_rs.py::test_serialization_failure_run_ids_include_tool_use_id` |
| `src/events/pre_tool_use.rs` | universal-output, hook-specific invalid reason, process error, and exit-code 2 source contracts | `tests/test_hooks_events_pre_tool_use_rs.py::test_pre_tool_use_source_contract_failure_edges` |
| `src/events/post_tool_use.rs` | `command_input_uses_request_tool_name` | `tests/test_hooks_events_post_tool_use_rs.py::test_command_input_uses_request_tool_name_and_subagent_fields` |
| `src/events/post_tool_use.rs` | `block_decision_stops_normal_processing` | `tests/test_hooks_events_post_tool_use_rs.py::test_block_decision_stops_normal_processing` |
| `src/events/post_tool_use.rs` | `additional_context_is_recorded` | `tests/test_hooks_events_post_tool_use_rs.py::test_additional_context_is_recorded` |
| `src/events/post_tool_use.rs` | `unsupported_updated_mcp_tool_output_fails_open` | `tests/test_hooks_events_post_tool_use_rs.py::test_unsupported_updated_mcp_tool_output_fails_open` |
| `src/events/post_tool_use.rs` | `exit_two_surfaces_feedback_to_model_without_blocking` | `tests/test_hooks_events_post_tool_use_rs.py::test_exit_two_surfaces_feedback_to_model_without_blocking` |
| `src/events/post_tool_use.rs` | `continue_false_stops_with_reason` | `tests/test_hooks_events_post_tool_use_rs.py::test_continue_false_stops_with_reason` |
| `src/events/post_tool_use.rs` | `plain_stdout_is_ignored_for_post_tool_use` | `tests/test_hooks_events_post_tool_use_rs.py::test_plain_stdout_is_ignored_for_post_tool_use` |
| `src/events/post_tool_use.rs` | `preview_and_completed_run_ids_include_tool_use_id` | `tests/test_hooks_events_post_tool_use_rs.py::test_preview_and_completed_run_ids_include_tool_use_id` |
| `src/events/post_tool_use.rs` | `serialization_failure_run_ids_include_tool_use_id` | `tests/test_hooks_events_post_tool_use_rs.py::test_serialization_failure_run_ids_include_tool_use_id` |
| `src/events/post_tool_use.rs` | invalid block reason, invalid JSON, missing stderr feedback, process error, no-status, and feedback aggregation source contracts | `tests/test_hooks_events_post_tool_use_rs.py` |
| `src/events/session_start.rs` | `plain_stdout_becomes_model_context` | `tests/test_hooks_events_session_start_rs.py::test_plain_stdout_becomes_model_context` |
| `src/events/session_start.rs` | `continue_false_preserves_context_for_later_turns` | `tests/test_hooks_events_session_start_rs.py::test_continue_false_preserves_context_for_later_turns` |
| `src/events/session_start.rs` | `invalid_json_like_stdout_fails_instead_of_becoming_model_context` | `tests/test_hooks_events_session_start_rs.py::test_invalid_json_like_stdout_fails_instead_of_becoming_model_context` |
| `src/events/session_start.rs` | `subagent_start_plain_stdout_becomes_model_context` | `tests/test_hooks_events_session_start_rs.py::test_subagent_start_plain_stdout_becomes_model_context` |
| `src/events/session_start.rs` | `subagent_start_continue_false_is_ignored` | `tests/test_hooks_events_session_start_rs.py::test_subagent_start_continue_false_is_ignored` |
| `src/events/stop.rs` | `block_decision_with_reason_sets_continuation_prompt` | `tests/test_hooks_events_stop_rs.py::test_block_decision_with_reason_sets_continuation_prompt` |
| `src/events/stop.rs` | `block_decision_without_reason_is_invalid` | `tests/test_hooks_events_stop_rs.py::test_block_decision_without_reason_is_invalid` |
| `src/events/stop.rs` | `continue_false_overrides_block_decision` | `tests/test_hooks_events_stop_rs.py::test_continue_false_overrides_block_decision` |
| `src/events/stop.rs` | `exit_code_two_uses_stderr_feedback_only` | `tests/test_hooks_events_stop_rs.py::test_exit_code_two_uses_stderr_feedback_only` |
| `src/events/stop.rs` | `exit_code_two_without_stderr_does_not_block` | `tests/test_hooks_events_stop_rs.py::test_exit_code_two_without_stderr_does_not_block` |
| `src/events/stop.rs` | `block_decision_with_blank_reason_fails_instead_of_blocking` | `tests/test_hooks_events_stop_rs.py::test_block_decision_with_blank_reason_fails_instead_of_blocking` |
| `src/events/stop.rs` | `invalid_stdout_fails_instead_of_silently_nooping` | `tests/test_hooks_events_stop_rs.py::test_invalid_stdout_fails_instead_of_silently_nooping` |
| `src/events/stop.rs` | `aggregate_results_concatenates_blocking_reasons_in_declaration_order` | `tests/test_hooks_events_stop_rs.py::test_aggregate_results_concatenates_blocking_reasons_in_declaration_order` |
| `src/events/stop.rs` | target matcher, SubagentStop error text, process failure, and stop-over-block aggregation source contracts | `tests/test_hooks_events_stop_rs.py` |
| `src/events/user_prompt_submit.rs` | `continue_false_preserves_context_for_later_turns` | `tests/test_hooks_events_user_prompt_submit_rs.py::test_continue_false_preserves_context_for_later_turns` |
| `src/events/user_prompt_submit.rs` | `claude_block_decision_blocks_processing` | `tests/test_hooks_events_user_prompt_submit_rs.py::test_claude_block_decision_blocks_processing` |
| `src/events/user_prompt_submit.rs` | `claude_block_decision_requires_reason` | `tests/test_hooks_events_user_prompt_submit_rs.py::test_claude_block_decision_requires_reason` |
| `src/events/user_prompt_submit.rs` | `exit_code_two_blocks_processing` | `tests/test_hooks_events_user_prompt_submit_rs.py::test_exit_code_two_blocks_processing` |
| `src/events/user_prompt_submit.rs` | plain stdout, invalid JSON-looking stdout, warning, process error, other non-zero, and missing status source contracts | `tests/test_hooks_events_user_prompt_submit_rs.py` |
| `src/engine/output_parser.rs` | `permission_request_rejects_reserved_updated_input_field` | `tests/test_hooks_engine_output_parser_rs.py::test_permission_request_rejects_reserved_fields_from_rust_tests` |
| `src/engine/output_parser.rs` | `permission_request_rejects_reserved_updated_permissions_field` | `tests/test_hooks_engine_output_parser_rs.py::test_permission_request_rejects_reserved_fields_from_rust_tests` |
| `src/engine/output_parser.rs` | `permission_request_rejects_reserved_interrupt_field` | `tests/test_hooks_engine_output_parser_rs.py::test_permission_request_rejects_reserved_fields_from_rust_tests` |
| `src/engine/output_parser.rs` | `parse_json`, `looks_like_json`, universal output projection, PreToolUse hook-specific/legacy decisions, PermissionRequest defaults, PostToolUse invalid block reasons, SessionStart/Stop/UserPromptSubmit output source contracts | `tests/test_hooks_engine_output_parser_rs.py` |
| `src/engine/schema_loader.rs` | `loads_generated_hook_schemas` | `tests/test_hooks_engine_schema_loader_rs.py::test_loads_generated_hook_schemas` |
| `src/engine/schema_loader.rs` | `GeneratedHookSchemas` field inventory, `generated_hook_schemas` OnceLock caching, and named invalid schema errors | `tests/test_hooks_engine_schema_loader_rs.py` |
| `src/engine/dispatcher.rs` | `select_handlers_keeps_duplicate_stop_handlers` | `tests/test_hooks_engine_dispatcher_rs.py::test_select_handlers_keeps_duplicate_stop_handlers` |
| `src/engine/dispatcher.rs` | `select_handlers_keeps_overlapping_session_start_matchers` | `tests/test_hooks_engine_dispatcher_rs.py::test_select_handlers_keeps_overlapping_session_start_matchers` |
| `src/engine/dispatcher.rs` | `compact_hooks_match_trigger` | `tests/test_hooks_engine_dispatcher_rs.py::test_compact_hooks_match_trigger` |
| `src/engine/dispatcher.rs` | `pre_tool_use_matches_tool_name`, `post_tool_use_matches_tool_name`, `pre_tool_use_star_matcher_matches_all_tools` | `tests/test_hooks_engine_dispatcher_rs.py::test_tool_use_handlers_match_tool_name_and_star_matcher` |
| `src/engine/dispatcher.rs` | `pre_tool_use_regex_alternation_matches_each_tool_name`, `pre_tool_use_aliases_match_once_per_handler` | `tests/test_hooks_engine_dispatcher_rs.py::test_pre_tool_use_regex_alternation_and_aliases_match_once_per_handler` |
| `src/engine/dispatcher.rs` | `user_prompt_submit_ignores_matcher`, `select_handlers_preserves_declaration_order` | `tests/test_hooks_engine_dispatcher_rs.py::test_user_prompt_submit_ignores_matcher_and_selection_preserves_order` |
| `src/engine/dispatcher.rs` | `scope_for_event`, `running_summary`, `completed_summary`, and `execute_handlers` source contracts | `tests/test_hooks_engine_dispatcher_rs.py` |
| `src/engine/command_runner.rs` | `build_command`, `default_shell_command`, and `run_command` source contracts for shell argv, env/cwd/stdin/stdout/stderr, spawn errors, timeout errors, exit code, and timestamp/duration projection | `tests/test_hooks_engine_command_runner_rs.py` |
| `src/engine/discovery.rs` | matcher normalization/validation, bypass trust, disabled state, star matcher, commandWindows override, TOML hooks parsing with malformed state entries, trust/enabled/list-entry source contracts | `tests/test_hooks_engine_discovery_rs.py` |
| `src/engine/mod.rs` | `ClaudeHooksEngine::{new,warnings,preview_*,run_*}` facade/orchestration source contracts, `plugin_hook_load_warnings_are_startup_warnings`, output spilling wrappers, and run-id decoration | `tests/test_hooks_engine_mod_rs.py` |
| `src/legacy_notify.rs` | `tests::test_user_notification` | `tests/test_hooks_legacy_notify_rs.py::test_user_notification_serializes_historical_wire_shape` |
| `src/legacy_notify.rs` | `tests::legacy_notify_json_matches_historical_wire_shape` | `tests/test_hooks_legacy_notify_rs.py::test_legacy_notify_json_matches_payload_after_agent_event` |
| `src/legacy_notify.rs` | `notify_hook` empty command and spawn-error source contracts | `tests/test_hooks_legacy_notify_rs.py::test_notify_hook_empty_argv_succeeds_without_spawn`, `tests/test_hooks_legacy_notify_rs.py::test_notify_hook_spawn_error_failed_continue` |
| `src/output_spill.rs` | `small_hook_output_remains_inline` | `tests/test_hooks_output_spill_rs.py::test_small_hook_output_remains_inline` |
| `src/output_spill.rs` | `large_hook_output_spills_to_file` | `tests/test_hooks_output_spill_rs.py::test_large_hook_output_spills_to_file` |
| `src/output_spill.rs` | `maybe_spill_texts` and `maybe_spill_prompt_fragments` source contracts | `tests/test_hooks_output_spill_rs.py::test_maybe_spill_texts_preserves_order_and_spills_individually`, `tests/test_hooks_output_spill_rs.py::test_maybe_spill_prompt_fragments_preserves_hook_run_id` |
| `src/registry.rs` | `HooksConfig` default, `Hooks::new`, `Hooks::dispatch`, `list_hooks`, and `command_from_argv` source contracts | `tests/test_hooks_registry_rs.py` |
| `src/registry.rs` | `engine/mod_tests.rs` managed/plugin `list_hooks(...)` registry-visible contracts | `tests/test_hooks_registry_rs.py::test_list_hooks_feature_gate_and_discovery_forwarding` |
| `src/schema.rs` | `generated_hook_schemas_match_fixtures` | `tests/test_hooks_schema_rs.py::test_generated_hook_schemas_match_python_fixtures` |
| `src/schema.rs` | `turn_scoped_hook_inputs_include_codex_turn_id_extension` | `tests/test_hooks_schema_rs.py::test_turn_scoped_hook_inputs_include_codex_turn_id_extension` |
| `src/schema.rs` | `subagent_context_fields_are_optional_for_hooks_that_run_inside_subagents` | `tests/test_hooks_schema_rs.py::test_subagent_context_fields_are_optional_for_hooks_that_run_inside_subagents` |
| `src/schema.rs` | `subagent_context_fields_serialize_flat_and_omit_when_absent` | `tests/test_hooks_schema_rs.py::test_subagent_context_fields_serialize_flat_and_omit_when_absent` |
| `src/schema.rs` | canonical schema JSON, fixture-name inventory, generated-directory replacement, nullable string helpers, hook-event const schemas, permission-mode/source/compaction-trigger enum schemas | `tests/test_hooks_schema_rs.py` |
| `src/types.rs` | `tests::hook_payload_serializes_stable_wire_shape` | `tests/test_hooks_types_rs.py::HooksTypesRsTests::test_hook_payload_serializes_stable_wire_shape` |
| `src/types.rs` | `HookResult::should_abort_operation`, `Hook::default`, `Hook::execute` source contract | `tests/test_hooks_types_rs.py::HooksTypesRsTests::test_hook_result_abort_and_default_hook_execute` |

## Focused Validation

- `python -m pytest tests/test_hooks_types_rs.py -q --tb=short`
  passed on 2026-06-21 with `2 passed`.
- `python -m pytest tests/test_hooks_declarations_rs.py -q --tb=short`
  passed on 2026-06-21 with `1 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m pytest tests/test_hooks_legacy_notify_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py -q --tb=short`
  passed on 2026-06-21 with `13 passed`.
- `python -m pytest tests/test_hooks_output_spill_rs.py -q --tb=short`
  passed on 2026-06-21 with `4 passed`.
- `python -m pytest tests/test_hooks_registry_rs.py -q --tb=short`
  passed on 2026-06-21 with `7 passed`.
- `python -m pytest tests/test_hooks_events_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `12 passed`.
- `python -m pytest tests/test_hooks_events_session_start_rs.py -q --tb=short`
  passed on 2026-06-21 with `6 passed`.
- `python -m pytest tests/test_hooks_events_user_prompt_submit_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m pytest tests/test_hooks_events_stop_rs.py -q --tb=short`
  passed on 2026-06-21 with `12 passed`.
- `python -m pytest tests/test_hooks_events_pre_tool_use_rs.py -q --tb=short`
  passed on 2026-06-21 with `16 passed`.
- `python -m pytest tests/test_hooks_events_post_tool_use_rs.py -q --tb=short`
  passed on 2026-06-21 with `11 passed`.
- `python -m pytest tests/test_hooks_events_permission_request_rs.py -q --tb=short`
  passed on 2026-06-21 with `11 passed`.
- `python -m pytest tests/test_hooks_events_compact_rs.py -q --tb=short`
  passed on 2026-06-21 with `11 passed`.
- `python -m pytest tests/test_hooks_schema_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m pytest tests/test_hooks_engine_output_parser_rs.py -q --tb=short`
  passed on 2026-06-21 with `6 passed`.
- `python -m pytest tests/test_hooks_engine_schema_loader_rs.py -q --tb=short`
  passed on 2026-06-21 with `3 passed`.
- `python -m pytest tests/test_hooks_engine_dispatcher_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m pytest tests/test_hooks_engine_command_runner_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m pytest tests/test_hooks_engine_discovery_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m pytest tests/test_hooks_engine_mod_rs.py -q --tb=short`
  passed on 2026-06-21 with `7 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py -q --tb=short`
  passed on 2026-06-21 with `138 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py -q --tb=short`
  passed on 2026-06-21 with `146 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py tests/test_hooks_engine_mod_rs.py -q --tb=short`
  passed on 2026-06-21 with `153 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `161 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `169 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py tests/test_hooks_engine_mod_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `176 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py -q --tb=short`
  passed on 2026-06-21 with `133 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `156 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py -q --tb=short`
  passed on 2026-06-21 with `125 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `148 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py -q --tb=short`
  passed on 2026-06-21 with `122 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `145 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py -q --tb=short`
  passed on 2026-06-21 with `50 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `73 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py -q --tb=short`
  passed on 2026-06-21 with `62 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `85 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py -q --tb=short`
  passed on 2026-06-21 with `78 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `101 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py -q --tb=short`
  passed on 2026-06-21 with `89 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `112 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py -q --tb=short`
  passed on 2026-06-21 with `100 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `123 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py -q --tb=short`
  passed on 2026-06-21 with `111 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `134 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py -q --tb=short`
  passed on 2026-06-21 with `116 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `139 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `31 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k hooks -q --tb=short`
  passed on 2026-06-21 with `1 passed, 17 deselected`.
- `python -m pytest tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py tests/test_external_crate_interfaces.py -k 'hooks or external_crate_facades' -q --tb=short`
  passed on 2026-06-21 with `27 passed, 17 deselected`.
- `python -m pytest tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed on 2026-06-21 with `23 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_types_rs.py`
  passed on 2026-06-21.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_engine_mod_rs.py`
  passed on 2026-06-21.

## Remaining Gap

None. `codex-hooks` has Rust-derived/source-contract coverage for all tracked
crate modules and focused hooks/core validation passed with the `src/engine/mod.rs`
facade/orchestration coverage included.
