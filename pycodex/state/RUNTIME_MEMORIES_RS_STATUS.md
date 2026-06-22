# `codex-state/src/runtime/memories.rs` alignment status

Status: `complete`

Rust owner: `codex-state`  
Rust module: `codex/codex-rs/state/src/runtime/memories.rs`  
Python module: `pycodex/state/runtime/memories.py`

## Behavior contract

- `MemoryStore` accepts the memories DB and state DB separately, matching the
  Rust store's independent `pool` and `state_pool`.
- Stage-1 behavior mirrors Rust claim/update semantics: up-to-date checks
  against `stage1_outputs` and `jobs.last_success_watermark`, running lease and
  retry backoff skip outcomes, running-cap enforcement, retry reset on newer
  watermarks, success/no-output/failure finalization, output upsert, and global
  phase-2 enqueueing.
- Output listing and phase-2 input selection hydrate persisted memory rows
  through enabled `threads` metadata and skip missing/disabled threads.
- Retention pruning preserves selected phase-2 rows and prunes only stale
  unselected outputs by `COALESCE(last_usage, source_updated_at)`.
- Polluted memory mode updates the state DB and enqueues phase-2 forgetting
  when the thread participated in the selected baseline.
- Global phase-2 behavior mirrors singleton job enqueue/claim/heartbeat,
  success, selected snapshot rewrite, failure, unowned failure fallback,
  cooldown, retry, and running-lease skip handling.

## Python adaptation notes

- Claimed job outcomes use the existing model dataclasses
  `Stage1JobClaimed`/`Phase2JobClaimed`; skipped outcomes use the existing
  string enums from `pycodex.state.model.memories`.
- The Python store implements persistence/selection state only. Memory model
  generation, artifact materialization, and filesystem consolidation remain
  caller-owned, as in the Rust runtime boundary.
- Schema creation and migration execution remain owned by migrations/runtime
  initialization modules.

## Validation

- `python -m pytest tests/test_state_runtime_memories_rs.py -q` passed with
  `8 passed`.
- `python -m py_compile pycodex/state/runtime/memories.py
  pycodex/state/runtime/__init__.py pycodex/state/__init__.py
  tests/test_state_runtime_memories_rs.py`
- Formal parity coverage now includes stage-1 up-to-date skip/claim, success
  output persistence and phase-2 enqueue, no-output deletion, startup filters,
  usage/selection/retention, polluted memory mode enqueueing, phase-2
  claim/heartbeat/success snapshot/cooldown, failure retry/unowned fallback,
  and clear-all memory data behavior.

Full `codex-state` tests remain deferred until the crate's functional module
work is complete.
