# codex-memories-write src/guard.rs Status

Rust crate: `codex-memories-write`
Rust module: `src/guard.rs`
Python module: `pycodex.memories.write`

## Status

`complete_slice`

## Evidence

- Rust source: `codex/codex-rs/memories/write/src/guard.rs`
- Rust tests: `codex/codex-rs/memories/write/src/guard_tests.rs`
- Python tests: `tests/test_memories_write_guard_rs.py`

## Covered Contracts

- `snapshot_allows_startup` blocks startup when `rate_limit_reached_type` is present.
- `min_remaining_percent` is clamped to `0..=100` and converted into a max-used threshold.
- Both primary and secondary rate-limit windows must be at or below the threshold.
- Missing primary or secondary windows are treated as allowed.
- `rate_limits_ok` defaults to allowing startup when auth, backend-client
  construction, fetch, or snapshot selection returns no answer.
- Non-Codex-backend auth skips backend fetching.
- Backend snapshots prefer `CODEX_LIMIT_ID` and otherwise fall back to the
  first returned snapshot.
- Backend client construction and `get_rate_limits_many` are represented by
  dependency-light injectable facades.

## Open Outside This Module Slice

- Exact native `codex_backend_client::Client::from_auth` transport identity.
