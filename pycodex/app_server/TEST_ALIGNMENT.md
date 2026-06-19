# codex-app-server test alignment

Rust crate: `codex-app-server`

Python package: `pycodex/app_server`

Status: `complete`

## 2026-06-19 crate validation

`codex-app-server` is complete for the current Python porting scope. All
module status files and README module-map rows are complete.

Validation used the app-server-only test set: 60 `tests/test_app_server*.py`
files excluding sibling crates `test_app_server_client*` and
`test_app_server_protocol_common.py`.

- `python -m pytest @($tests) -q` -> 584 passed.
- `python -m compileall -q pycodex/app_server @($tests)` -> passed.

The broader `test_app_server*` glob also selects tests owned by
`codex-app-server-client` and `codex-app-server-protocol`; those sibling-crate
failures are not app-server completion evidence.

## Rust modules

- `src/lib.rs`
  -> `pycodex/app_server/__init__.py`
  -> `tests/test_app_server_lib_rs.py`
- `src/main.rs`
  -> `pycodex/app_server/main.py`
  -> `tests/test_app_server_main_rs.py`
- `src/mcp_refresh.rs`
  -> `pycodex/app_server/mcp_refresh.py`
  -> `tests/test_app_server_mcp_refresh_rs.py`
- `src/models.rs`
  -> `pycodex/app_server/models.py`
  -> `tests/test_app_server_models_rs.py`
- `src/outgoing_message.rs`
  -> `pycodex/app_server/outgoing_message.py`
  -> `tests/test_app_server_outgoing_message_rs.py`
- `src/request_serialization.rs`
  -> `pycodex/app_server/request_serialization.py`
  -> `tests/test_app_server_request_serialization_rs.py`
- `src/analytics_utils.rs`
  -> `pycodex/app_server/analytics_utils.py`
  -> `tests/test_app_server_analytics_utils_rs.py`
- `src/app_server_tracing.rs`
  -> `pycodex/app_server/app_server_tracing.py`
  -> `tests/test_app_server_tracing_rs.py`
- `src/attestation.rs`
  -> `pycodex/app_server/attestation.py`
  -> `tests/test_app_server_attestation_rs.py`
- `src/bespoke_event_handling.rs`
  -> `pycodex/app_server/bespoke_event_handling.py`
  -> `tests/test_app_server_bespoke_event_handling_rs.py`
- `src/bin/notify_capture.rs`
  -> `pycodex/app_server/bin/notify_capture.py`
  -> `tests/test_app_server_bin_notify_capture_rs.py`
- `src/bin/test_notify_capture.rs`
  -> `pycodex/app_server/bin/test_notify_capture.py`
  -> `tests/test_app_server_bin_test_notify_capture_rs.py`
- `src/command_exec.rs`
  -> `pycodex/app_server/command_exec.py`
  -> `tests/test_app_server_command_exec_rs.py`
- `src/config/mod.rs`
  -> `pycodex/app_server/config/__init__.py`
  -> `tests/test_app_server_config_mod_rs.py`
- `src/config/external_agent_config.rs`
  -> `pycodex/app_server/config/external_agent_config.py`
  -> `tests/test_app_server_config_external_agent_config_rs.py`
- `src/connection_rpc_gate.rs`
  -> `pycodex/app_server/connection_rpc_gate.py`
  -> `tests/test_app_server_connection_rpc_gate_rs.py`
- `src/config_manager.rs`
  -> `pycodex/app_server/config_manager.py`
  -> `tests/test_app_server_config_manager_rs.py`
- `src/config_manager_service.rs`
  -> `pycodex/app_server/config_manager_service.py`
  -> `tests/test_app_server_config_manager_service_rs.py`
- `src/dynamic_tools.rs`
  -> `pycodex/app_server/dynamic_tools.py`
  -> `tests/test_app_server_dynamic_tools_rs.py`
- `src/error_code.rs`
  -> `pycodex/app_server/error_code.py`
  -> `tests/test_app_server_error_code_rs.py`
- `src/extensions.rs`
  -> `pycodex/app_server/extensions.py`
  -> `tests/test_app_server_extensions_rs.py`
- `src/filters.rs`
  -> `pycodex/app_server/filters.py`
  -> `tests/test_app_server_filters_rs.py`
- `src/fs_watch.rs`
  -> `pycodex/app_server/fs_watch.py`
  -> `tests/test_app_server_fs_watch_rs.py`
- `src/fuzzy_file_search.rs`
  -> `pycodex/app_server/fuzzy_file_search.py`
  -> `tests/test_app_server_fuzzy_file_search_rs.py`
- `src/in_process.rs`
  -> `pycodex/app_server/in_process.py`
  -> `tests/test_app_server_in_process_rs.py`
- `src/message_processor.rs`
  -> `pycodex/app_server/message_processor.py`
  -> `tests/test_app_server_message_processor_rs.py`
- `src/request_processors/initialize_processor.rs`
  -> `pycodex/app_server/request_processors_initialize_processor.py`
  -> `tests/test_app_server_request_processors_initialize_processor_rs.py`
- `src/request_processors/marketplace_processor.rs`
  -> `pycodex/app_server/request_processors_marketplace_processor.py`
  -> `tests/test_app_server_request_processors_marketplace_processor_rs.py`
- `src/request_processors/mcp_processor.rs`
  -> `pycodex/app_server/request_processors_mcp_processor.py`
  -> `tests/test_app_server_request_processors_mcp_processor_rs.py`
- `src/request_processors/plugins.rs`
  -> `pycodex/app_server/request_processors_plugins.py`
  -> `tests/test_app_server_request_processors_plugins_rs.py`
- `src/request_processors.rs`
  -> `pycodex/app_server/request_processors.py`
  -> `tests/test_app_server_request_processors_rs.py`
- `src/request_processors/account_processor.rs`
  -> `pycodex/app_server/request_processors_account_processor.py`
  -> `tests/test_app_server_request_processors_account_processor_rs.py`
- `src/request_processors/apps_processor.rs`
  -> `pycodex/app_server/request_processors_apps_processor.py`
  -> `tests/test_app_server_request_processors_apps_processor_rs.py`
- `src/request_processors/catalog_processor.rs`
  -> `pycodex/app_server/request_processors_catalog_processor.py`
  -> `tests/test_app_server_request_processors_catalog_processor_rs.py`
- `src/request_processors/command_exec_processor.rs`
  -> `pycodex/app_server/request_processors_command_exec_processor.py`
  -> `tests/test_app_server_request_processors_command_exec_processor_rs.py`
- `src/request_processors/config_processor.rs`
  -> `pycodex/app_server/request_processors_config_processor.py`
  -> `tests/test_app_server_request_processors_config_processor_rs.py`
- `src/request_processors/config_errors.rs`
  -> `pycodex/app_server/request_processors_config_errors.py`
  -> `tests/test_app_server_request_processors_config_errors_rs.py`
- `src/request_processors/environment_processor.rs`
  -> `pycodex/app_server/request_processors_environment_processor.py`
  -> `tests/test_app_server_request_processors_environment_processor_rs.py`
- `src/request_processors/external_agent_config_processor.rs`
  -> `pycodex/app_server/request_processors_external_agent_config_processor.py`
  -> `tests/test_app_server_request_processors_external_agent_config_processor_rs.py`
- `src/request_processors/feedback_doctor_report.rs`
  -> `pycodex/app_server/request_processors_feedback_doctor_report.py`
  -> `tests/test_app_server_request_processors_feedback_doctor_report_rs.py`
- `src/request_processors/feedback_processor.rs`
  -> `pycodex/app_server/request_processors_feedback_processor.py`
  -> `tests/test_app_server_request_processors_feedback_processor_rs.py`
- `src/request_processors/fs_processor.rs`
  -> `pycodex/app_server/request_processors_fs_processor.py`
  -> `tests/test_app_server_request_processors_fs_processor_rs.py`
- `src/request_processors/git_processor.rs`
  -> `pycodex/app_server/request_processors_git_processor.py`
  -> `tests/test_app_server_request_processors_git_processor_rs.py`
- `src/request_processors/process_exec_processor.rs`
  -> `pycodex/app_server/request_processors_process_exec_processor.py`
  -> `tests/test_app_server_request_processors_process_exec_processor_rs.py`
- `src/request_processors/remote_control_processor.rs`
  -> `pycodex/app_server/request_processors_remote_control_processor.py`
  -> `tests/test_app_server_request_processors_remote_control_processor_rs.py`
- `src/request_processors/request_errors.rs`
  -> `pycodex/app_server/request_processors_request_errors.py`
  -> `tests/test_app_server_request_processors_request_errors_rs.py`
- `src/request_processors/search.rs`
  -> `pycodex/app_server/request_processors_search.py`
  -> `tests/test_app_server_request_processors_search_rs.py`
- `src/request_processors/thread_goal_processor.rs`
  -> `pycodex/app_server/request_processors_thread_goal_processor.py`
  -> `tests/test_app_server_request_processors_thread_goal_processor_rs.py`
- `src/request_processors/thread_lifecycle.rs`
  -> `pycodex/app_server/request_processors_thread_lifecycle.py`
  -> `tests/test_app_server_request_processors_thread_lifecycle_rs.py`
- `src/request_processors/thread_processor.rs`
  -> `pycodex/app_server/request_processors_thread_processor.py`
  -> `tests/test_app_server_request_processors_thread_processor_rs.py`
- `src/request_processors/turn_processor.rs`
  -> `pycodex/app_server/request_processors_turn_processor.py`
  -> `tests/test_app_server_request_processors_turn_processor_rs.py`
- `src/request_processors/thread_summary.rs`
  -> `pycodex/app_server/request_processors_thread_summary.py`
  -> `tests/test_app_server_request_processors_thread_summary_rs.py`
- `src/request_processors/thread_resume_redaction.rs`
  -> `pycodex/app_server/request_processors_thread_resume_redaction.py`
  -> `tests/test_app_server_request_processors_thread_resume_redaction_rs.py`
- `src/request_processors/token_usage_replay.rs`
  -> `pycodex/app_server/request_processors_token_usage_replay.py`
  -> `tests/test_app_server_request_processors_token_usage_replay_rs.py`
- `src/request_processors/windows_sandbox_processor.rs`
  -> `pycodex/app_server/request_processors_windows_sandbox_processor.py`
  -> `tests/test_app_server_request_processors_windows_sandbox_processor_rs.py`
- `src/server_request_error.rs`
  -> `pycodex/app_server/server_request_error.py`
  -> `tests/test_app_server_server_request_error_rs.py`
- `src/skills_watcher.rs`
  -> `pycodex/app_server/skills_watcher.py`
  -> `tests/test_app_server_skills_watcher_rs.py`
- `src/thread_state.rs`
  -> `pycodex/app_server/thread_state.py`
  -> `tests/test_app_server_thread_state_rs.py`
- `src/thread_status.rs`
  -> `pycodex/app_server/thread_status.py`
  -> `tests/test_app_server_thread_status_rs.py`
- `src/transport.rs`
  -> `pycodex/app_server/transport.py`
  -> `tests/test_app_server_transport_rs.py`

All currently identified Rust source modules are mapped in Python. The crate
remains `partial` at the crate-status level until broader crate validation is
run, but `src/lib.rs` is complete and no longer has a
`run_main_with_transport_options(...)` implementation blocker.

## src/lib.rs

Rust source:

- `codex/codex-rs/app-server/src/lib.rs`

Rust local tests:

- `log_format_from_env_value_matches_json_values_case_insensitively`
- `log_format_from_env_value_defaults_for_non_json_values`

Python parity tests:

