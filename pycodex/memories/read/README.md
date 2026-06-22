# pycodex.memories.read

Python alignment target for Rust crate `codex-memories-read`.

Rust coordinates:

- `codex/codex-rs/memories/read/src/citations.rs`
- `codex/codex-rs/memories/read/src/usage.rs`
- `codex/codex-rs/memories/read/src/lib.rs`

Python mapping:

- `pycodex/memories/read/citations.py`
- `pycodex/memories/read/usage.py`
- `pycodex/memories/read/__init__.py`

Current status: complete.

Certified modules:

- `src/citations.rs`: complete. Parses memory citation blocks, citation entries, rollout IDs, legacy thread IDs, duplicate rollout IDs, and valid thread IDs.
- `src/usage.rs`: complete. Classifies safe memory read/search commands into telemetry usage kinds.
- `src/lib.rs`: complete. Exposes crate-root public API and `memory_root`.

Validation:

- `python -m pytest tests/test_memories_read_citations_rs.py tests/test_memories_read_usage_rs.py tests/test_memories_read_lib_rs.py -q`
- `python -m py_compile pycodex/memories/__init__.py pycodex/memories/read/__init__.py pycodex/memories/read/citations.py pycodex/memories/read/usage.py tests/test_memories_read_citations_rs.py tests/test_memories_read_usage_rs.py tests/test_memories_read_lib_rs.py`
