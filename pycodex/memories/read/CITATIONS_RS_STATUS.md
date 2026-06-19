# codex-memories-read src/citations.rs status

Rust coordinate: `codex/codex-rs/memories/read/src/citations.rs`

Python coordinate: `pycodex/memories/read/citations.py`

Status: complete.

Ported public API:

- `parse_memory_citation`
- `thread_ids_from_memory_citation`

Ported behavior:

- Extracts `<citation_entries>...</citation_entries>` blocks from each input string.
- Parses entry lines shaped as `path:start-end|note=[text]`.
- Extracts rollout IDs from `<rollout_ids>` blocks and legacy `<thread_ids>` blocks.
- Preserves rollout ID insertion order while removing duplicates.
- Converts only valid UUID-backed rollout IDs into `ThreadId` values.
- Returns `None` when no entries or rollout IDs are parsed.

Rust-derived test evidence:

- `tests/test_memories_read_citations_rs.py`

Validation:

- Syntax-only this turn because the full `codex-memories-read` crate functional code is not yet complete:
  `python -m py_compile pycodex/memories/__init__.py pycodex/memories/read/__init__.py pycodex/memories/read/citations.py tests/test_memories_read_citations_rs.py`
