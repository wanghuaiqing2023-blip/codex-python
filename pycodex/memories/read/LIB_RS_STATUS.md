# codex-memories-read src/lib.rs status

Rust coordinate: `codex/codex-rs/memories/read/src/lib.rs`

Python coordinate: `pycodex/memories/read/__init__.py`

Status: complete.

Ported public API:

- `citations` module exports: `parse_memory_citation`, `thread_ids_from_memory_citation`
- `usage` module exports: `MEMORIES_USAGE_METRIC`, `MemoriesUsageKind`,
  `memories_usage_kinds_from_command`
- `memory_root`

Ported behavior:

- `memory_root(codex_home)` returns `codex_home.join("memories")`.
- The Python adapter accepts `AbsolutePathBuf` or an absolute path-like value
  and rejects relative raw paths to preserve the Rust `AbsolutePathBuf`
  invariant.
- Crate-root exports expose the completed `citations.rs` and `usage.rs`
  public surfaces.

Rust-derived/source-contract test evidence:

- `tests/test_memories_read_lib_rs.py`

Focused validation:

- `python -m pytest tests/test_memories_read_citations_rs.py tests/test_memories_read_usage_rs.py tests/test_memories_read_lib_rs.py -q`
- `python -m py_compile pycodex/memories/__init__.py pycodex/memories/read/__init__.py pycodex/memories/read/citations.py pycodex/memories/read/usage.py tests/test_memories_read_citations_rs.py tests/test_memories_read_usage_rs.py tests/test_memories_read_lib_rs.py`
