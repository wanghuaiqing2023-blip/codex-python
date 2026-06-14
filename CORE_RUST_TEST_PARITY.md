# Core Rust Test Parity

Last updated: 2026-06-09

Purpose: track parity from existing Rust `codex-core` tests to Python tests. This is the priority source for future test work.

Rules:

- Add Python tests from existing Rust tests first.
- Prefer one Rust test behavior to one Python test behavior.
- Mark a row `mapped` only when there is a Python test file intentionally covering that Rust test file.
- Mark function-level parity in follow-up notes when individual Rust test functions are mirrored.
- Do not use broad import/coverage guards as proof of Rust test parity.

## Snapshot

| Area | Rust test files | Rust test functions found | Files with Python mapping | Files missing Python mapping |
| --- | ---: | ---: | ---: | ---: |
| `core/src` unit/module tests | 97 | 1717 | 66 | 31 |
| `core/tests` integration tests | 88 | 762 | 68 | 20 |

## Recommended first batches

1. Fill missing mappings for small pure helper test files in `core/src`, especially modules that already have Python implementations.
2. Mirror Rust embedded test functions for files already mapped but not function-complete.
3. Defer `core/tests/suite/*` runtime harness tests until the corresponding Python runtime harness exists.

## Unit/module test files from `core/src`

| Rust test file | Rust test functions | Python mapping | Status |
| --- | ---: | --- | --- |
| `codex/codex-rs/core/src/agent/control_tests.rs` | 45 | test_core_agent_control.py | mapped |
| `codex/codex-rs/core/src/agent/registry_tests.rs` | 15 | test_core_agent_registry.py | mapped |
| `codex/codex-rs/core/src/agent/role_tests.rs` | 19 | test_core_agent_role_coordinate.py, test_core_agent_roles.py | mapped |
| `codex/codex-rs/core/src/agents_md_tests.rs` | 23 | test_core_agents_md.py | mapped |
| `codex/codex-rs/core/src/apply_patch_tests.rs` | 1 | test_core_apply_patch.py | mapped |
| `codex/codex-rs/core/src/attestation.rs` | 0 | test_core_attestation.py | mapped |
| `codex/codex-rs/core/src/client_common_tests.rs` | 5 | test_core_client_common.py | mapped |
| `codex/codex-rs/core/src/client_tests.rs` | 10 | test_core_client.py | mapped |
| `codex/codex-rs/core/src/codex_delegate_tests.rs` | 6 | test_core_codex_delegate.py | mapped |
| `codex/codex-rs/core/src/command_canonicalization_tests.rs` | 4 | test_core_command_canonicalization.py | mapped |
| `codex/codex-rs/core/src/compact_tests.rs` | 16 | test_core_compact.py | mapped |
| `codex/codex-rs/core/src/config/config_loader_tests.rs` | 67 | tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py | mapped |
| `codex/codex-rs/core/src/config/config_tests.rs` | 265 | tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py | mapped |
| `codex/codex-rs/core/src/config/edit_tests.rs` | 44 | test_core_config_edit.py | mapped |
| `codex/codex-rs/core/src/config/network_proxy_spec_tests.rs` | 14 | test_core_network_proxy_loader.py | mapped |
| `codex/codex-rs/core/src/config/permissions_tests.rs` | 18 | test_core_config_permissions.py | mapped |
| `codex/codex-rs/core/src/config/schema_tests.rs` | 2 | test_core_config_schema.py | mapped |
| `codex/codex-rs/core/src/connectors_tests.rs` | 30 | test_core_connectors.py | mapped |
| `codex/codex-rs/core/src/context/contextual_user_message_tests.rs` | 7 | test_core_contextual_user_message.py | mapped |
| `codex/codex-rs/core/src/context/environment_context_tests.rs` | 9 | test_core_environment_context.py | mapped |
| `codex/codex-rs/core/src/context/permissions_instructions_tests.rs` | 16 | test_core_permissions_instructions.py | mapped |
| `codex/codex-rs/core/src/context_manager/history_tests.rs` | 63 | test_core_context_manager_history.py | mapped |
| `codex/codex-rs/core/src/event_mapping_tests.rs` | 15 | test_core_event_mapping.py | mapped |
| `codex/codex-rs/core/src/exec_env_tests.rs` | 12 | test_core_exec_env.py | mapped |
| `codex/codex-rs/core/src/exec_policy_tests.rs` | 76 | test_core_exec_policy.py | mapped |
| `codex/codex-rs/core/src/exec_policy_windows_tests.rs` | 5 | test_core_exec_policy.py | mapped |
| `codex/codex-rs/core/src/exec_tests.rs` | 39 | test_core_exec.py | mapped |
| `codex/codex-rs/core/src/git_info_tests.rs` | 25 | test_core_git_info.py | mapped |
| `codex/codex-rs/core/src/guardian/tests.rs` | 48 | tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py | mapped |
| `codex/codex-rs/core/src/mcp_tool_call_tests.rs` | 70 | test_core_mcp_tool_call.py | mapped |
| `codex/codex-rs/core/src/mcp_tool_exposure_test.rs` | 3 | test_core_mcp_tool_exposure.py | mapped |
| `codex/codex-rs/core/src/network_policy_decision_tests.rs` | 6 | test_core_network_policy_decision.py | mapped |
| `codex/codex-rs/core/src/network_proxy_loader_tests.rs` | 16 | test_core_network_proxy_loader.py | mapped |
| `codex/codex-rs/core/src/personality_migration_tests.rs` | 5 | test_core_personality_migration.py | mapped |
| `codex/codex-rs/core/src/plugins/discoverable_tests.rs` | 10 | test_core_plugins_discoverable.py | mapped |
| `codex/codex-rs/core/src/plugins/mentions_tests.rs` | 8 | test_core_mentions.py | mapped |
| `codex/codex-rs/core/src/plugins/render_tests.rs` | 2 | test_core_app_plugin_rendering.py | mapped |
| `codex/codex-rs/core/src/plugins/test_support.rs` | 0 | test_core_plugins_test_support.py, test_core_test_support.py | mapped |
| `codex/codex-rs/core/src/realtime_context_tests.rs` | 9 | test_core_realtime_context.py | mapped |
| `codex/codex-rs/core/src/realtime_conversation_tests.rs` | 11 | test_core_realtime_conversation.py | mapped |
| `codex/codex-rs/core/src/safety_tests.rs` | 8 | test_core_safety.py | mapped |
| `codex/codex-rs/core/src/sandbox_tags_tests.rs` | 8 | test_core_sandbox_tags.py | mapped |
| `codex/codex-rs/core/src/session/mcp_tests.rs` | 6 | test_core_mcp.py | mapped |
| `codex/codex-rs/core/src/session/rollout_reconstruction_tests.rs` | 19 | test_core_session_rollout_reconstruction.py | mapped |
| `codex/codex-rs/core/src/session/tests/guardian_tests.rs` | 8 | tests/test_core_session_guardian.py | mapped |
| `codex/codex-rs/core/src/session/tests.rs` | 185 | tests/test_core_session_tests.py, tests/test_core_session_runtime.py, tests/test_core_session_handlers.py, tests/test_core_session_input_queue.py, tests/test_core_session_request_permissions.py, tests/test_core_session_guardian.py, tests/test_core_session_review.py, tests/test_core_session_rollout_reconstruction.py, tests/test_core_session_multi_agents.py, tests/test_core_goals.py, tests/test_core_client.py, tests/test_core_network_proxy_loader.py, tests/test_core_context_network_rule_saved.py, tests/test_core_state_session.py, tests/test_exec_session.py | mapped |
| `codex/codex-rs/core/src/session/turn_tests.rs` | 1 | tests/test_core_client.py | mapped |
| `codex/codex-rs/core/src/shell_snapshot_tests.rs` | 16 | test_core_shell_snapshot.py | mapped |
| `codex/codex-rs/core/src/shell_tests.rs` | 9 | test_core_shell.py | mapped |
| `codex/codex-rs/core/src/state/session_tests.rs` | 6 | test_core_state_session.py | mapped |
| `codex/codex-rs/core/src/stream_events_utils_tests.rs` | 19 | test_core_stream_events_utils.py | mapped |
| `codex/codex-rs/core/src/tasks/mod_tests.rs` | 6 | test_core_tasks_root.py | mapped |
| `codex/codex-rs/core/src/test_support.rs` | 0 | test_core_test_support.py | mapped |
| `codex/codex-rs/core/src/thread_manager_tests.rs` | 26 | test_core_thread_manager.py | mapped |
| `codex/codex-rs/core/src/thread_rollout_truncation_tests.rs` | 11 | test_core_thread_rollout_truncation.py | mapped |
| `codex/codex-rs/core/src/tools/context_tests.rs` | 14 | test_core_context.py, test_core_tools_context.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/agent_jobs_spec_tests.rs` | 2 | test_core_agent_jobs.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/agent_jobs_tests.rs` | 5 | test_core_agent_jobs.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/apply_patch_spec_tests.rs` | 2 | test_core_apply_patch.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/apply_patch_tests.rs` | 9 | test_core_apply_patch.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/dynamic_tests.rs` | 1 | test_core_dynamic_tool_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/mcp_resource_spec_tests.rs` | 3 | test_core_mcp_resource_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/mcp_resource_tests.rs` | 6 | test_core_mcp_resource_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/mcp_search_tests.rs` | 2 | test_core_mcp_tool_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/multi_agents_spec_tests.rs` | 9 | test_core_multi_agents_spec.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/multi_agents_tests.rs` | 75 | tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/request_plugin_install_tests.rs` | 5 | test_core_request_plugin_install.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/request_user_input_spec_tests.rs` | 3 | test_core_request_user_input_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/request_user_input_tests.rs` | 1 | test_core_request_user_input_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/shell_spec_tests.rs` | 4 | test_core_shell_spec.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/shell_tests.rs` | 7 | test_core_shell.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/test_sync.rs` | 0 | tests/test_core_test_sync_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/test_sync_spec.rs` | 0 | tests/test_core_test_sync_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/test_sync_spec_tests.rs` | 1 | test_core_test_sync_handler.py | mapped |
| `codex/codex-rs/core/src/tools/handlers/unified_exec_tests.rs` | 13 | test_core_unified_exec.py | mapped |
| `codex/codex-rs/core/src/tools/hosted_spec_tests.rs` | 3 | test_core_hosted_spec.py | mapped |
| `codex/codex-rs/core/src/tools/network_approval_tests.rs` | 15 | test_core_network_approval.py | mapped |
| `codex/codex-rs/core/src/tools/registry_tests.rs` | 8 | test_core_tool_registry.py | mapped |
| `codex/codex-rs/core/src/tools/router_tests.rs` | 6 | test_core_tool_router.py | mapped |
| `codex/codex-rs/core/src/tools/runtimes/apply_patch_tests.rs` | 7 | test_core_apply_patch.py | mapped |
| `codex/codex-rs/core/src/tools/runtimes/mod_tests.rs` | 21 | test_core_tool_runtimes.py | mapped |
| `codex/codex-rs/core/src/tools/runtimes/shell/unix_escalation_tests.rs` | 16 | test_core_tool_runtimes.py | mapped |
| `codex/codex-rs/core/src/tools/sandboxing_tests.rs` | 9 | test_core_sandboxing.py | mapped |
| `codex/codex-rs/core/src/tools/spec_plan_tests.rs` | 15 | test_core_spec_plan.py | mapped |
| `codex/codex-rs/core/src/tools/tool_dispatch_trace_tests.rs` | 4 | test_core_tool_dispatch_trace.py | mapped |
| `codex/codex-rs/core/src/turn_diff_tracker_tests.rs` | 10 | test_core_turn_diff_tracker.py | mapped |
| `codex/codex-rs/core/src/turn_metadata_tests.rs` | 11 | test_core_turn_metadata.py | mapped |
| `codex/codex-rs/core/src/turn_timing_tests.rs` | 5 | test_core_turn_timing.py | mapped |
| `codex/codex-rs/core/src/unified_exec/async_watcher_tests.rs` | 3 | test_core_unified_exec_async_watcher.py | mapped |
| `codex/codex-rs/core/src/unified_exec/head_tail_buffer_tests.rs` | 6 | test_core_unified_exec.py | mapped |
| `codex/codex-rs/core/src/unified_exec/mod_tests.rs` | 12 | test_core_unified_exec.py, test_core_unified_exec_module_contract.py | mapped |
| `codex/codex-rs/core/src/unified_exec/process_manager_tests.rs` | 11 | test_core_unified_exec.py | mapped |
| `codex/codex-rs/core/src/unified_exec/process_tests.rs` | 4 | test_core_unified_exec.py | mapped |
| `codex/codex-rs/core/src/user_shell_command_tests.rs` | 3 | test_core_user_shell_command.py | mapped |
| `codex/codex-rs/core/src/util_tests.rs` | 7 | test_core_util.py | mapped |
| `codex/codex-rs/core/src/windows_sandbox_read_grants_tests.rs` | 3 | test_core_windows_sandbox_read_grants.py | mapped |
| `codex/codex-rs/core/src/windows_sandbox_tests.rs` | 9 | test_core_windows_sandbox.py | mapped |

## Integration test files from `core/tests`

| Rust test file | Rust test functions | Python mapping | Status |
| --- | ---: | --- | --- |
| `codex/codex-rs/core/tests/all.rs` | 0 | not applicable: Rust integration aggregator only | mapped |
| `codex/codex-rs/core/tests/responses_headers.rs` | 4 | tests/test_core_responses_headers.py | mapped |
| `codex/codex-rs/core/tests/suite/abort_tasks.rs` | 3 | tests/test_core_suite_abort_tasks.py | mapped |
| `codex/codex-rs/core/tests/suite/additional_context.rs` | 6 | tests/test_core_suite_additional_context.py | mapped |
| `codex/codex-rs/core/tests/suite/agent_jobs.rs` | 4 | test_core_agent_jobs.py | mapped |
| `codex/codex-rs/core/tests/suite/agent_websocket.rs` | 7 | tests/test_core_suite_agent_websocket.py | mapped |
| `codex/codex-rs/core/tests/suite/agents_md.rs` | 3 | test_core_agents_md.py | mapped |
| `codex/codex-rs/core/tests/suite/apply_patch_cli.rs` | 35 | tests/test_core_suite_apply_patch_cli.py | mapped |
| `codex/codex-rs/core/tests/suite/approvals.rs` | 10 | tests/test_core_suite_approvals.py | mapped |
| `codex/codex-rs/core/tests/suite/cli_stream.rs` | 7 | tests/test_core_suite_cli_stream.py | mapped |
| `codex/codex-rs/core/tests/suite/client.rs` | 36 | test_core_client.py | mapped |
| `codex/codex-rs/core/tests/suite/client_websockets.rs` | 37 | tests/test_core_suite_client_websockets.py | mapped |
| `codex/codex-rs/core/tests/suite/code_mode.rs` | 47 | test_core_code_mode.py | mapped |
| `codex/codex-rs/core/tests/suite/codex_delegate.rs` | 3 | test_core_codex_delegate.py | mapped |
| `codex/codex-rs/core/tests/suite/collaboration_instructions.rs` | 12 | tests/test_core_suite_collaboration_instructions.py | mapped |
| `codex/codex-rs/core/tests/suite/compact.rs` | 27 | test_core_compact.py | mapped |
| `codex/codex-rs/core/tests/suite/compact_remote.rs` | 30 | test_core_compact_remote.py | mapped |
| `codex/codex-rs/core/tests/suite/compact_remote_parity.rs` | 8 | tests/test_core_suite_compact_remote_parity.py | mapped |
| `codex/codex-rs/core/tests/suite/compact_resume_fork.rs` | 4 | tests/test_core_suite_compact_resume_fork.py | mapped |
| `codex/codex-rs/core/tests/suite/deprecation_notice.rs` | 3 | tests/test_core_suite_deprecation_notice.py | mapped |
| `codex/codex-rs/core/tests/suite/exec.rs` | 6 | test_core_exec.py | mapped |
| `codex/codex-rs/core/tests/suite/exec_policy.rs` | 5 | test_core_exec_policy.py | mapped |
| `codex/codex-rs/core/tests/suite/fork_thread.rs` | 2 | tests/test_core_suite_fork_thread.py | mapped |
| `codex/codex-rs/core/tests/suite/guardian_review.rs` | 1 | test_core_guardian_review.py | mapped |
| `codex/codex-rs/core/tests/suite/hierarchical_agents.rs` | 2 | tests/test_core_suite_hierarchical_agents.py | mapped |
| `codex/codex-rs/core/tests/suite/hooks.rs` | 40 | tests/test_core_suite_hooks.py | mapped |
| `codex/codex-rs/core/tests/suite/hooks_mcp.rs` | 5 | tests/test_core_suite_hooks_mcp.py | mapped |
| `codex/codex-rs/core/tests/suite/image_rollout.rs` | 2 | tests/test_core_suite_image_rollout.py | mapped |
| `codex/codex-rs/core/tests/suite/items.rs` | 14 | tests/test_core_suite_items.py | mapped |
| `codex/codex-rs/core/tests/suite/json_result.rs` | 2 | tests/test_core_suite_json_result.py | mapped |
| `codex/codex-rs/core/tests/suite/live_cli.rs` | 2 | tests/test_core_suite_live_cli.py | mapped |
| `codex/codex-rs/core/tests/suite/mcp_turn_metadata.rs` | 2 | tests/test_core_suite_mcp_turn_metadata.py | mapped |
| `codex/codex-rs/core/tests/suite/model_overrides.rs` | 2 | tests/test_core_suite_model_overrides.py | mapped |
| `codex/codex-rs/core/tests/suite/model_switching.rs` | 12 | tests/test_core_suite_model_switching.py | mapped |
| `codex/codex-rs/core/tests/suite/model_visible_layout.rs` | 6 | tests/test_core_suite_model_visible_layout.py | mapped |
| `codex/codex-rs/core/tests/suite/models_cache_ttl.rs` | 4 | tests/test_core_suite_models_cache_ttl.py | mapped |
| `codex/codex-rs/core/tests/suite/models_etag_responses.rs` | 1 | tests/test_core_suite_models_etag_responses.py | mapped |
| `codex/codex-rs/core/tests/suite/openai_file_mcp.rs` | 1 | tests/test_core_suite_openai_file_mcp.py | mapped |
| `codex/codex-rs/core/tests/suite/otel.rs` | 24 | tests/test_core_suite_otel.py | mapped |
| `codex/codex-rs/core/tests/suite/override_updates.rs` | 3 | tests/test_core_suite_override_updates.py | mapped |
| `codex/codex-rs/core/tests/suite/pending_input.rs` | 7 | `tests/test_core_suite_pending_input.py` | mapped |
| `codex/codex-rs/core/tests/suite/permissions_messages.rs` | 7 | `tests/test_core_suite_permissions_messages.py` | mapped |
| `codex/codex-rs/core/tests/suite/personality.rs` | 12 | `tests/test_core_suite_personality.py` | mapped |
| `codex/codex-rs/core/tests/suite/personality_migration.rs` | 11 | `tests/test_core_suite_personality_migration.py` | mapped |
| `codex/codex-rs/core/tests/suite/plugins.rs` | 3 | `tests/test_core_suite_plugins.py` | mapped |
| `codex/codex-rs/core/tests/suite/prompt_caching.rs` | 8 | `tests/test_core_suite_prompt_caching.py` | mapped |
| `codex/codex-rs/core/tests/suite/prompt_debug_tests.rs` | 1 | `tests/test_core_suite_prompt_debug_tests.py` | mapped |
| `codex/codex-rs/core/tests/suite/quota_exceeded.rs` | 1 | `tests/test_core_suite_quota_exceeded.py` | mapped |
| `codex/codex-rs/core/tests/suite/realtime_conversation.rs` | 38 | test_core_realtime_conversation.py | mapped |
| `codex/codex-rs/core/tests/suite/remote_env.rs` | 9 | tests/test_core_suite_remote_env.py | mapped |
| `codex/codex-rs/core/tests/suite/remote_models.rs` | 16 | test_core_suite_remote_models.py | mapped |
| `codex/codex-rs/core/tests/suite/request_compression.rs` | 2 | test_core_suite_request_compression.py | mapped |
| `codex/codex-rs/core/tests/suite/request_permissions.rs` | 14 | tests/test_core_suite_request_permissions.py | mapped |
| `codex/codex-rs/core/tests/suite/request_permissions_tool.rs` | 2 | tests/test_core_suite_request_permissions_tool.py | mapped |
| `codex/codex-rs/core/tests/suite/request_plugin_install.rs` | 1 | test_core_request_plugin_install.py | mapped |
| `codex/codex-rs/core/tests/suite/request_user_input.rs` | 6 | tests/test_core_suite_request_user_input.py | mapped |
| `codex/codex-rs/core/tests/suite/responses_api_proxy_headers.rs` | 1 | tests/test_core_suite_responses_api_proxy_headers.py | mapped |
| `codex/codex-rs/core/tests/suite/resume.rs` | 4 | tests/test_core_suite_resume.py | mapped |
| `codex/codex-rs/core/tests/suite/resume_warning.rs` | 1 | tests/test_core_suite_resume_warning.py | mapped |
| `codex/codex-rs/core/tests/suite/review.rs` | 11 | tests/test_core_suite_review.py | mapped |
| `codex/codex-rs/core/tests/suite/rmcp_client.rs` | 15 | tests/test_core_suite_rmcp_client.py | mapped |
| `codex/codex-rs/core/tests/suite/rollout_list_find.rs` | 7 | tests/test_core_suite_rollout_list_find.py | mapped |
| `codex/codex-rs/core/tests/suite/safety_check_downgrade.rs` | 7 | `tests/test_core_suite_safety_check_downgrade.py` | mapped |
| `codex/codex-rs/core/tests/suite/search_tool.rs` | 14 | `tests/test_core_suite_search_tool.py` | mapped |
| `codex/codex-rs/core/tests/suite/shell_command.rs` | 9 | `tests/test_core_suite_shell_command.py` | mapped |
| `codex/codex-rs/core/tests/suite/shell_serialization.rs` | 9 | `tests/test_core_suite_shell_serialization.py` | mapped |
| `codex/codex-rs/core/tests/suite/shell_snapshot.rs` | 8 | test_core_shell_snapshot.py | mapped |
| `codex/codex-rs/core/tests/suite/skill_approval.rs` | 2 | `tests/test_core_suite_skill_approval.py` | mapped |
| `codex/codex-rs/core/tests/suite/skills.rs` | 1 | test_core_skills.py | mapped |
| `codex/codex-rs/core/tests/suite/spawn_agent_description.rs` | 1 | `tests/test_core_suite_spawn_agent_description.py` | mapped |
| `codex/codex-rs/core/tests/suite/sqlite_state.rs` | 7 | `tests/test_core_suite_sqlite_state.py` | mapped |
| `codex/codex-rs/core/tests/suite/stream_error_allows_next_turn.rs` | 1 | `tests/test_core_suite_stream_error_allows_next_turn.py` | mapped |
| `codex/codex-rs/core/tests/suite/stream_no_completed.rs` | 1 | `tests/test_core_suite_stream_no_completed.py` | mapped |
| `codex/codex-rs/core/tests/suite/subagent_notifications.rs` | 9 | `tests/test_core_suite_subagent_notifications.py` | mapped |
| `codex/codex-rs/core/tests/suite/tool_harness.rs` | 5 | `tests/test_core_suite_tool_harness.py` | mapped |
| `codex/codex-rs/core/tests/suite/tool_parallelism.rs` | 5 | `tests/test_core_suite_tool_parallelism.py` | mapped |
| `codex/codex-rs/core/tests/suite/tools.rs` | 9 | `tests/test_core_suite_tools.py` | mapped |
| `codex/codex-rs/core/tests/suite/truncation.rs` | 10 | `tests/test_core_suite_truncation.py` | mapped |
| `codex/codex-rs/core/tests/suite/turn_state.rs` | 2 | `tests/test_core_suite_turn_state.py` | mapped |
| `codex/codex-rs/core/tests/suite/unified_exec.rs` | 31 | test_core_unified_exec.py | mapped |
| `codex/codex-rs/core/tests/suite/unstable_features_warning.rs` | 2 | `tests/test_core_suite_unstable_features_warning.py` | mapped |
| `codex/codex-rs/core/tests/suite/user_notification.rs` | 1 | `tests/test_core_suite_user_notification.py` | mapped |
| `codex/codex-rs/core/tests/suite/user_shell_cmd.rs` | 7 | `tests/test_core_suite_user_shell_cmd.py` | mapped |
| `codex/codex-rs/core/tests/suite/view_image.rs` | 16 | `tests/test_core_suite_view_image.py` | mapped |
| `codex/codex-rs/core/tests/suite/web_search.rs` | 5 | test_core_web_search.py | mapped |
| `codex/codex-rs/core/tests/suite/websocket_fallback.rs` | 4 | `tests/test_core_suite_websocket_fallback.py` | mapped |
| `codex/codex-rs/core/tests/suite/window_headers.rs` | 1 | `tests/test_core_suite_window_headers.py` | mapped |
| `codex/codex-rs/core/tests/suite/windows_sandbox.rs` | 2 | test_core_windows_sandbox.py | mapped |

## Function-level inventory

Use this section when porting individual Rust test functions. Status defaults to `todo` until explicitly mirrored.

### Unit/module tests

#### `codex/codex-rs/core/src/agent/control_tests.rs`

- `send_input_errors_when_manager_dropped` -> todo
- `get_status_returns_not_found_without_manager` -> todo
- `on_event_updates_status_from_task_started` -> todo
- `on_event_updates_status_from_task_complete` -> todo
- `on_event_updates_status_from_error` -> todo
- `on_event_updates_status_from_turn_aborted` -> todo
- `on_event_updates_status_from_shutdown_complete` -> todo
- `spawn_agent_errors_when_manager_dropped` -> todo
- `resume_agent_errors_when_manager_dropped` -> todo
- `send_input_errors_when_thread_missing` -> todo
- `get_status_returns_not_found_for_missing_thread` -> todo
- `get_status_returns_pending_init_for_new_thread` -> todo
- `subscribe_status_errors_for_missing_thread` -> todo
- `subscribe_status_updates_on_shutdown` -> todo
- `send_input_submits_user_message` -> todo
- `send_inter_agent_communication_without_turn_queues_message_without_triggering_turn` -> todo
- `spawn_agent_creates_thread_and_sends_prompt` -> todo
- `spawn_agent_can_fork_parent_thread_history_with_sanitized_items` -> todo
- `spawn_agent_fork_strips_parent_usage_hints_from_compacted_history` -> todo
- `spawn_agent_fork_flushes_parent_rollout_before_loading_history` -> todo
- `spawn_agent_fork_last_n_turns_keeps_only_recent_turns` -> todo
- `spawn_agent_fork_last_n_turns_drops_parent_startup_prefix_when_under_limit` -> todo
- `spawn_agent_fork_last_n_turns_strips_parent_usage_hints` -> todo
- `spawn_agent_respects_max_threads_limit` -> todo
- `spawn_agent_releases_slot_after_shutdown` -> todo
- `spawn_agent_limit_shared_across_clones` -> todo
- `resume_agent_respects_max_threads_limit` -> todo
- `resume_agent_releases_slot_after_resume_failure` -> todo
- `spawn_child_completion_notifies_parent_history` -> todo
- `multi_agent_v2_completion_ignores_dead_direct_parent` -> todo
- `multi_agent_v2_completion_queues_message_for_direct_parent` -> todo
- `completion_watcher_notifies_parent_when_child_is_missing` -> todo
- `spawn_thread_subagent_gets_random_nickname_in_session_source` -> todo
- `spawn_thread_subagent_uses_role_specific_nickname_candidates` -> todo
- `resume_thread_subagent_restores_stored_nickname_and_role` -> todo
- `resume_agent_from_rollout_reads_archived_rollout_path` -> todo
- `list_agent_subtree_thread_ids_includes_anonymous_and_closed_descendants` -> todo
- `list_agent_subtree_thread_ids_includes_live_descendants_without_state_db` -> todo
- `shutdown_agent_tree_closes_live_descendants` -> todo
- `shutdown_agent_tree_closes_descendants_when_started_at_child` -> todo
- `resume_agent_from_rollout_does_not_reopen_closed_descendants` -> todo
- `resume_closed_child_reopens_open_descendants` -> todo
- `resume_agent_from_rollout_reopens_open_descendants_after_manager_shutdown` -> todo
- `resume_agent_from_rollout_uses_edge_data_when_descendant_metadata_source_is_stale` -> todo
- `resume_agent_from_rollout_skips_descendants_when_parent_resume_fails` -> todo

