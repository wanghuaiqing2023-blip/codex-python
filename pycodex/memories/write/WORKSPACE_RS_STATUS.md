# codex-memories-write src/workspace.rs

Rust crate: `codex-memories-write`
Rust module: `src/workspace.rs`
Python package: `pycodex.memories.write`

## Status

`complete_slice`

## Rust Anchors

- `prepare_memory_workspace`
- `memory_workspace_diff`
- `write_workspace_diff`
- `reset_memory_workspace_baseline`
- `remove_workspace_diff`
- `render_workspace_diff_file`
- `previous_char_boundary`

## Covered Contract

- Creates the memory root and removes generated `phase2_workspace_diff.md`
  before workspace preparation or diffing.
- Recovers an unusable local `.git` directory by replacing it with a fresh
  git baseline repository rooted at the memory directory.
- Resets the memory workspace baseline after removing the generated diff
  artifact.
- Disables Git line-ending conversion for Python-created baseline repositories
  so Windows `core.autocrlf` does not diverge from Rust `gix` raw blob
  identity.
- Renders workspace status rows and bounded unified diffs with the Rust
  truncation marker and UTF-8 byte-boundary handling.

## Python Tests

- `tests/test_memories_write_workspace_rs.py::test_render_workspace_diff_file_bounds_large_diff`
- `tests/test_memories_write_workspace_rs.py::test_reset_memory_workspace_baseline_removes_generated_diff`
- `tests/test_memories_write_workspace_rs.py::test_prepare_memory_workspace_recovers_unusable_git_dir`
- `tests/test_memories_write_workspace_rs.py::test_previous_char_boundary_handles_multibyte_text`

## Validation

2026-06-22:

- `python -m pytest tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `15 passed, 1 skipped`

2026-06-22 phase2 run orchestration follow-up:

- `python -m pytest tests\test_core_git_info.py tests\test_memories_write_workspace_rs.py -q --tb=short`
  - `21 passed, 7 subtests passed`

## Remaining Outside This Module

- Startup orchestration in `src/start.rs`.
- Phase 1 and phase 2 live model/runtime flows.
- Extension resource seeding and pruning.
- State DB integration and live backend rate-limit fetch.
