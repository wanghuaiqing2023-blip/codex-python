# codex-memories-write src/phase2.rs

Rust crate: `codex-memories-write`
Rust module: `src/phase2.rs`
Python package: `pycodex.memories.write`

## Status

`complete_slice`

## Rust Anchors

- `sync_phase2_workspace_inputs`
- `run`
- `get_watermark`
- `is_final_agent_status`
- `emit_metrics`
- `emit_token_usage_metrics`
- `job::claim`
- `job::failed`
- `job::succeed`
- `agent::get_config`
- `agent::get_prompt`
- `agent::loop_agent`
- `agent::handle`

## Covered Contract

- Syncs selected Stage 1 outputs into the memory workspace by writing rollout
  summaries and `raw_memories.md`, then pruning old extension resources.
- Computes the completion watermark as the maximum of the claimed watermark
  and the newest selected memory timestamp.
- Treats only `PendingInit`, `Running`, and `Interrupted` agent statuses as
  non-final.
- Emits phase-2 dispatch counters with positive input counts and the
  `agent_spawned` status.
- Emits token usage histograms with Rust `token_type` tags and clamps negative
  raw token counts to zero.
- Global Phase 2 claim maps Rust skipped outcomes to stable reason strings,
  records the `claimed` counter for claimed jobs, and preserves the ownership
  token plus input watermark.
- Failure persistence records a reason counter, tries strict ownership failure
  update first, then falls back to the unowned running-job update when strict
  ownership returns false.
- Success persistence records a reason counter and delegates the completion
  watermark plus selected Stage 1 outputs to the state runtime.
- Consolidation agent config is cloned and hardened: cwd moves to the memory
  root, the run is ephemeral, memory generation/use is disabled, apps/MCP
  servers are disabled, approval is set to never, recursion-prone features are
  disabled, and sandbox policy allows only memory-root workspace writes with no
  network.
- Consolidation model defaults to the Rust stage-two model and can be
  overridden by `memories.consolidation_model`.
- Consolidation prompt is returned as one text `UserInput` containing the
  rendered Phase 2 consolidation prompt.
- Agent loop heartbeat loss and heartbeat update failures return Rust-shaped
  errored final statuses.
- Completed agents emit token usage metrics, confirm ownership with a final
  heartbeat, reset the workspace baseline, mark success, and request
  consolidation-agent shutdown.
- Completed agents do not reset the baseline or mark success when the final
  ownership heartbeat returns false.
- Non-completed final statuses mark `failed_agent`; ownership confirmation
  errors mark `failed_confirm_ownership`.
- Run-level orchestration follows Rust's strict phase-2 order: start timer,
  require state DB, claim the global job, prepare the git-backed memory
  workspace, harden agent config, load DB-selected inputs, sync workspace
  files, inspect workspace diff, succeed immediately when there are no changes,
  write the diff file when there are changes, spawn the consolidation agent,
  handle completed-agent ownership/baseline reset/success, and emit dispatch
  metrics.

## Python Tests

- `tests/test_memories_write_phase2_rs.py::test_phase_two_get_watermark_uses_latest_memory_timestamp_or_claimed_watermark`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_is_final_agent_status_matches_rust_nonfinal_variants`
- `tests/test_memories_write_phase2_rs.py::test_emit_phase_two_metrics_records_input_and_agent_spawned`
- `tests/test_memories_write_phase2_rs.py::test_emit_phase_two_token_usage_metrics_clamps_negative_values`
- `tests/test_memories_write_phase2_rs.py::test_sync_phase2_workspace_inputs_syncs_current_selection_and_prunes_extensions`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_claim_maps_rust_outcomes_and_records_claim_metric`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_failed_uses_strict_update_then_unowned_fallback`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_succeed_records_reason_counter_and_persists_watermark_selection`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_agent_config_hardens_consolidation_worker`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_agent_config_uses_configured_model_and_prompt_text`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_loop_agent_maps_heartbeat_loss_and_failure_to_errored_status`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_handle_completed_agent_confirms_ownership_resets_and_succeeds`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_handle_completed_agent_does_not_reset_or_succeed_after_lost_lock`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_handle_failed_agent_and_confirm_ownership_error_mark_failures`
- `tests/test_memories_write_phase2_rs.py::test_phase_two_run_tracks_workspace_diff_spawns_agent_and_resets_baseline`

## Validation

2026-06-22:

- `python -m pytest tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `32 passed, 1 skipped`

2026-06-22 DB persistence follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `16 passed`
- Included in full memories/write validation:
  - `40 passed, 1 skipped`

2026-06-22 agent config follow-up:

- `python -m pytest tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `10 passed`
- Included in full memories/write validation:
  - `42 passed, 1 skipped`

2026-06-22 agent completion follow-up:

- `python -m pytest tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `14 passed`
- Included in full memories/write validation:
  - `46 passed, 1 skipped`

2026-06-22 run orchestration follow-up:

- `python -m pytest tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `15 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `66 passed, 1 skipped`
- `python -m pytest tests\test_core_git_info.py tests\test_memories_write_workspace_rs.py -q --tb=short`
  - `21 passed, 7 subtests passed`
- `python -m py_compile pycodex\memories\write\__init__.py pycodex\git_utils\__init__.py tests\test_memories_write_phase2_rs.py`
  - passed

## Remaining Outside This Slice

- Exact Tokio heartbeat timing, select! scheduling, and shutdown timeout
  identity.
- Real `ModelClient` phase-1 network streaming and native `CodexThread`
  consolidation-agent runtime identity.