#### `codex/codex-rs/core/src/agent/registry_tests.rs`

- `format_agent_nickname_adds_ordinals_after_reset` -> todo
- `session_depth_defaults_to_zero_for_root_sources` -> todo
- `thread_spawn_depth_increments_and_enforces_limit` -> todo
- `non_thread_spawn_subagents_default_to_depth_zero` -> todo
- `reservation_drop_releases_slot` -> todo
- `commit_holds_slot_until_release` -> todo
- `release_ignores_unknown_thread_id` -> todo
- `release_is_idempotent_for_registered_threads` -> todo
- `failed_spawn_keeps_nickname_marked_used` -> todo
- `agent_nickname_resets_used_pool_when_exhausted` -> todo
- `released_nickname_stays_used_until_pool_reset` -> todo
- `repeated_resets_advance_the_ordinal_suffix` -> todo
- `register_root_thread_indexes_root_path` -> todo
- `reserved_agent_path_is_released_when_spawn_fails` -> todo
- `committed_agent_path_is_indexed_until_release` -> todo

#### `codex/codex-rs/core/src/agent/role_tests.rs`

- `apply_role_defaults_to_default_and_leaves_config_unchanged` -> todo
- `apply_role_returns_error_for_unknown_role` -> todo
- `apply_explorer_role_sets_model_and_adds_session_flags_layer` -> todo
- `apply_empty_explorer_role_preserves_current_model_and_reasoning_effort` -> todo
- `apply_role_returns_unavailable_for_missing_user_role_file` -> todo
- `apply_role_returns_unavailable_for_invalid_user_role_toml` -> todo
- `apply_role_ignores_agent_metadata_fields_in_user_role_file` -> todo
- `apply_role_preserves_unspecified_keys` -> todo
- `apply_role_reports_explicit_service_tier` -> todo
- `apply_role_preserves_existing_service_tier_without_override` -> todo
- `apply_role_does_not_materialize_default_sandbox_workspace_write_fields` -> todo
- `apply_role_takes_precedence_over_existing_session_flags_for_same_key` -> todo
- `apply_role_skills_config_disables_skill_for_spawned_agent` -> todo
- `spawn_tool_spec_build_deduplicates_user_defined_built_in_roles` -> todo
- `spawn_tool_spec_lists_user_defined_roles_before_built_ins` -> todo
- `spawn_tool_spec_marks_role_locked_model_and_reasoning_effort` -> todo
- `spawn_tool_spec_marks_role_locked_reasoning_effort_only` -> todo
- `spawn_tool_spec_marks_role_locked_service_tier` -> todo
- `built_in_config_file_contents_resolves_explorer_only` -> todo

#### `codex/codex-rs/core/src/agents_md_tests.rs`

- `no_doc_file_returns_none` -> todo
- `no_environment_returns_none` -> todo
- `doc_smaller_than_limit_is_returned` -> todo
- `global_doc_invalid_utf8_warns_and_uses_lossy_text` -> todo
- `project_doc_invalid_utf8_warns_and_uses_lossy_text` -> todo
- `doc_larger_than_limit_is_truncated` -> todo
- `finds_doc_in_repo_root` -> todo
- `zero_byte_limit_disables_docs` -> todo
- `zero_byte_limit_disables_discovery` -> todo
- `merges_existing_instructions_with_agents_md` -> todo
- `keeps_existing_instructions_when_doc_missing` -> todo
- `concatenates_root_and_cwd_docs` -> todo
- `project_root_markers_are_honored_for_agents_discovery` -> todo
- `instruction_sources_include_global_before_agents_md_docs` -> todo
- `agents_local_md_preferred` -> todo
- `uses_configured_fallback_when_agents_missing` -> todo
- `agents_md_preferred_over_fallbacks` -> todo
- `agents_md_directory_is_ignored` -> todo
- `agents_md_special_file_is_ignored` -> todo
- `override_directory_falls_back_to_agents_md_file` -> todo
- `skills_are_not_appended_to_agents_md` -> todo
- `apps_feature_does_not_emit_user_instructions_by_itself` -> todo
- `apps_feature_does_not_append_to_agents_md_user_instructions` -> todo

#### `codex/codex-rs/core/src/apply_patch_tests.rs`

- `convert_apply_patch_maps_add_variant` -> todo

#### `codex/codex-rs/core/src/client_common_tests.rs`

- `serializes_text_verbosity_when_set` -> todo
- `serializes_text_schema_with_strict_format` -> todo
- `serializes_text_schema_with_non_strict_format` -> todo
- `omits_text_when_not_set` -> todo
- `serializes_flex_service_tier_when_set` -> todo

#### `codex/codex-rs/core/src/client_tests.rs`

- `build_subagent_headers_sets_other_subagent_label` -> todo
- `build_subagent_headers_sets_internal_memory_consolidation_label` -> todo
- `build_ws_client_metadata_includes_window_lineage_and_turn_metadata` -> todo
- `summarize_memories_returns_empty_for_empty_input` -> todo
- `dropped_response_stream_traces_cancelled_partial_output` -> todo
- `response_stream_records_last_model_feedback_ids` -> todo
- `dropped_backpressured_response_stream_traces_cancelled_partial_output` -> todo
- `auth_request_telemetry_context_tracks_attached_auth_and_retry_phase` -> todo
- `websocket_handshake_includes_attestation_for_chatgpt_codex_responses` -> todo
- `non_chatgpt_codex_endpoints_omit_attestation_generation` -> todo

#### `codex/codex-rs/core/src/codex_delegate_tests.rs`

- `forward_events_cancelled_while_send_blocked_shuts_down_delegate` -> todo
- `forward_ops_preserves_submission_trace_context` -> todo
- `run_codex_thread_interactive_respects_pre_cancelled_spawn` -> todo
- `handle_request_permissions_uses_tool_call_id_for_round_trip` -> todo
- `handle_exec_approval_uses_call_id_for_guardian_review_and_approval_id_for_reply` -> todo
- `delegated_mcp_guardian_abort_returns_synthetic_decline_answer` -> todo

#### `codex/codex-rs/core/src/command_canonicalization_tests.rs`

- `canonicalizes_word_only_shell_scripts_to_inner_command` -> todo
- `canonicalizes_heredoc_scripts_to_stable_script_key` -> todo
- `canonicalizes_powershell_wrappers_to_stable_script_key` -> todo
- `preserves_non_shell_commands` -> todo

#### `codex/codex-rs/core/src/compact_tests.rs`

- `content_items_to_text_joins_non_empty_segments` -> todo
- `content_items_to_text_ignores_image_only_content` -> todo
- `collect_user_messages_extracts_user_text_only` -> todo
- `collect_user_messages_filters_session_prefix_entries` -> todo
- `collect_user_messages_filters_legacy_warnings` -> todo
- `build_token_limited_compacted_history_truncates_overlong_user_messages` -> todo
- `build_token_limited_compacted_history_appends_summary_message` -> todo
- `should_use_remote_compact_task_for_azure_provider` -> todo
- `process_compacted_history_replaces_developer_messages` -> todo
- `process_compacted_history_reinjects_full_initial_context` -> todo
- `process_compacted_history_drops_non_user_content_messages` -> todo
- `process_compacted_history_drops_legacy_warnings` -> todo
- `process_compacted_history_inserts_context_before_last_real_user_message_only` -> todo
- `process_compacted_history_reinjects_model_switch_message` -> todo
- `insert_initial_context_before_last_real_user_or_summary_keeps_summary_last` -> todo
- `insert_initial_context_before_last_real_user_or_summary_keeps_compaction_last` -> todo

#### `codex/codex-rs/core/src/config/config_loader_tests.rs`

- `cli_overrides_resolve_relative_paths_against_cwd` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `returns_config_error_for_invalid_user_config_toml` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `ignore_user_config_keeps_empty_user_layer` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `ignore_rules_marks_config_stack_for_exec_policy_rule_skip` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `returns_config_error_for_invalid_managed_config_toml` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `returns_config_error_for_schema_error_in_user_config` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `top_level_allow_managed_hooks_only_in_user_config_does_not_enable_requirements_policy` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `hooks_allow_managed_hooks_only_in_user_config_does_not_enable_requirements_policy` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `strict_config_rejects_unknown_user_config_key` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `strict_config_rejects_unknown_cli_override_key` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `strict_config_rejects_unknown_cli_override_key_with_relative_path_override` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `strict_config_rejects_unknown_feature_cli_override_key` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `strict_config_rejects_unknown_feature_user_config_key` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `strict_config_points_to_unknown_nested_key` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `schema_error_points_to_feature_value` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `merges_managed_config_layer_on_top` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `returns_empty_when_all_layers_missing` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `selected_user_config_file_layers_over_base_user_config` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `includes_thread_config_layers_in_stack` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `managed_preferences_take_highest_precedence` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `managed_preferences_expand_home_directory_in_workspace_write_roots` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `managed_preferences_requirements_are_applied` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `managed_preferences_requirements_take_precedence` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `load_requirements_toml_produces_expected_constraints` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `cloud_requirements_take_precedence_over_mdm_requirements` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `cloud_requirements_are_not_overwritten_by_system_requirements` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `system_remote_sandbox_config_keeps_cloud_sandbox_modes` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `load_requirements_toml_resolves_deny_read_against_parent` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `load_requirements_toml_resolves_deny_read_glob_against_parent` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `load_config_layers_includes_cloud_requirements` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `system_requirements_define_managed_permission_profiles` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `system_allowed_permissions_keep_builtin_permission_fallbacks` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `system_allowed_permissions_keep_explicit_builtin_defaults` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `system_requirements_preserve_allowed_configured_permission_default` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `system_requirements_warn_for_disallowed_explicit_permission_override` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `load_config_layers_can_ignore_managed_requirements` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `load_config_layers_includes_cloud_hook_requirements` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `load_config_layers_applies_matching_remote_sandbox_config` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `load_config_layers_fails_when_cloud_requirements_loader_fails` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `project_layers_prefer_closest_cwd` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `linked_worktree_project_layers_keep_worktree_config_but_use_root_repo_hooks` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `linked_worktree_project_layers_use_root_repo_hooks_without_worktree_config_toml` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `nested_project_root_markers_do_not_redirect_regular_repo_hooks` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `project_paths_resolve_relative_to_dot_codex_and_override_in_order` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `cli_override_model_instructions_file_sets_base_instructions` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `inline_instructions_set_base_instructions` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `project_layer_is_added_when_dot_codex_exists_without_config_toml` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `codex_home_is_not_loaded_as_project_layer_from_home_dir` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `codex_home_within_project_tree_is_not_double_loaded` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `project_layers_disabled_when_untrusted_or_unknown` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `project_layer_ignores_unsupported_config_keys` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `project_trust_does_not_match_configured_alias_for_canonical_cwd` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `cli_override_can_update_project_local_mcp_server_when_project_is_trusted` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `cli_override_for_disabled_project_local_mcp_server_returns_invalid_transport` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `invalid_project_config_ignored_when_untrusted_or_unknown` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `project_layer_without_config_toml_is_disabled_when_untrusted_or_unknown` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `cli_overrides_with_relative_paths_do_not_break_trust_check` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `project_root_markers_supports_alternate_markers` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `parses_single_prefix_rule_from_raw_toml` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `parses_multiple_prefix_rules_from_raw_toml` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `converts_rules_toml_into_internal_policy_representation` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `head_any_of_expands_into_multiple_program_rules` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `missing_decision_is_rejected` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `allow_decision_is_rejected` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `empty_prefix_rules_is_rejected` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `loads_requirements_exec_policy_without_rules_files` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py
- `merges_requirements_exec_policy_with_file_rules` -> tests/test_core_config_loader.py, tests/test_core_config_root.py, tests/test_core_config_permissions.py, tests/test_core_network_proxy_loader.py, tests/test_core_skill_config_rules.py, tests/test_core_exec_policy.py, tests/test_config_overrides.py, tests/test_core_config_schema.py

#### `codex/codex-rs/core/src/config/config_tests.rs`

- `load_config_normalizes_relative_cwd_override` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_loads_global_agents_instructions` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_prefers_global_agents_override_instructions` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_toml_parsing` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `parses_bundled_skills_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tools_web_search_true_deserializes_to_none` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tools_web_search_false_deserializes_to_none` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `rejects_provider_auth_with_env_key` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `rejects_provider_aws_for_custom_provider` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `accepts_amazon_bedrock_aws_profile_override` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_applies_amazon_bedrock_aws_profile_override` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_rejects_unsupported_amazon_bedrock_overrides` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_deserializes_model_availability_nux` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_status_line_use_colors_defaults_to_enabled` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_deserializes_status_line_use_colors_disabled` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_deserializes_terminal_resize_reflow_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `runtime_config_defaults_model_availability_nux` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_vim_mode_default_defaults_to_false` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_vim_mode_default_true` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_raw_output_mode_defaults_to_false` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_raw_output_mode_true` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `runtime_config_uses_tui_raw_output_mode` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_deserializes_permission_profiles` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_rejects_empty_mitm_action_reference_list` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_rejects_empty_mitm_action_definition` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profile_network_to_proxy_config_preserves_mitm_hooks` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profile_network_to_proxy_config_preserves_mitm_hook_declaration_order` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_proxy_policy_does_not_start_managed_network_proxy_without_feature` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_proxy_policy_starts_managed_network_proxy` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `network_proxy_feature_is_no_op_without_sandbox_network` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `network_proxy_feature_matrix_preserves_sandbox_network_semantics` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `network_proxy_cli_overrides_merge_toggle_with_proxy_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `experimental_network_requirements_enable_proxy_without_feature` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `network_proxy_feature_uses_profile_network_proxy_settings` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `disabled_network_proxy_feature_does_not_start_profile_proxy_policy` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_network_disabled_by_default_does_not_start_proxy` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_permissions_profile_populates_runtime_sandbox_policy` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_permissions_extended_profile_preserves_parent_metadata` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permission_profile_override_populates_runtime_permissions` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permission_snapshot_setter_preserves_permission_constraints` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permission_profile_override_preserves_managed_unrestricted_filesystem` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `managed_unrestricted_permission_profile_still_enables_network_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permission_profile_override_keeps_memories_root_out_of_legacy_projection` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permission_profile_override_preserves_configured_network_policy_without_starting_proxy` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `workspace_root_glob_none_compiles_to_filesystem_pattern_entry` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_require_default_permissions` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_permissions_can_select_builtin_profile_without_permissions_table` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_permissions_read_only_keeps_add_dir_read_only` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `workspace_profile_applies_rules_to_runtime_and_profile_workspace_roots` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `explicit_builtin_workspace_profile_ignores_legacy_workspace_write_settings` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_permissions_profile_can_extend_builtin_workspace` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_permissions_profile_can_extend_builtin_read_only` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `empty_config_defaults_to_builtin_profile_for_trusted_project` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `implicit_builtin_workspace_profile_preserves_sandbox_workspace_write_settings` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `implicit_builtin_workspace_profile_preserves_add_dir_metadata_carveouts` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `empty_config_defaults_to_builtin_read_only_without_trust_decision` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_permissions_can_select_builtin_full_access_profile` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `legacy_danger_no_sandbox_is_rejected` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `user_defined_permission_profile_names_cannot_use_builtin_prefix` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `unknown_builtin_permission_profile_name_is_rejected` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_allow_direct_write_roots_outside_workspace_root` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_reject_nested_entries_for_non_workspace_roots` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_allow_unknown_special_paths` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_allow_unknown_special_paths_with_nested_entries` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_allow_missing_filesystem_with_warning` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_allow_empty_filesystem_with_warning` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_reject_workspace_root_parent_traversal` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permissions_profiles_allow_network_enablement` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_theme_deserializes_from_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_theme_defaults_to_none` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_session_picker_view_deserializes_from_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_pet_deserializes_from_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_session_picker_view_defaults_to_none` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_pet_defaults_to_none` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_pet_anchor_deserializes_from_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_pet_anchor_defaults_to_composer` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_pet_anchor_rejects_unknown_value` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tui_config_missing_notifications_field_defaults_to_enabled` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `runtime_config_resolves_terminal_resize_reflow_defaults_and_overrides` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `forced_chatgpt_workspace_id_empty_values_disable_runtime_restriction` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `legacy_remote_thread_store_endpoint_is_rejected` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `profile_tui_rejects_unsupported_settings` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `runtime_config_resolves_session_picker_view_default_and_override` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_sandbox_config_parsing` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `legacy_sandbox_mode_builds_profiles_with_compatible_projection` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `filter_mcp_servers_by_allowlist_enforces_identity_rules` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `filter_mcp_servers_by_allowlist_allows_all_when_unset` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `filter_mcp_servers_by_allowlist_blocks_all_when_empty` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `filter_plugin_mcp_servers_by_allowlist_enforces_plugin_and_identity_rules` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `filter_plugin_mcp_servers_by_allowlist_blocks_unlisted_plugin` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `rebuild_preserving_session_layers_refreshes_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `rebuild_preserving_session_layers_refreshes_plugin_derived_mcp_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `to_mcp_config_omits_plugin_id_when_user_server_shadows_plugin_mcp` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `to_mcp_config_applies_plugin_mcp_cloud_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `to_mcp_config_empty_mcp_requirements_disable_plugin_mcps` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `add_dir_override_extends_workspace_writable_roots` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_zsh_path_sets_runtime_zsh_path` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `sqlite_home_defaults_to_codex_home_for_workspace_write` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `workspace_write_includes_configured_writable_root_once_without_memories_root` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `memory_tool_makes_memories_root_readable_without_creating_or_widening_writes` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_defaults_to_file_cli_auth_store_mode` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_resolves_explicit_keyring_auth_store_mode` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_resolves_default_oauth_store_mode` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `local_dev_builds_force_file_cli_auth_store_modes` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `local_dev_builds_force_file_mcp_oauth_store_modes` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `feedback_enabled_defaults_to_true` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `web_search_mode_defaults_to_none_if_unset` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `web_search_mode_prefers_config_over_legacy_flags` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `web_search_mode_disabled_overrides_legacy_request` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `web_search_mode_for_turn_uses_preference_for_read_only` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `web_search_mode_for_turn_prefers_live_for_disabled_permissions` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `web_search_mode_for_turn_respects_disabled_for_disabled_permissions` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `web_search_mode_for_turn_falls_back_when_live_is_disallowed` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `project_profiles_are_ignored` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `unselected_profile_sandbox_mode_is_ignored` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `feature_table_overrides_legacy_flags` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `legacy_toggles_map_to_features` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `responses_websocket_features_do_not_change_wire_api` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_honors_explicit_file_oauth_store_mode` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `managed_config_overrides_oauth_store_mode` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_global_mcp_servers_returns_empty_if_missing` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_round_trips_entries` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `managed_config_wins_over_cli_overrides` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_global_mcp_servers_accepts_legacy_ms_field` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `mcp_servers_toml_parses_per_tool_approval_overrides` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `mcp_servers_toml_ignores_unknown_server_fields` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `mcp_servers_toml_parses_tool_approval_override_for_reserved_name` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `desktop_toml_round_trips_opaque_nested_values` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `to_mcp_config_preserves_apps_feature_from_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `to_mcp_config_flows_mcp_tool_prefix_from_feature` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `to_mcp_config_preserves_auth_elicitation_feature_from_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_global_mcp_servers_rejects_inline_bearer_token` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_serializes_env_sorted` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_serializes_env_vars` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_serializes_sourced_env_vars` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_serializes_cwd` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_streamable_http_serializes_bearer_token` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_streamable_http_serializes_custom_headers` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_streamable_http_removes_optional_sections` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_streamable_http_isolates_headers_between_servers` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_serializes_disabled_flag` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_serializes_required_flag` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_serializes_tool_filters` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `replace_mcp_servers_streamable_http_serializes_oauth_resource` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `set_model_updates_defaults` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `for_config_writes_selected_user_config_file` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `profile_v2_config_path_resolves_validated_names` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `set_model_overwrites_existing_model` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `cli_override_sets_compact_prompt` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `loads_compact_prompt_from_file` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_uses_requirements_guardian_policy_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_deserializes_auto_review_policy` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_uses_auto_review_guardian_policy_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `requirements_guardian_policy_beats_auto_review` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_ignores_empty_auto_review_guardian_policy_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_ignores_empty_requirements_guardian_policy_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_rejects_missing_agent_role_config_file` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `agent_role_relative_config_file_resolves_against_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `agent_role_relative_config_file_resolves_from_config_layer` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `agent_role_file_metadata_overrides_config_toml_metadata` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `agent_role_file_without_developer_instructions_is_dropped_with_warning` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `legacy_agent_role_config_file_allows_missing_developer_instructions` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `agent_role_without_description_after_merge_is_dropped_with_warning` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `discovered_agent_role_file_without_name_is_dropped_with_warning` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `agent_role_file_name_takes_precedence_over_config_key` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `loads_legacy_split_agent_roles_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `discovers_multiple_standalone_agent_role_files` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `mixed_legacy_and_standalone_agent_role_sources_merge_with_precedence` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `higher_precedence_agent_role_can_inherit_description_from_lower_layer` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_resolves_agent_interrupt_message` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_normalizes_agent_role_nickname_candidates` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_rejects_empty_agent_role_nickname_candidates` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_rejects_duplicate_agent_role_nickname_candidates` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_rejects_unsafe_agent_role_nickname_candidates` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `model_catalog_json_loads_from_path` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `model_catalog_json_rejects_empty_catalog` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `legacy_profile_selection_is_rejected` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `metrics_exporter_defaults_to_statsig_when_missing` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `trace_exporter_defaults_to_none_when_log_exporter_is_set` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_applies_otel_trace_metadata` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `load_config_drops_invalid_otel_trace_metadata_entries` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `explicit_null_service_tier_override_maps_to_default_service_tier` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `default_service_tier_override_uses_default_request_value` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `legacy_fast_service_tier_override_uses_priority_request_value` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_priority_service_tier_uses_priority_request_value` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_service_tier_accepts_arbitrary_string` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_legacy_fast_service_tier_uses_priority_request_value` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `fast_default_opt_out_notice_config_is_respected` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_requirements_web_search_mode_allowlist_does_not_warn_when_unset` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_set_project_trusted_writes_explicit_tables` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_set_project_trusted_converts_inline_to_explicit` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_set_project_trusted_migrates_top_level_inline_projects_preserving_entries` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `active_project_does_not_match_configured_alias_for_canonical_cwd` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_set_default_oss_provider` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_set_default_oss_provider_rejects_legacy_ollama_chat_provider` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_load_config_rejects_legacy_ollama_chat_provider_with_helpful_error` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_untrusted_project_gets_workspace_write_sandbox` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `derive_sandbox_policy_falls_back_to_read_only_for_implicit_defaults` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `derive_sandbox_policy_preserves_windows_downgrade_for_unsupported_fallback` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_resolve_oss_provider_explicit_override` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_resolve_oss_provider_from_global_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_resolve_oss_provider_none_when_not_configured` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_resolve_oss_provider_explicit_overrides_global` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_deserializes_mcp_oauth_callback_port` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_toml_deserializes_mcp_oauth_callback_url` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_loads_mcp_oauth_callback_port_from_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_loads_allow_login_shell_from_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_loads_apps_mcp_path_override_from_feature_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_defaults_enabled_apps_mcp_path_override_to_plugin_service` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_preserves_explicit_apps_mcp_path_override_path` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_loads_apps_mcp_product_sku_from_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `config_loads_mcp_oauth_callback_url_from_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_untrusted_project_gets_unless_trusted_approval_policy` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `requirements_disallowing_default_sandbox_falls_back_to_required_default` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `explicit_sandbox_mode_falls_back_when_disallowed_by_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `danger_full_access_with_never_is_rejected_when_requirements_force_read_only` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `named_full_access_profile_with_never_is_rejected_when_requirements_force_read_only` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permission_profile_override_falls_back_when_disallowed_by_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `active_profile_is_cleared_when_requirements_force_fallback` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `bypass_hook_trust_adds_startup_warning` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `permission_profile_override_preserves_split_write_roots` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `requirements_web_search_mode_overrides_danger_full_access_default` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `requirements_disallowing_default_approval_falls_back_to_required_default` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `explicit_approval_policy_falls_back_when_disallowed_by_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `feature_requirements_normalize_effective_feature_values` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `feature_requirements_auto_review_disables_guardian_approval` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `browser_feature_requirements_are_valid` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `debug_config_lockfile_export_settings_load_from_nested_table` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `debug_config_lockfile_load_path_loads_lock_from_nested_table` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `explicit_feature_config_is_normalized_by_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `approvals_reviewer_defaults_to_manual_only_without_guardian_feature` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `prompt_instruction_blocks_can_be_disabled_from_config` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `approvals_reviewer_stays_manual_only_when_guardian_feature_is_enabled` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `approvals_reviewer_can_be_set_in_config_without_guardian_approval` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `requirements_disallowing_default_approvals_reviewer_falls_back_to_required_default` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `root_approvals_reviewer_falls_back_when_disallowed_by_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `approvals_reviewer_preserves_valid_user_choice_when_allowed_by_requirements` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `smart_approvals_alias_is_ignored` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `multi_agent_v2_config_from_feature_table` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `multi_agent_v2_default_session_thread_cap_counts_root` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `multi_agent_v2_rejects_agents_max_threads` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `multi_agent_v2_rejects_invalid_wait_timeouts` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `multi_agent_v2_rejects_invalid_tool_namespace` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `multi_agent_v2_session_thread_cap_one_disallows_subagents` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `feature_requirements_normalize_runtime_feature_mutations` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `feature_requirements_warn_on_collab_legacy_alias` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `feature_requirements_warn_and_ignore_unknown_feature` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tool_suggest_discoverables_load_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tool_suggest_disabled_tools_load_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `tool_suggest_disabled_tools_merge_across_config_layers` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `experimental_realtime_start_instructions_load_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `experimental_thread_config_endpoint_loads_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `experimental_realtime_ws_base_url_loads_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `experimental_realtime_ws_backend_prompt_loads_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `experimental_realtime_ws_startup_context_loads_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `experimental_realtime_ws_model_loads_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `realtime_config_partial_table_uses_realtime_defaults` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `realtime_loads_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `realtime_audio_loads_from_config_toml` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_notifications_true` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_notifications_custom_array` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_notification_method` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_notification_condition_defaults_to_unfocused` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_notification_condition_always` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py
- `test_tui_notification_condition_rejects_unknown_value` -> tests/test_core_config.py, tests/test_core_config_root.py, tests/test_core_config_loader.py, tests/test_core_config_permissions.py, tests/test_core_config_otel.py, tests/test_protocol_config_types.py, tests/test_core_skill_config_rules.py, tests/test_config_overrides.py, tests/test_exec_config_plan.py, tests/test_core_network_proxy_loader.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v2_handler.py

#### `codex/codex-rs/core/src/config/edit_tests.rs`

