# codex-api/src/search.rs status

Rust module: `codex/codex-rs/codex-api/src/search.rs`

Python module: `pycodex/codex_api/search.py`

Status: `complete`

Ported contract:

- `SearchRequest` serializes `id`, optional model/reasoning/input,
  commands/settings, and `max_output_tokens`, skipping absent fields.
- `SearchInput` preserves Rust's untagged shape: text is a bare string and
  item input is an array of response items.
- `SearchCommands` preserves command field names for search/image query,
  open, click, find, screenshot, finance, weather, sports, time, and response
  length operations.
- Search operation dataclasses preserve Rust field names, including `ref_id`,
  `pageno`, `utc_offset`, `date_from`, `date_to`, `num_games`, and `fn`.
- Search-related enums serialize to Rust lowercase or snake_case wire values.
- Rust `u64` fields reject negative and boolean values before serialization:
  `recency`, `lineno`, `id`, `pageno`, `duration`, `num_games`,
  `max_results`, and `max_output_tokens`.
- `SearchSettings` preserves user location, context size, filters, image
  settings, allowed callers, and external web access, skipping absent fields.
- `SearchResponse` decodes the required `encrypted_output` payload.

Validation:

- `python -m pytest tests/test_codex_api_search_rs.py -q --tb=short` passed
  on 2026-06-21 with `7 passed, 16 subtests passed`.
- `python -m py_compile pycodex/codex_api/search.py tests/test_codex_api_search_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `236 passed, 65 subtests passed`.