- `test_log_format_from_env_value_matches_json_values_case_insensitively`
- `test_log_format_from_env_value_defaults_for_non_json_values`
- `test_log_format_from_env_value_rejects_json_like_values`
- `test_log_format_from_env_reads_log_format_key`
- `test_crate_root_module_inventory_projection_matches_rust_declarations`
- `test_logging_subscriber_projection_assembles_default_layers`
- `test_logging_subscriber_projection_assembles_json_optional_layers_and_warnings`
- `test_runtime_startup_handles_projection_initializes_after_installation_id`
- `test_runtime_startup_handles_projection_stops_on_installation_id_error`
- `test_app_server_runtime_options_default_matches_rust`
- `test_run_main_default_transport_options_projects_rust_defaults`
- `test_runtime_transport_decisions_match_stdio_single_client_mode`
- `test_runtime_transport_decisions_enable_graceful_signal_for_non_stdio`
- `test_remote_control_runtime_decision_requires_request_and_state_db`
- `test_remote_control_runtime_decision_logs_when_requested_without_state_db`
- `test_remote_control_runtime_decision_reports_no_transport_errors`
- `test_transport_startup_projection_starts_stdio_connection`
- `test_transport_startup_projection_starts_unix_socket_acceptor`
- `test_transport_startup_projection_starts_websocket_acceptor_with_policy`
- `test_transport_startup_projection_off_starts_no_acceptor`
- `test_transport_startup_projection_rejects_unknown_transport`
- `test_transport_acceptor_startup_projection_starts_stdio_before_lock_drop`
- `test_transport_acceptor_startup_projection_unix_error_prevents_push_and_drop`
- `test_transport_acceptor_startup_projection_websocket_policy_error_prevents_acceptor`
- `test_transport_acceptor_startup_projection_websocket_success_pushes_handle`
- `test_transport_acceptor_startup_projection_off_only_drops_lock`
- `test_unix_socket_startup_lock_projection_skips_non_unix_transports`
- `test_unix_socket_startup_lock_projection_prepares_unix_socket`
- `test_unix_socket_startup_lock_projection_stops_on_lock_path_error`
- `test_unix_socket_startup_lock_projection_stops_on_acquire_error`
- `test_unix_socket_startup_lock_projection_stops_on_prepare_error`
- `test_remote_control_startup_projection_passes_stdio_client_name_receiver`
- `test_remote_control_startup_projection_preserves_disabled_flag`
- `test_remote_control_startup_projection_error_prevents_accept_handle_push`
- `test_app_text_range_projects_core_text_range_fields`
- `test_config_warning_from_error_uses_config_location_when_present`
- `test_config_warning_from_error_without_config_location_keeps_details_only`
- `test_exec_policy_warning_location_matches_parse_policy_branches`
- `test_analytics_rpc_transport_buckets_like_rust`
- `test_project_config_warning_lists_disabled_project_layers`
- `test_project_config_warning_returns_none_without_disabled_projects`
- `test_collect_config_warnings_preserves_rust_accumulation_order`
- `test_collect_config_warnings_omits_absent_optional_sources`
- `test_system_bwrap_warning_projection_appends_summary_only_notification`
- `test_system_bwrap_warning_projection_omits_absent_warning`
- `test_configured_thread_config_loader_defaults_to_noop`
- `test_configured_thread_config_loader_uses_remote_endpoint`
- `test_config_preload_projection_replaces_cloud_requirements_on_success`
- `test_config_preload_projection_warns_and_continues_on_failure`
- `test_config_provider_startup_projection_uses_env_manager_when_ignoring_user_config`
- `test_config_provider_startup_projection_maps_fallible_setup_order`
- `test_runtime_auth_manager_projection_disables_codex_api_key_env`
- `test_main_config_load_projection_uses_loaded_config_on_success`
- `test_main_config_load_projection_strict_failure_returns_original_error`
- `test_main_config_load_projection_nonstrict_failure_warns_and_loads_default`
- `test_main_config_load_projection_default_config_error_maps_invalid_data`
- `test_personality_migration_projection_skips_when_disabled`
- `test_personality_migration_projection_warns_on_deserialize_failure`
- `test_personality_migration_projection_reloads_after_applied_migration`
- `test_personality_migration_projection_maps_reload_error`
- `test_personality_migration_projection_ignores_skipped_statuses`
- `test_personality_migration_projection_warns_on_migration_error`
- `test_personality_migration_projection_rejects_unknown_status`
- `test_state_db_startup_projection_marks_state_db_available_on_success`
- `test_state_db_startup_projection_returns_sqlite_home_error_on_failure`
- `test_runtime_resource_startup_projection_starts_log_db_from_state_db`
- `test_runtime_resource_startup_projection_skips_log_db_without_state_db`
- `test_runtime_channel_startup_projection_uses_shared_channel_capacity`
- `test_telemetry_startup_projection_records_process_and_sqlite_on_success`
- `test_telemetry_startup_projection_maps_build_error_before_install`
- `test_outbound_control_event_opened_preserves_router_fields`
- `test_outbound_control_event_closed_and_disconnect_all_shapes`
- `test_outbound_router_startup_projection_initializes_biased_select_worker`
- `test_outbound_router_control_projection_inserts_opened_connection`
- `test_outbound_router_control_projection_removes_closed_connection`
- `test_outbound_router_control_projection_disconnects_and_clears_all`
- `test_outbound_router_control_projection_breaks_on_closed_channel`
  covers Rust's outbound-router-exited info log after loop break.
- `test_outbound_router_control_projection_rejects_negative_count`
- `test_outbound_router_outgoing_projection_routes_present_envelope`
- `test_outbound_router_outgoing_projection_breaks_on_closed_channel`
  covers Rust's outbound-router-exited info log after loop break.
  These tests cover only the `src/lib.rs` delegation/closed-channel branch;
  concrete `route_outgoing_envelope(...)` routing belongs to the sibling
  Rust `transport` module.
- `test_outgoing_message_runtime_projection_assembles_sender_and_analytics_client`
- `test_message_processor_args_projection_assembles_runtime_fields`
- `test_message_processor_args_projection_preserves_optional_state_and_plugin_task`
- `test_processor_startup_projection_initializes_loop_state`
- `test_processor_worker_spawn_projection_matches_rust_capture_boundary`
- `test_processor_select_topology_projection_matches_rust_arm_order_and_gates`
- `test_connection_opened_projection_creates_outbound_and_connection_state`
- `test_connection_opened_projection_breaks_when_outbound_control_send_fails`
- `test_connection_closed_projection_skips_unknown_connections`
- `test_connection_closed_projection_notifies_for_known_connections`
- `test_connection_closed_projection_breaks_when_outbound_control_send_fails`
- `test_connection_closed_projection_breaks_when_single_client_drains`
- `test_transport_event_channel_closed_projection_breaks_processor_loop`
- `test_incoming_request_projection_skips_unknown_connection`
  covers the Rust unknown-connection warning/drop branch.
- `test_incoming_request_projection_syncs_session_flags_after_processing`
- `test_incoming_request_projection_warns_when_opted_out_update_fails`
- `test_incoming_request_projection_triggers_initialize_side_effects_once`
  also covers forwarding `session.request_attestation()` to
  `connection_initialized`.
- `test_incoming_non_request_projection_routes_known_connections`
- `test_incoming_non_request_projection_drops_unknown_connections`
  covers Rust response/notification/error unknown-connection warning/drop
  behavior by message kind.
- `test_incoming_non_request_projection_rejects_unknown_kind`
- `test_remote_control_status_projection_ignores_closed_watcher`
- `test_remote_control_status_projection_ignores_unchanged_status`
- `test_remote_control_status_projection_notifies_on_change`
  cover Rust's continue-loop control flow for the status watcher branch.
- `test_thread_created_projection_attaches_initialized_connections_only`
- `test_thread_created_projection_lagged_keeps_listener_without_attach`
- `test_thread_created_projection_closed_disables_thread_listener`
  cover Rust thread-created watcher continue-loop behavior and lagged warnings.
- `test_thread_created_projection_rejects_unknown_result`
- `test_processor_exit_projection_cleans_up_when_not_forced`
- `test_processor_exit_projection_skips_cleanup_when_forced`
  cover Rust's unconditional processor-task-exited info log.
- `test_processor_loop_update_projection_finishes_with_disconnect_all`
- `test_processor_loop_update_projection_noop_continues_loop`
- `test_processor_shutdown_signal_projection_disabled_when_not_graceful`
- `test_processor_shutdown_signal_projection_disabled_when_forced`
- `test_processor_shutdown_signal_projection_error_continues_loop`
- `test_processor_shutdown_signal_projection_calls_on_signal_with_counts`
- `test_processor_running_turn_watcher_projection_disabled_until_shutdown_requested`
- `test_processor_running_turn_watcher_projection_continues_on_change`
- `test_processor_running_turn_watcher_projection_warns_when_closed`
- `test_runtime_finalization_projection_orders_shutdown_with_otel`
- `test_runtime_finalization_projection_skips_absent_otel`
- `test_runtime_finalization_projection_ignores_join_results`
- `test_runtime_finalization_projection_rejects_negative_handle_count`
- `test_shutdown_state_waits_for_running_turns_after_first_signal`
- `test_shutdown_state_finishes_when_no_turns_are_running`
- `test_shutdown_state_forceable_second_signal_forces_finish`
- `test_shutdown_state_repeated_graceful_signal_does_not_force`
- `test_shutdown_state_repeated_signals_do_not_reset_wait_log_count`
- `test_shutdown_signal_maps_ctrl_c_to_forceable`
- `test_shutdown_signal_maps_unix_terminate_to_forceable`
- `test_shutdown_signal_maps_unix_hangup_to_graceful_only`
- `test_shutdown_signal_non_unix_ignores_hangup_waiter`
- `test_run_main_executes_default_runtime_orchestration`
- `test_run_main_with_transport_options_runs_hooks_in_rust_order`
- `test_run_main_with_transport_options_errors_without_transport_or_remote_control`

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_lib_rs.py -q`
  -> `134 passed`.

## src/dynamic_tools.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/dynamic_tools.rs`

Rust local tests:

- None in module.

Python parity tests:

- `test_decode_response_accepts_camel_case_dynamic_tool_response`
- `test_decode_response_invalid_value_uses_rust_fallback_message`
- `test_fallback_response_uses_input_text_and_failure_success_flag`
- `test_core_response_from_app_server_response_preserves_items_and_success`
- `test_on_call_response_projection_success_builds_dynamic_tool_response_op`
- `test_on_call_response_projection_turn_transition_error_returns_without_submit`
- `test_on_call_response_projection_client_error_uses_request_failed_fallback`
- `test_on_call_response_projection_receiver_canceled_uses_request_failed_fallback`

Coverage notes:

- Covers Rust's local `decode_response(...)`, `fallback_response(...)`, and
  `on_call_response(...)` response decision tree through a deterministic
  projection.
- Real `oneshot::Receiver` awaiting, `CodexThread::submit(...)`, and tracing
  emission remain runtime integration boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_dynamic_tools_rs.py -q` -> 8 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/dynamic_tools.py tests/test_app_server_dynamic_tools_rs.py`.

## src/models.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/models.rs`

Rust local tests:

- None in module.

Python parity tests:

- `test_reasoning_efforts_from_preset_preserves_effort_and_description`
- `test_model_from_preset_projects_all_app_server_fields`
- `test_model_from_preset_marks_hidden_without_upgrade_or_nux`
- `test_supported_models_from_presets_filters_hidden_unless_requested`
- `test_supported_models_requests_online_if_uncached_strategy`

Coverage notes:

- Covers Rust's module-local `model_from_preset(...)`,
  `reasoning_efforts_from_preset(...)`, and `supported_models(...)`
  list/filter/map contract.
- Concrete `ThreadManager` model cache/online refresh behavior remains owned by
  runtime/model-manager dependencies.

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_models_rs.py -q`
  -> `5 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/models.py
  tests/test_app_server_models_rs.py`.

## src/skills_watcher.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/skills_watcher.rs`

Rust local tests:

- None in module.

Python parity tests:

- `test_skills_watcher_new_projection_records_real_watcher_setup`
- `test_skills_watcher_new_projection_falls_back_to_noop_watcher_on_init_error`
- `test_register_thread_config_without_environment_selection_returns_default_registration`
- `test_register_thread_config_unknown_environment_warns_and_returns_default`
- `test_register_thread_config_remote_environment_returns_default`
- `test_register_thread_config_local_environment_builds_skills_input_and_recursive_roots`
- `test_watch_paths_from_skill_roots_marks_every_root_recursive`
- `test_event_loop_iteration_clears_cache_and_sends_skills_changed`
- `test_event_loop_iteration_none_breaks_loop`
- `test_event_loop_spawn_without_runtime_warns_and_returns`
- `test_shutdown_projection_cancels_shutdown_token_and_constants_match_rust_cfgs`

Coverage notes:

- Covers Rust's local watcher setup fallback, shutdown, register-thread-config
  environment branches, recursive watch-path mapping, event-loop action, and
  no-runtime spawn warning branch through deterministic projections.
- Real file watcher subscriptions, throttled timing, Tokio task scheduling,
  cancellation tokens, and outgoing async delivery remain runtime integration
  boundaries.

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_skills_watcher_rs.py -q`
  -> 11 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/skills_watcher.py tests/test_app_server_skills_watcher_rs.py`.

## src/extensions.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/extensions.rs`

Rust local tests:

- `app_server_event_sink_forwards_thread_goal_updates`

Python parity tests:

- `test_thread_extensions_projection_records_rust_install_order`
- `test_app_server_thread_goal_from_core_preserves_goal_fields`
- `test_app_server_event_sink_forwards_thread_goal_updates`
- `test_app_server_event_sink_drops_unsupported_extension_events`
- `test_guardian_agent_spawn_projection_calls_spawn_subagent_when_manager_alive`
- `test_guardian_agent_spawn_projection_reports_dropped_thread_manager`

Coverage notes:

- Covers Rust's local extension registry install order, event sink forwarding
  and drop branches, thread-goal conversion, and guardian weak-manager
  upgrade/delegation boundary through deterministic projections.
- Real extension registry building/install hooks, AuthManager/OpenTelemetry
  integration, and concrete async subagent spawning remain runtime integration
  boundaries.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_extensions_rs.py` (6 passed) plus `py_compile` for the
  Python module and parity test.

## src/connection_rpc_gate.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/connection_rpc_gate.rs`

Rust local tests:

- `run_executes_while_open`
- `run_drops_future_without_polling_after_shutdown`
- `shutdown_waits_for_started_run_to_finish`
- `shutdown_drops_late_runs_while_waiting_for_inflight_work`
- `run_is_counted_before_handler_body_continues`

Python parity tests:

- `test_run_executes_while_open`
- `test_run_drops_future_without_polling_after_shutdown`
- `test_shutdown_waits_for_started_run_to_finish`
- `test_shutdown_drops_late_runs_while_waiting_for_inflight_work`
- `test_run_is_counted_before_handler_body_continues`

Coverage notes:

- Covers Rust's per-connection accepting flag, token/inflight accounting,
  shutdown close/wait behavior, and late-run drop path with an `asyncio`
  implementation.
    - Exact Tokio `TaskTracker` internals and scheduler fairness remain runtime
      details.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_connection_rpc_gate_rs.py -q`
  -> 5 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/connection_rpc_gate.py tests/test_app_server_connection_rpc_gate_rs.py`.

## src/command_exec.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/command_exec.rs`

Rust local tests mirrored:

- `windows_sandbox_streaming_exec_is_rejected`
- `windows_sandbox_process_ids_reject_write_requests`
- `windows_sandbox_process_ids_reject_terminate_requests`
- `dropped_control_request_is_reported_as_not_running`

Python parity tests:

- `test_streaming_exec_requires_client_process_id`
- `test_windows_sandbox_streaming_exec_is_rejected`
- `test_windows_sandbox_custom_output_cap_is_rejected`
- `test_windows_sandbox_process_ids_reject_write_and_terminate_requests`
- `test_write_requires_delta_or_close_stdin`
- `test_write_decodes_base64_and_records_control_for_active_stream`
- `test_write_rejects_when_stdin_streaming_not_enabled`
- `test_resize_validates_terminal_size`
- `test_resize_records_control_for_active_session`
- `test_duplicate_active_process_id_is_rejected_with_json_string_repr`
- `test_connection_closed_removes_sessions_and_marks_active_controls_terminated`
- `test_command_no_longer_running_error_uses_process_error_repr`
- `test_generated_process_ids_are_unquoted_and_increment`

Coverage notes:

- Covers Rust's module-local command/exec control-plane contract: generated and
  client process ids, JSON-string error rendering for client ids, duplicate
  session rejection, Windows restricted-token sandbox validation, unsupported
  Windows-sandbox control errors, actionable write validation, base64 decoding,
  stdin-streaming guard, terminate/resize control recording, connection-close
  cleanup, not-running error text, and terminal-size validation.
- Real PTY/pipe spawning, sandbox execution, network proxy lifetime, output
  chunk coalescing, output cap truncation, `bytes_to_string_smart(...)`,
  expiration select-loop behavior, IO drain timeout timing, and concrete
  outgoing response/notification delivery remain runtime/dependency boundaries.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_command_exec_rs.py` (13 passed) plus `py_compile` for
  the Python module and parity test.

## src/config/mod.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/config/mod.rs`

Rust local tests:

- None in this parent module; behavior is defined by the single child-module
  declaration.

Python parity tests:

- `test_config_mod_declares_external_agent_config_child_module`

Coverage notes:

- Covers the parent namespace contract for
  `pub(crate) mod external_agent_config;`: child module name, intended Python
  child path, and crate-private visibility.
- `src/config/external_agent_config.rs` owns the migration/config behavior and
  remains a separate module boundary.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_config_mod_rs.py` (1 passed) plus `py_compile` for the
  Python module and parity test.

## src/config/external_agent_config.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/config/external_agent_config.rs`

Rust local tests:

- `codex/codex-rs/app-server/src/config/external_agent_config_tests.rs`

Python parity tests:

- `test_external_agent_config_constants_match_rust`
- `test_external_agent_config_data_shapes_match_rust_defaults`
- `test_external_agent_session_source_path_accepts_only_existing_jsonl_under_projects`
- `test_default_external_agent_home_prefers_home_then_userprofile_then_relative`
- `test_merge_json_settings_recursively_overrides_existing_values`
- `test_collect_enabled_plugins_filters_disabled_and_invalid_plugin_ids`
- `test_collect_marketplace_import_sources_resolves_sources_and_adds_official_marketplace`
- `test_relative_local_path_detection_matches_rust_prefixes`
- `test_rewrite_external_agent_terms_matches_case_insensitive_boundary_behavior`
- `test_build_config_from_external_projects_supported_settings_only`
- `test_json_env_value_to_string_matches_rust_json_value_cases`
- `test_merge_missing_toml_values_only_inserts_missing_keys`
- `test_migrated_mcp_server_names_named_migrations_and_empty_table`
- `test_migration_metric_tags_include_counts_only_for_skill_like_items`

Coverage notes:

- Covers dependency-light behavior owned by the module: constants, migration
  data shapes, default external-agent home selection, recursive JSON settings
  merge, enabled plugin filtering, marketplace-source discovery, official
  marketplace fallback, relative source resolution, external-agent term
  rewriting, external settings projection into Codex config tables, JSON env
  value stringification, missing-only TOML merge semantics, MCP server name
  extraction, named migration construction, empty-table detection, metric tag
  construction, and external session source path canonicalization.
- Keeps full filesystem migration, real session detection/replay, MCP/hook/
  subagent/command import execution, marketplace install policy, and async
  plugin import execution as runtime/dependency boundaries under the current
  extension-area compatibility policy.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_config_external_agent_config_rs.py` (14 passed) plus
  `py_compile` for the Python module and parity test.

## src/bin/notify_capture.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/bin/notify_capture.rs`

Cargo registration:

- `codex/codex-rs/app-server/Cargo.toml`
  registers `codex-app-server-test-notify-capture` at
  `src/bin/notify_capture.rs`.

Rust local tests:

- None in this helper binary; behavior is defined by the source contract and
  binary registration.

Python parity tests:

- `test_notify_capture_temp_path_matches_rust_display_format`
- `test_run_notify_capture_requires_output_path_argument`
- `test_run_notify_capture_requires_payload_argument`
- `test_run_notify_capture_rejects_extra_arguments`
- `test_write_notify_capture_payload_moves_synced_temp_file`
- `test_run_notify_capture_accepts_pathlike_output_and_payload`
- `test_payload_to_lossy_text_replaces_invalid_bytes`

Coverage notes:

- Covers the module-scoped helper-binary contract: skipping the program
  argument, requiring exactly output path and payload arguments, exact Rust
  error strings for missing/extra arguments, `OsString::to_string_lossy`
  projection, `format!("{}.tmp", output_path.display())` temp path semantics,
  temp-file write/flush/fsync behavior, and final move into the output path.
- Treats concrete `anyhow::Context` filesystem wrapping and platform-specific
  `std::fs::rename` overwrite details as runtime/platform boundaries; Python
  uses normal filesystem exceptions and `os.replace` for the same write-through
  move sequence.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_bin_notify_capture_rs.py` (7 passed) plus
  `py_compile` for the Python module and parity test.

## src/bespoke_event_handling.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/bespoke_event_handling.rs`

Rust local tests:

- `test_handle_turn_diff_emits_v2_notification`
- `test_handle_turn_plan_update_emits_notification_for_v2`
- `test_hook_prompt_raw_response_emits_item_completed`
- `test_handle_turn_complete_emits_*`
- `test_handle_turn_interrupted_emits_interrupted_with_error`
- `test_handle_token_count_event_*`

Python parity tests:

- `test_turn_diff_updated_notification_matches_rust_payload_shape`
- `test_turn_plan_updated_notification_maps_update_plan_steps`
- `test_turn_completed_notification_uses_not_loaded_empty_turn`
- `test_hook_prompt_item_completed_payload_only_for_user_hook_prompt_messages`
- `test_mcp_server_elicitation_response_fallbacks_match_rust`
- `test_request_permissions_response_fallbacks_and_strict_scope_guard`
- `test_render_review_output_text_joins_explanation_and_findings_with_fallback`
- `test_map_file_change_approval_decision_matches_review_decision_variants`

Coverage notes:

- Covers module-local conversion and fallback helpers: turn diff/plan/
  completion notification shaping, hook prompt item-completed payload filtering,
  MCP elicitation fallback/cancel/decline behavior, permissions response
  fallback and strict session-scope guard, review output text rendering,
  file-change approval mapping, and millisecond timestamp projection.
- Keeps full `apply_bespoke_event_handling` async dispatch, concrete
  `CodexThread::submit(...)`, watcher/permit lifetimes, outgoing transport
  emission, thread-state mutation, command-execution approval side effects,
  rollback store loading, and concrete permission-profile intersection as
  runtime/dependency boundaries.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_bespoke_event_handling_rs.py` (8 passed) plus
  `py_compile` for the Python module and parity test.

## src/bin/test_notify_capture.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/bin/test_notify_capture.rs`

Rust local tests:

- None in this helper; behavior is defined by the source contract.

Python parity tests:

- `test_test_notify_capture_temp_path_matches_rust_with_extension`
- `test_run_test_notify_capture_requires_output_argument`
- `test_run_test_notify_capture_requires_payload_argument`
- `test_payload_to_utf8_text_rejects_invalid_bytes`
- `test_write_test_notify_capture_payload_moves_json_tmp_file`
- `test_run_test_notify_capture_ignores_extra_arguments`

Coverage notes:

- Covers the helper contract: skipping the program argument, missing output and
  payload error strings, strict `OsString::into_string` UTF-8 behavior,
  `PathBuf::with_extension("json.tmp")` temp path construction, temp-file
  writes, final move into the output path, and ignored extra arguments after
  the payload.
- Preserves Rust-aligned helper/export names while marking pytest-looking
  helper objects as non-tests in Python so focused parity collection does not
  treat the exported helper as a pytest test function.
- Treats concrete `anyhow` filesystem error propagation and platform-specific
  `std::fs::rename` overwrite details as runtime/platform boundaries; Python
  uses normal filesystem exceptions and `os.replace` for the same temp-write
  move sequence.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_bin_test_notify_capture_rs.py` (6 passed) plus
  `py_compile` for the Python module and parity test.

## src/fuzzy_file_search.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/fuzzy_file_search.rs`

Rust local tests:

- None in this module; behavior is defined by the source contract and consumed
  by request processors.

Python parity tests:

- `test_run_fuzzy_file_search_empty_roots_returns_empty_without_runner`
- `test_run_fuzzy_file_search_maps_and_sorts_matches`
- `test_run_fuzzy_file_search_failure_returns_empty`
- `test_collect_files_sorts_snapshot_matches_and_preserves_payload_fields`
- `test_session_update_records_latest_query_and_forwards_to_inner_session`
- `test_session_snapshot_sends_only_matching_latest_query_and_empty_query_has_no_files`
- `test_session_complete_and_close_respect_canceled_flag`

Coverage notes:

- Covers Rust's app-server bridge around `codex-file-search`: one-shot search
  options, empty roots, error-to-empty fallback, result projection/sorting,
  session construction, query update/cancel gates, reporter stale-snapshot
  filtering, empty-query update payloads, and completed notifications.
- Concrete file walking/matching/session runtime remains owned by
  `codex-file-search`; Tokio `spawn_blocking`, runtime spawn scheduling, and
  tracing side effects remain runtime/platform details.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_fuzzy_file_search_rs.py` (7 passed) plus `py_compile`
  for the Python module and parity test.

## src/mcp_refresh.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/mcp_refresh.rs`

Rust local tests:

- `strict_refresh_reports_thread_planning_failures`
- `best_effort_refresh_attempts_every_loaded_thread`

Python parity tests:

- `test_strict_refresh_reports_thread_planning_failures_and_queues_nothing`
- `test_best_effort_refresh_attempts_every_loaded_thread`
- `test_strict_refresh_wraps_thread_load_failures_like_rust`
- `test_best_effort_refresh_skips_load_and_submit_failures`
- `test_build_refresh_config_serializes_servers_and_oauth_mode`
- `test_queue_refresh_wraps_submit_errors_with_thread_id`

Coverage notes:

- Covers Rust's strict refresh pre-load, all-thread planning-before-queue
  contract, best-effort per-thread skip behavior, thread-load and submit error
  text, refresh-config serialization, and `Op::RefreshMcpServers` submit
  boundary through deterministic async projections.
- Concrete `ConfigManager`, `ThreadManager`, `CodexThread`, MCP manager runtime,
  tracing warnings, Rust `io::Error::other` identity, and Tokio scheduling
  remain dependency/runtime boundaries.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_mcp_refresh_rs.py` (6 passed) plus `py_compile` for
  the Python module and parity test.

## src/config_manager.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/config_manager.rs`

Rust local tests:

- None in this module; behavior is defined by source and app-server runtime
  use.

Python parity tests:

- `test_current_handles_and_replace_methods_match_rust_storage_contract`
- `test_load_with_cli_overrides_merges_request_and_extracts_bypass_hook_trust`
- `test_load_with_cli_overrides_rejects_non_bool_bypass_hook_trust`
- `test_load_latest_config_for_thread_rebuilds_and_applies_runtime_state`
- `test_load_config_layers_delegates_current_state_to_loader`
- `test_protected_feature_keys_combines_effective_config_and_requirements`
- `test_apply_runtime_feature_enablement_skips_protected_and_unknown_features`
- `test_load_default_config_adds_user_profile_layer_when_loader_overrides_present`

Coverage notes:

- Covers Rust's app-server config manager storage/swap helpers, CLI plus
  request override merge order, typed `bypass_hook_trust` extraction and
  validation, latest/default/thread config load handoff shape, runtime feature
  enablement with protected-key skip semantics, arg0 dispatch path application,
  and config-layer loader argument shaping through deterministic projections.
  - Concrete `ConfigBuilder::build(...)`,
    `Config::load_default_with_cli_overrides_for_codex_home(...)`,
    `load_config_layers_state(...)`, filesystem/config parsing, AuthManager/cloud
    loader internals, tracing warnings, lock poisoning, exact Rust IO error
    identity, and global residency side effects remain runtime/dependency
    boundaries.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_config_manager_rs.py` (8 passed) plus `py_compile`
  for the Python module and parity test.

## src/config_manager_service.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/config_manager_service.rs`
- `codex/codex-rs/app-server/src/config_manager_service_tests.rs`