- `blocking_set_model_top_level` -> todo
- `set_service_tier_saves_default_as_default` -> todo
- `set_service_tier_saves_priority_as_fast` -> todo
- `set_service_tier_preserves_unknown_service_tier` -> todo
- `builder_with_edits_applies_custom_paths` -> todo
- `session_picker_view_edit_writes_root_tui_setting` -> todo
- `keymap_binding_edit_writes_root_action_binding` -> todo
- `keymap_bindings_edit_writes_single_binding_as_string` -> todo
- `keymap_bindings_edit_writes_multiple_bindings_as_array` -> todo
- `keymap_binding_edit_replaces_existing_binding_without_touching_profile` -> todo
- `keymap_binding_clear_edit_removes_root_action_binding_without_touching_profile` -> todo
- `set_model_availability_nux_count_writes_shown_count` -> todo
- `set_skill_config_writes_disabled_entry` -> todo
- `set_skill_config_removes_entry_when_enabled` -> todo
- `set_skill_config_writes_name_selector_entry` -> todo
- `blocking_set_model_ignores_inline_legacy_profile_contents` -> todo
- `blocking_set_model_writes_through_symlink_chain` -> todo
- `blocking_set_model_replaces_symlink_on_cycle` -> todo
- `batch_write_table_upsert_preserves_inline_comments` -> todo
- `blocking_clear_model_does_not_follow_legacy_active_profile` -> todo
- `blocking_set_model_does_not_follow_legacy_active_profile` -> todo
- `blocking_set_hide_full_access_warning_preserves_table` -> todo
- `blocking_set_hide_rate_limit_model_nudge_preserves_table` -> todo
- `blocking_set_hide_gpt5_1_migration_prompt_preserves_table` -> todo
- `blocking_set_hide_gpt_5_1_codex_max_migration_prompt_preserves_table` -> todo
- `blocking_record_model_migration_seen_preserves_table` -> todo
- `blocking_set_hide_external_config_migration_prompt_home_preserves_table` -> todo
- `blocking_set_hide_external_config_migration_prompt_project_preserves_table` -> todo
- `blocking_set_external_config_migration_prompt_home_last_prompted_at_preserves_table` -> todo
- `blocking_set_external_config_migration_prompt_project_last_prompted_at_preserves_table` -> todo
- `blocking_replace_mcp_servers_round_trips` -> todo
- `blocking_replace_mcp_servers_serializes_tool_approval_overrides` -> todo
- `blocking_replace_mcp_servers_preserves_inline_comments` -> todo
- `blocking_replace_mcp_servers_preserves_inline_comment_suffix` -> todo
- `blocking_replace_mcp_servers_preserves_inline_comment_after_removing_keys` -> todo
- `blocking_replace_mcp_servers_preserves_inline_comment_prefix_on_update` -> todo
- `blocking_clear_path_noop_when_missing` -> todo
- `blocking_set_path_updates_notifications` -> todo
- `async_builder_set_model_persists` -> todo
- `blocking_builder_set_model_round_trips_back_and_forth` -> todo
- `blocking_set_asynchronous_helpers_available` -> todo
- `blocking_builder_set_realtime_audio_persists_and_clears` -> todo
- `blocking_builder_set_realtime_voice_persists_and_clears` -> todo
- `replace_mcp_servers_blocking_clears_table_when_empty` -> todo

#### `codex/codex-rs/core/src/config/network_proxy_spec_tests.rs`

- `build_state_with_audit_metadata_threads_metadata_to_state` -> todo
- `requirements_allowed_domains_are_a_baseline_for_user_allowlist` -> todo
- `requirements_allowed_domains_do_not_override_user_denies_for_same_pattern` -> todo
- `requirements_allowlist_expansion_keeps_user_entries_mutable` -> todo
- `managed_unrestricted_profile_allows_domain_expansion` -> todo
- `danger_full_access_keeps_managed_allowlist_and_denylist_fixed` -> todo
- `managed_allowed_domains_only_disables_default_mode_allowlist_expansion` -> todo
- `managed_allowed_domains_only_ignores_user_allowlist_and_hard_denies_misses` -> todo
- `managed_allowed_domains_only_without_managed_allowlist_blocks_all_user_domains` -> todo
- `managed_allowed_domains_only_blocks_all_user_domains_in_full_access_without_managed_list` -> todo
- `deny_only_requirements_do_not_create_allow_constraints_in_full_access` -> todo
- `allow_only_requirements_do_not_create_deny_constraints_in_full_access` -> todo
- `requirements_denied_domains_are_a_baseline_for_default_mode` -> todo
- `requirements_denylist_expansion_keeps_user_entries_mutable` -> todo

#### `codex/codex-rs/core/src/config/permissions_tests.rs`

- `normalize_absolute_path_for_platform_simplifies_windows_verbatim_paths` -> todo
- `windows_verbatim_path_prefix_does_not_count_as_glob_syntax` -> todo
- `restricted_read_implicitly_allows_helper_executables` -> todo
- `network_toml_ignores_legacy_network_list_keys` -> todo
- `network_permission_containers_project_allowed_and_denied_entries` -> todo
- `network_toml_overlays_unix_socket_permissions_by_path` -> todo
- `permissions_profiles_resolve_extends_parent_first_with_child_overrides` -> todo
- `permissions_profiles_reject_undefined_extends_parent` -> todo
- `permissions_profiles_reject_unsupported_builtin_extends_parent` -> todo
- `permissions_profiles_reject_extends_cycles` -> todo
- `profile_network_proxy_config_keeps_proxy_disabled_for_bare_network_access` -> todo
- `profile_network_proxy_config_keeps_proxy_disabled_for_proxy_policy` -> todo
- `compile_permission_profile_workspace_roots_resolves_enabled_entries` -> todo
- `read_write_glob_warnings_skip_supported_deny_read_globs_and_trailing_subpaths` -> todo
- `unreadable_globstar_warning_is_suppressed_when_scan_depth_is_configured` -> todo
- `glob_scan_max_depth_must_be_positive` -> todo
- `read_write_trailing_glob_suffix_compiles_as_subpath` -> todo
- `read_write_glob_patterns_still_reject_non_subpath_globs` -> todo

#### `codex/codex-rs/core/src/config/schema_tests.rs`

- `config_schema_matches_fixture` -> todo
- `config_schema_hides_unsupported_inline_mcp_bearer_token` -> todo

#### `codex/codex-rs/core/src/connectors_tests.rs`

- `accessible_connectors_from_mcp_tools_carries_plugin_display_names` -> todo
- `refresh_accessible_connectors_cache_from_mcp_tools_writes_latest_installed_apps` -> todo
- `accessible_connectors_from_mcp_tools_preserves_description` -> todo
- `app_tool_policy_uses_global_defaults_for_destructive_hints` -> todo
- `app_tool_policy_defaults_missing_destructive_hint_to_true` -> todo
- `app_tool_policy_defaults_missing_open_world_hint_to_true` -> todo
- `app_is_enabled_uses_default_for_unconfigured_apps` -> todo
- `app_is_enabled_prefers_per_app_override_over_default` -> todo
- `requirements_disabled_connector_overrides_enabled_connector` -> todo
- `requirements_enabled_does_not_override_disabled_connector` -> todo
- `cloud_requirements_disable_connector_overrides_user_apps_config` -> todo
- `cloud_requirements_disable_connector_applies_without_user_apps_table` -> todo
- `local_requirements_disable_connector_overrides_user_apps_config` -> todo
- `local_requirements_disable_connector_applies_without_user_apps_table` -> todo
- `with_app_enabled_state_preserves_unrelated_disabled_connector` -> todo
- `app_tool_policy_honors_default_app_enabled_false` -> todo
- `app_tool_policy_uses_managed_approval_without_apps_config` -> todo
- `managed_app_tool_approval_uses_raw_tool_name` -> todo
- `cloud_requirements_tool_approval_overrides_user_apps_config` -> todo
- `local_requirements_tool_approval_overrides_user_apps_config` -> todo
- `local_requirements_tool_approval_does_not_match_tool_title` -> todo
- `app_tool_policy_allows_per_app_enable_when_default_is_disabled` -> todo
- `app_tool_policy_per_tool_enabled_true_overrides_app_level_disable_flags` -> todo
- `app_tool_policy_default_tools_enabled_true_overrides_app_level_tool_hints` -> todo
- `app_tool_policy_default_tools_enabled_false_overrides_app_level_tool_hints` -> todo
- `app_tool_policy_uses_default_tools_approval_mode` -> todo
- `app_tool_policy_matches_prefix_stripped_tool_name_for_tool_config` -> todo
- `tool_suggest_connector_ids_include_configured_tool_suggest_discoverables` -> todo
- `tool_suggest_connector_ids_exclude_disabled_tool_suggestions` -> todo
- `tool_suggest_uses_connector_id_fallback_when_directory_cache_is_empty` -> todo

#### `codex/codex-rs/core/src/context/contextual_user_message_tests.rs`

- `detects_environment_context_fragment` -> todo
- `detects_agents_instructions_fragment` -> todo
- `detects_subagent_notification_fragment_case_insensitively` -> todo
- `detects_goal_context_fragment` -> todo
- `contextual_user_fragment_is_dyn_compatible` -> todo
- `ignores_regular_user_text` -> todo
- `detects_hook_prompt_fragment_and_roundtrips_escaping` -> todo

#### `codex/codex-rs/core/src/context/environment_context_tests.rs`

- `serialize_workspace_write_environment_context` -> todo
- `serialize_environment_context_with_network` -> todo
- `serialize_read_only_environment_context` -> todo
- `equals_except_shell_compares_cwd` -> todo
- `equals_except_shell_compares_cwd_differences` -> todo
- `equals_except_shell_ignores_shell` -> todo
- `serialize_environment_context_with_subagents` -> todo
- `serialize_environment_context_with_multiple_selected_environments` -> todo
- `serialize_environment_context_prefers_environment_shell_when_present` -> todo

#### `codex/codex-rs/core/src/context/permissions_instructions_tests.rs`

- `renders_sandbox_mode_text` -> todo
- `builds_permissions_with_network_access_override` -> todo
- `builds_permissions_from_profile` -> todo
- `includes_request_rule_instructions_for_on_request` -> todo
- `includes_request_permissions_tool_instructions_for_unless_trusted_when_enabled` -> todo
- `includes_request_permissions_tool_instructions_for_on_failure_when_enabled` -> todo
- `includes_request_permission_rule_instructions_for_on_request_when_enabled` -> todo
- `includes_request_permissions_tool_instructions_for_on_request_when_tool_is_enabled` -> todo
- `on_request_includes_tool_guidance_alongside_inline_permission_guidance_when_both_exist` -> todo
- `auto_review_approvals_append_auto_review_specific_guidance` -> todo
- `auto_review_approvals_omit_auto_review_specific_guidance_when_approval_is_never` -> todo
- `granular_policy_lists_prompted_and_rejected_categories_separately` -> todo
- `granular_policy_includes_command_permission_instructions_when_sandbox_approval_can_prompt` -> todo
- `granular_policy_omits_shell_permission_instructions_when_inline_requests_are_disabled` -> todo
- `granular_policy_includes_request_permissions_tool_only_when_that_prompt_can_still_fire` -> todo
- `granular_policy_lists_request_permissions_category_without_tool_section_when_tool_unavailable` -> todo

#### `codex/codex-rs/core/src/context_manager/history_tests.rs`

- `filters_non_api_messages` -> todo
- `non_last_reasoning_tokens_return_zero_when_no_user_messages` -> todo
- `non_last_reasoning_tokens_ignore_entries_after_last_user` -> todo
- `items_after_last_model_generated_tokens_include_user_and_tool_output` -> todo
- `items_after_last_model_generated_tokens_are_zero_without_model_generated_items` -> todo
- `inter_agent_assistant_messages_are_turn_boundaries` -> todo
- `for_prompt_preserves_inter_agent_assistant_messages` -> todo
- `drop_last_n_user_turns_treats_inter_agent_assistant_messages_as_instruction_turns` -> todo
- `legacy_inter_agent_assistant_messages_are_not_turn_boundaries` -> todo
- `total_token_usage_includes_all_items_after_last_model_generated_item` -> todo
- `for_prompt_strips_images_when_model_does_not_support_images` -> todo
- `for_prompt_preserves_image_generation_calls_when_images_are_supported` -> todo
- `for_prompt_clears_image_generation_result_when_images_are_unsupported` -> todo
- `estimate_token_count_with_base_instructions_uses_provided_text` -> todo
- `remove_first_item_removes_matching_output_for_function_call` -> todo
- `remove_first_item_removes_matching_call_for_output` -> todo
- `remove_last_item_removes_matching_call_for_output` -> todo
- `replace_last_turn_images_replaces_tool_output_images` -> todo
- `replace_last_turn_images_does_not_touch_user_images` -> todo
- `remove_first_item_handles_local_shell_pair` -> todo
- `drop_last_n_user_turns_preserves_prefix` -> todo
- `drop_last_n_user_turns_ignores_session_prefix_user_messages` -> todo
- `drop_last_n_user_turns_trims_context_updates_above_rolled_back_turn` -> todo
- `drop_last_n_user_turns_clears_reference_context_for_mixed_developer_context_bundles` -> todo
- `remove_first_item_handles_custom_tool_pair` -> todo
- `normalization_retains_local_shell_outputs` -> todo
- `record_items_truncates_function_call_output_content` -> todo
- `record_items_truncates_custom_tool_call_output_content` -> todo
- `record_items_respects_custom_token_limit` -> todo
- `format_exec_output_truncates_large_error` -> todo
- `format_exec_output_marks_byte_truncation_without_omitted_lines` -> todo
- `format_exec_output_returns_original_when_within_limits` -> todo
- `format_exec_output_reports_omitted_lines_and_keeps_head_and_tail` -> todo
- `format_exec_output_prefers_line_marker_when_both_limits_exceeded` -> todo
- `normalize_adds_missing_output_for_function_call` -> todo
- `normalize_adds_missing_output_for_custom_tool_call` -> todo
- `normalize_adds_missing_output_for_local_shell_call_with_id` -> todo
- `normalize_removes_orphan_function_call_output` -> todo
- `normalize_removes_orphan_custom_tool_call_output` -> todo
- `normalize_mixed_inserts_and_removals` -> todo
- `normalize_adds_missing_output_for_function_call_inserts_output` -> todo
- `normalize_adds_missing_output_for_tool_search_call` -> todo
- `normalize_adds_missing_output_for_custom_tool_call_panics_in_debug` -> todo
- `normalize_adds_missing_output_for_local_shell_call_with_id_panics_in_debug` -> todo
- `normalize_removes_orphan_function_call_output_panics_in_debug` -> todo
- `normalize_removes_orphan_custom_tool_call_output_panics_in_debug` -> todo
- `normalize_removes_orphan_client_tool_search_output` -> todo
- `normalize_removes_orphan_client_tool_search_output_panics_in_debug` -> todo
- `normalize_keeps_server_tool_search_output_without_matching_call` -> todo
- `normalize_mixed_inserts_and_removals_panics_in_debug` -> todo
- `image_data_url_payload_does_not_dominate_message_estimate` -> todo
- `image_data_url_payload_does_not_dominate_function_call_output_estimate` -> todo
- `image_data_url_payload_does_not_dominate_custom_tool_call_output_estimate` -> todo
- `non_base64_image_urls_are_unchanged` -> todo
- `encrypted_function_output_uses_plaintext_byte_estimate` -> todo
- `data_url_without_base64_marker_is_unchanged` -> todo
- `non_image_base64_data_url_is_unchanged` -> todo
- `mixed_case_data_url_markers_are_adjusted` -> todo
- `multiple_inline_images_apply_multiple_fixed_costs` -> todo
- `original_detail_images_scale_with_dimensions` -> todo
- `original_detail_images_are_capped_at_max_patch_count` -> todo
- `original_detail_webp_images_scale_with_dimensions` -> todo
- `text_only_items_unchanged` -> todo

#### `codex/codex-rs/core/src/event_mapping_tests.rs`

- `parses_user_message_with_text_and_two_images` -> todo
- `skips_local_image_label_text` -> todo
- `parses_assistant_message_input_text_for_backward_compatibility` -> todo
- `skips_unnamed_image_label_text` -> todo
- `skips_user_instructions_and_env` -> todo
- `parses_hook_prompt_message_as_distinct_turn_item` -> todo
- `parses_hook_prompt_and_hides_other_contextual_fragments` -> todo
- `goal_context_does_not_parse_as_visible_turn_item` -> todo
- `parses_agent_message` -> todo
- `parses_reasoning_summary_and_raw_content` -> todo
- `parses_reasoning_including_raw_content` -> todo
- `parses_web_search_call` -> todo
- `parses_web_search_open_page_call` -> todo
- `parses_web_search_find_in_page_call` -> todo
- `parses_partial_web_search_call_without_action_as_other` -> todo

#### `codex/codex-rs/core/src/exec_env_tests.rs`

- `test_core_inherit_defaults_keep_sensitive_vars` -> todo
- `test_core_inherit_with_default_excludes_enabled` -> todo
- `test_include_only` -> todo
- `test_set_overrides` -> todo
- `populate_env_inserts_thread_id` -> todo
- `populate_env_omits_thread_id_when_missing` -> todo
- `test_inherit_all` -> todo
- `test_inherit_all_with_default_excludes` -> todo
- `test_core_inherit_respects_case_insensitive_names_on_windows` -> todo
- `create_env_inserts_pathext_on_windows_when_missing` -> todo
- `create_env_preserves_existing_pathext_case_insensitively_on_windows` -> todo
- `test_inherit_none` -> todo

#### `codex/codex-rs/core/src/exec_policy_tests.rs`

- `child_uses_parent_exec_policy_when_layer_stack_matches` -> todo
- `child_uses_parent_exec_policy_when_non_exec_policy_layers_differ` -> todo
- `child_does_not_use_parent_exec_policy_when_ignore_rules_differs` -> todo
- `child_does_not_use_parent_exec_policy_when_requirements_exec_policy_differs` -> todo
- `returns_empty_policy_when_no_policy_files_exist` -> todo
- `rules_path_file_returns_read_dir_error` -> todo
- `collect_policy_files_returns_empty_when_dir_missing` -> todo
- `format_exec_policy_error_with_source_renders_range` -> todo
- `parse_starlark_line_from_message_extracts_path_and_line` -> todo
- `parse_starlark_line_from_message_rejects_zero_line` -> todo
- `loads_policies_from_policy_subdirectory` -> todo
- `merges_requirements_exec_policy_network_rules` -> todo
- `preserves_host_executables_when_requirements_overlay_is_present` -> todo
- `ignores_policies_outside_policy_dir` -> todo
- `ignores_policy_files_when_config_stack_disables_exec_policy_rules` -> todo
- `ignore_user_project_rules_keeps_system_policy_files` -> todo
- `ignores_rules_from_untrusted_project_layers` -> todo
- `loads_policies_from_multiple_config_layers` -> todo
- `evaluates_bash_lc_inner_commands` -> todo
- `commands_for_exec_policy_falls_back_for_empty_shell_script` -> todo
- `commands_for_exec_policy_falls_back_for_whitespace_shell_script` -> todo
- `ignore_user_config_keeps_user_policy_files` -> todo
- `evaluates_heredoc_script_against_prefix_rules` -> todo
- `omits_auto_amendment_for_heredoc_fallback_prompts` -> todo
- `drops_requested_amendment_for_heredoc_fallback_prompts_when_it_wont_match` -> todo
- `drops_requested_amendment_for_heredoc_fallback_prompts_when_it_matches` -> todo
- `heredoc_with_variable_assignment_is_not_reduced_to_allowed_prefix` -> todo
- `heredoc_redirect_without_escalation_runs_inside_sandbox` -> todo
- `heredoc_redirect_with_escalation_requires_approval` -> todo
- `justification_is_included_in_forbidden_exec_approval_requirement` -> todo
- `exec_approval_requirement_prefers_execpolicy_match` -> todo
- `absolute_path_exec_approval_requirement_matches_host_executable_rules` -> todo
- `absolute_path_exec_approval_requirement_ignores_disallowed_host_executable_paths` -> todo
- `requested_prefix_rule_can_approve_absolute_path_commands` -> todo
- `exec_approval_requirement_respects_approval_policy` -> todo
- `unmatched_granular_policy_still_prompts_for_restricted_sandbox_escalation` -> todo
- `unmatched_on_request_uses_split_filesystem_policy_for_escalation_prompts` -> todo
- `known_safe_on_request_still_prompts_for_restricted_sandbox_escalation` -> todo
- `managed_cwd_write_profile_is_not_read_only` -> todo
- `managed_unresolvable_write_profile_is_still_read_only` -> todo
- `exec_approval_requirement_prompts_for_inline_additional_permissions_under_on_request` -> todo
- `exec_approval_requirement_prompts_for_known_safe_escalation_under_on_request` -> todo
- `exec_approval_requirement_rejects_known_safe_escalation_when_granular_sandbox_is_disabled` -> todo
- `exec_approval_requirement_rejects_unmatched_sandbox_escalation_when_granular_sandbox_is_disabled` -> todo
- `mixed_rule_and_sandbox_prompt_prioritizes_rule_for_rejection_decision` -> todo
- `mixed_rule_and_sandbox_prompt_rejects_when_granular_rules_are_disabled` -> todo
- `exec_approval_requirement_falls_back_to_heuristics` -> todo
- `empty_bash_lc_script_falls_back_to_original_command` -> todo
- `whitespace_bash_lc_script_falls_back_to_original_command` -> todo
- `request_rule_uses_prefix_rule` -> todo
- `request_rule_falls_back_when_prefix_rule_does_not_approve_all_commands` -> todo
- `heuristics_apply_when_other_commands_match_policy` -> todo
- `append_execpolicy_amendment_updates_policy_and_file` -> todo
- `append_execpolicy_amendment_rejects_empty_prefix` -> todo
- `proposed_execpolicy_amendment_is_present_for_single_command_without_policy_match` -> todo
- `proposed_execpolicy_amendment_is_omitted_when_policy_prompts` -> todo
- `proposed_execpolicy_amendment_is_present_for_multi_command_scripts` -> todo
- `proposed_execpolicy_amendment_uses_first_no_match_in_multi_command_scripts` -> todo
- `proposed_execpolicy_amendment_is_present_when_heuristics_allow` -> todo
- `proposed_execpolicy_amendment_is_suppressed_when_policy_matches_allow` -> todo
- `multi_segment_shell_requires_policy_allow_for_every_segment_to_bypass_sandbox` -> todo
- `multi_segment_shell_bypasses_sandbox_when_every_segment_matches_policy_allow` -> todo
- `derive_requested_execpolicy_amendment_returns_none_for_missing_prefix_rule` -> todo
- `derive_requested_execpolicy_amendment_returns_none_for_empty_prefix_rule` -> todo
- `derive_requested_execpolicy_amendment_returns_none_for_exact_banned_prefix_rule` -> todo
- `derive_requested_execpolicy_amendment_returns_none_for_windows_and_pypy_variants` -> todo
- `derive_requested_execpolicy_amendment_returns_none_for_shell_and_powershell_variants` -> todo
- `derive_requested_execpolicy_amendment_allows_non_exact_banned_prefix_rule_match` -> todo
- `derive_requested_execpolicy_amendment_returns_none_when_policy_matches` -> todo
- `dangerous_rm_rf_requires_approval_in_danger_full_access` -> todo
- `verify_approval_requirement_for_unsafe_powershell_command` -> todo
- `dangerous_command_allowed_when_sandbox_is_explicitly_disabled` -> todo
- `dangerous_command_forbidden_in_external_sandbox_when_policy_matches` -> todo
- `exec_policies_only_load_from_trusted_project_layers` -> todo
- `exec_policies_require_project_trust_without_config_toml` -> todo
- `exec_policy_warnings_ignore_untrusted_project_rules_without_config_toml` -> todo

#### `codex/codex-rs/core/src/exec_policy_windows_tests.rs`

- `evaluates_powershell_inner_commands_against_prompt_rules` -> tests/test_core_exec_policy.py
- `evaluates_powershell_inner_commands_against_allow_rules` -> tests/test_core_exec_policy.py
- `commands_for_exec_policy_parses_powershell_shell_wrapper` -> tests/test_core_exec_policy.py
- `unmatched_safe_powershell_words_are_allowed` -> tests/test_core_exec_policy.py
- `unmatched_dangerous_powershell_inner_commands_require_approval` -> tests/test_core_exec_policy.py

#### `codex/codex-rs/core/src/exec_tests.rs`

- `sandbox_detection_requires_keywords` -> todo
- `sandbox_detection_identifies_keyword_in_stderr` -> todo
- `sandbox_detection_respects_quick_reject_exit_codes` -> todo
- `sandbox_detection_ignores_non_sandbox_mode` -> todo
- `sandbox_detection_ignores_network_policy_text_in_non_sandbox_mode` -> todo
- `sandbox_detection_uses_aggregated_output` -> todo
- `sandbox_detection_ignores_network_policy_text_with_zero_exit_code` -> todo
- `read_output_limits_retained_bytes_for_shell_capture` -> todo
- `aggregate_output_prefers_stderr_on_contention` -> todo
- `aggregate_output_fills_remaining_capacity_with_stderr` -> todo
- `aggregate_output_rebalances_when_stderr_is_small` -> todo
- `aggregate_output_keeps_stdout_then_stderr_when_under_cap` -> todo
- `read_output_retains_all_bytes_for_full_buffer_capture` -> todo
- `aggregate_output_keeps_all_bytes_when_uncapped` -> todo
- `full_buffer_capture_policy_disables_caps_and_exec_expiration` -> todo
- `exec_full_buffer_capture_ignores_expiration` -> todo
- `exec_full_buffer_capture_keeps_io_drain_timeout_when_descendant_holds_pipe_open` -> todo
- `process_exec_tool_call_preserves_full_buffer_capture_policy` -> todo
- `windows_restricted_token_skips_external_sandbox_policies` -> todo
- `windows_restricted_token_runs_for_legacy_restricted_policies` -> todo
- `windows_proxy_enforcement_uses_elevated_backend` -> todo
- `windows_restricted_token_rejects_network_only_restrictions` -> todo
- `windows_restricted_token_allows_legacy_restricted_policies` -> todo
- `windows_restricted_token_allows_legacy_workspace_write_policies` -> todo
- `windows_elevated_allows_split_restricted_read_policies` -> todo
- `windows_restricted_token_rejects_split_only_filesystem_policies` -> todo
- `windows_restricted_token_rejects_root_write_read_only_carveouts` -> todo
- `windows_restricted_token_supports_full_read_split_write_read_carveouts` -> todo
- `windows_restricted_token_rejects_unreadable_split_carveouts` -> todo
- `windows_elevated_supports_split_restricted_read_roots` -> todo
- `windows_elevated_supports_split_write_read_carveouts` -> todo
- `windows_elevated_supports_unreadable_split_carveouts` -> todo
- `windows_elevated_supports_unreadable_globs` -> todo
- `windows_elevated_rejects_reopened_writable_descendants` -> todo
- `process_exec_tool_call_uses_platform_sandbox_for_network_only_restrictions` -> todo
- `sandbox_detection_flags_sigsys_exit_code` -> todo
- `kill_child_process_group_kills_grandchildren_on_timeout` -> todo
- `process_exec_tool_call_respects_cancellation_token` -> todo
- `process_exec_tool_call_cancellation_allows_sigterm_cleanup` -> todo

#### `codex/codex-rs/core/src/git_info_tests.rs`

- `test_recent_commits_non_git_directory_returns_empty` -> todo
- `test_recent_commits_orders_and_limits` -> todo
- `test_collect_git_info_non_git_directory` -> todo
- `test_collect_git_info_git_repository` -> todo
- `test_collect_git_info_with_remote` -> todo
- `test_collect_git_info_detached_head` -> todo
- `test_collect_git_info_with_branch` -> todo
- `test_get_has_changes_non_git_directory_returns_none` -> todo
- `test_get_has_changes_clean_repo_returns_false` -> todo
- `test_get_has_changes_with_tracked_change_returns_true` -> todo
- `test_get_has_changes_with_untracked_change_returns_true` -> todo
- `test_get_has_changes_ignores_repo_fsmonitor_config` -> todo
- `test_get_has_changes_ignores_configured_hooks_path` -> todo
- `test_get_git_working_tree_state_clean_repo` -> todo
- `test_get_git_working_tree_state_with_changes` -> todo
- `test_get_git_working_tree_state_branch_fallback` -> todo
- `resolve_root_git_project_for_trust_returns_none_outside_repo` -> todo
- `get_git_repo_root_with_fs_detects_gitdir_pointer` -> todo
- `resolve_root_git_project_for_trust_regular_repo_returns_repo_root` -> todo
- `resolve_root_git_project_for_trust_detects_worktree_and_returns_main_root` -> todo
- `resolve_root_git_project_for_trust_detects_worktree_pointer_without_git_command` -> todo
- `resolve_root_git_project_for_trust_non_worktrees_gitdir_returns_none` -> todo
- `test_get_git_working_tree_state_unpushed_commit` -> todo
- `test_git_info_serialization` -> todo
- `test_git_info_serialization_with_nones` -> todo

#### `codex/codex-rs/core/src/guardian/tests.rs`

