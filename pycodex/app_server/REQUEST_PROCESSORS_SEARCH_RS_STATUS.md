# codex-app-server src/request_processors/search.rs status

Rust module: `codex/codex-rs/app-server/src/request_processors/search.rs`

Python module: `pycodex/app_server/request_processors_search.py`

Status: `complete`

## Scope

Covered behavior:

- `SearchRequestProcessor::new(...)` stores outgoing sender state plus empty
  pending one-shot search and stateful session maps.
- `fuzzy_file_search(...)` cancellation-token handling: replacing an existing
  token cancels the previous flag, empty query returns an empty response
  without invoking the fuzzy-search runner, and cleanup removes only the flag
  inserted by the current request.
- `fuzzy_file_search_session_start_response(...)` rejects an empty
  `sessionId`, maps start failures through `internal_error`, and stores the
  created session by id.
- `fuzzy_file_search_session_update_response(...)` updates an existing session
  and maps missing sessions through `invalid_request`.
- `fuzzy_file_search_session_stop(...)` removes an existing session and
  succeeds even when the id is absent.

Deferred/out of module:

- The actual filesystem fuzzy-search algorithm and reporter behavior are owned
  by sibling module `src/fuzzy_file_search.rs`.
- Tokio mutex scheduling, spawned task timing, and concrete outgoing transport
  delivery remain runtime/dependency boundaries.

## Evidence

Rust source:

- `codex/codex-rs/app-server/src/request_processors/search.rs`
- `codex/codex-rs/app-server/src/fuzzy_file_search.rs` for session Drop
  semantics used by the stop boundary.

Python parity tests:

- `tests/test_app_server_request_processors_search_rs.py`

Focused validation passed on 2026-06-19:

- `python -m pytest tests/test_app_server_request_processors_search_rs.py -q`
  -> 6 passed.
- `python -m py_compile pycodex/app_server/request_processors_search.py tests/test_app_server_request_processors_search_rs.py`
