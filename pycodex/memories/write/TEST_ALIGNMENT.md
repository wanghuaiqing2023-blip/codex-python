# codex-memories-write Test Alignment

Rust crate: `codex-memories-write`
Rust path: `codex/codex-rs/memories/write`

## Status

`complete`

The `src/storage.rs`, `src/prompts.rs`, `src/guard.rs`, `src/control.rs`,
`src/workspace.rs`, `src/extensions/*`, and `src/start.rs` modules have
dependency-light complete slices in Python. `src/phase1.rs`
serialization/schema/stats/metrics/run orchestration helpers and `src/phase2.rs`
workspace/metrics helpers are also covered. `src/runtime.rs`
context/telemetry/stage-one request helpers are covered. Phase 1 and Phase 2 DB
claim/result helper slices are covered. Phase 2 consolidation agent
config/prompt/completion helpers are covered. Runtime stage-one stream event
handling and consolidation agent spawn/shutdown facade helpers are covered.
Exact live model-client network streaming, Tokio task scheduling identity,
native backend-client transport identity, and native spawned-agent runtime
identity are documented as non-blocking implementation differences for the
dependency-light Python projection.

## Rust-Derived Tests

| Rust module | Rust tests/contracts | Python tests | Status |
|---|---|---|---|
| `src/storage.rs` / `src/storage_tests.rs` | `rollout_summary_file_stem_uses_uuid_timestamp_and_hash_when_slug_missing` | `tests/test_memories_write_storage_rs.py::test_rollout_summary_file_stem_uses_uuid_timestamp_and_hash_when_slug_missing` | complete |
| `src/storage.rs` / `src/storage_tests.rs` | `rollout_summary_file_stem_sanitizes_and_truncates_slug` | `tests/test_memories_write_storage_rs.py::test_rollout_summary_file_stem_sanitizes_and_truncates_slug` | complete |
| `src/storage.rs` / `src/storage_tests.rs` | `rollout_summary_file_stem_uses_uuid_timestamp_and_hash_when_slug_is_empty` | `tests/test_memories_write_storage_rs.py::test_rollout_summary_file_stem_uses_uuid_timestamp_and_hash_when_slug_is_empty` | complete |
| `src/storage.rs` / `src/storage_tests.rs` | `sync_rollout_summaries_and_raw_memories_file_keeps_latest_memories_only` | `tests/test_memories_write_storage_rs.py::test_sync_rollout_summaries_and_raw_memories_file_keeps_latest_memories_only` | complete |
| `src/prompts.rs` / `src/prompts_tests.rs` | `build_stage_one_input_message_truncates_rollout_using_model_context_window` | `tests/test_memories_write_prompts_rs.py::test_build_stage_one_input_message_truncates_rollout_using_model_context_window` | complete |
| `src/prompts.rs` / `src/prompts_tests.rs` | `build_stage_one_input_message_uses_default_limit_when_model_context_window_missing` | `tests/test_memories_write_prompts_rs.py::test_build_stage_one_input_message_uses_default_limit_when_model_context_window_missing` | complete |
| `src/prompts.rs` / `src/prompts_tests.rs` | `build_consolidation_prompt_points_to_workspace_diff_and_extension_tree` | `tests/test_memories_write_prompts_rs.py::test_build_consolidation_prompt_points_to_workspace_diff_and_extension_tree` | complete |
| `src/guard.rs` / `src/guard_tests.rs` | `startup_check_uses_configured_remaining_threshold` | `tests/test_memories_write_guard_rs.py::test_startup_check_uses_configured_remaining_threshold` | complete |
| `src/guard.rs` / `src/guard_tests.rs` | `startup_check_skips_when_primary_or_secondary_is_too_low` | `tests/test_memories_write_guard_rs.py::test_startup_check_skips_when_primary_or_secondary_is_too_low` | complete |
| `src/guard.rs` / `src/guard_tests.rs` | `startup_check_skips_when_limit_is_reached` | `tests/test_memories_write_guard_rs.py::test_startup_check_skips_when_limit_is_reached` | complete |
| `src/guard.rs` | `rate_limits_ok` missing/non-backend auth default allow | `tests/test_memories_write_guard_rs.py::test_rate_limits_ok_allows_when_auth_missing_or_not_backend` | complete_slice |
| `src/guard.rs` | `rate_limits_check` Codex limit id selection | `tests/test_memories_write_guard_rs.py::test_rate_limits_check_selects_codex_limit_before_first_snapshot` | complete_slice |
| `src/guard.rs` | `rate_limits_check` first-snapshot fallback block | `tests/test_memories_write_guard_rs.py::test_rate_limits_check_falls_back_to_first_snapshot_and_blocks` | complete_slice |
| `src/guard.rs` | `rate_limits_ok` client/fetch/empty fallback allow | `tests/test_memories_write_guard_rs.py::test_rate_limits_ok_defaults_true_on_client_or_fetch_failures` | complete_slice |
| `src/control.rs` | `clear_memory_root_contents_preserves_root_directory` | `tests/test_memories_write_control_rs.py::test_clear_memory_root_contents_preserves_root_directory` | complete |
| `src/control.rs` | `clear_memory_root_contents_rejects_symlinked_root` | `tests/test_memories_write_control_rs.py::test_clear_memory_root_contents_rejects_symlinked_root` | complete; skipped on non-Unix hosts matching Rust `#[cfg(unix)]` |
| `src/workspace.rs` / `src/workspace_tests.rs` | `render_workspace_diff_file_bounds_large_diff` | `tests/test_memories_write_workspace_rs.py::test_render_workspace_diff_file_bounds_large_diff` | complete |
| `src/workspace.rs` / `src/workspace_tests.rs` | `reset_memory_workspace_baseline_removes_generated_diff` | `tests/test_memories_write_workspace_rs.py::test_reset_memory_workspace_baseline_removes_generated_diff` | complete |
| `src/workspace.rs` / `src/workspace_tests.rs` | `prepare_memory_workspace_recovers_unusable_git_dir` | `tests/test_memories_write_workspace_rs.py::test_prepare_memory_workspace_recovers_unusable_git_dir` | complete |
| `src/workspace.rs` / `src/workspace_tests.rs` | `previous_char_boundary_handles_multibyte_text` | `tests/test_memories_write_workspace_rs.py::test_previous_char_boundary_handles_multibyte_text` | complete |
| `src/extensions/ad_hoc.rs` / `src/extensions/ad_hoc_tests.rs` | `seeds_instructions_without_overwriting_existing_file` | `tests/test_memories_write_extensions_rs.py::test_seeds_instructions_without_overwriting_existing_file` | complete |
| `src/extensions/prune.rs` / `src/extensions/prune_tests.rs` | `prunes_only_old_resources_from_extensions_with_instructions` | `tests/test_memories_write_extensions_rs.py::test_prunes_only_old_resources_from_extensions_with_instructions` | complete |
| `src/extensions/prune.rs` / `src/extensions/prune_tests.rs` | `parses_timestamp_prefix_from_resource_file_name` | `tests/test_memories_write_extensions_rs.py::test_parses_timestamp_prefix_from_resource_file_name` | complete |
| `src/start.rs` | Startup eligibility gates in `start_memories_startup_task` | `tests/test_memories_write_start_rs.py::test_memory_startup_skip_reason_matches_start_rs_gates` | complete |
| `src/start.rs` / `src/startup_tests.rs` | `memories_startup_creates_memory_root` plus startup source contract | `tests/test_memories_write_start_rs.py::test_start_memories_startup_task_creates_root_seeds_and_runs_phases` | complete_slice |
| `src/start.rs` | Rate-limit skip branch after pruning | `tests/test_memories_write_start_rs.py::test_start_memories_startup_task_rate_limit_skip_after_prune` | complete_slice |
| `src/phase1.rs` / `job::tests` | `classifies_memory_excluded_fragments` | `tests/test_memories_write_phase1_rs.py::test_classifies_memory_excluded_fragments` | complete |
| `src/phase1.rs` / `job::tests` | `output_schema_requires_rollout_slug_and_keeps_it_nullable` | `tests/test_memories_write_phase1_rs.py::test_output_schema_requires_rollout_slug_and_keeps_it_nullable` | complete |
| `src/phase1.rs` / `tests` | `serializes_memory_rollout_with_agents_removed_but_environment_kept` | `tests/test_memories_write_phase1_rs.py::test_serializes_memory_rollout_with_agents_removed_but_environment_kept` | complete |
| `src/phase1.rs` / `tests` | `serializes_memory_rollout_redacts_secrets_before_prompt_upload` | `tests/test_memories_write_phase1_rs.py::test_serializes_memory_rollout_redacts_secrets_before_prompt_upload` | complete |
| `src/phase1.rs` | `job::sample` prompt/schema/output redaction | `tests/test_memories_write_phase1_rs.py::test_phase_one_sample_builds_strict_prompt_streams_and_redacts_output` | complete_slice |
| `src/phase1.rs` | `job::sample` rollout-loader tuple consumption | `tests/test_memories_write_phase1_rs.py::test_phase_one_sample_uses_rollout_loader_tuple_shape` | complete_slice |
| `src/phase1.rs` + `codex-rollout/src/recorder.rs` | `job::sample` default real JSONL rollout loading | `tests/test_memories_write_phase1_rs.py::test_phase_one_sample_loads_real_rollout_jsonl_by_default` | complete_slice |
| `src/phase1.rs` | `StageOneOutput` deny-unknown-fields parse boundary | `tests/test_memories_write_phase1_rs.py::test_phase_one_sample_rejects_unknown_stage_one_output_fields` | complete_slice |
| `src/phase1.rs` / `tests` | `count_outcomes_sums_token_usage_across_all_jobs` | `tests/test_memories_write_phase1_rs.py::test_count_outcomes_sums_token_usage_across_all_jobs` | complete |
| `src/phase1.rs` / `tests` | `count_outcomes_keeps_usage_empty_when_no_job_reports_it` | `tests/test_memories_write_phase1_rs.py::test_count_outcomes_keeps_usage_empty_when_no_job_reports_it` | complete |
| `src/phase1.rs` | `emit_metrics` | `tests/test_memories_write_phase1_rs.py::test_emit_phase_one_metrics_matches_rust_counters_and_token_histograms` | complete_slice |
| `src/phase1.rs` | `claim_startup_jobs` | `tests/test_memories_write_phase1_rs.py::test_phase_one_claim_startup_jobs_builds_rust_params_and_returns_claims` | complete_slice |
| `src/phase1.rs` | `run` empty-claim branch and default model | `tests/test_memories_write_phase1_rs.py::test_phase_one_run_skips_after_empty_claims_and_uses_default_model` | complete_slice |
| `src/phase1.rs` | `run` claimed job orchestration and metrics | `tests/test_memories_write_phase1_rs.py::test_phase_one_run_runs_claimed_jobs_and_emits_aggregate_metrics` | complete_slice |
| `src/phase1.rs` | `job::run` sample success branch | `tests/test_memories_write_phase1_rs.py::test_phase_one_job_run_persists_sample_output_with_source_timestamp` | complete_slice |
| `src/phase1.rs` | `job::run` no-output branch | `tests/test_memories_write_phase1_rs.py::test_phase_one_job_run_marks_no_output_for_empty_model_fields` | complete_slice |
| `src/phase1.rs` | `job::run` sample-error branch | `tests/test_memories_write_phase1_rs.py::test_phase_one_job_run_marks_failed_when_sample_errors` | complete_slice |
| `src/phase1.rs` | `job::result::{failed,no_output,success}` | `tests/test_memories_write_phase1_rs.py::test_phase_one_result_markers_match_rust_db_calls_and_outcomes` | complete_slice |
| `src/phase2.rs` | `get_watermark` | `tests/test_memories_write_phase2_rs.py::test_phase_two_get_watermark_uses_latest_memory_timestamp_or_claimed_watermark` | complete |
| `src/phase2.rs` | `is_final_agent_status` | `tests/test_memories_write_phase2_rs.py::test_phase_two_is_final_agent_status_matches_rust_nonfinal_variants` | complete |
| `src/phase2.rs` | `emit_metrics` | `tests/test_memories_write_phase2_rs.py::test_emit_phase_two_metrics_records_input_and_agent_spawned` | complete |
| `src/phase2.rs` | `emit_token_usage_metrics` | `tests/test_memories_write_phase2_rs.py::test_emit_phase_two_token_usage_metrics_clamps_negative_values` | complete |
| `src/phase2.rs` | `sync_phase2_workspace_inputs` | `tests/test_memories_write_phase2_rs.py::test_sync_phase2_workspace_inputs_syncs_current_selection_and_prunes_extensions` | complete_slice |
| `src/phase2.rs` | `job::claim` | `tests/test_memories_write_phase2_rs.py::test_phase_two_claim_maps_rust_outcomes_and_records_claim_metric` | complete_slice |
| `src/phase2.rs` | `job::failed` | `tests/test_memories_write_phase2_rs.py::test_phase_two_failed_uses_strict_update_then_unowned_fallback` | complete_slice |
| `src/phase2.rs` | `job::succeed` | `tests/test_memories_write_phase2_rs.py::test_phase_two_succeed_records_reason_counter_and_persists_watermark_selection` | complete_slice |
| `src/phase2.rs` | `agent::get_config` | `tests/test_memories_write_phase2_rs.py::test_phase_two_agent_config_hardens_consolidation_worker` | complete_slice |
| `src/phase2.rs` | `agent::get_config` / `agent::get_prompt` | `tests/test_memories_write_phase2_rs.py::test_phase_two_agent_config_uses_configured_model_and_prompt_text` | complete_slice |
| `src/phase2.rs` | `agent::loop_agent` heartbeat outcomes | `tests/test_memories_write_phase2_rs.py::test_phase_two_loop_agent_maps_heartbeat_loss_and_failure_to_errored_status` | complete_slice |
| `src/phase2.rs` | `agent::handle` completed/success path | `tests/test_memories_write_phase2_rs.py::test_phase_two_handle_completed_agent_confirms_ownership_resets_and_succeeds` | complete_slice |
| `src/phase2.rs` | `agent::handle` completed/lost-lock path | `tests/test_memories_write_phase2_rs.py::test_phase_two_handle_completed_agent_does_not_reset_or_succeed_after_lost_lock` | complete_slice |
| `src/phase2.rs` | `agent::handle` failure paths | `tests/test_memories_write_phase2_rs.py::test_phase_two_handle_failed_agent_and_confirm_ownership_error_mark_failures` | complete_slice |
| `src/phase2.rs` / `src/startup_tests.rs` | `run` + `memories_startup_phase2_tracks_workspace_diff_across_runs` | `tests/test_memories_write_phase2_rs.py::test_phase_two_run_tracks_workspace_diff_spawns_agent_and_resets_baseline` | complete_slice |
| `src/runtime.rs` / `src/startup_tests.rs` | `stage_one_request_context` + `memories_startup_phase1_uses_live_thread_service_tier_and_detached_metadata` | `tests/test_memories_write_runtime_rs.py::test_stage_one_request_context_uses_thread_service_tier_and_detached_metadata` | complete_slice |
| `src/runtime.rs` | `stage_one_request_context` reasoning-summary selection | `tests/test_memories_write_runtime_rs.py::test_stage_one_request_context_config_reasoning_summary_overrides_model_default` | complete |
| `src/runtime.rs` | `stream_stage_one_prompt` delta/completed event handling | `tests/test_memories_write_runtime_rs.py::test_stream_stage_one_prompt_collects_deltas_and_completed_token_usage` | complete_slice |
| `src/runtime.rs` | `stream_stage_one_prompt` output-item fallback behavior | `tests/test_memories_write_runtime_rs.py::test_stream_stage_one_prompt_uses_message_item_only_when_no_delta_seen` | complete_slice |
| `src/runtime.rs` | `MemoryStartupContext` and `StageOneRequestContext` telemetry delegation | `tests/test_memories_write_runtime_rs.py::test_runtime_context_and_stage_one_context_delegate_telemetry` | complete |
| `src/runtime.rs` | `spawn_consolidation_agent` start options and initial submit | `tests/test_memories_write_runtime_rs.py::test_spawn_consolidation_agent_uses_memory_thread_options_and_submits_prompt` | complete_slice |
| `src/runtime.rs` | `spawn_consolidation_agent` submit-error cleanup | `tests/test_memories_write_runtime_rs.py::test_spawn_consolidation_agent_shuts_down_started_thread_when_submit_fails` | complete_slice |
| `src/runtime.rs` | `shutdown_consolidation_agent` remove/shutdown/timeout behavior | `tests/test_memories_write_runtime_rs.py::test_shutdown_consolidation_agent_prefers_removed_thread_and_times_out` | complete_slice |