- `guardian_rejection_circuit_breaker_interrupts_after_three_consecutive_denials` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_rejection_circuit_breaker_resets_consecutive_denials_on_non_denial` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `auto_review_rejection_circuit_breaker_interrupts_after_ten_recent_denials` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `auto_review_rejection_circuit_breaker_forgets_denials_outside_recent_review_window` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_transcript_keeps_original_numbering` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_prompt_full_mode_preserves_initial_review_format` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_prompt_delta_mode_preserves_original_numbering` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_prompt_delta_mode_handles_empty_delta` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_prompt_stale_delta_cursor_falls_back_to_full_prompt` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_prompt_stale_delta_version_falls_back_to_full_prompt` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `collect_guardian_transcript_entries_skips_contextual_user_messages` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `collect_guardian_transcript_entries_keeps_manual_approval_developer_message` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `collect_guardian_transcript_entries_includes_recent_tool_calls_and_output` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_truncate_text_keeps_prefix_suffix_and_xml_marker` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `format_guardian_action_pretty_truncates_large_string_fields` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `format_guardian_action_pretty_reports_no_truncation_for_small_payload` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_approval_request_to_json_renders_mcp_tool_call_shape` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_approval_request_to_json_renders_network_access_trigger` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_prompt_items_explains_network_access_review_scope` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_assessment_action_redacts_apply_patch_patch_text` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_request_turn_id_prefers_network_access_owner_turn` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_request_target_item_id_omits_network_access_trigger_call_id` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `cancelled_guardian_review_emits_terminal_abort_without_warning` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_timeout_message_distinguishes_timeout_from_policy_denial` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `routes_approval_to_guardian_requires_guardian_reviewer` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `routes_approval_to_guardian_allows_granular_review_policy` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_transcript_reserves_separate_budget_for_tool_evidence` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_transcript_preserves_recent_tool_context_when_user_history_is_large` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `parse_guardian_assessment_extracts_embedded_json` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `parse_guardian_assessment_treats_bare_allow_as_low_risk` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `parse_guardian_assessment_treats_bare_deny_as_high_risk` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_output_schema_requires_only_outcome_and_allows_optional_details` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_request_layout_matches_model_visible_request_snapshot` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `build_guardian_prompt_items_includes_parent_session_id` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_reuses_prompt_cache_key_and_appends_prior_reviews` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_reused_trunk_ignores_stale_prior_turn_completion` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_surfaces_responses_api_errors_in_rejection_reason` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_parallel_reviews_fork_from_last_committed_trunk_history` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_preserves_parent_network_proxy` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_clears_parent_developer_instructions` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_clears_legacy_notify` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_uses_live_network_proxy_state` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_disables_mcp_apps_and_plugins` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_allows_pinned_disabled_feature` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_uses_parent_active_model_instead_of_hardcoded_slug` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_keeps_bedrock_provider_for_bedrock_gpt_5_4` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_uses_requirements_guardian_policy_config` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py
- `guardian_review_session_config_uses_default_guardian_policy_without_requirements_override` -> tests/test_core_guardian_root.py, tests/test_core_guardian_prompt.py, tests/test_core_guardian_approval_request.py, tests/test_core_guardian_review.py, tests/test_core_guardian_tests.py

#### `codex/codex-rs/core/src/mcp_tool_call_tests.rs`

- `execute_mcp_tool_call_records_replayable_correlation` -> todo
- `mcp_app_resource_uri_reads_known_tool_meta_keys` -> todo
- `openai_file_params_are_only_honored_for_codex_apps` -> todo
- `approval_required_when_read_only_false_and_destructive` -> todo
- `approval_required_when_read_only_false_and_open_world` -> todo
- `approval_required_when_destructive_even_if_read_only_true` -> todo
- `approval_required_when_annotations_are_absent` -> todo
- `approval_not_required_when_read_only_and_other_hints_are_absent` -> todo
- `prompt_mode_does_not_allow_persistent_remember` -> todo
- `mcp_tool_call_span_records_expected_fields` -> todo
- `mcp_result_telemetry_records_allowlisted_span_fields` -> todo
- `mcp_result_telemetry_ignores_invalid_and_missing_values` -> todo
- `mcp_result_telemetry_truncates_long_target_id` -> todo
- `truncates_strings_on_char_boundaries` -> todo
- `approval_elicitation_request_uses_message_override_and_preserves_tool_params_keys` -> todo
- `custom_mcp_tool_question_mentions_server_name` -> todo
- `codex_apps_tool_question_uses_fallback_app_label` -> todo
- `trusted_codex_apps_tool_question_offers_always_allow` -> todo
- `codex_apps_tool_question_without_elicitation_omits_always_allow` -> todo
- `custom_mcp_tool_question_offers_session_remember_and_always_allow` -> todo
- `custom_servers_support_session_and_persistent_approval` -> todo
- `codex_apps_connectors_support_persistent_approval` -> todo
- `sanitize_mcp_tool_result_for_model_rewrites_image_content` -> todo
- `sanitize_mcp_tool_result_for_model_preserves_image_when_supported` -> todo
- `truncate_mcp_tool_result_for_event_preserves_small_result` -> todo
- `truncate_mcp_tool_result_for_event_bounds_large_result` -> todo
- `truncate_mcp_tool_result_for_event_bounds_large_error` -> todo
- `mcp_tool_call_request_meta_includes_turn_metadata_for_custom_server` -> todo
- `mcp_tool_call_request_meta_includes_turn_started_at_unix_ms` -> todo
- `plugin_mcp_tool_call_request_meta_includes_plugin_id` -> todo
- `mcp_tool_call_item_includes_plugin_id` -> todo
- `codex_apps_tool_call_request_meta_includes_turn_metadata_and_codex_apps_meta` -> todo
- `codex_apps_tool_call_request_meta_includes_call_id_without_existing_codex_apps_meta` -> todo
- `codex_apps_auth_elicitation_feature_disabled_returns_original_result` -> todo
- `codex_apps_auth_elicitation_non_host_owned_server_returns_original_result` -> todo
- `codex_apps_auth_elicitation_disallowed_by_policy_returns_original_result` -> todo
- `codex_apps_auth_elicitation_granular_mcp_disabled_returns_original_result` -> todo
- `codex_apps_auth_elicitation_feature_enabled_requests_elicitation` -> todo
- `mcp_tool_call_thread_id_meta_is_added_to_request_meta` -> todo
- `accepted_elicitation_content_converts_to_request_user_input_response` -> todo
- `approval_elicitation_meta_marks_tool_approvals` -> todo
- `approval_elicitation_meta_merges_session_and_always_persist_for_custom_servers` -> todo
- `guardian_mcp_review_request_includes_invocation_metadata` -> todo
- `guardian_mcp_review_request_includes_annotations_when_present` -> todo
- `guardian_review_decision_maps_to_mcp_tool_decision` -> todo
- `approval_elicitation_meta_includes_connector_source_for_codex_apps` -> todo
- `approval_elicitation_meta_merges_session_and_always_persist_with_connector_source` -> todo
- `declined_elicitation_response_stays_decline` -> todo
- `synthetic_decline_request_user_input_response_stays_decline` -> todo
- `accepted_elicitation_response_uses_always_persist_meta` -> todo
- `accepted_elicitation_response_uses_session_persist_meta` -> todo
- `accepted_elicitation_without_content_defaults_to_accept` -> todo
- `persist_codex_app_tool_approval_writes_tool_override` -> todo
- `persist_custom_mcp_tool_approval_writes_tool_override` -> todo
- `custom_mcp_tool_approval_mode_uses_server_default_with_tool_override` -> todo
- `custom_mcp_tool_approval_mode_uses_plugin_mcp_policy` -> todo
- `custom_mcp_tool_approval_mode_uses_updated_plugin_mcp_policy_after_cache_warm` -> todo
- `maybe_persist_mcp_tool_approval_reloads_session_config` -> todo
- `maybe_persist_mcp_tool_approval_reloads_session_config_for_custom_server` -> todo
- `maybe_persist_mcp_tool_approval_writes_plugin_mcp_policy` -> todo
- `maybe_persist_mcp_tool_approval_writes_project_config_for_project_server` -> todo
- `approve_mode_skips_when_annotations_do_not_require_approval` -> todo
- `guardian_mode_skips_auto_when_annotations_do_not_require_approval` -> todo
- `permission_request_hook_allows_mcp_tool_call` -> todo
- `permission_request_hook_uses_hook_tool_name_without_metadata` -> todo
- `permission_request_hook_runs_after_remembered_mcp_approval` -> todo
- `guardian_mode_mcp_denial_returns_rationale_message` -> todo
- `prompt_mode_waits_for_approval_when_annotations_do_not_require_approval` -> todo
- `full_access_mode_skips_mcp_tool_approval_for_all_approval_modes` -> todo
- `approve_mode_skips_guardian_in_every_permission_mode` -> todo

#### `codex/codex-rs/core/src/mcp_tool_exposure_test.rs`

- `directly_exposes_small_effective_tool_sets` -> todo
- `searches_large_effective_tool_sets` -> todo
- `always_defer_feature_defers_apps_too` -> todo

#### `codex/codex-rs/core/src/network_policy_decision_tests.rs`

- `network_approval_context_requires_ask_from_decider` -> todo
- `network_approval_context_maps_http_https_and_socks_protocols` -> todo
- `network_policy_decision_payload_deserializes_proxy_protocol_aliases` -> todo
- `execpolicy_network_rule_amendment_maps_protocol_action_and_justification` -> todo
- `denied_network_policy_message_requires_deny_decision` -> todo
- `denied_network_policy_message_for_denylist_block_is_explicit` -> todo

#### `codex/codex-rs/core/src/network_proxy_loader_tests.rs`

- `higher_precedence_profile_network_overlays_domain_entries` -> todo
- `higher_precedence_profile_network_overrides_matching_domain_entries` -> todo
- `higher_precedence_profile_network_overrides_named_mitm_actions` -> todo
- `execpolicy_network_rules_overlay_network_lists` -> todo
- `apply_network_constraints_includes_allow_all_unix_sockets_flag` -> todo
- `selected_network_from_tables_ignores_builtin_profile_without_permissions_table` -> todo
- `selected_network_from_tables_rejects_unknown_builtin_profile_without_permissions_table` -> todo
- `selected_network_from_tables_resolves_builtin_workspace_parent` -> todo
- `selected_network_from_tables_resolves_permission_profile_inheritance` -> todo
- `config_from_layers_resolves_inherited_profiles_across_layers` -> todo
- `config_from_layers_normalizes_profile_network_domains_before_merging_layers` -> todo
- `config_from_layers_uses_only_the_final_selected_profile_network` -> todo
- `trusted_constraints_use_only_the_final_selected_profile_network` -> todo
- `trusted_constraints_normalize_profile_network_domains_before_merging_layers` -> todo
- `apply_network_constraints_skips_empty_domain_sides` -> todo
- `apply_network_constraints_overlay_domain_entries` -> todo

#### `codex/codex-rs/core/src/personality_migration_tests.rs`

- `applies_when_sessions_exist_and_no_personality` -> todo
- `applies_when_only_archived_sessions_exist_and_no_personality` -> todo
- `skips_when_marker_exists` -> todo
- `skips_when_personality_explicit` -> todo
- `skips_when_no_sessions` -> todo

#### `codex/codex-rs/core/src/plugins/discoverable_tests.rs`

- `list_tool_suggest_discoverable_plugins_returns_uninstalled_curated_plugins` -> todo
- `list_tool_suggest_discoverable_plugins_returns_microsoft_curated_plugins` -> todo
- `list_tool_suggest_discoverable_plugins_deduplicates_allowlisted_configured_plugin` -> todo
- `list_tool_suggest_discoverable_plugins_ignores_missing_allowlisted_plugin` -> todo
- `list_tool_suggest_discoverable_plugins_returns_empty_when_plugins_feature_disabled` -> todo
- `list_tool_suggest_discoverable_plugins_normalizes_description` -> todo
- `list_tool_suggest_discoverable_plugins_omits_installed_curated_plugins` -> todo
- `list_tool_suggest_discoverable_plugins_omits_disabled_tool_suggestions` -> todo
- `list_tool_suggest_discoverable_plugins_includes_configured_plugin_ids` -> todo
- `list_tool_suggest_discoverable_plugins_does_not_reload_marketplace_per_plugin` -> todo

#### `codex/codex-rs/core/src/plugins/mentions_tests.rs`

- `collect_explicit_app_ids_from_linked_text_mentions` -> todo
- `collect_explicit_app_ids_dedupes_structured_and_linked_mentions` -> todo
- `collect_explicit_app_ids_ignores_non_app_paths` -> todo
- `collect_explicit_plugin_mentions_from_structured_paths` -> todo
- `collect_explicit_plugin_mentions_from_linked_text_mentions` -> todo
- `collect_explicit_plugin_mentions_dedupes_structured_and_linked_mentions` -> todo
- `collect_explicit_plugin_mentions_ignores_non_plugin_paths` -> todo
- `collect_explicit_plugin_mentions_ignores_dollar_linked_plugin_mentions` -> todo

#### `codex/codex-rs/core/src/plugins/render_tests.rs`

- `render_plugins_section_returns_none_for_empty_plugins` -> todo
- `render_plugins_section_includes_descriptions_and_skill_naming_guidance` -> todo

#### `codex/codex-rs/core/src/realtime_context_tests.rs`

- `current_thread_section_includes_short_turns_newest_first_until_budget` -> todo
- `current_thread_turn_truncation_preserves_start_and_end` -> todo
- `current_thread_section_keeps_latest_turns_when_history_exceeds_budget` -> todo
- `startup_context_blob_is_wrapped_in_tags_without_final_truncation` -> todo
- `fixed_section_budgets_apply_per_section_without_total_blob_truncation` -> todo
- `workspace_section_requires_meaningful_structure` -> todo
- `workspace_section_includes_tree_when_entries_exist` -> todo
- `workspace_section_includes_user_root_tree_when_distinct` -> todo
- `recent_work_section_groups_threads_by_cwd` -> todo

#### `codex/codex-rs/core/src/realtime_conversation_tests.rs`

- `prefers_handoff_input_transcript_over_active_transcript` -> todo
- `extracts_text_from_handoff_request_active_transcript_if_input_missing` -> todo
- `wraps_handoff_with_transcript_delta` -> todo
- `extracts_text_from_handoff_request_input_transcript_if_messages_missing` -> todo
- `ignores_empty_handoff_request_input_transcript` -> todo
- `wraps_realtime_delegation_input` -> todo
- `wraps_realtime_delegation_input_with_xml_escaping` -> todo
- `wraps_realtime_delegation_input_with_xml_escaping_without_transcript` -> todo
- `clears_active_handoff_explicitly` -> todo
- `uses_quicksilver_alpha_header_for_realtime_v1` -> todo
- `omits_quicksilver_alpha_header_for_realtime_v2` -> todo

#### `codex/codex-rs/core/src/safety_tests.rs`

- `test_writable_roots_constraint` -> todo
- `external_sandbox_auto_approves_in_on_request` -> todo
- `granular_with_all_flags_true_matches_on_request_for_out_of_root_patch` -> todo
- `granular_sandbox_approval_false_rejects_out_of_root_patch` -> todo
- `read_only_policy_rejects_patch_with_read_only_reason` -> todo
- `explicit_unreadable_paths_prevent_auto_approval_for_external_sandbox` -> todo
- `explicit_read_only_subpaths_prevent_auto_approval_for_external_sandbox` -> todo
- `missing_project_dot_codex_config_requires_approval` -> todo

#### `codex/codex-rs/core/src/sandbox_tags_tests.rs`

- `danger_full_access_is_untagged_even_when_linux_sandbox_defaults_apply` -> todo
- `external_sandbox_keeps_external_tag_when_linux_sandbox_defaults_apply` -> todo
- `default_linux_sandbox_uses_platform_sandbox_tag` -> todo
- `profile_sandbox_tag_distinguishes_disabled_from_external` -> todo
- `unrestricted_managed_profile_with_enabled_network_is_untagged` -> todo
- `root_write_managed_profile_with_enabled_network_is_untagged` -> todo
- `managed_network_enforcement_tags_unrestricted_profiles_as_sandboxed` -> todo
- `profile_policy_tag_reports_closest_legacy_mode` -> todo

#### `codex/codex-rs/core/src/session/mcp_tests.rs`

- `guardian_elicitation_review_request_builds_mcp_tool_call` -> todo
- `guardian_elicitation_review_request_defaults_missing_tool_params` -> todo
- `plugin_install_elicitation_telemetry_metadata_requires_install_tool_suggestion` -> todo
- `guardian_elicitation_review_request_requires_opt_in` -> todo
- `guardian_elicitation_review_request_declines_unsupported_opt_in_shapes` -> todo
- `guardian_decisions_map_to_elicitation_responses_without_session_state` -> todo

#### `codex/codex-rs/core/src/session/rollout_reconstruction_tests.rs`

- `record_initial_history_resumed_bare_turn_context_does_not_hydrate_previous_turn_settings` -> todo
- `record_initial_history_resumed_hydrates_previous_turn_settings_from_lifecycle_turn_with_missing_turn_context_id` -> todo
- `reconstruct_history_rollback_keeps_history_and_metadata_in_sync_for_completed_turns` -> todo
- `reconstruct_history_rollback_keeps_history_and_metadata_in_sync_for_incomplete_turn` -> todo
- `reconstruct_history_rollback_skips_non_user_turns_for_history_and_metadata` -> todo
- `reconstruct_history_rollback_counts_inter_agent_assistant_turns` -> todo
- `reconstruct_history_rollback_clears_history_and_metadata_when_exceeding_user_turns` -> todo
- `record_initial_history_resumed_rollback_skips_only_user_turns` -> todo
- `record_initial_history_resumed_rollback_drops_incomplete_user_turn_compaction_metadata` -> todo
- `record_initial_history_resumed_bare_turn_context_does_not_seed_reference_context_item` -> todo
- `record_initial_history_resumed_does_not_seed_reference_context_item_after_compaction` -> todo
- `reconstruct_history_legacy_compaction_without_replacement_history_does_not_inject_current_initial_context` -> todo
- `reconstruct_history_legacy_compaction_without_replacement_history_clears_later_reference_context_item` -> todo
- `record_initial_history_resumed_turn_context_after_compaction_reestablishes_reference_context_item` -> todo
- `record_initial_history_resumed_aborted_turn_without_id_clears_active_turn_for_compaction_accounting` -> todo
- `record_initial_history_resumed_unmatched_abort_preserves_active_turn_for_later_turn_context` -> todo
- `record_initial_history_resumed_trailing_incomplete_turn_compaction_clears_reference_context_item` -> todo
- `record_initial_history_resumed_trailing_incomplete_turn_preserves_turn_context_item` -> todo
- `record_initial_history_resumed_replaced_incomplete_compacted_turn_clears_reference_context_item` -> todo

#### `codex/codex-rs/core/src/session/tests/guardian_tests.rs`

- `request_permissions_routes_to_guardian_when_reviewer_is_enabled` -> todo
- `request_permissions_guardian_review_stops_when_cancelled` -> todo
- `guardian_allows_shell_command_additional_permissions_requests_past_policy_validation` -> todo
- `strict_auto_review_turn_grant_forces_guardian_for_shell_command_policy_skip` -> todo
- `guardian_allows_unified_exec_additional_permissions_requests_past_policy_validation` -> todo
- `process_compacted_history_preserves_separate_guardian_developer_message` -> todo
- `shell_command_allows_sticky_turn_permissions_without_inline_request_permissions_feature` -> todo
- `guardian_subagent_does_not_inherit_parent_exec_policy_rules` -> todo

#### `codex/codex-rs/core/src/session/tests.rs`

- `regular_turn_emits_turn_started_with_trace_id_without_waiting_for_startup_prewarm` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `request_mcp_server_elicitation_auto_accepts_when_auto_deny_is_enabled` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `interrupting_regular_turn_waiting_on_startup_prewarm_emits_turn_aborted` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `assistant_message_stream_parsers_can_be_seeded_from_output_item_added_text` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `assistant_message_stream_parsers_seed_buffered_prefix_stays_out_of_finish_tail` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `assistant_message_stream_parsers_seed_plan_parser_across_added_and_delta_boundaries` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `validated_network_policy_amendment_host_allows_normalized_match` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `validated_network_policy_amendment_host_rejects_mismatch` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `start_managed_network_proxy_applies_execpolicy_network_rules` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `start_managed_network_proxy_ignores_invalid_execpolicy_network_rules` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `managed_network_proxy_decider_survives_full_access_start` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `new_turn_refreshes_managed_network_proxy_for_sandbox_change` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `danger_full_access_turns_do_not_expose_managed_network_proxy` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `danger_full_access_tool_attempts_do_not_enforce_managed_network` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `workspace_write_turns_continue_to_expose_managed_network_proxy` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `user_shell_commands_do_not_inherit_managed_network_proxy` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `get_base_instructions_no_user_content` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `reload_user_config_layer_updates_effective_apps_config` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `reload_user_config_layer_updates_base_and_selected_profile_layers` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `reload_user_config_layer_refreshes_hooks` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `refresh_runtime_config_refreshes_hooks` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `reload_user_config_layer_updates_effective_tool_suggest_config` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `refresh_runtime_config_updates_runtime_refreshable_fields_and_keeps_session_static_settings` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `collect_explicit_app_ids_from_skill_items_includes_linked_mentions` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `collect_explicit_app_ids_from_skill_items_resolves_unambiguous_plain_mentions` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `collect_explicit_app_ids_from_skill_items_skips_plain_mentions_with_skill_conflicts` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `reconstruct_history_matches_live_compactions` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `reconstruct_history_uses_replacement_history_verbatim` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_initial_history_reconstructs_resumed_transcript` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_initial_history_new_defers_initial_context_until_first_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `resumed_history_injects_initial_context_on_first_context_update_only` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_initial_history_seeds_token_info_from_rollout` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `recompute_token_usage_uses_session_base_instructions` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `recompute_token_usage_updates_model_context_window` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_token_usage_info_notifies_extension_contributors` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `turn_start_lifecycle_exposes_turn_metadata_and_token_baseline` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `turn_error_lifecycle_exposes_error_and_stores` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `config_change_contributor_observes_effective_config_changes` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_initial_history_reconstructs_forked_transcript` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_configured_reports_permission_profile_for_external_sandbox` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_permission_profile_rebinds_runtime_workspace_roots` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `fork_startup_context_then_first_turn_diff_snapshot` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_initial_history_forked_hydrates_previous_turn_settings` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `thread_rollback_drops_last_turn_from_history` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `thread_rollback_clears_history_when_num_turns_exceeds_existing_turns` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `thread_rollback_fails_without_persisted_thread_history` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `thread_rollback_recomputes_previous_turn_settings_and_reference_context_from_replay` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `thread_rollback_restores_cleared_reference_context_item_after_compaction` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `thread_rollback_persists_marker_and_replays_cumulatively` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `thread_rollback_fails_when_turn_in_progress` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `thread_rollback_fails_when_num_turns_is_zero` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `set_rate_limits_retains_previous_credits` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `set_rate_limits_updates_plan_type_when_present` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `prefers_structured_content_when_present` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `includes_timed_out_message` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `turn_context_with_model_updates_model_fields` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `falls_back_to_content_when_structured_is_null` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `success_flag_reflects_is_error_true` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `success_flag_true_with_no_error_and_content_used` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `get_service_tier_does_not_use_model_default_when_absent_and_fast_mode_enabled` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `get_service_tier_does_not_use_model_default_when_fast_mode_disabled` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `get_service_tier_keeps_supported_explicit_tier` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `get_service_tier_does_not_default_when_model_has_no_default` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `get_service_tier_drops_unsupported_configured_tier_when_fast_mode_enabled` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `get_service_tier_ignores_configured_tier_when_fast_mode_disabled` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_settings_null_service_tier_update_uses_default_service_tier` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_settings_legacy_fast_service_tier_update_uses_priority_request_value` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_configuration_apply_preserves_profile_file_system_policy_on_cwd_only_update` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_configuration_apply_permission_profile_preserves_existing_deny_read_entries` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_configuration_apply_permission_profile_accepts_direct_write_roots` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_configuration_apply_rebinds_symbolic_profile_to_updated_workspace_roots` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_configuration_apply_retargets_implicit_workspace_root_on_cwd_update` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `active_profile_update_rebuilds_network_proxy_config` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `new_default_turn_uses_config_aware_skills_for_role_overrides` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_configuration_apply_retargets_legacy_workspace_root_on_cwd_update` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_configuration_apply_preserves_absolute_cwd_write_root_on_cwd_update` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_update_settings_does_not_rewrite_sticky_environment_cwds` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `relative_cwd_update_without_environments_resolves_under_session_cwd` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `cwd_update_does_not_rewrite_sticky_environment_cwd` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `absolute_cwd_update_with_turn_environment_is_allowed` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_new_fails_when_zsh_fork_enabled_without_packaged_zsh` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `resumed_root_session_uses_thread_id_as_session_id` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `resumed_subagent_session_keeps_inherited_session_id` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `notify_request_permissions_response_ignores_unmatched_call_id` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_granted_request_permissions_for_turn_uses_originating_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `enable_strict_auto_review_for_turn_uses_originating_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `strict_auto_review_session_scope_grants_no_permissions` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `request_permissions_emits_event_when_granular_policy_allows_requests` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `request_permissions_response_materializes_session_cwd_grants_before_recording` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `request_permissions_is_auto_denied_when_granular_policy_blocks_tool_requests` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `submit_with_id_captures_current_span_trace_context` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `new_default_turn_captures_current_span_trace_id` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `submission_dispatch_span_prefers_submission_trace_context` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `submission_dispatch_span_uses_debug_for_realtime_audio` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `op_kind_for_input_and_context_ops` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `user_turn_updates_approvals_reviewer` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `turn_environments_set_primary_environment` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `default_turn_overlays_session_cwd_onto_stored_thread_environments` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `default_turn_honors_empty_stored_thread_environments` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `primary_environment_uses_first_turn_environment` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `empty_turn_environments_clear_primary_environment` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `unknown_turn_environment_returns_error` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `duplicate_turn_environment_returns_error_without_mutating_session` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `spawn_task_turn_span_inherits_dispatch_trace_context` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `shutdown_complete_does_not_append_to_thread_store_after_shutdown` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `submission_loop_channel_close_emits_thread_stop_lifecycle` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `submission_loop_channel_close_aborts_active_turn_before_thread_stop_lifecycle` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `shutdown_and_wait_allows_multiple_waiters` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `shutdown_and_wait_waits_when_shutdown_is_already_in_progress` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `shutdown_and_wait_shuts_down_cached_guardian_subagent` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `cached_guardian_subagent_exposes_its_rollout_path` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `shutdown_and_wait_shuts_down_tracked_ephemeral_guardian_review` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `refresh_mcp_servers_is_deferred_until_next_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `spawn_task_does_not_update_previous_turn_settings_for_non_run_turn_tasks` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_settings_update_items_emits_environment_item_for_network_changes` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `environment_context_uses_session_shell_when_environment_shell_is_absent` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_settings_update_items_emits_environment_item_for_time_changes` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_settings_update_items_omits_environment_item_when_disabled` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_settings_update_items_emits_realtime_start_when_session_becomes_live` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_settings_update_items_emits_realtime_end_when_session_stops_being_live` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_settings_update_items_uses_previous_turn_settings_for_realtime_end` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_uses_previous_realtime_state` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_includes_prompt_fragments_from_extensions` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_omits_prompt_fragments_without_extension_state` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_adds_multi_agent_v2_root_usage_hint_as_developer_message` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_adds_multi_agent_v2_subagent_usage_hint_as_developer_message` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_omits_multi_agent_v2_usage_hints_when_feature_disabled` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_omits_default_image_save_location_with_image_history` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_omits_default_image_save_location_without_image_history` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_trims_skill_metadata_from_context_window_budget` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `emit_thread_start_skill_metrics_records_enabled_kept_and_truncated_values` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `emit_thread_start_skill_metrics_records_description_truncated_chars_without_omitted_skills` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_emits_thread_start_skill_warning_on_repeated_builds` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `handle_output_item_done_records_image_save_history_message` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `handle_output_item_done_skips_image_save_message_when_save_fails` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_uses_previous_turn_settings_for_realtime_end` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_restates_realtime_start_when_reference_context_is_missing` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `turn_context_item_omits_legacy_equivalent_file_system_sandbox_policy` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `turn_context_item_stores_split_file_system_sandbox_policy_when_different` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_context_updates_and_set_reference_context_item_injects_full_context_when_baseline_missing` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_context_updates_and_set_reference_context_item_reinjects_full_context_after_clear` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_context_updates_and_set_reference_context_item_persists_baseline_without_emitting_diffs` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_context_updates_and_set_reference_context_item_persists_split_file_system_policy_to_rollout` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `build_initial_context_prepends_model_switch_message` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `record_context_updates_and_set_reference_context_item_persists_full_reinjection_to_rollout` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `run_user_shell_command_does_not_set_reference_context_item` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `realtime_conversation_list_voices_emits_builtin_list` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `guardian_auto_review_interrupts_after_three_consecutive_denials` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `guardian_helper_review_interrupts_after_three_consecutive_denials` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `abort_regular_task_emits_marker_before_turn_aborted` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `abort_gracefully_emits_marker_before_turn_aborted` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `task_finish_emits_turn_item_lifecycle_for_leftover_pending_user_input` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `steer_input_requires_active_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `steer_input_enforces_expected_turn_id` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `steer_input_rejects_non_regular_turns` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `steer_input_returns_active_turn_id` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `abort_empty_active_turn_preserves_pending_input` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `interrupt_accounts_active_goal_without_pausing` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `shutdown_without_active_turn_keeps_active_goal_active` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `active_goal_continuation_runs_again_after_no_tool_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `pending_request_user_input_does_not_spawn_extra_goal_continuation` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `create_thread_goal_fills_empty_thread_preview` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `budget_limited_accounting_steers_active_turn_without_aborting` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `usage_limit_runtime_stops_active_goal_and_prevents_idle_continuation` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `external_goal_mutation_accounts_active_turn_before_status_change` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `external_objective_change_steers_active_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `external_active_goal_set_marks_current_turn_for_accounting` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `completed_goal_accounts_current_turn_tokens_before_tool_response` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `queue_only_mailbox_mail_waits_for_next_turn_after_answer_boundary` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `trigger_turn_mailbox_mail_waits_for_next_turn_after_answer_boundary` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `steered_input_reopens_mailbox_delivery_for_current_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `stale_defer_mailbox_delivery_does_not_override_steered_input` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `tool_calls_reopen_mailbox_delivery_for_current_turn` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `abort_review_task_emits_exited_then_aborted_and_records_history` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `fatal_tool_error_stops_turn_and_reports_error` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `create_goal_tool_rejects_existing_goal` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `update_goal_tool_rejects_pausing_goal` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `update_goal_tool_marks_goal_blocked` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `update_goal_tool_rejects_usage_limited_goal` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `update_goal_tool_marks_goal_complete` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `rejects_escalated_permissions_when_policy_not_on_request` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `shell_tool_cancellation_waits_for_runtime_cleanup` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `unified_exec_rejects_escalated_permissions_when_policy_not_on_request` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_start_hooks_only_load_from_trusted_project_layers` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`
- `session_start_hooks_require_project_trust_without_config_toml` -> `tests/test_core_session_tests.py`, `tests/test_core_session_runtime.py`, `tests/test_core_session_handlers.py`, `tests/test_core_session_input_queue.py`, `tests/test_core_session_request_permissions.py`, `tests/test_core_session_guardian.py`, `tests/test_core_session_review.py`, `tests/test_core_session_rollout_reconstruction.py`, `tests/test_core_session_multi_agents.py`, `tests/test_core_goals.py`, `tests/test_core_client.py`, `tests/test_core_network_proxy_loader.py`, `tests/test_core_context_network_rule_saved.py`, `tests/test_core_state_session.py`, `tests/test_exec_session.py`