Rust local tests mirrored:

- `clear_missing_nested_config_is_noop`
- `write_value_rejects_legacy_profile_selector`
- `write_value_rejects_legacy_profile_table`
- `batch_write_rejects_legacy_profile_selector`
- `write_value_defaults_to_user_config_path`
- `read_includes_origins_and_layers`
- `write_value_reports_override`
- `write_value_reports_managed_override`
- `version_conflict_rejected`
- `upsert_merges_tables_replace_overwrites`

Python parity tests:

- `test_parse_key_path_supports_bare_quoted_and_escaped_segments`
- `test_parse_key_path_rejects_empty_and_malformed_segments`
- `test_apply_merge_upsert_merges_tables_replace_overwrites`
- `test_clear_missing_nested_config_is_noop`
- `test_value_at_path_reads_mapping_and_array_segments`
- `test_write_value_rejects_legacy_profile_selector`
- `test_batch_write_rejects_legacy_profile_selector`
- `test_version_conflict_rejected`
- `test_write_value_defaults_to_user_config_path`
- `test_write_value_reports_override`
- `test_read_honors_include_layers_and_reports_origins`

Coverage notes:

- Covers Rust's module-local config service helper contract: write-code error
  extraction, keyPath parser validation, null-as-clear behavior, nested clear
  no-op behavior, table/array `value_at_path(...)`, replace/upsert merge
  semantics, default user config path selection, readonly non-user path
  rejection, expected-version conflict rejection, legacy profile write
  rejection, optional read layer inclusion, origin projection, and override
  metadata detection against effective higher-precedence config.
- Rust's comment-preserving TOML edit persistence, exact `ConfigEdit`
  text-position tracking, core config validation, feature-requirement
  validation, selected-profile filesystem loading, managed policy validation,
  reserved-provider checks, and actual config file writes remain
  runtime/dependency boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_config_manager_service_rs.py -q`
  -> 15 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/config_manager_service.py tests/test_app_server_config_manager_service_rs.py`.

## src/fs_watch.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/fs_watch.rs`

Rust local tests:

- `watch_uses_client_id_and_tracks_the_owner_scoped_entry`
- `unwatch_is_scoped_to_the_connection_that_created_the_watch`
- `watch_rejects_duplicate_id_for_the_same_connection`
- `connection_closed_removes_only_that_connections_watches`

Python parity tests:

- `test_watch_uses_client_id_and_tracks_owner_scoped_entry`
- `test_unwatch_is_scoped_to_connection_that_created_watch`
- `test_watch_rejects_duplicate_id_for_same_connection`
- `test_same_watch_id_is_allowed_for_different_connections`
- `test_connection_closed_removes_only_that_connections_watches`
- `test_fs_changed_notification_joins_root_sorts_and_skips_empty_events`
- `test_debounce_receiver_projection_accumulates_unique_paths`
- `test_watch_and_unwatch_accept_camel_case_mapping_params`

Coverage notes:

- Covers Rust's app-server watch bookkeeping contract: watch keys are scoped by
  connection and watch ID, duplicate watch IDs are rejected per connection,
  watches register non-recursive paths, unwatch is owner-scoped,
  connection-close removes only that connection's watches, changed paths are
  joined to the watch root and sorted, empty changed-path batches do not emit,
  and debounce accumulation drains unique paths into one event.
- Concrete `codex-file-watcher` construction/subscription/registration,
  fallback-to-noop internals, Tokio task spawning and biased select behavior,
  exact debounce timing, oneshot termination wait ordering, and outgoing
  transport delivery remain runtime/dependency boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_fs_watch_rs.py -q` -> 8 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/fs_watch.py tests/test_app_server_fs_watch_rs.py`.

## src/outgoing_message.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/outgoing_message.rs`

Rust local tests mirrored:

- `send_response_routes_to_target_connection`
- `send_response_clears_registered_request_context`
- `send_error_routes_to_target_connection`
- `send_server_notification_to_connection_and_wait_tracks_write_completion`
- `connection_closed_clears_registered_request_contexts`
- `notify_client_error_forwards_error_to_waiter`
- `pending_requests_for_thread_returns_thread_requests_in_request_id_order`
- `cancel_requests_for_thread_cancels_all_thread_requests`

Additional Python coverage:

- `ThreadScopedOutgoingMessageSender::abort_pending_server_requests`
- `replay_requests_to_connection_for_thread`

Python parity tests:

- `test_send_response_routes_to_target_connection`
- `test_send_response_clears_registered_request_context`
- `test_send_error_routes_to_target_connection`
- `test_send_server_notification_to_connection_and_wait_tracks_write_completion`
- `test_connection_closed_clears_registered_request_contexts`
- `test_notify_client_error_forwards_error_to_waiter`
- `test_pending_requests_for_thread_returns_thread_requests_in_request_id_order`
- `test_cancel_requests_for_thread_cancels_all_thread_requests`
- `test_thread_scoped_abort_pending_server_requests_uses_turn_transition_error_reason`
- `test_replay_requests_to_connection_for_thread_routes_pending_requests`

Coverage notes:

- Covers Rust's local outgoing coordinator memory contract: request ID
  allocation, pending callback futures, thread-scoped request tracking,
  response/error routing, server notification envelopes, write-completion wait
  projection, request-context cleanup, and turn-transition abort error data.
- Notification JSON method serialization and typed
  `ServerRequest::response_from_result(...)` decoding are protocol-module
  boundaries.
- Concrete transport writer/backpressure, tracing instrumentation, and real
  analytics payloads remain runtime/dependency boundaries.
- Focused validation passed on 2026-06-19 with
  `tests/test_app_server_outgoing_message_rs.py` (10 passed) plus `py_compile`
  for the Python module and parity test.

## src/request_serialization.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_serialization.rs`

Rust local tests:

- `same_key_requests_run_fifo`
- `different_keys_run_concurrently`
- `closed_gate_request_is_skipped_and_following_requests_continue`
- `shutdown_of_live_gate_skips_already_queued_requests`
- `same_key_shared_reads_run_concurrently`
- `exclusive_write_waits_for_running_shared_reads`
- `later_shared_reads_do_not_jump_ahead_of_queued_write`

Python parity tests:

- `test_same_key_requests_run_fifo`
- `test_different_keys_run_concurrently`
- `test_closed_gate_request_is_skipped_and_following_requests_continue`
- `test_shutdown_of_live_gate_skips_already_queued_requests`
- `test_same_key_shared_reads_run_concurrently`
- `test_exclusive_write_waits_for_running_shared_reads`
- `test_later_shared_reads_do_not_jump_ahead_of_queued_write`
- `test_queue_key_from_scope_maps_connection_scoped_variants`

Coverage notes:

- Covers Rust's request serialization key/access mapping, per-key FIFO
  exclusive execution, cross-key concurrency, closed-gate skip-and-continue
  behavior, live-gate shutdown skip for already queued requests, contiguous
  shared-read batch draining, exclusive write barriers behind running shared
  reads, and the queued-write ordering rule that prevents later shared reads
  from jumping ahead.
- Concrete request processors, JSON-RPC handlers, exact Tokio spawn/scheduler
  ordering, tracing spans, and `futures::join_all` internals remain
  runtime/dependency boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_serialization_rs.py -q`
  -> 8 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_serialization.py tests/test_app_server_request_serialization_rs.py`.

## src/message_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/message_processor.rs`

Rust local tests:

- `codex/codex-rs/app-server/src/message_processor_tracing_tests.rs`
  covers tracing behavior; this module's message-processing shell contract is
  otherwise source-defined and projected with focused Python tests.

Python parity tests:

- `test_connection_session_state_matches_once_lock_defaults_and_single_initialize`
- `test_process_request_rejects_non_initialize_before_session_initialized`
- `test_initialize_request_bypasses_initialized_gate_and_notifies_thread_processor`
- `test_initialized_request_tracks_and_sends_some_response`
- `test_initialized_request_with_no_response_does_not_send_response`
- `test_experimental_request_requires_initialized_experimental_capability`
- `test_process_response_and_error_forward_to_outgoing_callbacks`
- `test_connection_closed_runs_rust_cleanup_order`
- `test_external_auth_refresh_bridge_maps_reason_and_response_payload`

Coverage notes:

- Covers Rust's connection session defaults/one-time initialization,
  external-auth refresh bridge mapping, initialize-first request handling,
  initialized/experimental gates, initialized-request tracking with raw request
  ids, injectable child dispatch, response/no-response/error forwarding, and
  connection-close cleanup ordering.
- Full construction of concrete child request processors, async queue
  execution, tracing spans, and Tokio task scheduling remain neighboring
  runtime/dependency boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_message_processor_rs.py -q`
  -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/message_processor.py tests/test_app_server_message_processor_rs.py`.

## src/request_processors.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors.rs`

Rust local tests:

- None in the parent module; child-module tests remain scoped to their owning
  files.

Python parity tests:

- `test_request_processors_parent_module_declares_rust_child_modules`
- `test_request_processors_parent_module_reexports_rust_processors`
- `test_request_processors_parent_module_reexports_thread_helpers`
- `test_build_api_turns_filters_to_limited_persisted_rollout_items`

Focused validation:

- `python -m pytest tests/test_app_server_request_processors_rs.py -q` -> 4
  passed.
- `python -m py_compile pycodex/app_server/request_processors.py tests/test_app_server_request_processors_rs.py`

Coverage notes:

- Covers Rust's parent-module declaration/re-export surface and
  `build_api_turns_from_rollout_items(...)` replay contract.
- Concrete child request processors, JSON-RPC routing, and transport/runtime
  dispatch remain sibling/dependency module boundaries.

## src/request_processors/account_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/account_processor.rs`

Rust behavior anchors:

- `ActiveLogin::login_id`, `ActiveLogin::cancel`, and drop-time cancellation.
- `login_api_key_common`, `login_chatgpt_auth_tokens_response`,
  `cancel_login_response`, `send_login_success_notifications`, `logout_v2`,
  `get_account_response`, `fetch_account_rate_limits`, and
  `send_add_credits_nudge_email_inner`.

Python parity tests:

- `test_current_account_updated_notification_uses_cached_auth`
- `test_login_api_key_common_rejects_external_auth_and_forced_chatgpt`
- `test_login_api_key_common_cancels_active_login_and_reloads`
- `test_cancel_login_response_validates_uuid_and_matches_active_login`
- `test_chatgpt_auth_tokens_respects_forced_login_and_workspace`
- `test_chatgpt_auth_tokens_success_clears_active_login_and_syncs_config`
- `test_send_login_success_notifications_emits_login_completed_then_account_updated`
- `test_logout_account_sends_result_before_account_updated_when_auth_mode_remains`
- `test_get_account_response_maps_missing_chatgpt_details_to_invalid_request`
- `test_get_account_response_projects_account_state`
- `test_rate_limits_selects_codex_primary_and_builds_by_id_map`
- `test_rate_limits_require_backend_auth_and_non_empty_snapshots`
- `test_add_credits_nudge_maps_credit_type_and_cooldown`

Coverage notes:

- Covers module-owned account request state, response/notification projection,
  and local JSON-RPC error mapping.
- Real credential persistence, browser/device-code login, backend HTTP, and
  plugin/MCP refresh side effects remain injected dependency boundaries.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_account_processor_rs.py -q`
  -> `13 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_account_processor.py
  tests/test_app_server_request_processors_account_processor_rs.py`.

## src/request_processors/initialize_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/initialize_processor.rs`

Rust behavior anchors:

- `NON_ORIGINATING_CLIENT_NAMES`
- `InitializeRequestProcessor::initialize`
- `send_initialize_notifications_to_connection`
- `send_initialize_notifications`
- `track_initialized_request`

Python parity tests:

- `test_initialize_rejects_already_initialized_session_before_side_effects`
- `test_initialize_rejects_invalid_client_name_before_session_commit`
- `test_initialize_commits_session_tracks_analytics_and_sends_response`
- `test_initialize_skips_global_identity_for_non_originating_clients`
- `test_initialize_session_race_returns_already_initialized`
- `test_initialize_notifications_are_sent_to_connection_or_broadcast`
- `test_track_initialized_request_forwards_request_id_and_payload`

Coverage notes:

- Covers initialize-time session state, capability extraction, client metadata
  side effects, analytics calls, response construction, and warning replay.
- Concrete transport routing and process-global default-client mutation are
  injectable runtime/dependency boundaries.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_initialize_processor_rs.py -q`
  -> `7 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_initialize_processor.py
  tests/test_app_server_request_processors_initialize_processor_rs.py`.

## src/request_processors/marketplace_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/marketplace_processor.rs`

Rust behavior anchors:

- `MarketplaceRequestProcessor::new`
- `marketplace_add`, `marketplace_remove`, and `marketplace_upgrade`
- `marketplace_add_inner`
- `marketplace_remove_inner`
- `marketplace_upgrade_response_inner`
- `load_latest_config`

Python parity tests:

- `test_marketplace_request_processor_new_stores_runtime_dependencies`
- `test_marketplace_add_maps_request_defaults_and_response`
- `test_marketplace_add_maps_invalid_request_error_like_rust`
- `test_marketplace_remove_maps_removed_root_to_installed_root`
- `test_marketplace_remove_maps_internal_error_like_rust`
- `test_marketplace_upgrade_loads_latest_config_and_maps_outcome`
- `test_marketplace_upgrade_default_plugins_manager_path_matches_rust_call_order`
- `test_marketplace_upgrade_maps_plugin_failure_to_invalid_request`
- `test_marketplace_upgrade_maps_load_latest_config_failure_to_internal_error`

Coverage notes:

- Covers constructor dependency storage, add/remove/upgrade facade parameter
  parsing and response projection, add sparse-path defaults, remove
  installed-root remapping, add/remove InvalidRequest/Internal JSON-RPC error
  mapping, latest-config reload behavior, plugins-manager lookup,
  plugins-config input forwarding, selected marketplace forwarding, upgrade
  response/error projection, and upgrade failure invalid-request mapping.
- Concrete marketplace repository IO, git/network behavior, plugin runtime
  upgrade implementation, and Tokio spawn-blocking scheduling remain injected
  runtime or extension-area boundaries.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_marketplace_processor_rs.py -q`
  -> `9 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_marketplace_processor.py
  tests/test_app_server_request_processors_marketplace_processor_rs.py`.

## src/request_processors/mcp_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/mcp_processor.rs`

Rust behavior anchors:

- `McpRequestProcessor::new`
- `mcp_server_refresh_response`
- `load_latest_config` and `load_thread`
- `mcp_server_oauth_login_response`
- `list_mcp_server_status_response`
- `read_mcp_resource`
- `send_mcp_resource_read_response`
- `call_mcp_server_tool`
- `with_mcp_tool_call_thread_id_meta`

Python parity tests:

- `test_with_mcp_tool_call_thread_id_meta_matches_rust_object_and_none_branches`
- `test_list_mcp_server_status_response_sorts_unions_paginates_and_defaults_auth`
- `test_list_mcp_server_status_response_rejects_invalid_cursor_like_rust`
- `test_mcp_server_refresh_maps_queue_failure_to_internal_error`
- `test_load_thread_maps_parse_and_missing_thread_errors`
- `test_send_mcp_resource_read_response_deserializes_or_internal_errors`
- `test_mcp_resource_read_with_thread_sends_thread_result`
- `test_mcp_server_tool_call_loads_thread_injects_meta_and_sends_response`
- `test_mcp_server_oauth_login_rejects_missing_or_non_http_server`
- `test_resolve_oauth_scopes_prefers_request_then_server_then_discovered`

Coverage notes:

- Covers constructor dependency storage and wrapper return shapes, refresh
  queue delegation and internal-error text, latest-config and thread-load
  error mapping, OAuth login validation for missing/non-HTTP servers, scope
  resolution precedence, status-list server-name union/sort, cursor validation
  and pagination, unsupported auth defaults, resource-read thread/threadless
  response projection and deserialize errors, tool-call thread loading,
  `threadId` metadata injection, core tool-result conversion, and
  already-mapped JSON-RPC error forwarding.
- Real MCP status collection, threadless resource runtime, OAuth browser
  login, concrete MCP tool execution, async task spawning, and Tokio
  scheduling remain injected runtime or extension-area boundaries.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_mcp_processor_rs.py -q`
  -> `10 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_mcp_processor.py
  tests/test_app_server_request_processors_mcp_processor_rs.py`.

## src/request_processors/plugins.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/plugins.rs`

Rust behavior anchors:

- `PluginRequestProcessor::new`
- public facade methods for plugin list/read/share/install/uninstall surfaces
- `effective_plugins_changed_callback` and cache-clearing helpers
- `plugin_skills_to_info`
- `local_plugin_interface_to_info`
- `marketplace_plugin_source_to_info`
- `share_context_for_source`
- `convert_configured_marketplace_plugin_to_plugin_summary`
- remote visible-scope and share conversion helpers
- `validate_client_plugin_share_targets`

Python parity tests:

- `test_plugin_request_processor_new_stores_rust_constructor_dependencies`
- `test_plugin_skills_to_info_preserves_skill_fields_and_disabled_paths`
- `test_local_plugin_interface_to_info_adds_none_url_and_empty_remote_screenshot_fields`
- `test_marketplace_plugin_source_to_info_maps_local_and_git_variants`
- `test_share_context_for_source_only_uses_shared_local_path_mapping`
- `test_convert_configured_marketplace_plugin_to_plugin_summary_maps_policy_and_context`
- `test_remote_installed_plugin_visible_scopes_tracks_feature_flags`
- `test_validate_client_plugin_share_targets_rejects_workspace_principal`
- `test_remote_plugin_share_converters_preserve_enum_values`
- `test_plugin_share_principal_from_remote_maps_type_role_id_and_name`
- `test_public_facade_methods_delegate_to_injected_response_handlers`
- `test_effective_plugins_changed_clears_plugin_skill_caches_and_refreshes`

Coverage notes:

- Covers constructor dependency storage, public facade delegation for
  list/read/share/install/uninstall surfaces, effective-plugin cache clearing
  and best-effort refresh boundaries, latest-config reload and workspace
  plugin fallback behavior, skill/interface summary conversion, local/git
  marketplace source conversion, local share-context lookup, configured
  marketplace plugin summary conversion, remote visible-scope calculation,
  share discoverability/update/target/principal conversion, and client
  share-target workspace-principal invalid-request mapping.
- Concrete plugin discovery, marketplace sync, remote plugin install/uninstall,
  OAuth login, app-auth probing, and share-service calls remain injected
  runtime or extension-area boundaries.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_plugins_rs.py -q`
  -> `12 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_plugins.py
  tests/test_app_server_request_processors_plugins_rs.py`.

## src/request_processors/apps_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/apps_processor.rs`

Rust local tests:

- None in this module; behavior is defined by the source contract.

Python parity tests:

- `test_parse_apps_cursor_maps_invalid_values_to_invalid_request`
- `test_paginate_apps_matches_rust_limit_and_next_cursor`
- `test_merge_loaded_apps_marks_accessible_directory_items_and_appends_missing`
- `test_should_send_update_when_accessible_or_fully_loaded`
- `test_apps_list_returns_empty_when_apps_disabled_for_auth`
- `test_apps_list_loads_thread_cwd_and_spawns_background_task`
- `test_apps_list_response_sends_updates_and_returns_paginated_response`
- `test_apps_list_task_retries_when_codex_apps_not_ready`

Coverage notes:

- Covers Rust's apps request processor construction, app/list thread loading,
  config snapshot fallback CWD, feature/auth and workspace plugin gating,
  spawned list-task boundary, shutdown cancellation hook, cached/interim/final
  update notifications, connector merge and enabled-state projection, cursor
  parsing, pagination, codex-apps-readiness retry, and JSON-RPC error mapping.
- Concrete connector discovery, MCP environment-manager loading, workspace
  backend fetch, Tokio task scheduling, and exact timeout timing remain
  injected dependency/runtime boundaries.
- Focused validation on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_apps_processor_rs.py -q`
  -> 8 passed.
- Syntax validation on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_apps_processor.py tests/test_app_server_request_processors_apps_processor_rs.py`.

## src/request_processors/catalog_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/catalog_processor.rs`

Rust behavior anchors:

- `SKILLS_LIST_CWD_CONCURRENCY`
- `skills_to_info`, `hooks_to_info`, and `errors_to_info`
- `list_models` and `list_collaboration_modes`
- `experimental_feature_list_response`
- `permission_profile_list_response`
- `skills_config_write_response_inner`
- `mock_experimental_method_inner`

Python parity tests:

- `test_list_models_matches_rust_pagination_and_hidden_flag`
- `test_list_models_rejects_invalid_cursor_like_rust`
- `test_paginate_rejects_cursor_past_total_with_rust_message`
- `test_list_collaboration_modes_wraps_thread_manager_masks`
- `test_permission_profile_list_prepends_builtins_and_sorts_configured_profiles`
- `test_mock_experimental_method_echoes_value`
- `test_skills_to_info_maps_enabled_flag_interface_dependencies_and_errors`
- `test_hooks_to_info_and_hook_errors_preserve_catalog_fields`
- `test_workspace_plugins_enabled_falls_back_true_on_error`
- `test_skills_config_write_requires_exactly_one_selector_and_clears_caches`

Coverage notes:

- Covers catalog dependency storage, list pagination, model and collaboration
  mode projection, permission profile ordering, experimental feature
  projection, skill/hook metadata projection, skills config write validation,
  and mock echo behavior.
- Real skill discovery, hook discovery, plugin root loading, and config edit
  persistence remain injected runtime/dependency boundaries.
- Focused validation on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_catalog_processor_rs.py -q`
  -> 10 passed.
- Syntax validation on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_catalog_processor.py tests/test_app_server_request_processors_catalog_processor_rs.py`.

## src/request_processors/command_exec_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/command_exec_processor.rs`

Rust behavior anchors:

- `CommandExecRequestProcessor::new`
- `one_off_command_exec`
- `command_exec_write`, `command_exec_resize`, and `command_exec_terminate`
- `connection_closed`
- `require_local_environment`
- `exec_one_off_command_inner`

Python parity tests:

- `test_one_off_requires_local_environment_like_rust`
- `test_one_off_validates_rust_request_conflicts`
- `test_one_off_projects_cwd_env_timeout_capture_and_manager_start`
- `test_disable_output_and_timeout_project_full_buffer_and_cancellation`
- `test_permission_profile_loads_cwd_config_and_maps_disallowed_warning`
- `test_sandbox_policy_validation_errors_are_invalid_request`
- `test_network_proxy_and_exec_builder_errors_map_to_internal_error`
- `test_control_methods_delegate_to_command_exec_manager_errors`

Coverage notes:

- Covers request-level command/exec validation, cwd/env projection,
  output/timeout/capture policy selection, permission-profile reload mapping,
  sandbox policy validation mapping, network/exec internal-error projection,
  and control-method delegation to `CommandExecManager`.
- Concrete process spawning, sandbox construction, and managed network proxy
  lifetime behavior remain injected runtime/dependency boundaries.
- Focused validation on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_command_exec_processor_rs.py -q`
  -> 13 passed.
- Syntax validation on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_command_exec_processor.py tests/test_app_server_request_processors_command_exec_processor_rs.py`.

## src/request_processors/config_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/config_processor.rs`

Rust behavior anchors:

- `ConfigRequestProcessor::new`
- `read`
- `config_requirements_read`
- `value_write` and `batch_write`
- `experimental_feature_enablement_set`
- `model_provider_capabilities_read`
- `handle_config_mutation`
- `refresh_apps_list_after_experimental_feature_enablement_set`
- `map_requirements_toml_to_api` and child mapping helpers
- `map_error` and `config_write_error`

Rust local tests:

- `requirements_api_includes_allow_managed_hooks_only`
- `requirements_api_includes_allow_appshots`
- `requirements_api_includes_computer_use_requirements`

Python parity tests:

- `test_read_replaces_non_object_features_and_injects_supported_enablement`
- `test_requirements_api_includes_allow_managed_hooks_only`
- `test_requirements_api_includes_allow_appshots`
- `test_requirements_api_includes_computer_use_requirements`
- `test_requirements_mapping_filters_external_sandbox_and_appends_disabled_web_search`
- `test_batch_write_reloads_user_config_and_clears_caches_after_success`
- `test_value_write_maps_config_manager_write_errors_and_skips_cache_clear`
- `test_experimental_feature_enablement_set_validates_keys_and_sends_response`
- `test_experimental_feature_enablement_set_rejects_unsupported_alias_and_unknown`
- `test_plugin_enabled_candidates_feed_analytics_after_successful_write`

Coverage notes:

- Covers config read delegation with feature enablement injection,
  requirements TOML-to-protocol mapping, config value/batch mutation
  boundaries, write-error data, runtime feature enablement validation,
  user-config refresh fan-out, plugin-toggle analytics hooks, model-provider
  capability projection, and apps-list refresh trigger boundaries.
- Concrete connector directory refresh, app-enabled-state merging, installed
  plugin telemetry metadata loading, real thread-manager runtime refresh, and
  model-provider construction remain injected dependency/runtime boundaries.
- Focused validation on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_config_processor_rs.py -q`
  -> 10 passed.
- Syntax validation on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_config_processor.py tests/test_app_server_request_processors_config_processor_rs.py`.

## src/request_processors/fs_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/fs_processor.rs`

Rust behavior anchors:

- `FsRequestProcessor::new`
- `file_system`
- `connection_closed`
- `read_file`
- `write_file`
- `create_directory`
- `get_metadata`
- `read_directory`
- `remove`
- `copy`
- `watch`
- `unwatch`
- `map_fs_error`

Python parity tests:

- `test_file_system_requires_local_environment_like_rust`
- `test_read_file_returns_base64_data_and_passes_no_sandbox`
- `test_write_file_decodes_base64_and_rejects_invalid_base64`
- `test_create_remove_and_copy_use_rust_default_options`
- `test_metadata_and_directory_entries_project_protocol_shapes`
- `test_fs_errors_map_invalid_input_to_invalid_request_otherwise_internal`
- `test_watch_unwatch_and_connection_closed_delegate_after_fs_gate`

Coverage notes:

- Covers local filesystem gating, base64 read/write payload handling,
  create/remove default option projection, copy option forwarding,
  metadata and directory entry shape conversion, filesystem invalid-input
  error mapping, and watch/unwatch/connection-close delegation.
- Concrete filesystem access, sandboxing, and watcher backends remain
  injected runtime/dependency boundaries.
- Focused validation on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_fs_processor_rs.py -q`
  -> 7 passed.
- Syntax validation on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_fs_processor.py tests/test_app_server_request_processors_fs_processor_rs.py`.

## src/request_processors/process_exec_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/process_exec_processor.rs`

Rust behavior anchors:

- `ProcessExecRequestProcessor::new`
- `process_spawn`
- `process_write_stdin`
- `process_resize_pty`
- `process_kill`
- `connection_closed`
- `require_local_environment`
- `ProcessExecManager::start`
- `ProcessExecManager::write_stdin`
- `ProcessExecManager::resize_pty`
- `ProcessExecManager::kill`
- `ProcessExecManager::connection_closed`
- `terminal_size_from_protocol`
- `no_active_process_error`
- `process_no_longer_running_error`
- `collect_spawn_process_output`

Python parity tests:

- `test_process_spawn_requires_local_environment_like_rust`
- `test_process_spawn_validates_rust_request_fields_before_start`
- `test_process_spawn_projects_env_timeout_output_size_and_sends_response`
- `test_process_spawn_defaults_output_cap_and_timeout_semantics`
- `test_manager_rejects_duplicate_handles_and_routes_controls`
- `test_write_stdin_validation_and_missing_process_errors_match_rust`
- `test_terminal_size_and_error_helpers_match_rust_text`
- `test_connection_closed_removes_sessions_and_records_kill_control`
- `test_output_capture_caps_and_stream_notifications_match_contract`

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_request_processors_process_exec_processor_rs.py -q`
  -> 9 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/request_processors_process_exec_processor.py tests/test_app_server_request_processors_process_exec_processor_rs.py`

Coverage notes:

- Covers process/spawn request validation, local-environment gating,
  environment override projection, timeout double-option semantics,
  output-cap defaults, terminal-size conversion, connection/process-handle
  session bookkeeping, duplicate-handle rejection, stdin/resize/kill control
  routing, close-triggered kill controls, and output capture/delta projection.
- Real PTY/pipe process spawning, Tokio task scheduling, expiration waiting,
  stdout/stderr drain timing, and process-exit notification delivery remain
  injected runtime/dependency boundaries.

## src/request_processors/config_errors.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/config_errors.rs`

Rust behavior anchors:

- `config_load_error_marks_cloud_requirements_failures_for_relogin`
- `config_load_error_leaves_non_cloud_requirements_failures_unmarked`
- `config_load_error_marks_non_auth_cloud_requirements_failures_without_relogin`

Python parity tests:

- `test_config_load_error_marks_cloud_requirements_failures_for_relogin`
- `test_config_load_error_leaves_non_cloud_requirements_failures_unmarked`
- `test_config_load_error_marks_non_auth_cloud_requirements_failures_without_relogin`

Coverage notes:

- Covers Rust's config-load invalid-request construction and optional
  `cloudRequirements` data projection, including Auth relogin action,
  optional status code, Debug-style error code text, and non-cloud unmarked
  failures.
- Config loading/cloud requirements fetching and calling request processors
  remain neighboring module boundaries.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_config_errors_rs.py -q`
  -> `3 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_config_errors.py
  tests/test_app_server_request_processors_config_errors_rs.py`.

## src/request_processors/request_errors.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/request_errors.rs`

Rust local tests:

- None in this module; behavior is defined by the source contract.

Python parity tests:

- `test_environment_selection_error_message_returns_invalid_request_message`
- `test_environment_selection_error_message_uses_display_for_other_codex_errors`
- `test_environment_selection_error_message_accepts_rust_shaped_duck_values`

Coverage notes:

- Covers Rust's environment-selection error helper: invalid request variants
  return their raw message, while all other errors use display text.
- Environment selection, request processor call sites, and JSON-RPC error
  construction remain neighboring module boundaries.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_request_errors_rs.py -q`
  -> `3 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_request_errors.py
  tests/test_app_server_request_processors_request_errors_rs.py`.

## src/request_processors/search.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/search.rs`
- `codex/codex-rs/app-server/src/fuzzy_file_search.rs` for session Drop
  cancellation semantics used by stop/removal.

Rust behavior anchors:

- `SearchRequestProcessor::new`
- `SearchRequestProcessor::fuzzy_file_search`
- `SearchRequestProcessor::fuzzy_file_search_session_start_response`
- `SearchRequestProcessor::fuzzy_file_search_session_update_response`
- `SearchRequestProcessor::fuzzy_file_search_session_stop`

Python parity tests:

- `test_fuzzy_file_search_empty_query_returns_empty_without_runner`
- `test_fuzzy_file_search_replaces_matching_cancellation_token_and_cleans_current_flag`
- `test_fuzzy_file_search_keeps_newer_pending_flag_when_current_finishes_late`
- `test_fuzzy_file_search_session_start_rejects_empty_session_id`
- `test_fuzzy_file_search_session_start_stores_session_and_maps_start_error`
- `test_fuzzy_file_search_session_update_and_stop_match_session_map_behavior`

Coverage notes:

- Covers the request-processor state and error-mapping contract around fuzzy
  search. The actual search algorithm and reporter notifications remain owned
  by sibling module `src/fuzzy_file_search.rs`.
- Tokio mutex scheduling, spawned task timing, and concrete outgoing delivery
  remain runtime/dependency boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_search_rs.py -q`
  -> 6 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_search.py tests/test_app_server_request_processors_search_rs.py`.

## src/request_processors/environment_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/environment_processor.rs`

Rust local tests:

- None in this module; behavior is defined by the source contract.

Python parity tests:

- `test_environment_request_processor_new_stores_environment_manager`
- `test_environment_add_upserts_environment_and_returns_empty_response`
- `test_environment_add_accepts_camel_case_params_mapping`
- `test_environment_add_maps_manager_error_to_invalid_request`

Coverage notes:

- Covers Rust's environment processor constructor, environment-add delegation,
  invalid-request error mapping, and empty response payload.
- Concrete environment manager internals, MessageProcessor JSON-RPC dispatch,
  response-envelope conversion, and async scheduling remain neighboring
  boundaries.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_environment_processor_rs.py -q`
  -> `4 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_environment_processor.py
  tests/test_app_server_request_processors_environment_processor_rs.py`.

## src/request_processors/external_agent_config_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/external_agent_config_processor.rs`

Rust local tests mirrored:

- `migration_items_that_update_runtime_sources_trigger_refresh`

Python parity tests:

- `test_migration_items_that_update_runtime_sources_trigger_refresh`
- `test_session_not_detected_error_maps_invalid_params`
- `test_detect_maps_core_items_and_details_to_protocol`
- `test_import_no_items_sends_response_only`
- `test_import_sends_response_refresh_and_completed_notification_without_background`
- `test_validate_pending_session_imports_dedupes_by_detected_source`
- `test_validate_pending_session_imports_rejects_undetected_session`
- `test_import_schedules_background_sessions_plugins_and_clears_caches`

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_request_processors_external_agent_config_processor_rs.py -q`
  -> 8 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/request_processors_external_agent_config_processor.py tests/test_app_server_request_processors_external_agent_config_processor_rs.py`

Coverage notes:

- Covers Rust's external-agent config processor control flow: detect option
  projection, migration item/detail mapping, config import request handling,
  runtime refresh gating, RPC response-before-background ordering, immediate
  completion notification, background session/plugin scheduling, session
  source-path validation/dedupe, plugin cache clear hooks, and JSON-RPC error
  mapping.
- Full external session replay, thread startup, plugin installation, imported
  session ledger persistence, concrete cache internals, and Tokio scheduling
  remain dependency/runtime boundaries.

## src/request_processors/feedback_doctor_report.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/feedback_doctor_report.rs`

Rust local tests mirrored:

- `doctor_report_tags_summarize_status_counts`

Python parity tests:

- `test_doctor_report_tags_summarize_status_counts_like_rust`
- `test_doctor_report_tags_accept_array_checks_and_unknown_ids`
- `test_truncate_tag_value_matches_rust_limit_and_ellipsis`
- `test_parse_doctor_report_stdout_uses_first_json_object`
- `test_doctor_feedback_report_builds_pretty_attachment_and_tags`
- `test_doctor_feedback_report_is_best_effort`

Coverage notes:

- Covers Rust's best-effort doctor attachment helper: current-executable
  fallback, command failure/no-json skip behavior, first-JSON-object parsing,
  pretty JSON attachment bytes, tag extraction from object and array check
  shapes, missing check ids as `unknown`, and 256-character truncation with
  ellipsis.
- Concrete `codex doctor --json` report generation and feedback upload
  assembly remain neighboring module boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_feedback_doctor_report_rs.py -q`
  -> 6 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_feedback_doctor_report.py tests/test_app_server_request_processors_feedback_doctor_report_rs.py`.

## src/request_processors/feedback_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/feedback_processor.rs`

Rust local tests mirrored:

- `windows_sandbox_log_attachment_uses_current_log` (platform-neutral injected
  resolver adaptation)

Python parity tests:

- `test_disabled_config_rejects_feedback_upload`
- `test_upload_without_logs_passes_snapshot_options`
- `test_cached_auth_feedback_tag_hooks_match_rust_method_names`
- `test_include_logs_collects_rollouts_sqlite_logs_doctor_tags_and_extra_files`
- `test_subtree_listing_falls_back_to_state_db_descendants`
- `test_resolve_rollout_path_falls_back_to_state_db`
- `test_auto_review_rollout_filename_matches_rust_format`
- `test_windows_sandbox_log_attachment_uses_current_log`

Coverage notes:

- Covers Rust's feedback upload control flow: config gating, thread-id parsing,
  cached auth feedback tag hook names, snapshot upload dispatch, no-log upload
  options, log DB flush, subtree thread lookup with state-DB fallback, sqlite
  feedback log override lookup, rollout attachment collection, guardian trunk
  filename override, Windows sandbox log attachment projection, explicit extra
  log-file dedupe, doctor-report attachment/tag merging, session-source
  propagation, and upload error mapping.
- Concrete feedback backend upload, live app-server thread runtime, auth trace
  logging, and platform Windows sandbox log-path discovery remain injected
  runtime boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_feedback_processor_rs.py -q`
  -> 8 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_feedback_processor.py tests/test_app_server_request_processors_feedback_processor_rs.py`.

## src/request_processors/git_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/git_processor.rs`

Rust local tests:

- None in this module; behavior is defined by the source contract.

Python parity tests:

- `test_git_request_processor_new_is_stateless`
- `test_git_diff_to_remote_projects_sha_and_diff_response`
- `test_git_diff_to_remote_accepts_mapping_params`
- `test_git_diff_to_remote_maps_absent_diff_to_invalid_request`

Coverage notes:

- Covers Rust's stateless processor constructor, diff-to-origin delegation,
  `GitDiffToRemoteResponse` projection, and invalid-request failure mapping.
- Actual git remote diff computation remains owned by `codex-git-utils`;
  MessageProcessor JSON-RPC dispatch and response-envelope conversion remain
  neighboring runtime boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_git_processor_rs.py -q`
  -> 4 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_git_processor.py tests/test_app_server_request_processors_git_processor_rs.py`.

## src/request_processors/remote_control_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/remote_control_processor.rs`

Rust local tests:

- None in this module; behavior is defined by the source contract.

Python parity tests:

- `test_remote_control_processor_missing_handle_maps_internal_error`
- `test_remote_control_enable_maps_handle_status_and_unavailable_error`
- `test_remote_control_disable_and_status_read_project_status_fields`
- `test_remote_control_processor_accepts_mapping_status_shapes`

Coverage notes:

- Covers optional handle storage, missing-handle internal errors, enable
  unavailable invalid-request mapping, and status field projection for enable,
  disable, and status-read responses.
- Remote-control server startup, status watchers, and concrete transport handle
  implementation remain neighboring runtime/dependency boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_remote_control_processor_rs.py -q`
  -> 4 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_remote_control_processor.py tests/test_app_server_request_processors_remote_control_processor_rs.py`.

## src/request_processors/windows_sandbox_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/windows_sandbox_processor.rs`

Rust local tests mirrored:

- `determine_windows_sandbox_readiness_reports_not_configured_when_disabled`
- `determine_windows_sandbox_readiness_reports_ready_for_unelevated_mode`
- `determine_windows_sandbox_readiness_reports_ready_for_complete_elevated_mode`
- `determine_windows_sandbox_readiness_reports_update_required_when_elevated_setup_is_stale`

Python parity tests:

- `test_determine_windows_sandbox_readiness_reports_not_configured_when_disabled`
- `test_determine_windows_sandbox_readiness_reports_ready_for_unelevated_mode`
- `test_determine_windows_sandbox_readiness_reports_ready_for_complete_elevated_mode`
- `test_determine_windows_sandbox_readiness_reports_update_required_when_elevated_setup_is_stale`
- `test_windows_sandbox_setup_start_sends_started_response_then_completion_notification`
- `test_windows_sandbox_setup_start_completion_notification_reports_error`

Coverage notes:

- Covers Rust's readiness status mapping, immediate setup-start response,
  command cwd/config reload projection, setup request assembly, and completion
  notification shape.
