# codex-analytics test alignment

Rust crate: `codex-analytics`

Python package: `pycodex/analytics`

Status: `module_progress`

## Certified Modules

- `codex/codex-rs/analytics/src/accepted_lines.rs` -> `pycodex/analytics/__init__.py`

## Certified Module Slices

- `codex/codex-rs/analytics/src/events.rs` accepted-line event request shape -> `accepted_line_fingerprint_event_requests`
- `codex/codex-rs/analytics/src/lib.rs` time helpers -> `now_unix_seconds`, `now_unix_millis`
- `codex/codex-rs/analytics/src/facts.rs` selected public enum/data compatibility surface

## Rust Tests And Contracts

- Rust `src/accepted_lines.rs` tests are migrated in `tests/test_analytics_accepted_lines_rs.py`.
- Rust `analytics_client_tests::accepted_line_fingerprints_event_serializes_expected_shape` is migrated in `tests/test_analytics_accepted_lines_rs.py`.

## Python Tests

- `tests/test_analytics_accepted_lines_rs.py`

## Validation

- `python -m pytest tests/test_analytics_accepted_lines_rs.py -q --tb=short` (`4 passed`)
- `python -m py_compile pycodex/analytics/__init__.py tests/test_analytics_accepted_lines_rs.py` passed

## Remaining Gaps

- `src/client.rs` native analytics queueing, auth, batching, and HTTP transport.
- `src/reducer.rs` analytics state machine and event emission orchestration.
- Full `src/events.rs` event serialization matrix beyond the accepted-line event.
- Full `src/facts.rs` fact model parity beyond selected compatibility shapes.
- Rust `analytics_client_tests.rs` broader event/reducer tests are not yet migrated.