#### `codex/codex-rs/core/src/session/turn_tests.rs`

- `plan_mode_uses_contributed_turn_item_for_last_agent_message` -> `tests/test_core_client.py::test_plan_mode_uses_contributed_turn_item_for_last_agent_message`

#### `codex/codex-rs/core/src/shell_snapshot_tests.rs`

- `strip_snapshot_preamble_removes_leading_output` -> todo
- `strip_snapshot_preamble_requires_marker` -> todo
- `snapshot_file_name_parser_supports_legacy_and_suffixed_names` -> todo
- `bash_snapshot_filters_invalid_exports` -> todo
- `bash_snapshot_preserves_multiline_exports` -> todo
- `try_new_creates_and_deletes_snapshot_file` -> todo
- `try_new_uses_distinct_generation_paths` -> todo
- `snapshot_shell_does_not_inherit_stdin` -> todo
- `timed_out_snapshot_shell_is_terminated` -> todo
- `macos_zsh_snapshot_includes_sections` -> todo
- `linux_bash_snapshot_includes_sections` -> todo
- `linux_sh_snapshot_includes_sections` -> todo
- `windows_powershell_snapshot_includes_sections` -> todo
- `cleanup_stale_snapshots_removes_orphans_and_keeps_live` -> todo
- `cleanup_stale_snapshots_removes_stale_rollouts` -> todo
- `cleanup_stale_snapshots_skips_active_session` -> todo

#### `codex/codex-rs/core/src/shell_tests.rs`

- `detects_zsh` -> todo
- `fish_fallback_to_zsh` -> todo
- `detects_bash` -> todo
- `detects_sh` -> todo
- `can_run_on_shell_test` -> todo
- `derive_exec_args` -> todo
- `test_current_shell_detects_zsh` -> todo
- `detects_powershell_as_default` -> todo
- `finds_powershell` -> todo

#### `codex/codex-rs/core/src/state/session_tests.rs`

- `merge_connector_selection_deduplicates_entries` -> todo
- `clear_connector_selection_removes_entries` -> todo
- `set_rate_limits_defaults_limit_id_to_codex_when_missing` -> todo
- `replace_history_clears_auto_compact_window_prefill_without_advancing` -> todo
- `set_rate_limits_defaults_to_codex_when_limit_id_missing_after_other_bucket` -> todo
- `set_rate_limits_carries_credits_and_plan_type_from_codex_to_codex_other` -> todo

#### `codex/codex-rs/core/src/stream_events_utils_tests.rs`

- `external_context_pollution_items_include_web_search_and_tool_search` -> todo
- `external_context_pollution_items_exclude_local_tool_calls` -> todo
- `handle_non_tool_response_item_strips_citations_from_assistant_message` -> todo
- `handle_non_tool_response_item_runs_turn_item_contributors_only_when_requested` -> todo
- `handle_output_item_done_returns_contributed_last_agent_message` -> todo
- `finalized_turn_item_defers_mailbox_for_contributed_visible_text` -> todo
- `finalized_turn_item_keeps_mailbox_open_for_commentary_text` -> todo
- `last_assistant_message_from_item_strips_citations_and_plan_blocks` -> todo
- `last_assistant_message_from_item_returns_none_for_citation_only_message` -> todo
- `last_assistant_message_from_item_returns_none_for_plan_only_hidden_message` -> todo
- `completed_item_defers_mailbox_delivery_for_unknown_phase_messages` -> todo
- `completed_item_keeps_mailbox_delivery_open_for_commentary_messages` -> todo
- `completed_item_defers_mailbox_delivery_for_image_generation_calls` -> todo
- `save_image_generation_result_saves_base64_to_png_in_codex_home` -> todo
- `save_image_generation_result_rejects_data_url_payload` -> todo
- `save_image_generation_result_overwrites_existing_file` -> todo
- `save_image_generation_result_sanitizes_call_id_for_codex_home_output_path` -> todo
- `save_image_generation_result_rejects_non_standard_base64` -> todo
- `save_image_generation_result_rejects_non_base64_data_urls` -> todo

#### `codex/codex-rs/core/src/tasks/mod_tests.rs`

- `emit_turn_network_proxy_metric_records_active_turn` -> todo
- `emit_turn_network_proxy_metric_records_inactive_turn` -> todo
- `emit_turn_memory_metric_records_read_allowed_with_citations` -> todo
- `emit_turn_memory_metric_records_config_disabled_without_citations` -> todo
- `emit_compact_metric_records_manual_remote_v2` -> todo
- `emit_compact_metric_records_auto_local` -> todo

#### `codex/codex-rs/core/src/thread_manager_tests.rs`

- `truncates_before_requested_user_message` -> todo
- `out_of_range_truncation_drops_only_unfinished_suffix_mid_turn` -> todo
- `fork_thread_accepts_legacy_usize_snapshot_argument` -> todo
- `out_of_range_truncation_drops_pre_user_active_turn_prefix` -> todo
- `ignores_session_prefix_messages_when_truncating` -> todo
- `shutdown_all_threads_bounded_submits_shutdown_to_every_thread` -> todo
- `start_thread_rejects_explicit_local_environment_when_default_provider_is_disabled` -> todo
- `start_thread_uses_all_default_environments_from_codex_home` -> todo
- `start_thread_keeps_internal_threads_hidden_from_normal_lookups` -> todo
- `resume_and_fork_do_not_restore_thread_environments_from_rollout` -> todo
- `explicit_installation_id_skips_codex_home_file` -> todo
- `resume_active_thread_from_rollout_returns_running_thread` -> todo
- `resume_stopped_thread_from_rollout_spawns_new_thread` -> todo
- `resume_stopped_thread_from_rollout_preserves_thread_source` -> todo
- `rollout_path_resume_and_fork_read_history_through_thread_store` -> todo
- `new_uses_active_provider_for_model_refresh` -> todo
- `interrupted_fork_snapshot_appends_interrupt_boundary` -> todo
- `disabled_interrupted_fork_snapshot_appends_only_interrupt_event` -> todo
- `interrupted_snapshot_is_not_mid_turn` -> todo
- `multi_agent_v2_interrupted_marker_uses_developer_input_message` -> todo
- `completed_legacy_event_history_is_not_mid_turn` -> todo
- `mixed_response_and_legacy_user_event_history_is_mid_turn` -> todo
- `interrupted_fork_snapshot_does_not_synthesize_turn_id_for_legacy_history` -> todo
- `interrupted_fork_snapshot_preserves_explicit_turn_id` -> todo
- `interrupted_fork_snapshot_uses_persisted_mid_turn_history_without_live_source` -> todo
- `resumed_thread_keeps_paused_goal_paused` -> todo

#### `codex/codex-rs/core/src/thread_rollout_truncation_tests.rs`

- `truncates_rollout_from_start_before_nth_user_only` -> todo
- `truncation_max_keeps_full_rollout` -> todo
- `truncates_rollout_from_start_applies_thread_rollback_markers` -> todo
- `ignores_session_prefix_messages_when_truncating_rollout_from_start` -> todo
- `truncates_rollout_to_last_n_fork_turns_counts_trigger_turn_messages` -> todo
- `truncates_rollout_to_last_n_fork_turns_drops_startup_prefix_even_when_under_limit` -> todo
- `truncates_rollout_to_last_n_fork_turns_applies_thread_rollback_markers` -> todo
- `fork_turn_positions_ignore_zero_turn_rollback_markers` -> todo
- `truncates_rollout_to_last_n_fork_turns_discards_trigger_boundaries_in_rolled_back_suffix` -> todo
- `truncates_rollout_to_last_n_fork_turns_discards_rolled_back_assistant_instruction_turns` -> todo
- `truncates_rollout_to_last_n_fork_turns_keeps_full_rollout_when_n_is_large` -> todo

#### `codex/codex-rs/core/src/tools/context_tests.rs`

- `custom_tool_calls_should_roundtrip_as_custom_outputs` -> todo
- `function_payloads_remain_function_outputs` -> todo
- `mcp_code_mode_result_serializes_full_call_tool_result` -> todo
- `mcp_tool_output_response_item_includes_wall_time` -> todo
- `mcp_tool_output_response_item_truncates_large_structured_content` -> todo
- `mcp_tool_output_response_item_preserves_content_items` -> todo
- `mcp_tool_output_code_mode_result_stays_raw_call_tool_result` -> todo
- `custom_tool_calls_can_derive_text_from_content_items` -> todo
- `tool_search_payloads_roundtrip_as_tool_search_outputs` -> todo
- `log_preview_uses_content_items_when_plain_text_is_missing` -> todo
- `telemetry_preview_returns_original_within_limits` -> todo
- `telemetry_preview_truncates_by_bytes` -> todo
- `telemetry_preview_truncates_by_lines` -> todo
- `exec_command_tool_output_formats_truncated_response` -> todo

#### `codex/codex-rs/core/src/tools/handlers/agent_jobs_spec_tests.rs`

- `spawn_agents_on_csv_tool_requires_csv_and_instruction` -> todo
- `report_agent_job_result_tool_requires_result_payload` -> todo

#### `codex/codex-rs/core/src/tools/handlers/agent_jobs_tests.rs`

- `parse_csv_supports_quotes_and_commas` -> todo
- `csv_escape_quotes_when_needed` -> todo
- `render_instruction_template_expands_placeholders_and_escapes_braces` -> todo
- `render_instruction_template_leaves_unknown_placeholders` -> todo
- `ensure_unique_headers_rejects_duplicates` -> todo

#### `codex/codex-rs/core/src/tools/handlers/apply_patch_spec_tests.rs`

- `create_apply_patch_freeform_tool_matches_expected_spec` -> todo
- `create_apply_patch_freeform_tool_includes_environment_id_when_requested` -> todo

#### `codex/codex-rs/core/src/tools/handlers/apply_patch_tests.rs`

- `pre_tool_use_payload_uses_freeform_patch_input` -> todo
- `post_tool_use_payload_uses_patch_input_and_tool_output` -> todo
- `diff_consumer_streams_apply_patch_changes` -> todo
- `diff_consumer_streams_apply_patch_changes_with_environment_header` -> todo
- `diff_consumer_sends_next_update_after_buffer_interval` -> todo
- `reconcile_environment_id_requires_selection_when_enabled` -> todo
- `approval_keys_include_move_destination` -> todo
- `write_permissions_for_paths_skip_dirs_already_writable_under_workspace_root` -> todo
- `write_permissions_for_paths_keep_dirs_outside_workspace_root` -> todo

#### `codex/codex-rs/core/src/tools/handlers/dynamic_tests.rs`

- `search_info_uses_dynamic_tool_metadata_and_parameter_names` -> todo

#### `codex/codex-rs/core/src/tools/handlers/mcp_resource_spec_tests.rs`

- `list_mcp_resources_tool_matches_expected_spec` -> todo
- `list_mcp_resource_templates_tool_matches_expected_spec` -> todo
- `read_mcp_resource_tool_matches_expected_spec` -> todo

#### `codex/codex-rs/core/src/tools/handlers/mcp_resource_tests.rs`

- `resource_with_server_serializes_server_field` -> todo
- `list_resources_payload_from_single_server_copies_next_cursor` -> todo
- `list_resources_payload_from_all_servers_is_sorted` -> todo
- `call_tool_result_from_content_marks_success` -> todo
- `parse_arguments_handles_empty_and_json` -> todo
- `template_with_server_serializes_server_field` -> todo

#### `codex/codex-rs/core/src/tools/handlers/mcp_search_tests.rs`

- `search_info_uses_mcp_tool_metadata_and_parameter_names` -> todo
- `search_info_uses_connector_name_for_output_namespace_description` -> todo

#### `codex/codex-rs/core/src/tools/handlers/multi_agents_spec_tests.rs`

- `spawn_agent_tool_v2_requires_task_name_and_lists_visible_models` -> todo
- `spawn_agent_tool_v1_keeps_legacy_fork_context_field` -> todo
- `spawn_agent_tool_caps_visible_model_summaries` -> todo
- `spawn_agent_tool_hides_service_tier_with_spawn_metadata` -> todo
- `send_message_tool_requires_message_and_has_no_output_schema` -> todo
- `followup_task_tool_requires_message_and_has_no_output_schema` -> todo
- `wait_agent_tool_v2_uses_timeout_only_summary_output` -> todo
- `list_agents_tool_includes_path_prefix_and_agent_fields` -> todo
- `list_agents_tool_status_schema_includes_interrupted` -> todo

#### `codex/codex-rs/core/src/tools/handlers/multi_agents_tests.rs`

