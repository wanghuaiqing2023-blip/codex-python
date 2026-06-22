# codex-memories-read test alignment

Rust crate: `codex-memories-read`

Python package: `pycodex/memories/read`

Status: `complete`

Module mapping:

- `codex/codex-rs/memories/read/src/citations.rs` -> `pycodex/memories/read/citations.py` (`complete`)
- `codex/codex-rs/memories/read/src/usage.rs` -> `pycodex/memories/read/usage.py` (`complete`)
- `codex/codex-rs/memories/read/src/lib.rs` -> `pycodex/memories/read/__init__.py` (`complete`)

Rust-derived coverage for `src/citations.rs`:

- `parse_memory_citation_supports_legacy_thread_ids`
- `parse_memory_citation_supports_rollout_ids`
- `parse_memory_citation_extracts_entries_and_rollout_ids`

Additional source-contract coverage:

- Empty or malformed input returns `None` when no entries or rollout IDs parse.
- `src/usage.rs` enum tag strings, safe-command gate, read/search path classification, and list/unknown/non-memory path ignores.
- `src/lib.rs` `memory_root` joins `memories`, enforces absolute raw path inputs, and re-exports public citations/usage symbols.

Validation:

- `python -m pytest tests/test_memories_read_citations_rs.py tests/test_memories_read_usage_rs.py tests/test_memories_read_lib_rs.py -q`
- `python -m py_compile pycodex/memories/__init__.py pycodex/memories/read/__init__.py pycodex/memories/read/citations.py pycodex/memories/read/usage.py tests/test_memories_read_citations_rs.py tests/test_memories_read_usage_rs.py tests/test_memories_read_lib_rs.py`
