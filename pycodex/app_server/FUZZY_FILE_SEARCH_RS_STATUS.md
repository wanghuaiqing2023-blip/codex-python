# codex-app-server src/fuzzy_file_search.rs Status

Rust source:

- `codex/codex-rs/app-server/src/fuzzy_file_search.rs`

Python target:

- `pycodex/app_server/fuzzy_file_search.py`

Status: `complete`

Covered behavior:

- One-shot `run_fuzzy_file_search(...)` empty-root early return.
- Search options use `MATCH_LIMIT = 50`, `MAX_THREADS = 12`, non-zero thread
  count, and `compute_indices = true`.
- Search errors map to an empty result list.
- Result mapping preserves root, path, match type, file name, score, and
  indices.
- Result ordering matches Rust's score-descending/path-ascending comparator.
- Session startup constructs the same search options and wires a reporter.
- Session query updates are ignored after cancellation; otherwise latest query
  is stored before forwarding to the inner search session.
- Reporter ignores canceled or stale snapshots, emits empty files for an empty
  query, sends update notifications for current snapshots, and sends completed
  notifications.
- Session close/drop marks the shared cancellation flag.

Deferred runtime boundaries:

- Concrete `codex-file-search` walking/matching/session runtime remains owned by
  that crate; this module uses its Python boundary through injectable runner and
  session factory hooks.
- Exact Tokio `spawn_blocking`, runtime spawn scheduling, tracing warnings, and
  Arc/atomic memory-ordering details remain runtime/platform details.

Validation:

- `python -m pytest tests/test_app_server_fuzzy_file_search_rs.py -q`
  passed on 2026-06-19 with 7 tests.
- `python -m py_compile pycodex/app_server/fuzzy_file_search.py
  tests/test_app_server_fuzzy_file_search_rs.py` passed on 2026-06-19.
