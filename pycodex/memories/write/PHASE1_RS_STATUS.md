# codex-memories-write src/phase1.rs

Rust crate: `codex-memories-write`
Rust module: `src/phase1.rs`
Python package: `pycodex.memories.write`

## Status

`complete_slice`

## Rust Anchors

- `output_schema`
- `StageOneOutput`
- `job::run`
- `job::sample`
- `job::serialize_filtered_rollout_response_items`
- `job::sanitize_response_item_for_memories`
- `job::is_memory_excluded_contextual_user_fragment`
- `job::matches_marked_fragment`
- `aggregate_stats`
- `emit_metrics`
- `run`
- `JobResult`
- `JobOutcome`
- `Stats`
- `claim_startup_jobs`
- `job::result::{failed,no_output,success}`

## Covered Contract

- Phase-1 model output schema requires `raw_memory`, `rollout_summary`, and
  nullable `rollout_slug`, with `additionalProperties: false`.
- AGENTS.md and `<skill>...</skill>` contextual user fragments are excluded
  from memory rollout serialization.
- Environment context and subagent notification user fragments are retained.
- Empty user messages after filtering are dropped.
- Non-message persistable response items are retained.
- Rollout serialization is secret-redacted before prompt upload.
- `job::sample` builds a strict stage-one `Prompt` with the Rust system prompt,
  serialized rollout contents, output schema, and single user input message.
- `job::sample` consumes the Rust `RolloutRecorder::load_rollout_items` tuple
  shape through the rollout-loader boundary.
- `job::sample` defaults to the completed `pycodex.rollout.RolloutRecorder`
  loader, consuming real JSONL rollout files without a test-injected loader.
- `StageOneOutput` parsing preserves required field and unknown-field rejection
  behavior, then redacts `raw_memory`, `rollout_summary`, and nullable
  `rollout_slug`.
- `job::run` maps sample errors to `result::failed` and a failed `JobResult`
  without token usage.
- `job::run` maps empty `raw_memory` or `rollout_summary` to
  `result::no_output`, preserving sample token usage.
- `job::run` maps non-empty output to `result::success`, passing the claimed
  thread id, ownership token, `updated_at.timestamp()`, raw memory, summary,
  slug, and token usage.
- Phase-1 job statistics count claimed/succeeded/no-output/failed outcomes and
  sum token usage only when at least one job reports usage.
- Phase-1 metrics emit Rust job/output counters and token usage histograms.
- Startup job claims build Rust `Stage1StartupClaimParams` with interactive
  session sources, scan/lease constants, and memory config limits.
- Run-level orchestration builds one stage-one request context using
  `memories.extract_model` or the Rust default model, starts the e2e timer,
  claims jobs, emits `skipped_no_candidates` for empty claims, runs claimed jobs
  with the shared request context, aggregates outcomes, and emits metrics.
- Failed jobs persist the retry delay while ignoring DB errors.
- No-output and success result helpers map DB update success to Rust
  `JobOutcome` variants and return `Failed` when the DB is unavailable or the
  ownership update fails.

## Python Tests

- `tests/test_memories_write_phase1_rs.py::test_classifies_memory_excluded_fragments`
- `tests/test_memories_write_phase1_rs.py::test_output_schema_requires_rollout_slug_and_keeps_it_nullable`
- `tests/test_memories_write_phase1_rs.py::test_serializes_memory_rollout_with_agents_removed_but_environment_kept`
- `tests/test_memories_write_phase1_rs.py::test_serializes_memory_rollout_redacts_secrets_before_prompt_upload`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_sample_builds_strict_prompt_streams_and_redacts_output`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_sample_uses_rollout_loader_tuple_shape`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_sample_loads_real_rollout_jsonl_by_default`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_sample_rejects_unknown_stage_one_output_fields`
- `tests/test_memories_write_phase1_rs.py::test_count_outcomes_sums_token_usage_across_all_jobs`
- `tests/test_memories_write_phase1_rs.py::test_count_outcomes_keeps_usage_empty_when_no_job_reports_it`
- `tests/test_memories_write_phase1_rs.py::test_emit_phase_one_metrics_matches_rust_counters_and_token_histograms`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_claim_startup_jobs_builds_rust_params_and_returns_claims`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_run_skips_after_empty_claims_and_uses_default_model`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_run_runs_claimed_jobs_and_emits_aggregate_metrics`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_job_run_persists_sample_output_with_source_timestamp`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_job_run_marks_no_output_for_empty_model_fields`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_job_run_marks_failed_when_sample_errors`
- `tests/test_memories_write_phase1_rs.py::test_phase_one_result_markers_match_rust_db_calls_and_outcomes`

## Validation

2026-06-22:

- `python -m pytest tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `27 passed, 1 skipped`

2026-06-22 DB persistence follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py tests\test_memories_write_phase2_rs.py -q --tb=short`
  - `16 passed`
- Included in full memories/write validation:
  - `40 passed, 1 skipped`

2026-06-22 run orchestration follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py -q --tb=short`
  - `11 passed`
- Included in full memories/write validation:
  - `54 passed, 1 skipped`

2026-06-22 sample prompt/output follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py -q --tb=short`
  - `14 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `57 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 job run branch follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py -q --tb=short`
  - `17 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `60 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 default rollout loader follow-up:

- `python -m pytest tests\test_memories_write_phase1_rs.py -q --tb=short`
  - `18 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `61 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

## Remaining Outside This Slice

- Live stage-one model request streaming.
- End-to-end `job::run` over real rollout files/model stream.
- Exact native Rust Tokio file-reader identity is delegated to the completed
  `pycodex.rollout` port.
