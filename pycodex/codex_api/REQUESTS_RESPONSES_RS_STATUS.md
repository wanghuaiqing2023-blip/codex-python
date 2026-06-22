# codex-api/src/requests/responses.rs status

Rust module: `codex/codex-rs/codex-api/src/requests/responses.rs`

Python module: `pycodex/codex_api/requests/responses.py`

Status: `complete`

Ported contract:

- `Compression` exposes the public request compression surface for `None` and
  `Zstd`.
- `attach_item_ids` returns without mutation when the payload has no `input`
  field or when `input` is not an array.
- `attach_item_ids` zips serialized input payload entries with original
  `ResponseItem` values, inserts non-empty ids only into object entries, and
  truncates to the shorter side.
- `attach_item_ids` replaces an existing serialized `id` field when Rust's
  `obj.insert(...)` branch applies.
- Id reattachment is limited to the Rust or-pattern variants: reasoning,
  message, web search call, function call, tool search call, local shell call,
  and custom tool call.

Validation:

- Focused validation passed on 2026-06-21:
  `python -m pytest tests/test_codex_api_requests_responses_rs.py -q --tb=short`
  (`6 passed, 3 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_api\requests\responses.py tests\test_codex_api_requests_responses_rs.py`.
- Codex API focused validation passed on 2026-06-21:
  `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` (`207 passed, 45 subtests passed`).
