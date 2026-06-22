# pycodex.analytics

Rust crate: `codex-analytics`

Rust anchor: `codex/codex-rs/analytics`

This package mirrors the public crate interface exported from
`analytics/src/lib.rs`.  Source-confirmed event/fact data shapes and accepted
line fingerprint helpers are ported; analytics transport/client emission is a
lightweight compatibility boundary.

## Module Map

| Rust module | Python module | Status | Notes |
|---|---|---|---|
| `src/accepted_lines.rs` | `pycodex/analytics/__init__.py` | `complete` | Accepted-line diff parsing, effective-line normalization, domain-separated SHA1 fingerprinting, and accepted-line event request projection are mapped. Event upload intentionally omits path/line hashes, matching Rust. |
| `src/lib.rs` | `pycodex/analytics/__init__.py` | `module_progress` | Time helpers and selected public exports are mapped. |
| `src/facts.rs` | `pycodex/analytics/__init__.py` | `module_progress` | Selected enum/data-shape compatibility surface is present. |
| `src/events.rs` | `pycodex/analytics/__init__.py` | `module_progress` | Selected enum/data-shape compatibility surface plus accepted-line event shape is present. |
| `src/client.rs` | `pycodex/analytics/__init__.py` | `shim` | `AnalyticsEventsClient` is a lightweight compatibility boundary; native async transport remains open. |
| `src/reducer.rs` | _not yet ported_ | `not_started` | Analytics reducer state machine and event emission orchestration remain open. |

Focused validation passed:

- `python -m pytest tests/test_analytics_accepted_lines_rs.py -q --tb=short` -> `4 passed`
- `python -m py_compile pycodex/analytics/__init__.py tests/test_analytics_accepted_lines_rs.py` passed
