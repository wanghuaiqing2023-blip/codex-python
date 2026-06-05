# Unified exec process manager state

## Upstream graph/source slice

- Graph-selected core path:
  - `codex-rs/core/src/unified_exec/process_manager.rs#allocate_process_id`
  - `codex-rs/core/src/unified_exec/process_manager.rs#release_process_id`
  - `codex-rs/core/src/unified_exec/process_manager.rs#prune_processes_if_needed`
  - `codex-rs/core/src/unified_exec/process_manager.rs#process_id_to_prune_from_meta`
- Confirmed Rust behavior:
  - Test/deterministic process ids start at `1000` and increase beyond reserved ids.
  - Releasing a process id removes both the reservation and stored process entry.
  - Pruning starts once the process store reaches `MAX_UNIFIED_EXEC_PROCESSES`.
  - The eight most recently used processes are protected; outside that set, exited processes are pruned first, then least-recently-used live processes.

## Python changes

- Added `ProcessEntry` and a lightweight `UnifiedExecProcessManager` state layer in `pycodex.core.unified_exec`.
- The manager supports deterministic id allocation, release, process lookup, touch/update, pruning, and terminating all stored processes.
- Exported the new state types from `pycodex.core`.
- Added focused coverage for allocation, release, pruning, recency protection, and terminate-all cleanup.

## Validation

- `python -m py_compile pycodex/core/unified_exec.py pycodex/core/__init__.py tests/test_core_unified_exec.py`
- `python -m unittest tests.test_core_unified_exec`
- `python -m unittest tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_router`
- `python -m unittest tests.test_exec_local_runtime`

Known gaps:

- This is the pure state slice only. Full Python parity for spawning, output streaming, sandbox retry, and network approval inside the unified exec manager remains future core work.
