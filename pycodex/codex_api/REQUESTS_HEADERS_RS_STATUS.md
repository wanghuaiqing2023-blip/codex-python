# codex-api/src/requests/headers.rs status

Rust module: `codex/codex-rs/codex-api/src/requests/headers.rs`

Python module: `pycodex/codex_api/requests/headers.py`

Status: `complete`

Ported contract:

- `build_session_headers` inserts optional `session-id` and `thread-id`
  headers through the same guarded header insertion boundary as Rust.
- `subagent_header` maps subagent sources to `review`, `compact`,
  `memory_consolidation`, `collab_spawn`, or a caller-provided label.
- `insert_header` skips invalid header names or values instead of raising,
  matching Rust's `if let (Ok(...), Ok(...))` branch.
- Header value validation follows `HeaderValue::from_str`: visible ASCII and
  HTAB are accepted, while other control characters, DEL, and non-ASCII text
  are skipped.

Intentional adaptation:

- Rust consumes `codex_protocol::protocol::SessionSource` and
  `SubAgentSource`. Python defines a small local representation for this
  module boundary until the broader protocol/session source types are needed.

Validation:

- Focused validation passed on 2026-06-21:
  `python -m pytest tests/test_codex_api_requests_headers_rs.py -q --tb=short`
  (`5 passed, 4 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_api\requests\headers.py tests\test_codex_api_requests_headers_rs.py`.
- Codex API focused validation passed on 2026-06-21:
  `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` (`206 passed, 45 subtests passed`).
