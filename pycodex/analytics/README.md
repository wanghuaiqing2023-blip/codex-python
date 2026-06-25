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
| `src/lib.rs` | `pycodex/analytics/__init__.py` | `complete` | Time helpers and public dependency-light exports are mapped. |
| `src/facts.rs` | `pycodex/analytics/__init__.py` | `complete` | Public enum serde values, compaction implementation v2 serde label, turn-steer/input error rejection mapping, `CodexCompactionEvent`, `TurnResolvedConfigFact`, and selected data-shape compatibility surface are mapped. |
| `src/events.rs` | `pycodex/analytics/__init__.py` | `complete` | Selected enum/data-shape compatibility surface, accepted-line event shape, app/plugin/hook metadata projection, skill path normalization, plugin-state event names, guardian-review payload shape, review status/resolution values, review event shape, subagent source labels including memory-consolidation/other sources, command execution/file-change/MCP/dynamic/collab/web-search/image-generation tool-item event shapes, and app/plugin/hook event wrappers are present. |
| `src/client.rs` | `pycodex/analytics/__init__.py` | `complete` | Client request/response enqueue filtering, notification filtering, accepted-line isolated batching, plugin/app-used dedupe helpers, disabled-client queue suppression, Codex-backend auth gating, and dependency-light real local HTTP POST transport are mapped. |
| `src/reducer.rs` | `pycodex/analytics/__init__.py` | `complete` | Custom fact ingestion for skill/app/plugin/hook facts, client request/response relevance guards, initialize/thread lifecycle connection caching, subagent parent connection inheritance, reducer thread-context lookup, subagent tool-item inherited metadata projection, turn-event assembly/tool-count projection, managed full-disk/restricted-network sandbox policy projection, accepted-line latest-diff emission on turn completion, TurnStart pending/error-response lifecycle guard, turn started/completed notification lifecycle, turn-steer pending response/error lifecycle projection, tool item started/completed lifecycle for command/file-change/MCP/dynamic/collab/web-search/image-generation events, compaction event ingestion/projection, thread-initialized/subagent-thread-started event projection, guardian review terminal-status mapping, guardian review custom fact projection, effective permissions review result/response projection, review event serialization, item review summary denormalization, `emit_review_event` projection, aborted review request idempotency, and guardian completed notification projection are mapped. |

Focused validation passed:

- `python -m pytest tests/test_analytics_client_rs.py -q --tb=short` -> `5 passed`
- `python -m pytest tests/test_analytics_accepted_lines_rs.py tests/test_analytics_client_rs.py tests/test_analytics_events_rs.py tests/test_analytics_facts_rs.py tests/test_analytics_reducer_rs.py tests/test_analytics_turn_event_rs.py tests/test_analytics_turn_steer_rs.py tests/test_analytics_compaction_rs.py tests/test_analytics_thread_initialized_rs.py tests/test_analytics_review_rs.py tests/test_analytics_tool_item_events_rs.py -q --tb=short` -> `89 passed`
- `python -m py_compile pycodex/analytics/__init__.py tests/test_analytics_turn_event_rs.py` passed

`analytics_client_tests.rs` migrated-test evidence is indexed by exact Rust test
name in `TEST_ALIGNMENT.md`.

## Native Runtime Differences

The Python port intentionally does not embed Rust's native Tokio analytics queue,
exact async `AuthManager` identity, exact `reqwest` client/timeout behavior, or
full app-server protocol runtime orchestration. Those are non-blocking
implementation differences for this dependency-light port; the stable event,
fact, client filtering/batching/transport, and reducer projection contracts are
covered by Rust-derived tests.

`codex-analytics` is `complete` for the dependency-light Python projection.
