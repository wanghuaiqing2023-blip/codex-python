# `codex-state/src/runtime/threads.rs` alignment status

Status: `complete`

Rust owner: `codex-state`  
Rust module: `codex/codex-rs/state/src/runtime/threads.rs`  
Python module: `pycodex/state/runtime/threads.py`

## Behavior contract

- Thread reads convert the migrated `threads` row through the ported
  `ThreadRow`/`ThreadMetadata` model surface.
- Runtime thread writes preserve Rust insert/upsert semantics, including
  `created_at_ms`/`updated_at_ms`, preview fallback from first user message,
  initial memory-mode selection, non-empty preview preservation on stale
  upserts, and existing non-null Git field preservation.
- Thread listing mirrors Rust's visible-thread filters, source/provider/CWD
  filters, search term matching, archive filtering, sort anchors, and
  `page_size + 1` next-anchor calculation.
- Thread-spawn graph helpers mirror edge upsert, status updates, child and
  descendant traversal, path lookup, conflict-safe edge insertion from
  subagent source strings/JSON, and Rust's duplicate-agent-path error.
- Mutators mirror title, preview-if-empty, memory mode, touch, Git update,
  archive/unarchive, rollout item application, and delete row-count behavior.

## Python adaptation notes

- `RuntimeThreadStore` accepts either an existing `sqlite3.Connection` or a
  database path, matching the other Python runtime stores.
- `delete_thread` exposes optional `memories` and `thread_goals` cleanup hooks
  so this module does not implement neighboring `runtime/memories.rs` behavior.
- Source parsing supports Rust-style serialized subagent JSON and the current
  Python protocol's string form for thread-spawn sources.
- Schema creation and migration execution remain owned by the migrations/runtime
  initialization modules.

## Validation

- `python -m pytest tests/test_state_runtime_threads_rs.py -q` passed with
  `7 passed`.
- `python -m py_compile pycodex/state/runtime/threads.py
  pycodex/state/runtime/__init__.py pycodex/state/__init__.py
  tests/test_state_runtime_threads_rs.py`
- Formal parity coverage now includes upsert/insert-if-absent preservation,
  preview-if-empty, title/touch/Git updates, unique `updated_at_ms` allocation,
  legacy `updated_at` seconds fallback, listing filters/search/anchors,
  exact-title and rollout-path lookups, thread-spawn edge status/traversal/path
  lookup/source parsing, rollout item memory-mode restoration, archive/
  unarchive, delete hooks, and preview fallback behavior.

Full `codex-state` tests remain deferred until the crate's functional module
work is complete.