- Concrete Windows setup execution, Tokio spawn scheduling, and MessageProcessor
  JSON-RPC dispatch remain neighboring runtime boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_windows_sandbox_processor_rs.py -q`
  -> 6 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_windows_sandbox_processor.py tests/test_app_server_request_processors_windows_sandbox_processor_rs.py`.

## src/request_processors/thread_summary.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/thread_summary.rs`

Rust local tests mirrored:

- `extract_conversation_summary_prefers_plain_user_messages`

Python parity tests:

- `test_extract_conversation_summary_prefers_plain_user_messages`
- `test_with_thread_spawn_agent_metadata_only_overlays_thread_spawn`
- `test_permission_profile_projection_maps_active_and_sandbox_policy`
- `test_thread_settings_from_config_snapshot_projects_rust_fields`
- `test_thread_settings_from_core_snapshot_matches_config_projection`
- `test_thread_started_notification_clears_turns`
- `test_summary_to_thread_materializes_not_loaded_thread_without_turns`

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_request_processors_thread_summary_rs.py -q`
  -> 7 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/request_processors_thread_summary.py tests/test_app_server_request_processors_thread_summary_rs.py`

Coverage notes:

- Covers Rust's thread-spawn agent metadata overlay, active permission profile
  and sandbox policy projection, thread settings projection from config/core
  snapshots, thread-started notification turn clearing, conversation-summary
  preview extraction after `USER_MESSAGE_BEGIN`, git-info mapping, and
  summary-to-thread materialization.
- Full rollout file IO, async filesystem metadata reads, and thread-processor
  JSON-RPC dispatch remain neighboring runtime boundaries.

## src/request_processors/thread_goal_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/thread_goal_processor.rs`

Rust local tests mirrored:

- Source-derived helper and request-processor contract; the Rust module does
  not define local `#[cfg(test)]` tests.

Python parity tests:

- `test_validate_goal_budget_rejects_non_positive_values`
- `test_thread_goal_status_roundtrips_state_values`
- `test_api_thread_goal_from_state_projects_protocol_goal_fields`
- `test_parse_thread_id_for_request_maps_invalid_request`
- `test_thread_goal_get_feature_gate_and_success_response`
- `test_thread_goal_set_creates_goal_sends_response_and_listener_update`
- `test_thread_goal_set_status_only_requires_existing_goal`
- `test_thread_goal_clear_sends_response_and_fallback_notification`
- `test_state_db_for_materialized_thread_reports_ephemeral_and_missing_state_db`
- `test_send_thread_goal_snapshot_notification_updates_or_clears`

Coverage notes:

- Covers Rust's Goals feature gate, thread id parsing error boundary,
  materialized state DB lookup, ephemeral running-thread rejection, missing
  sqlite state DB error, status conversion, positive budget validation,
  objective trimming/validation call-site, state-goal to protocol-goal
  projection, set/get/clear response ordering, listener-command preferred
  update/clear/snapshot delivery, fallback server notifications, preview
  update, and running-thread external mutation hooks.
- Concrete rollout reconciliation, rollout path discovery beyond injected
  fakes, sqlite persistence, Tokio channel scheduling, and real thread
  continuation execution remain neighboring runtime/dependency boundaries.

Validation:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_goal_processor_rs.py -q`
  -> 10 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_goal_processor.py tests/test_app_server_request_processors_thread_goal_processor_rs.py`.

## src/request_processors/token_usage_replay.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/token_usage_replay.rs`

Rust local tests mirrored:

- `replay_attribution_uses_already_loaded_history`
- `replay_attribution_falls_back_to_rebuilt_turn_position`

Python parity tests:

- `test_replay_attribution_uses_already_loaded_history`
- `test_replay_attribution_falls_back_to_rebuilt_turn_position`
- `test_replay_attribution_returns_none_without_token_count_owner`
- `test_latest_token_usage_turn_id_prefers_last_terminal_turn`
- `test_latest_token_usage_turn_id_falls_back_to_last_or_empty`
- `test_thread_token_usage_from_info_maps_core_usage_fields`
- `test_send_thread_token_usage_update_returns_early_without_info`
- `test_send_thread_token_usage_update_sends_to_connection_with_turn_id`

Coverage notes:

- Covers Rust's active-turn snapshot timing before token-count replay,
  loaded-id preference with rebuilt-position fallback, fallback turn-id
  selection, core `TokenUsageInfo` to app-server v2 `ThreadTokenUsage`
  mapping, and single-connection `ThreadTokenUsageUpdated` replay delivery.
- Conversation storage and concrete outgoing transport remain injected
  dependency/runtime boundaries.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_token_usage_replay_rs.py -q`
  -> 8 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_token_usage_replay.py tests/test_app_server_request_processors_token_usage_replay_rs.py`.

## src/request_processors/thread_lifecycle.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/thread_lifecycle.rs`

Rust local tests mirrored:

- Source-derived helper and lifecycle contract; the Rust module does not define
  local `#[cfg(test)]` tests.

Python parity tests:

- `test_unloading_state_uses_latest_idle_and_unsubscribed_timestamp`
- `test_ensure_conversation_listener_maps_missing_and_closed_connection`
- `test_ensure_conversation_listener_attaches_and_marks_raw_events`
- `test_merge_turn_history_with_active_turn_replaces_existing_turn`
- `test_set_thread_status_interrupts_stale_in_progress_turns_when_inactive`
- `test_handle_thread_listener_command_emits_goal_and_resolution_notifications`
- `test_unload_thread_without_subscribers_cancels_removes_and_notifies_on_complete`

Coverage notes:

- Covers Rust's unload target calculation, activity observation timestamp
  reset, listener attach missing-thread/closing-thread/closed-connection/
  attached branches, raw-event opt-in, listener replacement setup, shutdown
  classification boundary, unload request cancellation and state cleanup,
  `ThreadClosed` notification, listener-command goal update/clear/snapshot and
  server-request resolution dispatch, active-turn history replacement, and
  stale in-progress turn interruption when resolved status is inactive.
- Concrete Tokio select-loop scheduling, `CodexThread::next_event`,
  bespoke event translation, token usage replay, rollout file IO, and exact
  live-thread execution remain neighboring runtime/dependency boundaries.

Validation:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_lifecycle_rs.py -q`
  -> 7 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_lifecycle.py tests/test_app_server_request_processors_thread_lifecycle_rs.py`.

## src/request_processors/thread_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/thread_processor.rs`

Rust local tests mirrored:

- Source-derived helper/facade contract. The neighboring
  `thread_processor_tests.rs`, `thread_summary_tests.rs`, and child modules
  continue to cover broader runtime/list/read behavior separately.

Python parity tests:

- `test_thread_request_processor_new_preserves_dependency_surface`
- `test_validate_dynamic_tools_rejects_rust_reserved_and_duplicate_names`
- `test_validate_dynamic_tools_rejects_namespace_collisions_and_schema_errors`
- `test_thread_turns_cursor_serializes_camel_case_and_invalid_cursor_errors`
- `test_paginate_thread_turns_matches_asc_desc_anchor_semantics`
- `test_normalize_thread_turns_status_interrupts_without_active_thread`
- `test_resume_override_metadata_helpers_follow_model_override_rules`
- `test_collect_resume_override_mismatches_reports_ignored_running_overrides`
- `test_cwd_filters_name_and_permission_helpers`

Coverage notes:

- Covers Rust's constructor dependency surface, resume override mismatch
  reporting, persisted metadata merge rules, CWD filter normalization,
  dynamic tool local validation, turns-list cursor serialization/parsing,
  ascending/descending pagination anchors, stale in-progress turn
  interruption, active-turn merge, unsupported operation JSON-RPC errors,
  title-to-name updates, and project-trust permission checks.
- Concrete thread start/resume/fork/list/read/archive/unarchive execution,
  thread-store persistence, rollout IO, listener orchestration, telemetry,
  and dynamic tool schema parser internals remain neighboring
  runtime/dependency boundaries.

Validation:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_processor_rs.py -q`
  -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_processor.py tests/test_app_server_request_processors_thread_processor_rs.py`.

## src/request_processors/turn_processor.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/turn_processor.rs`

Rust local tests mirrored:

- Source-derived facade/helper contract; the Rust module does not define local
  `#[cfg(test)]` tests.

Python parity tests:

- `test_resolve_runtime_workspace_roots_resolves_against_base_and_dedupes`
- `test_map_additional_context_sorts_keys_and_projects_core_kind`
- `test_parse_thread_id_for_request_matches_invalid_request_error_shape`
- `test_load_thread_returns_thread_or_thread_not_found_error`
- `test_turn_start_wrapper_parses_params_and_delegates_to_inner_override`
- `test_turn_interrupt_wrapper_allows_none_or_empty_response`
- `test_thread_realtime_list_voices_uses_builtin_voice_list`
- `test_xcode_26_4_mcp_elicitations_auto_deny_matches_client_line`
- `test_track_error_response_forwards_to_analytics_client`

Coverage notes:

- Covers Rust's path resolution/deduplication helper, additional-context
  `BTreeMap` projection, thread-id parse error mapping, missing-thread error,
  public wrapper delegation shape, optional interrupt response preservation,
  builtin realtime voice-list response, analytics error forwarding, and the
  Xcode 26.4 MCP elicitation compatibility predicate.
- Concrete turn startup, settings override construction, live thread
  execution, realtime session control, review orchestration, listener setup,
  and core event routing remain neighboring runtime/dependency boundaries.

Validation:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_turn_processor_rs.py -q`
  -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_turn_processor.py tests/test_app_server_request_processors_turn_processor_rs.py`.

## src/request_processors/thread_resume_redaction.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/thread_resume_redaction.rs`

Rust local tests mirrored:

- `redacts_mcp_success_result_and_removes_image_generation`
- `redacts_mcp_error_message`

Python parity tests:

- `test_should_redact_thread_resume_payloads_matches_remote_client_names`
- `test_redacts_mcp_success_result_and_removes_image_generation`
- `test_redacts_mcp_error_message`

Coverage notes:

- Covers Rust's response-only `thread/resume` redaction helper: exact
  ChatGPT Android/iOS remote-client matching, MCP arguments replacement,
  successful MCP result replacement, MCP error message replacement, and
  image-generation item removal.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_resume_redaction_rs.py -q`
  -> 3 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_resume_redaction.py tests/test_app_server_request_processors_thread_resume_redaction_rs.py`.
- Integration into cold/running thread resume paths remains owned by
  neighboring `thread_processor.rs` and `thread_lifecycle.rs` modules.

## src/thread_status.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/thread_status.rs`

Rust local tests mirrored:

- `loaded_status_defaults_to_not_loaded_for_untracked_threads`
- `tracks_non_interactive_thread_status`
- `status_updates_track_single_thread`
- `resolves_in_progress_turn_to_active_status`
- `keeps_status_when_no_in_progress_turn`
- `system_error_sets_idle_flag_until_next_turn`
- `shutdown_marks_thread_not_loaded`
- `loaded_statuses_default_to_not_loaded_for_untracked_threads`
- `has_running_turns_tracks_runtime_running_flag_only`
- `status_change_emits_notification`
- `silent_upsert_skips_initial_notification`
- `status_watchers_receive_only_their_thread_updates`

Python parity tests:

- `test_loaded_status_defaults_to_not_loaded_for_untracked_threads`
- `test_tracks_non_interactive_thread_status`
- `test_status_updates_track_single_thread`
- `test_resolves_in_progress_turn_to_active_status`
- `test_keeps_status_when_no_in_progress_turn`
- `test_system_error_sets_idle_flag_until_next_turn`
- `test_shutdown_marks_thread_not_loaded`
- `test_loaded_statuses_default_to_not_loaded_for_untracked_threads`
- `test_has_running_turns_tracks_runtime_running_flag_only`
- `test_status_change_emits_notification`
- `test_silent_upsert_skips_initial_notification`
- `test_status_watchers_receive_only_their_thread_updates`

Coverage notes:

- Covers Rust's thread watch manager state machine, loaded/default status
  lookup, turn lifecycle status transitions, pending approval/user-input active
  flags, running-turn count, status subscriptions, status-changed notification
  shape, silent upsert behavior, and `resolve_thread_status(...)` in-progress
  turn override.
- Rust `tokio::sync::watch` receiver-count pruning and Drop-spawn guard
  release timing are represented by explicit Python subscription/guard APIs.
- Concrete outgoing-message envelope/channel delivery remains a sibling module
  boundary.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_thread_status_rs.py -q` -> 12 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/thread_status.py tests/test_app_server_thread_status_rs.py`.

## src/thread_state.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/thread_state.rs`

Rust local tests mirrored:

- `note_thread_settings_reports_only_effective_changes`

Python parity tests:

- `test_note_thread_settings_reports_only_effective_changes`
- `test_set_listener_replaces_previous_cancel_and_increments_generation`
- `test_clear_listener_cancels_sender_and_resets_history`
- `test_track_current_turn_event_updates_summary_and_terminal_turn`
- `test_resolve_server_request_on_thread_listener_queues_ordered_command`
- `test_thread_state_manager_subscribe_unsubscribe_and_remove_connection`
- `test_thread_state_manager_attestation_chooses_lowest_capable_connection`
- `test_remove_thread_state_clears_listener_and_connection_indexes`
- `test_pending_interrupt_and_rollback_defaults_match_rust_shape`

