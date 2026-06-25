# pycodex.external_agent_sessions

Rust crate: `codex-external-agent-sessions`

Python package for external-agent session detection and import helpers.

## Module Map

| Rust module | Python module | Status | Notes |
|---|---|---|---|
| `src/records.rs` | `pycodex/external_agent_sessions/__init__.py` | `complete` | JSONL record reading, title selection, message extraction, tool-call/result notes, timestamp parsing, and session summaries are mapped. |
| `src/detect.rs` | `pycodex/external_agent_sessions/__init__.py` | `complete` | Recent session discovery, project-root filtering, title precedence, recency filtering, ledger-based skip/redetect behavior, sorting, and max-count behavior are mapped. |
| `src/export.rs` | `pycodex/external_agent_sessions/__init__.py` | `complete` | Importable session loading, rollout item projection, user/agent events, import marker, turn completion, and token-count projection are mapped with stable Python dicts. |
| `src/ledger.rs` | `pycodex/external_agent_sessions/__init__.py` | `complete` | Import ledger path, content SHA256, current-source detection, idempotent record insertion, and JSON persistence are mapped. |
| `src/lib.rs` | `pycodex/external_agent_sessions/__init__.py` | `complete` | Public facade types, pending/validated import preparation, already-imported skip, and undetected-session rejection are mapped. |

Focused validation passed:

- `python -m pytest tests/test_external_agent_sessions_rs.py -q --tb=short` -> `18 passed`
- `python -m py_compile pycodex/external_agent_sessions/__init__.py tests/test_external_agent_sessions_rs.py` passed
