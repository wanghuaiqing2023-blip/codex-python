# codex-memories-write src/storage.rs Status

Rust crate: `codex-memories-write`
Rust module: `src/storage.rs`
Python module: `pycodex.memories.write`

## Status

`complete_slice`

## Evidence

- Rust source: `codex/codex-rs/memories/write/src/storage.rs`
- Rust tests: `codex/codex-rs/memories/write/src/storage_tests.rs`
- Python tests: `tests/test_memories_write_storage_rs.py`

## Covered Contracts

- `rollout_summary_file_stem` derives UUIDv7 timestamp fragments and lower-32-bit base62 short hashes.
- Rollout slugs are lowercased, non-ASCII/non-alphanumeric characters become `_`, trailing `_` is trimmed, and the slug prefix is capped at 60 characters.
- Empty or fully trimmed slugs do not add a suffix.
- `sync_rollout_summaries_from_memories` creates the layout, prunes stale `.md` summary files, and writes canonical rollout summary files.
- `rebuild_raw_memories_file_from_memories` writes Rust-shaped `raw_memories.md` metadata and references the canonical summary file.

## Open Outside This Module Slice

- Startup orchestration and state DB integration.
- Phase 1 model request construction and rollout sanitization.
- Phase 2 consolidation agent runtime.
- Prompt template rendering.
- Workspace diffing and extension resource management.
