# codex-memories-write runtime.rs Status

Rust crate: `codex-memories-write`
Rust module: `src/runtime.rs`
Python target: `pycodex.memories.write`

## Covered

- `MemoryStartupContext` dependency-light context projection:
  - `state_db`
  - `counter`
  - `histogram`
  - `start_timer`
- `StageOneRequestContext` dependency-light request context projection:
  - model info
  - session telemetry
  - reasoning effort
  - reasoning summary
  - service tier
  - detached turn metadata header
- `stage_one_request_context` source contract:
  - reads service tier from the live thread config snapshot
  - resolves model info through the thread manager models manager
  - uses `config.model_reasoning_summary` when set
  - falls back to `ModelInfo.default_reasoning_summary`
  - delegates turn metadata to `codex_core::build_turn_metadata_header` equivalent
  - clones/retargets telemetry with the requested model name
- `stream_stage_one_prompt` dependency-light stream contract:
  - creates a client session through an injected model client factory
  - passes prompt, model info, telemetry, reasoning effort/summary, service tier,
    and turn metadata to the stream call
  - appends `OutputTextDelta` text
  - uses `OutputItemDone(Message)` text only when no delta has been seen
  - stores `Completed` token usage and stops consuming events
  - ignores later stream events after completion
- Telemetry method delegation for both runtime contexts.
- `spawn_consolidation_agent` dependency-light runtime facade:
  - default environment selection from the thread manager
  - `InitialHistory::New`
  - internal `MemoryConsolidation` session source
  - `ThreadSource::MemoryConsolidation`
  - empty dynamic tools
  - disabled extended-history persistence
  - initial `Op::UserInput` submit
  - submit-error cleanup through `shutdown_consolidation_agent`
- `shutdown_consolidation_agent` dependency-light runtime facade:
  - removes the thread from the manager first
  - falls back to the supplied thread when removal returns none
  - waits for shutdown
  - reports the Rust-shaped timeout message

## Evidence

- Rust source: `codex/codex-rs/memories/write/src/runtime.rs`
- Rust test: `codex/codex-rs/memories/write/src/startup_tests.rs::memories_startup_phase1_uses_live_thread_service_tier_and_detached_metadata`
- Rust dependency source: `codex/codex-rs/core/src/turn_metadata.rs::build_turn_metadata_header`
- Rust dependency tests:
  - `codex/codex-rs/core/src/turn_metadata_tests.rs::build_turn_metadata_header_marks_detached_memory_without_turn_identity`
  - `codex/codex-rs/core/src/turn_metadata_tests.rs::build_turn_metadata_header_marks_memory_without_workspace_metadata`
- Python tests: `tests/test_memories_write_runtime_rs.py`

## Validation

2026-06-22:

- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `35 passed, 1 skipped`
- `python -m py_compile pycodex\memories\write\__init__.py tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py`
  - passed

2026-06-22 consolidation agent runtime follow-up:

- `python -m pytest tests\test_memories_write_runtime_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `49 passed, 1 skipped`

2026-06-22 stage-one streaming follow-up:

- `python -m pytest tests\test_memories_write_runtime_rs.py -q --tb=short`
  - `8 passed`
- `python -m pytest tests\test_memories_write_runtime_rs.py tests\test_memories_write_phase2_rs.py tests\test_memories_write_phase1_rs.py tests\test_memories_write_start_rs.py tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `51 passed, 1 skipped`

## Remaining Runtime Gaps

- Exact live `ModelClient::new` construction, installation id resolution, and
  network stream execution in `stream_stage_one_prompt`.
- Exact live `ThreadManager`/Tokio orchestration identity for spawned
  consolidation agents.
- `shutdown_consolidation_agent` exact Tokio timeout/cancellation behavior
  beyond the dependency-light timeout contract.
- Phase 1 state DB claim/result persistence and live rollout loading.
- Workspace baseline reset after a real spawned phase2 success.

Status: `complete_slice`; crate remains `module_progress`.
