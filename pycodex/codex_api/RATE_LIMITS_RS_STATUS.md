# codex-api/src/rate_limits.rs status

Rust module: `codex/codex-rs/codex-api/src/rate_limits.rs`

Python module: `pycodex/codex_api/rate_limits.py`

Status: `complete`

Ported contract:

- `RateLimitError` message-only display behavior.
- Default, per-limit, and all-limit header parsing for Codex rate-limit header
  families.
- Limit-id normalization from hyphenated header families to underscored ids.
- Primary/secondary rate-limit windows, limit-name headers, credits headers,
  promo message parsing, and reached-type header parsing.
- `codex.rate_limits` event JSON parsing for windows, credits, plan type, and
  metered/legacy limit names.
- `codex.rate_limits` event credits use strict JSON bool decoding, matching
  Rust serde behavior.
- Invalid/non-finite numeric values, unknown reached-type values, and zero-only
  windows are ignored as in the Rust helper branches.

Intentional adaptation:

- Rust returns `codex_protocol` snapshot structs. Python uses local dataclasses
  with the same field names for the module-scoped wire shape while the broader
  protocol package integration remains outside this slice.

Validation:

- `tests/test_codex_api_rate_limits_rs.py`
- Focused validation command:
  `python -m pytest tests/test_codex_api_rate_limits_rs.py -q --tb=short`
  (`10 passed`)
- Syntax validation:
  `python -m py_compile pycodex\codex_api\rate_limits.py tests\test_codex_api_rate_limits_rs.py`
- Codex API focused validation:
  `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` (`211 passed, 47 subtests passed`)