## Validation

2026-06-22:

- `python -m pytest tests\test_memories_write_storage_rs.py -q --tb=short`
  - `4 passed`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 prompts follow-up:

- `python -m pytest tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `7 passed`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 guard follow-up:

- `python -m pytest tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `10 passed`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 control follow-up:

- `python -m pytest tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `11 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 workspace follow-up:

- `python -m pytest tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `15 passed, 1 skipped`

2026-06-22 extensions follow-up:

- `python -m pytest tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `18 passed, 1 skipped`

2026-06-22 start follow-up:

- `python -m pytest tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `21 passed, 1 skipped`

2026-06-22 phase1 follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `27 passed, 1 skipped`

2026-06-22 phase2 follow-up:

- `python -m pytest tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `32 passed, 1 skipped`

2026-06-22 runtime follow-up:

- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `35 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 phase DB helper follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `16 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `40 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 phase2 agent config follow-up:

- `python -m pytest tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `10 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `42 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 phase2 agent completion follow-up:

- `python -m pytest tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `14 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `46 passed, 1 skipped`

2026-06-22 runtime consolidation agent follow-up:

- `python -m pytest tests\test_memories_write_runtime_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `49 passed, 1 skipped`

2026-06-22 runtime stage-one streaming follow-up:

- `python -m pytest tests\test_memories_write_runtime_rs.py -q --tb=short`
  - `8 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `51 passed, 1 skipped`

2026-06-22 phase1 run orchestration follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py -q --tb=short`
  - `11 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `54 passed, 1 skipped`

2026-06-22 phase1 sample prompt/output follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py -q --tb=short`
  - `14 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `57 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 phase1 job run branch follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py -q --tb=short`
  - `17 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `60 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 phase1 default rollout loader follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py -q --tb=short`
  - `18 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `61 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 guard rate-limits follow-up:

- `python -m pytest tests\test_memories_write_guard_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `65 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_guard_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 phase2 run orchestration follow-up:

- `python -m pytest tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `15 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `66 passed, 1 skipped`
- `python -m pytest tests\test_core_git_info.py tests\test_memories_write_workspace_rs.py -q --tb=short`
  - `21 passed, 7 subtests passed`
- `python -m py_compile pycodex\memories\write\__init__.py pycodex\git_utils\__init__.py tests\test_memories_write_phase2_rs.py`
  - passed