Coverage notes:

- Covers Rust's per-thread listener state, listener command variants,
  cancellation replacement, generation increment, active-turn history tracking,
  thread-settings baseline delta behavior, and server-request resolution
  handoff.
- Covers Rust's connection/thread reverse indexes, live connection capability
  storage, first attestation-capable connection selection, subscriber removal,
  thread removal cleanup, and has-connection watcher notifications.
- Exact Tokio mpsc/oneshot/watch scheduling, weak `Arc<CodexThread>` identity,
  concrete `CodexThread` execution, and outgoing transport delivery remain
  runtime/dependency boundaries.

Validation:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_thread_state_rs.py -q` -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/thread_state.py tests/test_app_server_thread_state_rs.py`.

## src/in_process.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/in_process.rs`

Rust local tests mirrored:

- `in_process_start_initializes_and_handles_typed_v2_request`
- `in_process_start_uses_requested_session_source_for_thread_start`
- `in_process_start_clamps_zero_channel_capacity`
- `guaranteed_delivery_helpers_cover_terminal_server_notifications`

Python parity tests:

- `test_in_process_start_initializes_and_handles_typed_v2_request_projection`
- `test_in_process_start_uses_requested_session_source_for_thread_start_projection`
- `test_in_process_start_clamps_zero_channel_capacity`
- `test_guaranteed_delivery_helpers_cover_terminal_server_notifications`
- `test_client_sender_try_send_maps_full_and_closed_queue_errors`
- `test_client_message_shapes_match_rust_variants`
- `test_runtime_projection_rejects_duplicate_request_id`
- `test_runtime_projection_maps_full_and_closed_processor_request_queue`
- `test_runtime_projection_handles_server_request_backpressure`
- `test_runtime_projection_shutdown_fans_out_pending_request_errors`
- `test_constants_match_rust_module_boundary`

Coverage notes:

- Covers Rust's in-process start-argument shape, capacity clamp, client/server
  message variants, client queue error mapping, initialize/initialized
  handshake projection, duplicate request-id rejection, full/closed processor
  request behavior, notification saturation, server-request backpressure
  errors, terminal notification delivery guarantee, and shutdown fan-out.
- Real Tokio task scheduling, `MessageProcessor` execution, auth/config/state
  DB construction, outbound routing execution, and concrete embedded runtime
  behavior remain dependency/runtime boundaries.

Validation:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_in_process_rs.py -q` -> 11 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/in_process.py tests/test_app_server_in_process_rs.py`.

## Known gaps

- `run_main(...)` covers Rust's default argument projection into
  `run_main_with_transport_options(...)`, and
  `run_main_with_transport_options(...)` now covers the crate-root
  hook-based startup/finalization orchestration.
- Concrete sibling-owned runtime effects behind `AppServerRuntimeHooks` remain
  integration boundaries: real config manager IO, telemetry provider
  installation, state DB startup, transport acceptors, remote-control server
  startup, outbound routing, `MessageProcessor` execution, and Tokio
  scheduling are not duplicated in the crate-root module.
- The real OS signal listener for `shutdown_signal(...)` remains open; Python
  currently covers the Rust signal mapping through injectable waiters.
- Transport acceptor startup and remote-control server startup remain open;
  Python currently covers only the local transport startup branch, Unix socket
  startup-lock preparation branch, fallible transport acceptor startup ordering,
  and runtime mode/enablement decisions.
- Async config loading, exec-policy checking, and concrete system bwrap warning
  rule computation remain open; Python currently covers the app-server
  system-bwrap warning call-site and warning accumulation order once those
  inputs are available plus the best-effort cloud requirements preload
  success/failure branch and the main config-load strict/fallback branch.
- Personality migration execution remains open; Python currently covers only
  the local control-flow branch after state DB startup.
- State DB initialization remains open; Python currently covers only the local
  success/error branch and Rust error-message prefix.
- Telemetry setup remains open; Python currently covers only the local
  provider build success/error branch and side-effect ordering.
- Tracing/log subscriber installation remains open; Python currently covers
  only local layer assembly and warning-emission decisions.
- Runtime handle startup remains open; Python currently covers only the local
  installation-id and pre-transport handle initialization branch.
- Auth manager runtime behavior remains open; Python currently covers only the
  local runtime creation call-site ordering and env opt-in flag.
- Transport event loop processing remains open; Python currently covers only
  the local connection-opened, connection-closed, transport-event channel
  closed, and incoming request post-processing projections, non-request
  connection gate routing, outbound router control-event/outgoing-envelope
  decisions, and processor-exit cleanup plus processor-loop
  shutdown-update/signal/running-turn watcher gates.
- MessageProcessor request execution and concrete JSON-RPC processor calls
  remain open; Python currently covers only the local `MessageProcessorArgs`
  assembly projection.
- Remote-control server/watch channel implementation remains open; Python
  currently covers only startup argument projection, startup failure ordering,
  and the status-change and thread-created projections after watcher events.
- Transport setup, config loading, telemetry setup, command routing, concrete
  outgoing routing in the sibling `transport` module, concrete shutdown
  execution, and all sibling modules remain
  unmapped; Python currently covers the local finalization order projection
  after worker handles complete.
- This package now owns the runtime handoff from `codex-app-server-client`;
  client code should not fabricate embedded app-server behavior locally.

## src/main.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/main.rs`

Rust local tests:

- None in this module; behavior is defined by source and integration binary
  startup usage.

Python parity tests:

- `test_disable_managed_config_from_debug_env_matches_rust_truth_table`
- `test_managed_config_path_from_debug_env_empty_is_none`
- `test_loader_overrides_debug_env_disable_takes_precedence`
- `test_loader_overrides_debug_env_uses_managed_config_path`
- `test_main_runtime_call_projection_matches_rust_main_defaults`
- `test_main_runtime_call_projection_applies_cli_fields_and_auth_conversion`
- `test_main_runtime_call_projection_release_ignores_debug_plugin_skip`
- `test_main_runtime_call_projection_projects_supported_listen_urls`

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_main_rs.py -q`
  -> `8 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/main.py
  tests/test_app_server_main_rs.py`.

Deferred dependency/runtime boundaries:

- This module only projects the binary startup wrapper into the
  `run_main_with_transport_options(...)` call. Arg0 dispatch, actual Clap
  parsing, websocket auth validation, and full app-server runtime startup are
  owned by neighboring crates/modules.

## src/transport.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/transport.rs`

Rust local tests:

- `to_connection_notification_respects_opt_out_filters`
- `to_connection_notifications_are_dropped_for_opted_out_clients`
- `to_connection_notifications_are_preserved_for_non_opted_out_clients`
- `experimental_notifications_are_dropped_without_capability`
- `experimental_notifications_are_preserved_with_capability`
- `command_execution_request_approval_strips_additional_permissions_without_capability`
- `command_execution_request_approval_keeps_additional_permissions_with_capability`
- `broadcast_does_not_block_on_slow_connection`
- `to_connection_stdio_waits_instead_of_disconnecting_when_writer_queue_is_full`

Python parity tests:

- `test_transport_reexport_surface_projection_matches_rust_use_declarations`
- `test_connection_state_projection_ignores_origin_and_creates_session`
- `test_disconnect_connection_projection_removes_and_cancels_when_present`
- `test_disconnect_connection_projection_reports_missing_connection`
- `test_transport_opted_out_notification_is_skipped`
- `test_transport_experimental_notification_requires_capability`
- `test_transport_unreadable_opt_outs_warn_and_do_not_skip`
- `test_transport_filters_approval_experimental_fields_without_capability`
- `test_transport_keeps_approval_experimental_fields_with_capability`
- `test_route_to_connection_drops_unknown_connection`
- `test_route_broadcast_targets_initialized_non_filtered_connections`
- `test_route_broadcast_disconnects_slow_disconnectable_connection`
- `test_route_to_connection_stdio_waits_instead_of_disconnecting_when_full`

Deferred dependency/runtime boundaries:

- Python covers the routing/filtering source contract with pure projections;
  real async mpsc writers, websocket sending, and oneshot completion are
  deferred until the crate runtime is implemented.
- Transport acceptor implementations live in `codex-app-server-transport`;
  this module records only the Rust `transport.rs` re-export surface.

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_transport_rs.py -q`
  -> 13 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/transport.py tests/test_app_server_transport_rs.py`.

## src/server_request_error.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/server_request_error.rs`

Rust local tests:

- `turn_transition_error_is_detected`
- `unrelated_error_is_not_detected`

Python parity tests:

- `test_turn_transition_error_is_detected`
- `test_unrelated_error_is_not_detected`
- `test_missing_or_non_string_reason_is_not_detected`

Deferred dependency/runtime boundaries:

- This module is pure JSON-RPC error classification. It does not execute the
  outgoing-message request cancellation path that consumes the helper.

Focused validation:

- 2026-06-19: `python -m pytest
  tests/test_app_server_server_request_error_rs.py -q` -> `3 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/server_request_error.py
  tests/test_app_server_server_request_error_rs.py`.

## src/error_code.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/error_code.rs`

Rust local tests:

- None in this module; behavior is defined by the source contract and consumed
  by sibling command/request/outgoing modules.

Python parity tests:

- `test_error_code_constants_match_rust_module`
- `test_error_helpers_construct_jsonrpc_error_without_data`
- `test_error_helpers_convert_message_like_rust_into_string`

Deferred dependency/runtime boundaries:

- This module only constructs protocol error values. It does not execute the
  request processors, command execution paths, in-process worker, or outgoing
  message sender paths that consume those errors.

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_error_code_rs.py -q`
  -> `3 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/error_code.py
  tests/test_app_server_error_code_rs.py`.

## src/filters.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/filters.rs`

Rust local tests:

- `compute_source_filters_defaults_to_interactive_sources`
- `compute_source_filters_empty_means_interactive_sources`
- `compute_source_filters_interactive_only_skips_post_filtering`
- `compute_source_filters_subagent_variant_requires_post_filtering`
- `source_kind_matches_distinguishes_subagent_variants`

Python parity tests:

- `test_compute_source_filters_defaults_to_interactive_sources`
- `test_compute_source_filters_empty_means_interactive_sources`
- `test_compute_source_filters_interactive_only_skips_post_filtering`
- `test_compute_source_filters_subagent_variant_requires_post_filtering`
- `test_source_kind_matches_distinguishes_subagent_variants`
- `test_source_kind_matches_app_server_unknown_and_generic_subagent`

Deferred dependency/runtime boundaries:

- This module only computes source filter constraints. It does not execute
  thread list/read queries or rollout post-filter application.

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_filters_rs.py -q`
  -> `6 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/filters.py
  tests/test_app_server_filters_rs.py`.

## src/analytics_utils.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/analytics_utils.rs`

Rust local tests:

- None in this module; behavior is defined by the source contract and consumed
  by `src/lib.rs` runtime setup.

Python parity tests:

- `test_analytics_events_client_from_config_trims_base_url_and_passes_enabled_flag`
- `test_analytics_events_client_from_config_accepts_mapping_config`

Deferred dependency/runtime boundaries:

- This module only shapes `AnalyticsEventsClient::new(...)` arguments.
  Analytics queueing, event serialization, and transport execution are owned by
  `codex-analytics`.

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_analytics_utils_rs.py -q`
  -> `2 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/analytics_utils.py
  tests/test_app_server_analytics_utils_rs.py`.

## src/attestation.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/attestation.rs`

Rust local tests:

- `app_server_attestation_header_value_wraps_opaque_client_payloads`
- `app_server_attestation_header_value_reports_app_server_failures`

Python parity tests:

- `test_app_server_attestation_header_value_wraps_opaque_client_payloads`
- `test_app_server_attestation_header_value_reports_app_server_failures`
- `test_attestation_request_projection_maps_rust_result_branches`
- `test_attestation_status_rejects_unknown_values`

Deferred dependency/runtime boundaries:

- This module currently covers the local status/envelope/result-mapping
  contract. Concrete `AttestationProvider` object wiring, weak outgoing sender
  upgrade, thread-state lookup, async timeout execution, JSON-RPC delivery, and
  HTTP header validation remain runtime dependencies.

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_attestation_rs.py -q`
  -> `4 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/attestation.py
  tests/test_app_server_attestation_rs.py`.

## src/app_server_tracing.rs

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/app_server_tracing.rs`

Rust local tests:

- None in this module; tracing behavior is covered indirectly by
  `src/message_processor_tracing_tests.rs`.

Python parity tests:

- `test_transport_name_matches_rust_transport_variants`
- `test_request_span_records_template_fields_and_session_client_info`
- `test_request_span_initialize_params_override_session_client_info`
- `test_request_span_uses_request_trace_before_env_trace`
- `test_request_span_uses_env_trace_when_request_traceparent_is_absent`
- `test_typed_request_span_uses_in_process_transport_and_typed_initialize_client_info`
- `test_transport_name_rejects_unknown_transport`

Deferred dependency/runtime boundaries:

- This module currently covers the pure span metadata and trace-source
  selection contract. Real `tracing::Span` construction, OpenTelemetry parent
  attachment, invalid carrier warnings, and global environment trace extraction
  remain telemetry/runtime dependencies.

Focused validation:

- 2026-06-19: `python -m pytest tests/test_app_server_tracing_rs.py -q`
  -> `7 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/app_server_tracing.py
  tests/test_app_server_tracing_rs.py`.