- `handler_rejects_non_function_payloads` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_rejects_empty_message` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_rejects_when_message_and_items_are_both_set` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_uses_explorer_role_and_preserves_approval_policy` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_fork_context_rejects_agent_type_override` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_fork_context_rejects_child_model_overrides` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_fork_turns_all_rejects_agent_type_override` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_defaults_to_full_fork_and_rejects_child_model_overrides` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_service_tier_override_validates_the_effective_child_model` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_service_tier_inheritance_preserves_supported_or_configured_tiers` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_role_service_tier_falls_back_to_supported_parent_tier` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_role_service_tier_does_not_hide_invalid_spawn_request` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_full_history_fork_accepts_explicit_service_tier` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_full_history_fork_accepts_explicit_service_tier` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_partial_fork_turns_allows_agent_type_override` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_returns_agent_id_without_task_name` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_requires_task_name` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_rejects_legacy_items_field` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_errors_when_manager_dropped` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_returns_path_and_send_message_accepts_relative_path` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_rejects_legacy_fork_context` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_rejects_invalid_fork_turns_string` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_rejects_zero_fork_turns` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_send_message_accepts_root_target_from_child` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_followup_task_rejects_root_target_from_child` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_list_agents_returns_completed_status_and_last_task_message` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_list_agents_filters_by_relative_path_prefix` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_list_agents_omits_closed_agents` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_send_message_rejects_legacy_items_field` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_send_message_rejects_interrupt_parameter` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_followup_task_completion_notifies_parent_on_every_turn` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_followup_task_rejects_legacy_items_field` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_interrupted_turn_does_not_notify_parent` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_omits_agent_id_when_named` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_surfaces_task_name_validation_errors` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_reapplies_runtime_sandbox_after_role_config` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_rejects_when_depth_limit_exceeded` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `spawn_agent_allows_depth_up_to_configured_max_depth` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_spawn_agent_ignores_configured_max_depth` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `send_input_rejects_empty_message` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `send_input_rejects_when_message_and_items_are_both_set` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `send_input_rejects_invalid_id` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `send_input_reports_missing_agent` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `send_input_interrupts_before_prompt` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `send_input_accepts_structured_items` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `resume_agent_rejects_invalid_id` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `resume_agent_reports_missing_agent` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `resume_agent_noops_for_active_agent` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `resume_agent_restores_closed_agent_and_accepts_send_input` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `resume_agent_rejects_when_depth_limit_exceeded` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `wait_agent_rejects_non_positive_timeout` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `wait_agent_rejects_invalid_target` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `wait_agent_rejects_empty_targets` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_accepts_timeout_only_argument` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_rejects_timeout_below_configured_min` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_accepts_explicit_timeout_at_configured_min` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_uses_configured_default_timeout` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_allows_zero_configured_timeout` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_rejects_timeout_above_configured_max` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_accepts_explicit_timeout_at_configured_max` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `wait_agent_returns_not_found_for_missing_agents` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `wait_agent_times_out_when_status_is_not_final` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `wait_agent_clamps_short_timeouts_to_minimum` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `wait_agent_returns_final_status_without_timeout` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_returns_summary_for_mailbox_activity` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_returns_for_already_queued_mail` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_wakes_on_any_mailbox_notification` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_wait_agent_does_not_return_completed_content` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_close_agent_accepts_task_name_target` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `multi_agent_v2_close_agent_rejects_root_target_and_id` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `close_agent_submits_shutdown_and_returns_previous_status` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `tool_handlers_cascade_close_and_resume_and_keep_explicitly_closed_subtrees_closed` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `build_agent_spawn_config_uses_turn_context_values` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `build_agent_spawn_config_preserves_base_user_instructions` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py
- `build_agent_resume_config_clears_base_instructions` -> tests/test_core_multi_agents_common.py, tests/test_core_multi_agents_spec.py, tests/test_core_multi_agents_v1_handler.py, tests/test_core_multi_agents_v2_handler.py, tests/test_core_session_multi_agents.py

#### `codex/codex-rs/core/src/tools/handlers/request_plugin_install_tests.rs`

- `verified_plugin_install_completed_requires_installed_plugin` -> todo
- `request_plugin_install_response_persists_only_decline_always_mode` -> todo
- `persist_disabled_install_request_writes_connector_config` -> todo
- `persist_disabled_install_request_writes_plugin_config` -> todo
- `persist_disabled_install_request_dedupes_existing_disabled_tools` -> todo

#### `codex/codex-rs/core/src/tools/handlers/request_user_input_spec_tests.rs`

- `request_user_input_tool_includes_questions_schema` -> todo
- `request_user_input_unavailable_messages_respect_default_mode_feature_flag` -> todo
- `request_user_input_tool_description_mentions_available_modes` -> todo

#### `codex/codex-rs/core/src/tools/handlers/request_user_input_tests.rs`

- `multi_agent_v2_request_user_input_rejects_subagent_threads` -> todo

#### `codex/codex-rs/core/src/tools/handlers/shell_spec_tests.rs`

- `exec_command_tool_matches_expected_spec` -> todo
- `write_stdin_tool_matches_expected_spec` -> todo
- `request_permissions_tool_includes_full_permission_schema` -> todo
- `shell_command_tool_matches_expected_spec` -> todo

#### `codex/codex-rs/core/src/tools/handlers/shell_tests.rs`

- `commands_generated_by_shell_command_handler_can_be_matched_by_is_known_safe_command` -> todo
- `shell_command_handler_to_exec_params_uses_session_shell_and_turn_context` -> todo
- `shell_command_handler_respects_explicit_login_flag` -> todo
- `shell_command_handler_defaults_to_non_login_when_disallowed` -> todo
- `shell_command_handler_rejects_login_when_disallowed` -> todo
- `shell_command_pre_tool_use_payload_uses_raw_command` -> todo
- `build_post_tool_use_payload_uses_tool_output_wire_value` -> todo

#### `codex/codex-rs/core/src/tools/handlers/test_sync_spec_tests.rs`

- `test_sync_tool_matches_expected_spec` -> todo

#### `codex/codex-rs/core/src/tools/handlers/unified_exec_tests.rs`

- `test_get_command_uses_default_shell_when_unspecified` -> todo
- `test_get_command_respects_explicit_bash_shell` -> todo
- `test_get_command_respects_explicit_powershell_shell` -> todo
- `test_get_command_respects_explicit_cmd_shell` -> todo
- `test_get_command_rejects_explicit_login_when_disallowed` -> todo
- `test_get_command_ignores_explicit_shell_in_zsh_fork_mode` -> todo
- `exec_command_pre_tool_use_payload_uses_raw_command` -> todo
- `exec_command_pre_tool_use_payload_skips_write_stdin` -> todo
- `exec_command_post_tool_use_payload_uses_output_for_noninteractive_one_shot_commands` -> todo
- `exec_command_post_tool_use_payload_uses_output_for_interactive_completion` -> todo
- `exec_command_post_tool_use_payload_skips_running_sessions` -> todo
- `write_stdin_post_tool_use_payload_uses_original_exec_call_id_and_command_on_completion` -> todo
- `write_stdin_post_tool_use_payload_keeps_parallel_session_metadata_separate` -> todo

#### `codex/codex-rs/core/src/tools/hosted_spec_tests.rs`

- `image_generation_tool_matches_expected_spec` -> todo
- `web_search_tool_preserves_configured_options` -> todo
- `web_search_tool_is_absent_when_disabled` -> todo

#### `codex/codex-rs/core/src/tools/network_approval_tests.rs`

- `pending_approvals_are_deduped_per_host_protocol_and_port` -> todo
- `pending_approvals_do_not_dedupe_across_ports` -> todo
- `session_approved_hosts_preserve_protocol_and_port_scope` -> todo
- `sync_session_approved_hosts_to_replaces_existing_target_hosts` -> todo
- `pending_waiters_receive_owner_decision` -> todo
- `allow_once_and_allow_for_session_both_allow_network` -> todo
- `only_never_policy_disables_network_approval_flow` -> todo
- `network_approval_flow_is_limited_to_restricted_sandbox_modes` -> todo
- `active_call_preserves_triggering_command_context` -> todo
- `record_blocked_request_sets_policy_outcome_for_owner_call` -> todo
- `blocked_request_policy_does_not_override_user_denial_outcome` -> todo
- `finish_call_returns_denial_and_unregisters_active_call` -> todo
- `deferred_finish_reuses_denial_result_after_first_consumer` -> todo
- `record_call_outcome_ignores_inactive_call` -> todo
- `record_blocked_request_ignores_ambiguous_unattributed_blocked_requests` -> todo

#### `codex/codex-rs/core/src/tools/registry_tests.rs`

- `handler_looks_up_namespaced_aliases_explicitly` -> todo
- `function_tools_expose_default_hook_payloads_and_rewrites` -> todo
- `function_hook_input_defaults_empty_arguments_to_object` -> todo
- `spawn_agent_function_tools_use_agent_matcher_alias` -> todo
- `code_mode_wait_does_not_expose_default_hook_payloads` -> todo
- `write_stdin_does_not_expose_default_pre_tool_use_payload` -> todo
- `post_tool_use_feedback_output_keeps_code_mode_result_typed` -> todo
- `dispatch_notifies_tool_lifecycle_contributors` -> todo

#### `codex/codex-rs/core/src/tools/router_tests.rs`

- `parallel_support_does_not_match_namespaced_local_tool_names` -> todo
- `build_tool_call_uses_namespace_for_registry_name` -> todo
- `mcp_parallel_support_uses_handler_data` -> todo
- `tools_without_handlers_do_not_support_parallel` -> todo
- `specs_filter_deferred_dynamic_tools` -> todo
- `extension_tool_executors_are_model_visible_and_dispatchable` -> todo

#### `codex/codex-rs/core/src/tools/runtimes/apply_patch_tests.rs`

- `wants_no_sandbox_approval_granular_respects_sandbox_flag` -> todo
- `guardian_review_request_includes_patch_context` -> todo
- `permission_request_payload_uses_apply_patch_hook_name_and_aliases` -> todo
- `approval_keys_include_environment_id` -> todo
- `sandbox_cwd_uses_patch_action_cwd` -> todo
- `file_system_sandbox_context_uses_active_attempt` -> todo
- `no_sandbox_attempt_has_no_file_system_context` -> todo

#### `codex/codex-rs/core/src/tools/runtimes/mod_tests.rs`

- `explicit_escalation_prepares_exec_without_managed_network` -> tests/test_core_tool_runtimes.py
- `explicit_escalation_keeps_user_proxy_env_without_codex_marker` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_bootstraps_in_user_shell` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_escapes_single_quotes` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_uses_bash_bootstrap_shell` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_uses_sh_bootstrap_shell` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_preserves_trailing_args` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_skips_when_cwd_mismatch` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_accepts_dot_alias_cwd` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_restores_explicit_override_precedence` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_restores_codex_thread_id_from_env` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_restores_proxy_env_from_process_env` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_refreshes_codex_proxy_git_ssh_command` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_restores_custom_git_ssh_command` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_clears_stale_codex_git_ssh_command_without_live_command` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_keeps_user_proxy_env_when_proxy_inactive` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_restores_live_env_when_snapshot_proxy_active` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_keeps_snapshot_path_without_override` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_applies_explicit_path_override` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_does_not_embed_override_values_in_argv` -> tests/test_core_tool_runtimes.py
- `maybe_wrap_shell_lc_with_snapshot_preserves_unset_override_variables` -> tests/test_core_tool_runtimes.py

#### `codex/codex-rs/core/src/tools/runtimes/shell/unix_escalation_tests.rs`

- `execve_prompt_rejection_keeps_prefix_rules_on_rules_flag` -> tests/test_core_tool_runtimes.py
- `execve_prompt_rejection_keeps_unmatched_commands_on_sandbox_flag` -> tests/test_core_tool_runtimes.py
- `approval_sandbox_permissions_only_downgrades_preapproved_additional_permissions` -> tests/test_core_tool_runtimes.py
- `extract_shell_script_preserves_login_flag` -> tests/test_core_tool_runtimes.py
- `extract_shell_script_supports_wrapped_command_prefixes` -> tests/test_core_tool_runtimes.py
- `extract_shell_script_rejects_unsupported_shell_invocation` -> tests/test_core_tool_runtimes.py
- `join_program_and_argv_replaces_original_argv_zero` -> tests/test_core_tool_runtimes.py
- `commands_for_intercepted_exec_policy_parses_plain_shell_wrappers` -> tests/test_core_tool_runtimes.py
- `map_exec_result_preserves_stdout_and_stderr` -> tests/test_core_tool_runtimes.py
- `shell_request_escalation_execution_is_explicit` -> tests/test_core_tool_runtimes.py
- `execve_permission_request_hook_short_circuits_prompt` -> tests/test_core_tool_runtimes.py
- `evaluate_intercepted_exec_policy_uses_wrapper_command_when_shell_wrapper_parsing_disabled` -> tests/test_core_tool_runtimes.py
- `evaluate_intercepted_exec_policy_matches_inner_shell_commands_when_enabled` -> tests/test_core_tool_runtimes.py
- `intercepted_exec_policy_uses_host_executable_mappings` -> tests/test_core_tool_runtimes.py
- `intercepted_exec_policy_treats_preapproved_additional_permissions_as_default` -> tests/test_core_tool_runtimes.py
- `intercepted_exec_policy_rejects_disallowed_host_executable_mapping` -> tests/test_core_tool_runtimes.py

#### `codex/codex-rs/core/src/tools/sandboxing_tests.rs`

- `bash_permission_request_payload_omits_missing_description` -> todo
- `bash_permission_request_payload_includes_description_when_present` -> todo
- `external_sandbox_skips_exec_approval_on_request` -> todo
- `restricted_sandbox_requires_exec_approval_on_request` -> todo
- `default_exec_approval_requirement_rejects_sandbox_prompt_when_granular_disables_it` -> todo
- `default_exec_approval_requirement_keeps_prompt_when_granular_allows_sandbox_approval` -> todo
- `additional_permissions_allow_bypass_sandbox_first_attempt_when_execpolicy_skips` -> todo
- `guardian_bypasses_sandbox_for_explicit_escalation_on_first_attempt` -> todo
- `deny_read_blocks_explicit_escalation_but_preserves_policy_bypass` -> todo

#### `codex/codex-rs/core/src/tools/spec_plan_tests.rs`

- `shell_family_registers_visible_unified_exec_and_hidden_legacy_shell` -> todo
- `environment_count_controls_environment_backed_tools` -> todo
- `host_context_gates_goal_and_agent_job_tools` -> todo
- `mcp_and_tool_search_follow_direct_and_deferred_tool_exposure` -> todo
- `invalid_mcp_tools_are_not_registered` -> todo
- `request_plugin_install_requires_all_discovery_features_and_discoverable_tools` -> todo
- `install_suggestion_tools_stay_visible_without_tool_search` -> todo
- `request_plugin_install_description_defers_inventory_to_list_tool` -> todo
- `code_mode_only_exposes_code_executor_and_hides_nested_tools` -> todo
- `multi_agent_feature_selects_one_agent_tool_family` -> todo
- `v1_multi_agent_tools_defer_when_tool_search_available` -> todo
- `multi_agent_v2_can_use_configured_tool_namespace` -> todo
- `multi_agent_v2_namespace_is_supported_by_bedrock_provider` -> todo
- `code_mode_only_can_expose_namespaced_multi_agent_v2_as_normal_tools` -> todo
- `hosted_tools_follow_provider_auth_model_and_config_gates` -> todo

#### `codex/codex-rs/core/src/tools/tool_dispatch_trace_tests.rs`

- `dispatch_lifecycle_trace_records_direct_and_code_mode_requesters` -> todo
- `dispatch_lifecycle_trace_records_unsupported_tool_failures` -> todo
- `dispatch_lifecycle_trace_records_incompatible_payload_failures` -> todo
- `missing_code_mode_wait_traces_only_the_wait_tool_call` -> todo

#### `codex/codex-rs/core/src/turn_diff_tracker_tests.rs`

- `accumulates_add_then_update_as_single_add` -> todo
- `invalidated_tracker_suppresses_existing_diff` -> todo
- `accumulates_delete` -> todo
- `accumulates_move_and_update` -> todo
- `pure_rename_yields_no_diff` -> todo
- `add_over_existing_file_becomes_update` -> todo
- `delete_then_readd_same_path_becomes_update` -> todo
- `move_over_existing_destination_without_content_change_deletes_source_only` -> todo
- `move_over_existing_destination_with_content_change_deletes_source_and_updates_destination` -> todo
- `preserves_committed_change_order_with_delete_then_move_overwrite` -> todo

#### `codex/codex-rs/core/src/turn_metadata_tests.rs`

- `build_turn_metadata_header_marks_detached_memory_without_turn_identity` -> todo
- `build_turn_metadata_header_marks_memory_without_workspace_metadata` -> todo
- `turn_metadata_state_uses_platform_sandbox_tag` -> todo
- `turn_metadata_state_uses_explicit_subagent_thread_source` -> todo
- `turn_metadata_state_includes_root_fork_lineage` -> todo
- `turn_metadata_state_includes_turn_started_at_unix_ms_after_start` -> todo
- `turn_metadata_state_includes_model_and_reasoning_effort_only_in_request_meta` -> todo
- `turn_metadata_state_marks_user_input_requested_during_turn_only_for_mcp_request_meta` -> todo
- `turn_metadata_state_ignores_client_reserved_metadata_before_start` -> todo
- `turn_metadata_state_merges_client_metadata_without_replacing_reserved_fields` -> todo
- `turn_metadata_state_overlays_compaction_only_on_compaction_requests` -> todo

#### `codex/codex-rs/core/src/turn_timing_tests.rs`

- `turn_timing_state_records_ttft_only_once_per_turn` -> todo
- `turn_timing_state_records_ttfm_independently_of_ttft` -> todo
- `turn_timing_state_records_turn_started_epoch_millis` -> todo
- `response_item_records_turn_ttft_for_first_output_signals` -> todo
- `response_item_records_turn_ttft_ignores_empty_non_output_items` -> todo

#### `codex/codex-rs/core/src/unified_exec/async_watcher_tests.rs`

- `split_valid_utf8_prefix_respects_max_bytes_for_ascii` -> todo
- `split_valid_utf8_prefix_avoids_splitting_utf8_codepoints` -> todo
- `split_valid_utf8_prefix_makes_progress_on_invalid_utf8` -> todo

#### `codex/codex-rs/core/src/unified_exec/head_tail_buffer_tests.rs`

- `keeps_prefix_and_suffix_when_over_budget` -> todo
- `max_bytes_zero_drops_everything` -> todo
- `head_budget_zero_keeps_only_last_byte_in_tail` -> todo
- `draining_resets_state` -> todo
- `chunk_larger_than_tail_budget_keeps_only_tail_end` -> todo
- `fills_head_then_tail_across_multiple_chunks` -> todo

#### `codex/codex-rs/core/src/unified_exec/mod_tests.rs`

- `push_chunk_preserves_prefix_and_suffix` -> todo
- `head_tail_buffer_default_preserves_prefix_and_suffix` -> todo
- `unified_exec_persists_across_requests` -> todo
- `multi_unified_exec_sessions` -> todo
- `unified_exec_timeouts` -> todo
- `unified_exec_pause_blocks_yield_timeout` -> todo
- `requests_with_large_timeout_are_capped` -> todo
- `completed_commands_do_not_persist_sessions` -> todo
- `reusing_completed_process_returns_unknown_process` -> todo
- `completed_pipe_commands_preserve_exit_code` -> todo
- `unified_exec_uses_remote_exec_server_when_configured` -> todo
- `remote_exec_server_rejects_inherited_fd_launches` -> todo

#### `codex/codex-rs/core/src/unified_exec/process_manager_tests.rs`

- `unified_exec_env_injects_defaults` -> todo
- `unified_exec_env_overrides_existing_values` -> todo
- `env_overlay_for_exec_server_keeps_runtime_changes_only` -> todo
- `exec_server_params_use_env_policy_overlay_contract` -> todo
- `exec_server_process_id_matches_unified_exec_process_id` -> todo
- `network_denial_fallback_message_names_sandbox_network_proxy` -> todo
- `late_network_denial_grace_observes_cancellation_after_exit` -> todo
- `failed_initial_end_for_unstored_process_uses_fallback_output` -> todo
- `pruning_prefers_exited_processes_outside_recently_used` -> todo
- `pruning_falls_back_to_lru_when_no_exited` -> todo
- `pruning_protects_recent_processes_even_if_exited` -> todo

#### `codex/codex-rs/core/src/unified_exec/process_tests.rs`

- `remote_write_unknown_process_marks_process_exited` -> todo
- `remote_write_closed_stdin_marks_process_exited` -> todo
- `fail_and_terminate_preserves_failure_message` -> todo
- `remote_process_waits_for_early_exit_event` -> todo

#### `codex/codex-rs/core/src/user_shell_command_tests.rs`

- `detects_user_shell_command_text_variants` -> todo
- `formats_basic_record` -> todo
- `uses_aggregated_output_over_streams` -> todo

#### `codex/codex-rs/core/src/util_tests.rs`

- `feedback_tags_macro_compiles` -> todo
- `emit_feedback_request_tags_records_sentry_feedback_fields` -> todo
- `emit_feedback_auth_recovery_tags_preserves_401_specific_fields` -> todo
- `emit_feedback_auth_recovery_tags_clears_stale_401_fields` -> todo
- `emit_feedback_request_tags_preserves_latest_auth_fields_after_unauthorized` -> todo
- `emit_feedback_request_tags_preserves_auth_env_fields_for_legacy_emitters` -> todo
- `normalize_thread_name_trims_and_rejects_empty` -> todo

#### `codex/codex-rs/core/src/windows_sandbox_read_grants_tests.rs`

- `rejects_relative_path` -> todo
- `rejects_missing_path` -> todo
- `rejects_file_path` -> todo

#### `codex/codex-rs/core/src/windows_sandbox_tests.rs`

- `elevated_flag_works_by_itself` -> todo
- `restricted_token_flag_works_by_itself` -> todo
- `no_flags_means_no_sandbox` -> todo
- `elevated_wins_when_both_flags_are_enabled` -> todo
- `legacy_mode_prefers_elevated` -> todo
- `legacy_mode_supports_alias_key` -> todo
- `resolve_windows_sandbox_mode_falls_back_to_legacy_keys` -> todo
- `resolve_windows_sandbox_private_desktop_defaults_to_true` -> todo
- `resolve_windows_sandbox_private_desktop_respects_explicit_cfg_value` -> todo

### Integration tests

#### `codex/codex-rs/core/tests/responses_headers.rs`

- `responses_stream_includes_subagent_header_on_review` -> `tests/test_core_responses_headers.py`
- `responses_stream_includes_subagent_header_on_other` -> `tests/test_core_responses_headers.py`
- `responses_respects_model_info_overrides_from_config` -> `tests/test_core_responses_headers.py`
- `responses_stream_includes_turn_metadata_header_for_git_workspace_e2e` -> `tests/test_core_responses_headers.py`

#### `codex/codex-rs/core/tests/suite/abort_tasks.rs`

- `interrupt_long_running_tool_emits_turn_aborted` -> `tests/test_core_suite_abort_tasks.py`
- `interrupt_tool_records_history_entries` -> `tests/test_core_suite_abort_tasks.py`
- `interrupt_persists_turn_aborted_marker_in_next_request` -> `tests/test_core_suite_abort_tasks.py`

#### `codex/codex-rs/core/tests/suite/additional_context.rs`

- `additional_context_is_model_visible_but_not_a_user_message_item` -> `tests/test_core_suite_additional_context.py`
- `external_context_like_user_text_remains_a_user_message_item` -> `tests/test_core_suite_additional_context.py`
- `additional_context_trust_controls_message_role` -> `tests/test_core_suite_additional_context.py`
- `additional_context_is_deduplicated_between_turns_while_retained` -> `tests/test_core_suite_additional_context.py`
- `additional_context_removes_one_value_while_adding_another` -> `tests/test_core_suite_additional_context.py`
- `additional_context_values_are_truncated_before_model_input` -> `tests/test_core_suite_additional_context.py`

#### `codex/codex-rs/core/tests/suite/agent_jobs.rs`

- `report_agent_job_result_rejects_wrong_thread` -> todo
- `spawn_agents_on_csv_runs_and_exports` -> todo
- `spawn_agents_on_csv_dedupes_item_ids` -> todo
- `spawn_agents_on_csv_stop_halts_future_items` -> todo

#### `codex/codex-rs/core/tests/suite/agent_websocket.rs`

- `websocket_test_codex_shell_chain` -> `tests/test_core_suite_agent_websocket.py`
- `websocket_first_turn_uses_startup_prewarm_and_create` -> `tests/test_core_suite_agent_websocket.py`
- `websocket_first_turn_handles_handshake_delay_with_startup_prewarm` -> `tests/test_core_suite_agent_websocket.py`
- `websocket_v2_test_codex_shell_chain` -> `tests/test_core_suite_agent_websocket.py`
- `websocket_v2_first_turn_uses_updated_fast_tier_after_startup_prewarm` -> `tests/test_core_suite_agent_websocket.py`
- `websocket_v2_first_turn_drops_fast_tier_after_startup_prewarm` -> `tests/test_core_suite_agent_websocket.py`
- `websocket_v2_next_turn_uses_updated_service_tier` -> `tests/test_core_suite_agent_websocket.py`

#### `codex/codex-rs/core/tests/suite/agents_md.rs`

- `agents_override_is_preferred_over_agents_md` -> todo
- `configured_fallback_is_used_when_agents_candidate_is_directory` -> todo
- `agents_docs_are_concatenated_from_project_root_to_cwd` -> todo

#### `codex/codex-rs/core/tests/suite/apply_patch_cli.rs`

- `apply_patch_cli_uses_codex_self_exe_with_linux_sandbox_helper_alias` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_multiple_operations_integration` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_multiple_chunks` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_moves_file_to_new_directory` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_updates_file_appends_trailing_newline` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_insert_only_hunk_modifies_file` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_move_overwrites_existing_destination` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_move_without_content_change_has_no_turn_diff` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_add_overwrites_existing_file` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_rejects_invalid_hunk_header` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_reports_missing_context` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_reports_missing_target_file` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_delete_missing_file_reports_error` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_rejects_empty_patch` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_delete_directory_reports_verification_error` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_rejects_path_traversal_outside_workspace` -> `tests/test_core_suite_apply_patch_cli.py`
- `intercepted_apply_patch_verification_uses_local_sandbox` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_does_not_write_through_symlink_escape_outside_workspace` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_preserves_existing_hard_link_outside_workspace` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_rejects_move_path_traversal_outside_workspace` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_verification_failure_has_no_side_effects` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_shell_command_heredoc_with_cd_updates_relative_workdir` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_can_use_shell_command_output_as_patch_input` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_custom_tool_streaming_emits_updated_changes` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_shell_command_heredoc_with_cd_emits_turn_diff` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_turn_diff_paths_stay_repo_relative_when_session_cwd_is_nested` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_shell_command_failure_propagates_error_and_skips_diff` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_shell_accepts_lenient_heredoc_wrapped_patch` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_end_of_file_anchor` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_cli_missing_second_chunk_context_rejected` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_emits_turn_diff_event_with_unified_diff` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_aggregates_diff_across_multiple_tool_calls` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_aggregates_diff_preserves_success_after_failure` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_clears_aggregated_diff_after_inexact_delta` -> `tests/test_core_suite_apply_patch_cli.py`
- `apply_patch_change_context_disambiguates_target` -> `tests/test_core_suite_apply_patch_cli.py`

#### `codex/codex-rs/core/tests/suite/approvals.rs`

- `approval_matrix_covers_group` -> `tests/test_core_suite_approvals.py`
- `approving_apply_patch_for_session_skips_future_prompts_for_same_file` -> `tests/test_core_suite_approvals.py`
- `approving_execpolicy_amendment_persists_policy_and_skips_future_prompts` -> `tests/test_core_suite_approvals.py`
- `spawned_subagent_execpolicy_amendment_propagates_to_parent_session` -> `tests/test_core_suite_approvals.py`
- `matched_prefix_rule_runs_unsandboxed_under_zsh_fork` -> `tests/test_core_suite_approvals.py`
- `invalid_requested_prefix_rule_falls_back_for_compound_command` -> `tests/test_core_suite_approvals.py`
- `approving_fallback_rule_for_compound_command_works` -> `tests/test_core_suite_approvals.py`
- `denying_network_policy_amendment_persists_policy_and_skips_future_network_prompt` -> `tests/test_core_suite_approvals.py`
- `network_approval_flow_survives_danger_full_access_session_start` -> `tests/test_core_suite_approvals.py`
- `compound_command_with_one_safe_command_still_requires_approval` -> `tests/test_core_suite_approvals.py`

#### `codex/codex-rs/core/tests/suite/cli_stream.rs`

- `responses_mode_stream_cli` -> `tests/test_core_suite_cli_stream.py`
- `responses_mode_stream_cli_supports_openai_base_url_config_override` -> `tests/test_core_suite_cli_stream.py`
- `exec_cli_applies_model_instructions_file` -> `tests/test_core_suite_cli_stream.py`
- `exec_cli_profile_applies_model_instructions_file` -> `tests/test_core_suite_cli_stream.py`
- `responses_api_stream_cli` -> `tests/test_core_suite_cli_stream.py`
- `integration_creates_and_checks_session_file` -> `tests/test_core_suite_cli_stream.py`
- `integration_git_info_unit_test` -> `tests/test_core_suite_cli_stream.py`

#### `codex/codex-rs/core/tests/suite/client.rs`

- `resume_includes_initial_messages_and_sends_prior_items` -> todo
- `resume_replays_legacy_js_repl_image_rollout_shapes` -> todo
- `resume_replays_image_tool_outputs_with_detail` -> todo
- `includes_session_id_thread_id_and_model_headers_in_request` -> todo
- `provider_auth_command_supplies_bearer_token` -> todo
- `provider_auth_command_refreshes_after_401` -> todo
- `includes_base_instructions_override_in_request` -> todo
- `chatgpt_auth_sends_correct_request` -> todo
- `prefers_apikey_when_config_prefers_apikey_even_with_chatgpt_tokens` -> todo
- `includes_user_instructions_message_in_request` -> todo
- `includes_apps_guidance_as_developer_message_for_chatgpt_auth` -> todo
- `omits_apps_guidance_for_api_key_auth_even_when_feature_enabled` -> todo
- `omits_apps_guidance_when_configured_off` -> todo
- `omits_environment_context_when_configured_off` -> todo
- `skills_append_to_developer_message` -> todo
- `skills_use_aliases_in_developer_message_under_budget_pressure` -> todo
- `includes_configured_effort_in_request` -> todo
- `includes_no_effort_in_request` -> todo
- `includes_default_reasoning_effort_in_request_when_defined_by_model_info` -> todo
- `user_turn_collaboration_mode_overrides_model_and_effort` -> todo
- `configured_reasoning_summary_is_sent` -> todo
- `user_turn_explicit_reasoning_summary_overrides_model_catalog_default` -> todo
- `reasoning_summary_is_omitted_when_disabled` -> todo
- `reasoning_summary_none_overrides_model_catalog_default` -> todo
- `includes_default_verbosity_in_request` -> todo
- `configured_verbosity_not_sent_for_models_without_support` -> todo
- `configured_verbosity_is_sent` -> todo
- `includes_developer_instructions_message_in_request` -> todo
- `azure_responses_request_includes_store_and_reasoning_ids` -> todo
- `token_count_includes_rate_limits_snapshot` -> todo
- `usage_limit_error_emits_rate_limit_event` -> todo
- `context_window_error_sets_total_tokens_to_model_window` -> todo
- `incomplete_response_emits_content_filter_error_message` -> todo
- `azure_overrides_assign_properties_used_for_responses_url` -> todo
- `env_var_overrides_loaded_auth` -> todo
- `history_dedupes_streamed_and_final_messages_across_turns` -> todo

#### `codex/codex-rs/core/tests/suite/client_websockets.rs`

- `responses_websocket_streams_request` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_streams_without_feature_flag_when_provider_supports_websockets` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_sends_response_processed_when_feature_enabled` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_sends_response_processed_after_remote_compaction_v2` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_omits_response_processed_without_feature` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_reuses_connection_with_per_turn_trace_payloads` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_preconnect_does_not_replace_turn_trace_payload` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_preconnect_reuses_connection` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_request_prewarm_reuses_connection` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_request_prewarm_traces_logical_request` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_reuses_connection_after_session_drop` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_preconnect_is_reused_even_with_header_changes` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_request_prewarm_is_reused_even_with_header_changes` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_prewarm_uses_v2_when_provider_supports_websockets` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_preconnect_runs_when_only_v2_feature_enabled` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_v2_requests_use_v2_when_provider_supports_websockets` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_v2_incremental_requests_are_reused_across_turns` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_v2_wins_when_both_features_enabled` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_emits_websocket_telemetry_events` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_includes_timing_metrics_header_when_runtime_metrics_enabled` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_omits_timing_metrics_header_when_runtime_metrics_disabled` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_emits_reasoning_included_event` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_emits_rate_limit_events` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_usage_limit_error_emits_rate_limit_event` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_invalid_request_error_with_status_is_forwarded` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_connection_limit_error_reconnects_and_completes` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_uses_incremental_create_on_prefix` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_forwards_turn_metadata_on_initial_and_incremental_create` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_preserves_custom_turn_metadata_fields` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_uses_previous_response_id_when_prefix_after_completed` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_creates_on_non_prefix` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_creates_when_non_input_request_fields_change` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_v2_creates_with_previous_response_id_on_prefix` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_v2_creates_without_previous_response_id_when_non_input_fields_change` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_v2_after_error_uses_full_create_without_previous_response_id` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_v2_surfaces_terminal_error_without_close_handshake` -> `tests/test_core_suite_client_websockets.py`
- `responses_websocket_v2_sets_openai_beta_header` -> `tests/test_core_suite_client_websockets.py`

#### `codex/codex-rs/core/tests/suite/code_mode.rs`

