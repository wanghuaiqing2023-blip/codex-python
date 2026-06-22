# codex-memories-write src/control.rs Status

Rust crate: `codex-memories-write`
Rust module: `src/control.rs`
Python module: `pycodex.memories.write`

## Status

`complete_slice`

## Evidence

- Rust source: `codex/codex-rs/memories/write/src/control.rs`
- Rust tests: inline `src/control.rs::tests`
- Python tests: `tests/test_memories_write_control_rs.py`

## Covered Contracts

- `clear_memory_root_contents` creates the memory root when needed.
- Clearing removes files and nested directories under the root.
- Clearing preserves the root directory itself.
- Symlinked memory roots are rejected before target contents can be removed.
- `clear_memory_roots_contents` targets both `memories` and `memories_extensions`.

## Open Outside This Module Slice

- Startup orchestration that decides when to clear memory roots.
- Cross-platform OS-specific symlink permission behavior beyond the Rust `#[cfg(unix)]` test boundary.
