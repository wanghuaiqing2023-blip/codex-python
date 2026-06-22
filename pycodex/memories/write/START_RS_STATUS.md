# codex-memories-write src/start.rs

Rust crate: `codex-memories-write`
Rust module: `src/start.rs`
Python package: `pycodex.memories.write`

## Status

`complete_slice`

## Rust Anchors

- `start_memories_startup_task`
- `config.ephemeral`
- `config.features.enabled(Feature::MemoryTool)`
- `SessionSource::is_non_root_agent`
- `MemoryStartupContext::state_db`
- `seed_extension_instructions`
- `guard::rate_limits_ok`
- `phase1::prune`
- `phase1::run`
- `phase2::run`

## Covered Contract

- Skips startup for ephemeral sessions.
- Skips startup when the memory tool feature is disabled.
- Skips startup for non-root agent sessions.
- Skips startup when state DB is unavailable.
- Creates the memory root for eligible startup.
- Seeds ad-hoc extension instructions before phase work.
- Runs phase 1 pruning before the rate-limit gate.
- Records `skipped_rate_limit` and does not run phase 1/phase 2 when the
  rate-limit gate fails.
- Runs phase 1 before phase 2 when eligible and rate limits allow startup.

## Python Tests

- `tests/test_memories_write_start_rs.py::test_memory_startup_skip_reason_matches_start_rs_gates`
- `tests/test_memories_write_start_rs.py::test_start_memories_startup_task_creates_root_seeds_and_runs_phases`
- `tests/test_memories_write_start_rs.py::test_start_memories_startup_task_rate_limit_skip_after_prune`

## Validation

2026-06-22:

- `python -m pytest tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `21 passed, 1 skipped`

## Remaining Outside This Module

- Exact Tokio `spawn` task identity and scheduling.
- `src/runtime.rs` live request context, model client streaming, and
  consolidation agent lifecycle.
- `src/phase1.rs` state DB claiming/model request behavior.
- `src/phase2.rs` state DB consolidation/model-agent behavior.