- `code_mode_can_return_exec_command_output` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_only_restricts_prompt_tools` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_only_guides_all_tools_search_and_calls_deferred_app_tools` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_only_can_call_nested_tools` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_update_plan_nested_tool_result_is_empty_object` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_nested_tool_calls_can_run_in_parallel` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exec_command_explicit_max_output_tokens_truncates` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exec_explicit_max_above_default_preserves_output` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exec_explicit_max_above_default_truncates_larger_output` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exec_explicit_max_above_truncation_policy_preserves_output` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exec_without_max_preserves_output_beyond_default` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exec_without_max_preserves_output_beyond_truncation_policy` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exec_explicit_max_output_tokens_truncates` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_returns_accumulated_output_when_script_fails` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exec_surfaces_handler_errors_as_exceptions` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_yield_and_resume_with_wait` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_yield_timeout_works_for_busy_loop` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_run_multiple_yielded_sessions` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_concurrent_cells_merge_only_the_stored_values_they_write` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_wait_can_terminate_and_continue` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_wait_returns_error_for_unknown_session` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_wait_terminate_returns_completed_session_if_it_finished_after_yield_control` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_background_keeps_running_on_later_turn_without_wait` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_wait_uses_its_own_max_tokens_budget` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_output_serialized_text_via_global_helper` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_resume_after_set_timeout` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_notify_injects_additional_exec_tool_output_into_active_context` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exit_stops_script_immediately` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_surfaces_text_stringify_errors` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_output_images_via_global_helper` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_use_view_image_result_with_image_helper` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_use_mcp_image_result_with_image_helper` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_apply_patch_via_nested_tool` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_print_structured_mcp_tool_result_fields` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_only_can_call_mcp_tool` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exposes_mcp_tools_on_global_tools_object` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_uses_non_prefixed_mcp_tool_names_when_feature_enabled` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exposes_namespaced_mcp_tools_on_global_tools_object` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exposes_normalized_illegal_mcp_tool_names` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_lists_global_scope_items` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exports_all_tools_metadata_for_builtin_tools` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_exports_all_tools_metadata_for_namespaced_mcp_tools` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_call_hidden_dynamic_tools` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_print_content_only_mcp_tool_result_fields` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_print_error_mcp_tool_result_fields` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_store_and_load_values_across_turns` -> `tests/test_core_suite_client_websockets.py`
- `code_mode_can_compare_elapsed_time_around_set_timeout` -> `tests/test_core_suite_client_websockets.py`

#### `codex/codex-rs/core/tests/suite/codex_delegate.rs`

- `codex_delegate_forwards_exec_approval_and_proceeds_on_approval` -> `tests/test_core_suite_client_websockets.py`
- `codex_delegate_forwards_patch_approval_and_proceeds_on_decision` -> `tests/test_core_suite_client_websockets.py`
- `codex_delegate_ignores_legacy_deltas` -> `tests/test_core_suite_client_websockets.py`

#### `codex/codex-rs/core/tests/suite/collaboration_instructions.rs`

- `no_collaboration_instructions_by_default` -> `tests/test_core_suite_collaboration_instructions.py`
- `user_input_includes_collaboration_instructions_after_override` -> `tests/test_core_suite_collaboration_instructions.py`
- `collaboration_instructions_added_on_user_turn` -> `tests/test_core_suite_collaboration_instructions.py`
- `collaboration_instructions_omitted_when_disabled` -> `tests/test_core_suite_collaboration_instructions.py`
- `override_then_next_turn_uses_updated_collaboration_instructions` -> `tests/test_core_suite_collaboration_instructions.py`
- `user_turn_overrides_collaboration_instructions_after_override` -> `tests/test_core_suite_collaboration_instructions.py`
- `collaboration_mode_update_emits_new_instruction_message` -> `tests/test_core_suite_collaboration_instructions.py`
- `collaboration_mode_update_noop_does_not_append` -> `tests/test_core_suite_collaboration_instructions.py`
- `collaboration_mode_update_emits_new_instruction_message_when_mode_changes` -> `tests/test_core_suite_collaboration_instructions.py`
- `collaboration_mode_update_noop_does_not_append_when_mode_is_unchanged` -> `tests/test_core_suite_collaboration_instructions.py`
- `resume_replays_collaboration_instructions` -> `tests/test_core_suite_collaboration_instructions.py`
- `empty_collaboration_instructions_are_ignored` -> `tests/test_core_suite_collaboration_instructions.py`

#### `codex/codex-rs/core/tests/suite/compact.rs`

- `summarize_context_three_requests_and_instructions` -> `tests/test_core_suite_collaboration_instructions.py`
- `manual_pre_compact_block_decision_does_not_block_compaction` -> `tests/test_core_suite_collaboration_instructions.py`
- `compact_hooks_respect_matchers_and_post_runs_after_compaction` -> `tests/test_core_suite_collaboration_instructions.py`
- `manual_compact_uses_custom_prompt` -> `tests/test_core_suite_collaboration_instructions.py`
- `manual_compact_emits_api_and_local_token_usage_events` -> `tests/test_core_suite_collaboration_instructions.py`
- `manual_compact_emits_context_compaction_items` -> `tests/test_core_suite_collaboration_instructions.py`
- `multiple_auto_compact_per_task_runs_after_token_limit_hit` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_runs_after_resume_when_token_usage_is_over_limit` -> `tests/test_core_suite_collaboration_instructions.py`
- `pre_sampling_compact_runs_on_switch_to_smaller_context_model` -> `tests/test_core_suite_collaboration_instructions.py`
- `body_after_prefix_model_switch_budget_compacts_with_next_model` -> `tests/test_core_suite_collaboration_instructions.py`
- `pre_sampling_compact_runs_after_resume_and_switch_to_smaller_model` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_persists_rollout_entries` -> `tests/test_core_suite_collaboration_instructions.py`
- `manual_compact_retries_after_context_window_error` -> `tests/test_core_suite_collaboration_instructions.py`
- `manual_compact_non_context_failure_retries_then_emits_task_error` -> `tests/test_core_suite_collaboration_instructions.py`
- `manual_compact_twice_preserves_latest_user_messages` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_allows_multiple_attempts_when_interleaved_with_other_turn_events` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_mid_turn_continuation_compaction` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_clamps_config_limit_to_context_window` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_body_after_prefix_ignores_starting_window_prefix` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_body_after_prefix_counts_growth_after_compaction` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_body_after_prefix_still_caps_at_context_window` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_counts_encrypted_reasoning_before_last_user` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_compact_runs_when_reasoning_header_clears_between_turns` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_pre_turn_compaction_including_incoming_user_message` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_pre_turn_compaction_strips_incoming_model_switch` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_pre_turn_compaction_context_window_exceeded` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_manual_compact_without_previous_user_messages` -> `tests/test_core_suite_collaboration_instructions.py`

#### `codex/codex-rs/core/tests/suite/compact_remote.rs`

- `remote_compact_replaces_history_for_followups` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_manual_compact_api_auth_omits_service_tier_and_reuses_prompt_cache_key` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_manual_compact_chatgpt_auth_reuses_service_tier_and_prompt_cache_key` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_v2_reuses_compaction_trigger_for_followups` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_v2_retries_failures_with_stream_retry_budget` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_v2_accepts_additional_output_items_before_compaction` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_filters_deferred_dynamic_tools` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_runs_automatically` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_trims_function_call_history_to_fit_context_window` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_remote_compact_trims_function_call_history_to_fit_context_window` -> `tests/test_core_suite_collaboration_instructions.py`
- `auto_remote_compact_failure_stops_agent_loop` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_trim_estimate_uses_session_base_instructions` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_manual_compact_emits_context_compaction_items` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_manual_compact_failure_emits_task_error_event` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_persists_replacement_history_in_rollout` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_and_resume_refresh_stale_developer_instructions` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_compact_refreshes_stale_developer_instructions_without_resume` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_pre_turn_compaction_restates_realtime_start` -> `tests/test_core_suite_collaboration_instructions.py`
- `remote_request_uses_custom_experimental_realtime_start_instructions` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_pre_turn_compaction_restates_realtime_end` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_manual_compact_restates_realtime_start` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_mid_turn_compaction_does_not_restate_realtime_end` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_compact_resume_restates_realtime_end` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_pre_turn_compaction_including_incoming_user_message` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_pre_turn_compaction_strips_incoming_model_switch` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_pre_turn_compaction_context_window_exceeded` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_mid_turn_continuation_compaction` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_mid_turn_compaction_summary_only_reinjects_context` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_mid_turn_compaction_multi_summary_reinjects_above_last_summary` -> `tests/test_core_suite_collaboration_instructions.py`
- `snapshot_request_shape_remote_manual_compact_without_previous_user_messages` -> `tests/test_core_suite_collaboration_instructions.py`

#### `codex/codex-rs/core/tests/suite/compact_remote_parity.rs`

- `remote_compaction_parity_manual_transcripts` -> `tests/test_core_suite_compact_remote_parity.py`
- `remote_compaction_parity_v2_api_key_sends_service_tier_upgrade` -> `tests/test_core_suite_compact_remote_parity.py`
- `remote_compaction_parity_manual_hooks` -> `tests/test_core_suite_compact_remote_parity.py`
- `remote_compaction_parity_pre_turn_auto` -> `tests/test_core_suite_compact_remote_parity.py`
- `remote_compaction_parity_mid_turn_auto` -> `tests/test_core_suite_compact_remote_parity.py`
- `normalize_string_rewrites_linux_temp_skill_paths` -> `tests/test_core_suite_compact_remote_parity.py`
- `normalize_string_rewrites_windows_temp_skill_paths` -> `tests/test_core_suite_compact_remote_parity.py`
- `normalize_string_rewrites_shell_wall_times` -> `tests/test_core_suite_compact_remote_parity.py`

#### `codex/codex-rs/core/tests/suite/compact_resume_fork.rs`

- `compact_resume_and_fork_preserve_model_history_view` -> `tests/test_core_suite_compact_resume_fork.py`
- `compact_resume_after_second_compaction_preserves_history` -> `tests/test_core_suite_compact_resume_fork.py`
- `snapshot_rollback_past_compaction_replays_append_only_history` -> `tests/test_core_suite_compact_resume_fork.py`
- `snapshot_rollback_followup_turn_trims_context_updates` -> `tests/test_core_suite_compact_resume_fork.py`

#### `codex/codex-rs/core/tests/suite/deprecation_notice.rs`

- `emits_deprecation_notice_for_legacy_feature_flag` -> `tests/test_core_suite_deprecation_notice.py`
- `emits_deprecation_notice_for_web_search_feature_flag_values` -> `tests/test_core_suite_deprecation_notice.py`
- `emits_deprecation_notice_for_use_legacy_landlock` -> `tests/test_core_suite_deprecation_notice.py`

#### `codex/codex-rs/core/tests/suite/exec.rs`

- `exit_code_0_succeeds` -> `tests/test_core_suite_deprecation_notice.py`
- `truncates_output_lines` -> `tests/test_core_suite_deprecation_notice.py`
- `truncates_output_bytes` -> `tests/test_core_suite_deprecation_notice.py`
- `exit_command_not_found_is_ok` -> `tests/test_core_suite_deprecation_notice.py`
- `openpty_works_under_real_exec_seatbelt_path` -> `tests/test_core_suite_deprecation_notice.py`
- `write_file_fails_as_sandbox_error` -> `tests/test_core_suite_deprecation_notice.py`

#### `codex/codex-rs/core/tests/suite/exec_policy.rs`

- `execpolicy_blocks_shell_invocation` -> `tests/test_core_suite_deprecation_notice.py`
- `shell_command_empty_script_with_collaboration_mode_does_not_panic` -> `tests/test_core_suite_deprecation_notice.py`
- `unified_exec_empty_script_with_collaboration_mode_does_not_panic` -> `tests/test_core_suite_deprecation_notice.py`
- `shell_command_whitespace_script_with_collaboration_mode_does_not_panic` -> `tests/test_core_suite_deprecation_notice.py`
- `unified_exec_whitespace_script_with_collaboration_mode_does_not_panic` -> `tests/test_core_suite_deprecation_notice.py`

#### `codex/codex-rs/core/tests/suite/fork_thread.rs`

- `fork_thread_twice_drops_to_first_message` -> `tests/test_core_suite_fork_thread.py`
- `fork_thread_from_history_does_not_require_source_rollout_path` -> `tests/test_core_suite_fork_thread.py`

#### `codex/codex-rs/core/tests/suite/guardian_review.rs`

- `guardian_review_session_does_not_inherit_legacy_notify` -> todo

#### `codex/codex-rs/core/tests/suite/hierarchical_agents.rs`

- `hierarchical_agents_appends_to_project_doc_in_user_instructions` -> `tests/test_core_suite_hierarchical_agents.py`
- `hierarchical_agents_emits_when_no_project_doc` -> `tests/test_core_suite_hierarchical_agents.py`

#### `codex/codex-rs/core/tests/suite/hooks.rs`

- `stop_hook_can_block_multiple_times_in_same_turn` -> `tests/test_core_suite_hooks.py`
- `session_start_hook_sees_materialized_transcript_path` -> `tests/test_core_suite_hooks.py`
- `session_start_runs_before_user_prompt_submit_on_first_turn` -> `tests/test_core_suite_hooks.py`
- `session_start_hook_spills_large_additional_context` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_hook_spills_large_additional_context` -> `tests/test_core_suite_hooks.py`
- `compact_session_start_hook_records_additional_context_for_next_turn` -> `tests/test_core_suite_hooks.py`
- `resumed_thread_runs_resume_then_compact_session_start_hooks` -> `tests/test_core_suite_hooks.py`
- `stop_hook_spills_large_continuation_prompt` -> `tests/test_core_suite_hooks.py`
- `resumed_thread_keeps_stop_continuation_prompt_in_history` -> `tests/test_core_suite_hooks.py`
- `multiple_blocking_stop_hooks_persist_multiple_hook_prompt_fragments` -> `tests/test_core_suite_hooks.py`
- `blocked_user_prompt_submit_persists_additional_context_for_next_turn` -> `tests/test_core_suite_hooks.py`
- `blocked_queued_prompt_does_not_strand_earlier_accepted_prompt` -> `tests/test_core_suite_hooks.py`
- `permission_request_hook_allows_shell_command_without_user_approval` -> `tests/test_core_suite_hooks.py`
- `permission_request_hook_allows_apply_patch_with_write_alias` -> `tests/test_core_suite_hooks.py`
- `permission_request_hook_sees_raw_exec_command_input` -> `tests/test_core_suite_hooks.py`
- `permission_request_hook_allows_network_approval_without_prompt` -> `tests/test_core_suite_hooks.py`
- `permission_request_hook_sees_retry_context_after_sandbox_denial` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_blocks_shell_command_before_execution` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_records_additional_context_for_shell_command` -> `tests/test_core_suite_hooks.py`
- `blocked_pre_tool_use_records_additional_context_for_shell_command` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_rewrites_shell_command_before_execution` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_rewrites_exec_command_before_execution` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_rewrites_code_mode_nested_exec_command_before_execution` -> `tests/test_core_suite_hooks.py`
- `plugin_pre_tool_use_blocks_shell_command_before_execution` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_blocks_shell_when_defined_in_config_toml` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_merges_hooks_json_and_config_toml` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_blocks_exec_command_before_execution` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_blocks_apply_patch_before_execution` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_rewrites_apply_patch_before_execution` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_blocks_apply_patch_with_write_alias` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_blocks_local_function_tool_before_execution` -> `tests/test_core_suite_hooks.py`
- `pre_tool_use_rewrites_local_function_tool_before_execution` -> `tests/test_core_suite_hooks.py`
- `post_tool_use_records_additional_context_for_shell_command` -> `tests/test_core_suite_hooks.py`
- `post_tool_use_block_decision_replaces_shell_command_output_with_reason` -> `tests/test_core_suite_hooks.py`
- `post_tool_use_continue_false_replaces_shell_command_output_with_stop_reason` -> `tests/test_core_suite_hooks.py`
- `post_tool_use_exit_two_replaces_one_shot_exec_command_output_with_feedback` -> `tests/test_core_suite_hooks.py`
- `post_tool_use_spills_large_feedback_message` -> `tests/test_core_suite_hooks.py`
- `post_tool_use_blocks_when_exec_session_completes_via_write_stdin` -> `tests/test_core_suite_hooks.py`
- `post_tool_use_records_additional_context_for_apply_patch` -> `tests/test_core_suite_hooks.py`
- `post_tool_use_records_apply_patch_context_with_edit_alias` -> `tests/test_core_suite_hooks.py`

#### `codex/codex-rs/core/tests/suite/hooks_mcp.rs`

- `pre_tool_use_blocks_mcp_tool_before_execution_with_legacy_prefixed_names` -> `tests/test_core_suite_hooks_mcp.py`
- `pre_tool_use_blocks_mcp_tool_before_execution_with_non_prefixed_names` -> `tests/test_core_suite_hooks_mcp.py`
- `pre_tool_use_rewrites_mcp_tool_before_execution` -> `tests/test_core_suite_hooks_mcp.py`
- `post_tool_use_records_mcp_tool_payload_and_context_with_legacy_prefixed_names` -> `tests/test_core_suite_hooks_mcp.py`
- `post_tool_use_records_mcp_tool_payload_and_context_with_non_prefixed_names` -> `tests/test_core_suite_hooks_mcp.py`

#### `codex/codex-rs/core/tests/suite/image_rollout.rs`

- `copy_paste_local_image_persists_rollout_request_shape` -> tests/test_core_suite_image_rollout.py
- `drag_drop_image_persists_rollout_request_shape` -> tests/test_core_suite_image_rollout.py

#### `codex/codex-rs/core/tests/suite/items.rs`

- `user_message_item_is_emitted` -> tests/test_core_suite_items.py
- `assistant_message_item_is_emitted` -> tests/test_core_suite_items.py
- `reasoning_item_is_emitted` -> tests/test_core_suite_items.py
- `web_search_item_is_emitted` -> tests/test_core_suite_items.py
- `image_generation_call_event_is_emitted` -> tests/test_core_suite_items.py
- `image_generation_call_event_is_emitted_when_image_save_fails` -> tests/test_core_suite_items.py
- `agent_message_content_delta_has_item_metadata` -> tests/test_core_suite_items.py
- `plan_mode_emits_plan_item_from_proposed_plan_block` -> tests/test_core_suite_items.py
- `plan_mode_strips_plan_from_agent_messages` -> tests/test_core_suite_items.py
- `plan_mode_streaming_citations_are_stripped_across_added_deltas_and_done` -> tests/test_core_suite_items.py
- `plan_mode_streaming_proposed_plan_tag_split_across_added_and_delta_is_parsed` -> tests/test_core_suite_items.py
- `plan_mode_handles_missing_plan_close_tag` -> tests/test_core_suite_items.py
- `reasoning_content_delta_has_item_metadata` -> tests/test_core_suite_items.py
- `reasoning_raw_content_delta_respects_flag` -> tests/test_core_suite_items.py

#### `codex/codex-rs/core/tests/suite/json_result.rs`

- `codex_returns_json_result_for_gpt5` -> tests/test_core_suite_json_result.py
- `codex_returns_json_result_for_gpt5_codex` -> tests/test_core_suite_json_result.py

#### `codex/codex-rs/core/tests/suite/live_cli.rs`

- `live_create_file_hello_txt` -> tests/test_core_suite_live_cli.py
- `live_print_working_directory` -> tests/test_core_suite_live_cli.py

#### `codex/codex-rs/core/tests/suite/mcp_turn_metadata.rs`

- `approved_mcp_tool_call_metadata_records_prior_user_input_request` -> tests/test_core_suite_mcp_turn_metadata.py
- `mcp_tool_call_metadata_records_prior_request_user_input_tool` -> tests/test_core_suite_mcp_turn_metadata.py

#### `codex/codex-rs/core/tests/suite/model_overrides.rs`

- `thread_settings_update_does_not_persist_when_config_exists` -> tests/test_core_suite_model_overrides.py
- `thread_settings_update_does_not_create_config_file` -> tests/test_core_suite_model_overrides.py

#### `codex/codex-rs/core/tests/suite/model_switching.rs`

- `model_change_appends_model_instructions_developer_message` -> tests/test_core_suite_model_switching.py
- `model_and_personality_change_only_appends_model_instructions` -> tests/test_core_suite_model_switching.py
- `service_tier_change_is_applied_on_next_http_turn` -> tests/test_core_suite_model_switching.py
- `flex_service_tier_is_applied_to_http_turn` -> tests/test_core_suite_model_switching.py
- `unsupported_service_tier_is_omitted_from_http_turn` -> tests/test_core_suite_model_switching.py
- `default_service_tier_override_is_omitted_from_http_turn` -> tests/test_core_suite_model_switching.py
- `null_service_tier_override_is_omitted_from_http_turn_with_catalog_default` -> tests/test_core_suite_model_switching.py
- `model_change_from_image_to_text_strips_prior_image_content` -> tests/test_core_suite_model_switching.py
- `generated_image_is_replayed_for_image_capable_models` -> tests/test_core_suite_model_switching.py
- `model_change_from_generated_image_to_text_preserves_prior_generated_image_call` -> tests/test_core_suite_model_switching.py
- `thread_rollback_after_generated_image_drops_entire_image_turn_history` -> tests/test_core_suite_model_switching.py
- `model_switch_to_smaller_model_updates_token_context_window` -> tests/test_core_suite_model_switching.py

#### `codex/codex-rs/core/tests/suite/model_visible_layout.rs`

- `snapshot_model_visible_layout_turn_overrides` -> tests/test_core_suite_model_visible_layout.py
- `snapshot_model_visible_layout_cwd_change_does_not_refresh_agents` -> tests/test_core_suite_model_visible_layout.py
- `snapshot_model_visible_layout_resume_with_personality_change` -> tests/test_core_suite_model_visible_layout.py
- `snapshot_model_visible_layout_resume_override_matches_rollout_model` -> tests/test_core_suite_model_visible_layout.py
- `snapshot_model_visible_layout_environment_context_includes_one_subagent` -> tests/test_core_suite_model_visible_layout.py
- `snapshot_model_visible_layout_environment_context_includes_two_subagents` -> tests/test_core_suite_model_visible_layout.py

#### `codex/codex-rs/core/tests/suite/models_cache_ttl.rs`

- `renews_cache_ttl_on_matching_models_etag` -> tests/test_core_suite_models_cache_ttl.py
- `uses_cache_when_version_matches` -> tests/test_core_suite_models_cache_ttl.py
- `refreshes_when_cache_version_missing` -> tests/test_core_suite_models_cache_ttl.py
- `refreshes_when_cache_version_differs` -> tests/test_core_suite_models_cache_ttl.py

#### `codex/codex-rs/core/tests/suite/models_etag_responses.rs`

- `refresh_models_on_models_etag_mismatch_and_avoid_duplicate_models_fetch` -> tests/test_core_suite_models_etag_responses.py

#### `codex/codex-rs/core/tests/suite/openai_file_mcp.rs`

- `codex_apps_file_params_upload_local_paths_before_mcp_tool_call` -> tests/test_core_suite_openai_file_mcp.py

#### `codex/codex-rs/core/tests/suite/otel.rs`

- `extract_log_field_handles_empty_bare_values` -> tests/test_core_suite_otel.py
- `extract_log_field_does_not_confuse_similar_keys` -> tests/test_core_suite_otel.py
- `responses_api_emits_api_request_event` -> tests/test_core_suite_otel.py
- `process_sse_emits_tracing_for_output_item` -> tests/test_core_suite_otel.py
- `process_sse_emits_failed_event_on_parse_error` -> tests/test_core_suite_otel.py
- `process_sse_records_failed_event_when_stream_closes_without_completed` -> tests/test_core_suite_otel.py
- `process_sse_failed_event_records_response_error_message` -> tests/test_core_suite_otel.py
- `process_sse_failed_event_logs_parse_error` -> tests/test_core_suite_otel.py
- `process_sse_failed_event_logs_missing_error` -> tests/test_core_suite_otel.py
- `process_sse_failed_event_logs_response_completed_parse_error` -> tests/test_core_suite_otel.py
- `process_sse_emits_completed_telemetry` -> tests/test_core_suite_otel.py
- `turn_and_completed_response_spans_record_token_usage` -> tests/test_core_suite_otel.py
- `handle_responses_span_records_response_kind_and_tool_name` -> tests/test_core_suite_otel.py
- `record_responses_sets_span_fields_for_response_events` -> tests/test_core_suite_otel.py
- `handle_response_item_records_tool_result_for_custom_tool_call` -> tests/test_core_suite_otel.py
- `handle_response_item_records_tool_result_for_function_call` -> tests/test_core_suite_otel.py
- `handle_response_item_records_tool_result_for_shell_command_call` -> tests/test_core_suite_otel.py
- `handle_shell_command_autoapprove_from_config_records_tool_decision` -> tests/test_core_suite_otel.py
- `handle_shell_command_user_approved_records_tool_decision` -> tests/test_core_suite_otel.py
- `handle_shell_command_user_approved_for_session_records_tool_decision` -> tests/test_core_suite_otel.py
- `handle_sandbox_error_user_approves_retry_records_tool_decision` -> tests/test_core_suite_otel.py
- `handle_shell_command_user_denies_records_tool_decision` -> tests/test_core_suite_otel.py
- `handle_sandbox_error_user_approves_for_session_records_tool_decision` -> tests/test_core_suite_otel.py
- `handle_sandbox_error_user_denies_records_tool_decision` -> tests/test_core_suite_otel.py

#### `codex/codex-rs/core/tests/suite/override_updates.rs`

- `thread_settings_update_without_user_turn_does_not_record_permissions_update` -> tests/test_core_suite_override_updates.py
- `thread_settings_update_without_user_turn_does_not_record_environment_update` -> tests/test_core_suite_override_updates.py
- `thread_settings_update_without_user_turn_does_not_record_collaboration_update` -> tests/test_core_suite_override_updates.py

#### `codex/codex-rs/core/tests/suite/pending_input.rs`

- `injected_user_input_triggers_follow_up_request_with_deltas` -> `tests/test_core_suite_pending_input.py`
- `queued_inter_agent_mail_triggers_follow_up_after_reasoning_item` -> `tests/test_core_suite_pending_input.py`
- `queued_inter_agent_mail_triggers_follow_up_after_commentary_message_item` -> `tests/test_core_suite_pending_input.py`
- `user_input_does_not_preempt_after_reasoning_item` -> `tests/test_core_suite_pending_input.py`
- `steered_user_input_waits_for_model_continuation_after_mid_turn_compact` -> `tests/test_core_suite_pending_input.py`
- `steered_user_input_follows_compact_when_only_the_steer_needs_follow_up` -> `tests/test_core_suite_pending_input.py`
- `steered_user_input_waits_when_tool_output_triggers_compact_before_next_request` -> `tests/test_core_suite_pending_input.py`

#### `codex/codex-rs/core/tests/suite/permissions_messages.rs`

- `permissions_message_sent_once_on_start` -> `tests/test_core_suite_permissions_messages.py`
- `permissions_message_added_on_override_change` -> `tests/test_core_suite_permissions_messages.py`
- `permissions_message_not_added_when_no_change` -> `tests/test_core_suite_permissions_messages.py`
- `permissions_message_omitted_when_disabled` -> `tests/test_core_suite_permissions_messages.py`
- `resume_replays_permissions_messages` -> `tests/test_core_suite_permissions_messages.py`
- `resume_and_fork_append_permissions_messages` -> `tests/test_core_suite_permissions_messages.py`
- `permissions_message_includes_writable_roots` -> `tests/test_core_suite_permissions_messages.py`

#### `codex/codex-rs/core/tests/suite/personality.rs`

- `personality_does_not_mutate_base_instructions_without_template` -> `tests/test_core_suite_personality.py`
- `base_instructions_override_disables_personality_template` -> `tests/test_core_suite_personality.py`
- `user_turn_personality_none_does_not_add_update_message` -> `tests/test_core_suite_personality.py`
- `config_personality_some_sets_instructions_template` -> `tests/test_core_suite_personality.py`
- `config_personality_none_sends_no_personality` -> `tests/test_core_suite_personality.py`
- `default_personality_is_pragmatic_without_config_toml` -> `tests/test_core_suite_personality.py`
- `user_turn_personality_some_adds_update_message` -> `tests/test_core_suite_personality.py`
- `user_turn_personality_same_value_does_not_add_update_message` -> `tests/test_core_suite_personality.py`
- `instructions_uses_base_if_feature_disabled` -> `tests/test_core_suite_personality.py`
- `user_turn_personality_skips_if_feature_disabled` -> `tests/test_core_suite_personality.py`
- `remote_model_friendly_personality_instructions_with_feature` -> `tests/test_core_suite_personality.py`
- `user_turn_personality_remote_model_template_includes_update_message` -> `tests/test_core_suite_personality.py`

#### `codex/codex-rs/core/tests/suite/personality_migration.rs`

- `migration_marker_exists_no_sessions_no_change` -> `tests/test_core_suite_personality_migration.py`
- `no_marker_no_sessions_no_change` -> `tests/test_core_suite_personality_migration.py`
- `no_marker_sessions_sets_personality` -> `tests/test_core_suite_personality_migration.py`
- `no_marker_sessions_preserves_existing_config_fields` -> `tests/test_core_suite_personality_migration.py`
- `no_marker_meta_only_rollout_is_treated_as_no_sessions` -> `tests/test_core_suite_personality_migration.py`
- `no_marker_explicit_global_personality_skips_migration` -> `tests/test_core_suite_personality_migration.py`
- `no_marker_profile_personality_does_not_skip_migration` -> `tests/test_core_suite_personality_migration.py`
- `marker_short_circuits_migration_with_legacy_profile` -> `tests/test_core_suite_personality_migration.py`
- `missing_legacy_profile_does_not_block_migration` -> `tests/test_core_suite_personality_migration.py`
- `applied_migration_is_idempotent_on_second_run` -> `tests/test_core_suite_personality_migration.py`
- `no_marker_archived_sessions_sets_personality` -> `tests/test_core_suite_personality_migration.py`

#### `codex/codex-rs/core/tests/suite/plugins.rs`

- `capability_sections_render_in_developer_message_in_order` -> `tests/test_core_suite_plugins.py`
- `explicit_plugin_mentions_inject_plugin_guidance` -> `tests/test_core_suite_plugins.py`
- `explicit_plugin_mentions_track_plugin_used_analytics` -> `tests/test_core_suite_plugins.py`

#### `codex/codex-rs/core/tests/suite/prompt_caching.rs`

- `prompt_tools_are_consistent_across_requests` -> `tests/test_core_suite_prompt_caching.py`
- `gpt_5_tools_without_apply_patch_append_apply_patch_instructions` -> `tests/test_core_suite_prompt_caching.py`
- `prefixes_context_and_instructions_once_and_consistently_across_requests` -> `tests/test_core_suite_prompt_caching.py`
- `overrides_turn_context_but_keeps_cached_prefix_and_key_constant` -> `tests/test_core_suite_prompt_caching.py`
- `override_before_first_turn_emits_environment_context` -> `tests/test_core_suite_prompt_caching.py`
- `per_turn_overrides_keep_cached_prefix_and_key_constant` -> `tests/test_core_suite_prompt_caching.py`
- `send_user_turn_with_no_changes_does_not_send_environment_context` -> `tests/test_core_suite_prompt_caching.py`
- `send_user_turn_with_changes_sends_environment_context` -> `tests/test_core_suite_prompt_caching.py`

#### `codex/codex-rs/core/tests/suite/prompt_debug_tests.rs`

- `build_prompt_input_includes_context_and_user_message` -> `tests/test_core_suite_prompt_debug_tests.py`

#### `codex/codex-rs/core/tests/suite/quota_exceeded.rs`

- `quota_exceeded_emits_single_error_event` -> `tests/test_core_suite_quota_exceeded.py`

#### `codex/codex-rs/core/tests/suite/realtime_conversation.rs`

- `conversation_start_audio_text_close_round_trip` -> tests/test_core_realtime_conversation.py
- `conversation_start_defaults_to_v2_and_gpt_realtime_1_5` -> tests/test_core_realtime_conversation.py
- `conversation_webrtc_start_posts_generated_session` -> tests/test_core_realtime_conversation.py
- `conversation_webrtc_close_while_sideband_connecting_drops_pending_join` -> tests/test_core_realtime_conversation.py
- `conversation_webrtc_sideband_connect_failure_closes_with_error` -> tests/test_core_realtime_conversation.py
- `conversation_start_uses_openai_env_key_fallback_with_chatgpt_auth` -> tests/test_core_realtime_conversation.py
- `conversation_transport_close_emits_closed_event` -> tests/test_core_realtime_conversation.py
- `conversation_audio_before_start_emits_error` -> tests/test_core_realtime_conversation.py
- `conversation_start_preflight_failure_emits_realtime_error_only` -> tests/test_core_realtime_conversation.py
- `conversation_start_connect_failure_emits_realtime_error_only` -> tests/test_core_realtime_conversation.py
- `conversation_text_before_start_emits_error` -> tests/test_core_realtime_conversation.py
- `conversation_second_start_replaces_runtime` -> tests/test_core_realtime_conversation.py
- `conversation_uses_experimental_realtime_ws_base_url_override` -> tests/test_core_realtime_conversation.py
- `conversation_uses_default_realtime_backend_prompt` -> tests/test_core_realtime_conversation.py
- `conversation_uses_empty_instructions_for_null_or_empty_prompt` -> tests/test_core_realtime_conversation.py
- `conversation_uses_explicit_start_voice` -> tests/test_core_realtime_conversation.py
- `conversation_uses_configured_realtime_voice` -> tests/test_core_realtime_conversation.py
- `conversation_rejects_voice_for_wrong_realtime_version` -> tests/test_core_realtime_conversation.py
- `conversation_uses_experimental_realtime_ws_backend_prompt_override` -> tests/test_core_realtime_conversation.py
- `conversation_uses_experimental_realtime_ws_startup_context_override` -> tests/test_core_realtime_conversation.py
- `conversation_disables_realtime_startup_context_with_empty_override` -> tests/test_core_realtime_conversation.py
- `conversation_start_injects_startup_context_from_thread_history` -> tests/test_core_realtime_conversation.py
- `conversation_startup_context_current_thread_selects_many_turns_by_budget` -> tests/test_core_realtime_conversation.py
- `conversation_startup_context_falls_back_to_workspace_map` -> tests/test_core_realtime_conversation.py
- `conversation_startup_context_is_truncated_and_sent_once_per_start` -> tests/test_core_realtime_conversation.py
- `conversation_user_text_turn_is_sent_to_realtime_when_active` -> tests/test_core_realtime_conversation.py
- `conversation_user_text_turn_is_capped_when_mirrored_to_realtime` -> tests/test_core_realtime_conversation.py
- `realtime_v2_noop_tool_call_returns_empty_function_output_without_response` -> tests/test_core_realtime_conversation.py
- `conversation_mirrors_assistant_message_text_to_realtime_handoff` -> tests/test_core_realtime_conversation.py
- `conversation_handoff_persists_across_item_done_until_turn_complete` -> tests/test_core_realtime_conversation.py
- `inbound_handoff_request_starts_turn` -> tests/test_core_realtime_conversation.py
- `inbound_handoff_request_uses_active_transcript` -> tests/test_core_realtime_conversation.py
- `inbound_handoff_request_sends_transcript_delta_after_each_handoff` -> tests/test_core_realtime_conversation.py
- `inbound_conversation_item_does_not_start_turn_and_still_forwards_audio` -> tests/test_core_realtime_conversation.py
- `delegated_turn_user_role_echo_does_not_redelegate_and_still_forwards_audio` -> tests/test_core_realtime_conversation.py
- `inbound_handoff_request_does_not_block_realtime_event_forwarding` -> tests/test_core_realtime_conversation.py
- `inbound_handoff_request_steers_active_turn` -> tests/test_core_realtime_conversation.py
- `inbound_handoff_request_starts_turn_and_does_not_block_realtime_audio` -> tests/test_core_realtime_conversation.py

