# pycodex.analytics

Rust crate: `codex-analytics`

Rust anchor: `codex/codex-rs/analytics`

This package mirrors the crate and child-module ownership exported from
`analytics/src/lib.rs`. The package root contains crate-owned helpers and Rust
public re-exports; implementation remains in the corresponding child module.

## Module Map

| Rust module | Python module | Status | Notes |
|---|---|---|---|
| `src/accepted_lines.rs` | `pycodex/analytics/accepted_lines.py` | `complete` | Accepted-line diff parsing, normalization, fingerprinting, and event request projection. |
| `src/lib.rs` | `pycodex/analytics/__init__.py` | `complete` | Time helpers and public dependency-light exports are mapped. |
| `src/facts.rs` | `pycodex/analytics/facts.py` | `complete` | Fact enums, inputs, errors, and event input data structures. |
| `src/events.rs` | `pycodex/analytics/events.py` | `complete` | Event enums, metadata, serialization shapes, and public guardian types. |
| `src/client.rs` | `pycodex/analytics/client.py` | `complete` | Filtering, batching, queueing, dedupe, auth gating, and HTTP emission. |
| `src/reducer.rs` | `pycodex/analytics/reducer.py` | `complete` | Fact ingestion, lifecycle state, review reduction, and event assembly. |

Focused validation passed:

- `python -B -m parity_harness structure --scope analytics` -> ownership and coverage `verified`
- Analytics module and consumer regressions -> `253 passed`

`analytics_client_tests.rs` migrated-test evidence is indexed by exact Rust test
name in `TEST_ALIGNMENT.md`.

The Python runtime adapts Tokio/reqwest mechanics to Python threading and
standard-library HTTP, while preserving the Rust-owned module boundaries and
tested event/client/reducer behavior.
