# codex-app-server src/filters.rs alignment

Rust module:

`codex/codex-rs/app-server/src/filters.rs`

Python target:

`pycodex/app_server/filters.py`

Status: `complete`

## Covered

- `compute_source_filters(...)` mirrors Rust's split between rollout-query
  source filtering and app-server post-filtering:
  absent or empty source kinds default to `INTERACTIVE_SESSION_SOURCES`, pure
  CLI/VSCode filters are pushed into allowed session sources, and exec,
  app-server, sub-agent, and unknown filters require post-filtering.
- `source_kind_matches(...)` mirrors Rust's mapping from app-server
  `ThreadSourceKind` to core `SessionSource`, including app-server as MCP,
  generic sub-agent, review, compact, thread-spawn, other, and unknown variants.
- The Python module reuses already-ported protocol and rollout source types and
  keeps runtime list/read execution outside this module boundary.

## Evidence

- Rust source:
  `codex/codex-rs/app-server/src/filters.rs`
- Rust local tests:
  `compute_source_filters_defaults_to_interactive_sources`
  `compute_source_filters_empty_means_interactive_sources`
  `compute_source_filters_interactive_only_skips_post_filtering`
  `compute_source_filters_subagent_variant_requires_post_filtering`
  `source_kind_matches_distinguishes_subagent_variants`
- Python tests:
  `tests/test_app_server_filters_rs.py`

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_filters_rs.py -q`
  -> `6 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/filters.py
  tests/test_app_server_filters_rs.py`.