#### `codex/codex-rs/core/tests/suite/remote_env.rs`

- `remote_test_env_can_connect_and_use_filesystem` -> tests/test_core_suite_remote_env.py
- `exec_command_routes_to_selected_remote_environment` -> tests/test_core_suite_remote_env.py
- `apply_patch_freeform_routes_to_selected_remote_environment` -> tests/test_core_suite_remote_env.py
- `apply_patch_approvals_are_remembered_per_environment` -> tests/test_core_suite_remote_env.py
- `apply_patch_intercepted_exec_command_routes_to_selected_remote_environment` -> tests/test_core_suite_remote_env.py
- `remote_test_env_sandboxed_read_allows_readable_root` -> tests/test_core_suite_remote_env.py
- `remote_test_env_sandboxed_read_rejects_symlink_parent_dotdot_escape` -> tests/test_core_suite_remote_env.py
- `remote_test_env_remove_removes_symlink_not_target` -> tests/test_core_suite_remote_env.py
- `remote_test_env_copy_preserves_symlink_source` -> tests/test_core_suite_remote_env.py

#### `codex/codex-rs/core/tests/suite/remote_models.rs`

- `remote_models_get_model_info_uses_longest_matching_prefix` -> tests/test_core_suite_remote_models.py
- `remote_models_config_context_window_override_clamps_to_max_context_window` -> tests/test_core_suite_remote_models.py
- `remote_models_config_override_above_max_uses_max_context_window` -> tests/test_core_suite_remote_models.py
- `remote_models_use_context_window_when_config_override_is_absent` -> tests/test_core_suite_remote_models.py
- `remote_models_long_model_slug_is_sent_with_high_reasoning` -> tests/test_core_suite_remote_models.py
- `namespaced_model_slug_uses_catalog_metadata_without_fallback_warning` -> tests/test_core_suite_remote_models.py
- `remote_models_remote_model_uses_unified_exec` -> tests/test_core_suite_remote_models.py
- `remote_models_truncation_policy_without_override_preserves_remote` -> tests/test_core_suite_remote_models.py
- `remote_models_truncation_policy_with_tool_output_override` -> tests/test_core_suite_remote_models.py
- `remote_models_apply_remote_base_instructions` -> tests/test_core_suite_remote_models.py
- `remote_models_do_not_append_removed_builtin_presets` -> tests/test_core_suite_remote_models.py
- `remote_models_merge_adds_new_high_priority_first` -> tests/test_core_suite_remote_models.py
- `remote_models_merge_replaces_overlapping_model` -> tests/test_core_suite_remote_models.py
- `remote_models_merge_preserves_bundled_models_on_empty_response` -> tests/test_core_suite_remote_models.py
- `remote_models_request_times_out_after_5s` -> tests/test_core_suite_remote_models.py
- `remote_models_hide_picker_only_models` -> tests/test_core_suite_remote_models.py

#### `codex/codex-rs/core/tests/suite/request_compression.rs`

- `request_body_is_zstd_compressed_for_codex_backend_when_enabled` -> tests/test_core_suite_request_compression.py
- `request_body_is_not_compressed_for_api_key_auth_even_when_enabled` -> tests/test_core_suite_request_compression.py

#### `codex/codex-rs/core/tests/suite/request_permissions.rs`

- `with_additional_permissions_requires_approval_under_on_request` -> todo
- `request_permissions_tool_is_auto_denied_when_granular_request_permissions_is_disabled` -> todo
- `relative_additional_permissions_resolve_against_tool_workdir` -> todo
- `read_only_with_additional_permissions_does_not_widen_to_unrequested_cwd_write` -> todo
- `read_only_with_additional_permissions_does_not_widen_to_unrequested_tmp_write` -> todo
- `workspace_write_with_additional_permissions_can_write_outside_cwd` -> todo
- `with_additional_permissions_denied_approval_blocks_execution` -> todo
- `request_permissions_grants_apply_to_later_exec_command_calls` -> todo
- `request_permissions_preapprove_explicit_exec_permissions_outside_on_request` -> todo
- `request_permissions_grants_apply_to_later_shell_command_calls` -> todo
- `request_permissions_grants_apply_to_later_shell_command_calls_without_inline_permission_feature` -> todo
- `partial_request_permissions_grants_do_not_preapprove_new_permissions` -> todo
- `request_permissions_grants_do_not_carry_across_turns` -> todo
- `request_permissions_session_grants_carry_across_turns` -> todo

#### `codex/codex-rs/core/tests/suite/request_permissions_tool.rs`

- `approved_folder_write_request_permissions_unblocks_later_exec_without_sandbox_args` -> tests/test_core_suite_request_permissions_tool.py
- `approved_folder_write_request_permissions_unblocks_later_apply_patch` -> tests/test_core_suite_request_permissions_tool.py

#### `codex/codex-rs/core/tests/suite/request_plugin_install.rs`

- `request_plugin_install_is_available_without_search_tool_after_discovery_attempts` -> todo

#### `codex/codex-rs/core/tests/suite/request_user_input.rs`

- `request_user_input_round_trip_resolves_pending` -> todo
- `request_user_input_interrupt_emits_deferred_token_count` -> todo
- `request_user_input_rejected_in_execute_mode_alias` -> todo
- `request_user_input_rejected_in_default_mode_by_default` -> todo
- `request_user_input_round_trip_in_default_mode_with_feature` -> todo
- `request_user_input_rejected_in_pair_mode_alias` -> todo

#### `codex/codex-rs/core/tests/suite/responses_api_proxy_headers.rs`

- `responses_api_parent_and_subagent_requests_include_identity_headers` -> tests/test_core_suite_responses_api_proxy_headers.py

#### `codex/codex-rs/core/tests/suite/resume.rs`

- `resume_includes_initial_messages_from_rollout_events` -> todo
- `resume_includes_initial_messages_from_reasoning_events` -> todo
- `resume_switches_models_preserves_base_instructions` -> todo
- `resume_model_switch_is_not_duplicated_after_pre_turn_override` -> todo

#### `codex/codex-rs/core/tests/suite/resume_warning.rs`

- `emits_warning_when_resumed_model_differs` -> tests/test_core_suite_resume_warning.py

#### `codex/codex-rs/core/tests/suite/review.rs`

- `review_op_emits_lifecycle_and_review_output` -> todo
- `review_uses_custom_review_model_from_config` -> todo
- `review_uses_session_model_when_review_model_unset` -> todo
- `review_history_surfaces_in_parent_session` -> todo
- `review_uses_overridden_cwd_for_base_branch_merge_base` -> todo

#### `codex/codex-rs/core/tests/suite/rmcp_client.rs`

- `stdio_server_round_trip` -> todo
- `stdio_server_uses_configured_cwd_before_runtime_fallback` -> todo
- `local_stdio_server_uses_runtime_fallback_cwd_when_config_omits_cwd` -> todo
- `stdio_mcp_tool_call_includes_sandbox_state_meta` -> todo
- `stdio_mcp_parallel_tool_calls_default_false_runs_serially` -> todo
- `stdio_mcp_read_only_tool_calls_run_concurrently_without_server_opt_in` -> todo
- `stdio_mcp_parallel_tool_calls_opt_in_runs_concurrently` -> todo
- `stdio_image_responses_round_trip` -> todo
- `stdio_image_responses_preserve_original_detail_metadata` -> todo
- `stdio_image_responses_are_sanitized_for_text_only_model` -> todo
- `stdio_server_propagates_whitelisted_env_vars` -> todo
- `stdio_server_propagates_explicit_local_env_var_source` -> todo
- `remote_stdio_env_var_source_does_not_copy_local_env` -> todo
- `streamable_http_tool_call_round_trip` -> todo
- `streamable_http_with_oauth_round_trip` -> todo

#### `codex/codex-rs/core/tests/suite/rollout_list_find.rs`

- `find_locates_rollout_file_by_id` -> todo
- `find_handles_gitignore_covering_codex_home_directory` -> todo
- `find_prefers_sqlite_path_by_id` -> todo
- `find_falls_back_to_filesystem_when_sqlite_has_no_match` -> todo
- `find_ignores_granular_gitignore_rules` -> todo
- `find_locates_rollout_file_written_by_recorder` -> todo
- `find_archived_locates_rollout_file_by_id` -> todo

#### `codex/codex-rs/core/tests/suite/safety_check_downgrade.rs`

- `openai_model_header_mismatch_emits_warning_event` -> todo
- `cyber_policy_response_emits_typed_error_without_retry` -> todo
- `response_model_field_mismatch_emits_warning_when_header_matches_requested` -> todo
- `openai_model_header_mismatch_only_emits_one_warning_per_turn` -> todo
- `openai_model_header_casing_only_mismatch_does_not_warn` -> todo
- `model_verification_emits_structured_event_without_reroute_or_warning` -> todo
- `model_verification_only_emits_once_per_turn` -> todo

#### `codex/codex-rs/core/tests/suite/search_tool.rs`

- `search_tool_enabled_by_default_adds_tool_search` -> todo
- `always_defer_feature_hides_small_app_tool_sets` -> todo
- `app_search_sources_are_hidden_for_api_key_auth` -> todo
- `search_tool_adds_discovery_instructions_to_tool_description` -> todo
- `search_tool_hides_apps_tools_without_search` -> todo
- `explicit_app_mentions_respect_always_defer` -> todo
- `tool_search_returns_deferred_tools_without_follow_up_tool_injection` -> todo
- `tool_search_returns_deferred_v1_multi_agent_tools` -> todo
- `tool_search_returns_deferred_dynamic_tool_and_routes_follow_up_call` -> todo
- `tool_search_indexes_only_enabled_non_app_mcp_tools` -> todo
- `tool_search_surfaced_mcp_tool_errors_are_returned_to_model` -> todo
- `tool_search_uses_non_app_mcp_server_instructions_as_namespace_description` -> todo
- `tool_search_matches_mcp_tools_by_distinct_name_description_and_schema_terms` -> todo
- `tool_search_matches_dynamic_tools_by_name_description_namespace_and_schema_terms` -> todo

#### `codex/codex-rs/core/tests/suite/shell_command.rs`

- `shell_command_works` -> todo
- `output_with_login` -> todo
- `output_without_login` -> todo
- `multi_line_output_with_login` -> todo
- `pipe_output_with_login` -> todo
- `pipe_output_without_login` -> todo
- `shell_command_times_out_with_timeout_ms` -> todo
- `unicode_output` -> todo
- `unicode_output_with_newlines` -> todo

#### `codex/codex-rs/core/tests/suite/shell_serialization.rs`

- `shell_output_preserves_fixture_json_as_freeform` -> todo
- `shell_output_records_duration` -> todo
- `apply_patch_custom_tool_call_creates_file` -> todo
- `apply_patch_custom_tool_call_updates_existing_file` -> todo
- `apply_patch_custom_tool_call_reports_failure_output` -> todo
- `shell_output_is_freeform_for_nonzero_exit` -> todo
- `shell_command_output_is_freeform` -> todo
- `shell_command_output_is_not_truncated_under_10k_bytes` -> todo
- `shell_command_output_is_not_truncated_over_10k_bytes` -> todo

#### `codex/codex-rs/core/tests/suite/shell_snapshot.rs`

- `linux_unified_exec_uses_shell_snapshot` -> todo
- `linux_shell_command_uses_shell_snapshot` -> todo
- `shell_command_snapshot_preserves_shell_environment_policy_set` -> todo
- `linux_unified_exec_snapshot_preserves_shell_environment_policy_set` -> todo
- `shell_command_snapshot_still_intercepts_apply_patch` -> todo
- `shell_snapshot_deleted_after_shutdown_with_skills` -> todo
- `macos_unified_exec_uses_shell_snapshot` -> todo
- `windows_unified_exec_uses_shell_snapshot` -> todo

#### `codex/codex-rs/core/tests/suite/skill_approval.rs`

- `shell_zsh_fork_skill_scripts_ignore_declared_permissions` -> todo
- `shell_zsh_fork_still_enforces_workspace_write_sandbox` -> todo

#### `codex/codex-rs/core/tests/suite/skills.rs`

- `user_turn_includes_skill_instructions` -> todo

#### `codex/codex-rs/core/tests/suite/spawn_agent_description.rs`

- `spawn_agent_description_lists_visible_models_and_reasoning_efforts` -> todo

#### `codex/codex-rs/core/tests/suite/sqlite_state.rs`

- `new_thread_is_recorded_in_state_db` -> todo
- `resume_restores_dynamic_tools_from_rollout_with_sqlite_enabled` -> todo
- `backfill_scans_existing_rollouts` -> todo
- `user_messages_persist_in_state_db` -> todo
- `web_search_marks_thread_memory_mode_polluted_when_configured` -> todo
- `mcp_call_marks_thread_memory_mode_polluted_when_configured` -> todo
- `tool_call_logs_include_thread_id` -> todo

#### `codex/codex-rs/core/tests/suite/stream_error_allows_next_turn.rs`

- `continue_after_stream_error` -> todo

#### `codex/codex-rs/core/tests/suite/stream_no_completed.rs`

- `retries_on_early_close` -> todo

#### `codex/codex-rs/core/tests/suite/subagent_notifications.rs`

- `subagent_start_replaces_session_start_and_injects_context` -> todo
- `subagent_stop_replaces_stop_and_skips_internal_subagents` -> todo
- `subagent_notification_is_included_without_wait` -> todo
- `spawned_child_receives_forked_parent_context` -> todo
- `spawn_agent_requested_model_and_reasoning_override_inherited_settings_without_role` -> todo
- `spawned_multi_agent_v2_child_inherits_parent_developer_context` -> todo
- `skills_toggle_skips_instructions_for_parent_and_spawned_child` -> todo
- `spawn_agent_role_overrides_requested_model_and_reasoning_settings` -> todo
- `spawn_agent_tool_description_mentions_role_locked_settings` -> todo

#### `codex/codex-rs/core/tests/suite/tool_harness.rs`

- `shell_command_tool_executes_command_and_streams_output` -> todo
- `update_plan_tool_emits_plan_update_event` -> todo
- `update_plan_tool_rejects_malformed_payload` -> todo
- `apply_patch_tool_executes_and_emits_patch_events` -> todo
- `apply_patch_reports_parse_diagnostics` -> todo

#### `codex/codex-rs/core/tests/suite/tool_parallelism.rs`

- `read_file_tools_run_in_parallel` -> `tests/test_core_suite_tool_parallelism.py::test_read_file_tools_run_in_parallel`
- `shell_tools_run_in_parallel` -> `tests/test_core_suite_tool_parallelism.py::test_shell_tools_run_in_parallel`
- `mixed_parallel_tools_run_in_parallel` -> `tests/test_core_suite_tool_parallelism.py::test_mixed_parallel_tools_run_in_parallel`
- `tool_results_grouped` -> `tests/test_core_suite_tool_parallelism.py::test_tool_results_grouped`
- `shell_tools_start_before_response_completed_when_stream_delayed` -> `tests/test_core_suite_tool_parallelism.py::test_shell_tools_start_before_response_completed_when_stream_delayed`

#### `codex/codex-rs/core/tests/suite/tools.rs`

- `empty_turn_environments_omits_environment_backed_tools` -> `tests/test_core_suite_tools.py::test_empty_turn_environments_omits_environment_backed_tools`
- `turn_environment_selection_keeps_environment_backed_tools` -> `tests/test_core_suite_tools.py::test_turn_environment_selection_keeps_environment_backed_tools`
- `custom_tool_unknown_returns_custom_output_error` -> `tests/test_core_suite_tools.py::test_custom_tool_unknown_returns_custom_output_error`
- `shell_command_escalated_permissions_rejected_then_ok` -> `tests/test_core_suite_tools.py::test_shell_command_escalated_permissions_rejected_then_ok`
- `sandbox_denied_shell_command_returns_original_output` -> `tests/test_core_suite_tools.py::test_sandbox_denied_shell_command_returns_original_output`
- `shell_command_enforces_glob_deny_read_policy` -> `tests/test_core_suite_tools.py::test_shell_command_enforces_glob_deny_read_policy`
- `unified_exec_spec_toggle_end_to_end` -> `tests/test_core_suite_tools.py::test_unified_exec_spec_toggle_end_to_end`
- `shell_command_timeout_includes_timeout_prefix_and_metadata` -> `tests/test_core_suite_tools.py::test_shell_command_timeout_includes_timeout_prefix_and_metadata`
- `shell_command_timeout_handles_background_grandchild_stdout` -> `tests/test_core_suite_tools.py::test_shell_command_timeout_handles_background_grandchild_stdout`

#### `codex/codex-rs/core/tests/suite/truncation.rs`

- `tool_call_output_configured_limit_chars_type` -> `tests/test_core_suite_truncation.py::test_tool_call_output_configured_limit_chars_type`
- `tool_call_output_exceeds_limit_truncated_chars_limit` -> `tests/test_core_suite_truncation.py::test_tool_call_output_exceeds_limit_truncated_chars_limit`
- `tool_call_output_exceeds_limit_truncated_for_model` -> `tests/test_core_suite_truncation.py::test_tool_call_output_exceeds_limit_truncated_for_model`
- `tool_call_output_truncated_only_once` -> `tests/test_core_suite_truncation.py::test_tool_call_output_truncated_only_once`
- `mcp_tool_call_output_exceeds_limit_truncated_for_model` -> `tests/test_core_suite_truncation.py::test_mcp_tool_call_output_exceeds_limit_truncated_for_model`
- `mcp_image_output_preserves_image_and_no_text_summary` -> `tests/test_core_suite_truncation.py::test_mcp_image_output_preserves_image_and_no_text_summary`
- `token_policy_marker_reports_tokens` -> `tests/test_core_suite_truncation.py::test_token_policy_marker_reports_tokens`
- `byte_policy_marker_reports_bytes` -> `tests/test_core_suite_truncation.py::test_byte_policy_marker_reports_bytes`
- `shell_command_output_not_truncated_with_custom_limit` -> `tests/test_core_suite_truncation.py::test_shell_command_output_not_truncated_with_custom_limit`
- `mcp_tool_call_output_not_truncated_with_custom_limit` -> `tests/test_core_suite_truncation.py::test_mcp_tool_call_output_not_truncated_with_custom_limit`

#### `codex/codex-rs/core/tests/suite/turn_state.rs`

- `responses_turn_state_persists_within_turn_and_resets_after` -> `tests/test_core_suite_turn_state.py::test_responses_turn_state_persists_within_turn_and_resets_after`
- `websocket_turn_state_persists_within_turn_and_resets_after` -> `tests/test_core_suite_turn_state.py::test_websocket_turn_state_persists_within_turn_and_resets_after`

#### `codex/codex-rs/core/tests/suite/unified_exec.rs`

- `unified_exec_intercepts_apply_patch_exec_command` -> todo
- `unified_exec_emits_exec_command_begin_event` -> todo
- `unified_exec_resolves_relative_workdir` -> todo
- `unified_exec_respects_workdir_override` -> todo
- `unified_exec_emits_exec_command_end_event` -> todo
- `unified_exec_emits_output_delta_for_exec_command` -> todo
- `unified_exec_full_lifecycle_with_background_end_event` -> todo
- `unified_exec_network_denial_emits_failed_background_end_event` -> todo
- `unified_exec_short_lived_network_denial_emits_failed_end_event` -> todo
- `unified_exec_emits_terminal_interaction_for_write_stdin` -> todo
- `unified_exec_terminal_interaction_captures_delayed_output` -> todo
- `unified_exec_emits_one_begin_and_one_end_event` -> todo
- `exec_command_reports_chunk_and_exit_metadata` -> todo
- `exec_command_clamps_model_requested_max_output_tokens_to_policy` -> todo
- `write_stdin_clamps_model_requested_max_output_tokens_to_policy` -> todo
- `unified_exec_defaults_to_pipe` -> todo
- `unified_exec_can_enable_tty` -> todo
- `unified_exec_respects_early_exit_notifications` -> todo
- `write_stdin_returns_exit_metadata_and_clears_session` -> todo
- `unified_exec_emits_end_event_when_session_dies_via_stdin` -> todo
- `unified_exec_keeps_long_running_session_after_turn_end` -> todo
- `unified_exec_interrupt_preserves_long_running_session` -> todo
- `unified_exec_reuses_session_via_stdin` -> todo
- `unified_exec_streams_after_lagged_output` -> todo
- `unified_exec_timeout_and_followup_poll` -> todo
- `unified_exec_formats_large_output_summary` -> todo
- `unified_exec_runs_under_sandbox` -> todo
- `unified_exec_enforces_glob_deny_read_policy` -> todo
- `unified_exec_python_prompt_under_seatbelt` -> todo
- `unified_exec_runs_on_all_platforms` -> todo
- `unified_exec_prunes_exited_sessions_first` -> todo

#### `codex/codex-rs/core/tests/suite/unstable_features_warning.rs`

- `emits_warning_when_unstable_features_enabled_via_config` -> `tests/test_core_suite_unstable_features_warning.py::test_emits_warning_when_unstable_features_enabled_via_config`
- `suppresses_warning_when_configured` -> `tests/test_core_suite_unstable_features_warning.py::test_suppresses_warning_when_configured`

#### `codex/codex-rs/core/tests/suite/user_notification.rs`

- `summarize_context_three_requests_and_instructions` -> `tests/test_core_suite_user_notification.py::test_summarize_context_three_requests_and_instructions`

#### `codex/codex-rs/core/tests/suite/user_shell_cmd.rs`

- `user_shell_cmd_ls_and_cat_in_temp_dir` -> `tests/test_core_suite_user_shell_cmd.py::test_user_shell_cmd_ls_and_cat_in_temp_dir`
- `user_shell_cmd_can_be_interrupted` -> `tests/test_core_suite_user_shell_cmd.py::test_user_shell_cmd_can_be_interrupted`
- `user_shell_command_does_not_replace_active_turn` -> `tests/test_core_suite_user_shell_cmd.py::test_user_shell_command_does_not_replace_active_turn`
- `user_shell_command_history_is_persisted_and_shared_with_model` -> `tests/test_core_suite_user_shell_cmd.py::test_user_shell_command_history_is_persisted_and_shared_with_model`
- `user_shell_command_does_not_set_network_sandbox_env_var` -> `tests/test_core_suite_user_shell_cmd.py::test_user_shell_command_does_not_set_network_sandbox_env_var`
- `user_shell_command_output_is_truncated_in_history` -> `tests/test_core_suite_user_shell_cmd.py::test_user_shell_command_output_is_truncated_in_history`
- `user_shell_command_is_truncated_only_once` -> `tests/test_core_suite_user_shell_cmd.py::test_user_shell_command_is_truncated_only_once`

#### `codex/codex-rs/core/tests/suite/view_image.rs`

- `user_turn_with_local_image_attaches_image` -> `tests/test_core_suite_view_image.py::test_user_turn_with_local_image_attaches_image`
- `user_turn_with_vertical_local_image_resizes_to_square_bounds` -> `tests/test_core_suite_view_image.py::test_user_turn_with_vertical_local_image_resizes_to_square_bounds`
- `view_image_tool_attaches_local_image` -> `tests/test_core_suite_view_image.py::test_view_image_tool_attaches_local_image`
- `view_image_routes_to_selected_local_environment` -> `tests/test_core_suite_view_image.py::test_view_image_routes_to_selected_local_environment`
- `view_image_tool_applies_local_sandbox_read_denies` -> `tests/test_core_suite_view_image.py::test_view_image_tool_applies_local_sandbox_read_denies`
- `view_image_routes_to_selected_remote_environment` -> `tests/test_core_suite_view_image.py::test_view_image_routes_to_selected_remote_environment`
- `view_image_tool_can_preserve_original_resolution_when_requested_on_gpt5_3_codex` -> `tests/test_core_suite_view_image.py::test_view_image_tool_can_preserve_original_resolution_when_requested_on_gpt5_3_codex`
- `view_image_tool_errors_clearly_for_unsupported_detail_values` -> `tests/test_core_suite_view_image.py::test_view_image_tool_errors_clearly_for_unsupported_detail_values`
- `view_image_tool_treats_null_detail_as_omitted` -> `tests/test_core_suite_view_image.py::test_view_image_tool_treats_null_detail_as_omitted`
- `view_image_tool_resizes_when_model_lacks_original_detail_support` -> `tests/test_core_suite_view_image.py::test_view_image_tool_resizes_when_model_lacks_original_detail_support`
- `view_image_tool_does_not_force_original_resolution_with_capability_only` -> `tests/test_core_suite_view_image.py::test_view_image_tool_does_not_force_original_resolution_with_capability_only`
- `view_image_tool_errors_when_path_is_directory` -> `tests/test_core_suite_view_image.py::test_view_image_tool_errors_when_path_is_directory`
- `view_image_tool_errors_for_non_image_files` -> `tests/test_core_suite_view_image.py::test_view_image_tool_errors_for_non_image_files`
- `view_image_tool_errors_when_file_missing` -> `tests/test_core_suite_view_image.py::test_view_image_tool_errors_when_file_missing`
- `view_image_tool_returns_unsupported_message_for_text_only_model` -> `tests/test_core_suite_view_image.py::test_view_image_tool_returns_unsupported_message_for_text_only_model`
- `replaces_invalid_local_image_after_bad_request` -> `tests/test_core_suite_view_image.py::test_replaces_invalid_local_image_after_bad_request`

#### `codex/codex-rs/core/tests/suite/web_search.rs`

- `web_search_mode_cached_sets_external_web_access_false` -> todo
- `web_search_mode_takes_precedence_over_legacy_flags` -> todo
- `web_search_mode_defaults_to_cached_when_features_disabled` -> todo
- `web_search_mode_updates_between_turns_with_permission_profile` -> todo
- `web_search_tool_config_from_config_toml_is_forwarded_to_request` -> todo

#### `codex/codex-rs/core/tests/suite/websocket_fallback.rs`

- `websocket_fallback_switches_to_http_on_upgrade_required_connect` -> `tests/test_core_suite_websocket_fallback.py::test_websocket_fallback_switches_to_http_on_upgrade_required_connect`
- `websocket_fallback_switches_to_http_after_retries_exhausted` -> `tests/test_core_suite_websocket_fallback.py::test_websocket_fallback_switches_to_http_after_retries_exhausted`
- `websocket_fallback_hides_first_websocket_retry_stream_error` -> `tests/test_core_suite_websocket_fallback.py::test_websocket_fallback_hides_first_websocket_retry_stream_error`
- `websocket_fallback_is_sticky_across_turns` -> `tests/test_core_suite_websocket_fallback.py::test_websocket_fallback_is_sticky_across_turns`

#### `codex/codex-rs/core/tests/suite/window_headers.rs`

- `window_id_advances_after_compact_persists_on_resume_and_resets_on_fork` -> `tests/test_core_suite_window_headers.py::test_window_id_advances_after_compact_persists_on_resume_and_resets_on_fork`

#### `codex/codex-rs/core/tests/suite/windows_sandbox.rs`

- `windows_restricted_token_rejects_exact_and_glob_deny_read_policy` -> todo
- `windows_elevated_enforces_exact_and_glob_deny_read_policy` -> todo



















