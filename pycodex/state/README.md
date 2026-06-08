# pycodex.state

Canonical Python package for helpers ported from the Rust workspace crate:

- Rust crate: `codex/codex-rs/state`
- Python package: `pycodex/state`

## Module correspondence

| Rust behavior area | Python module |
| --- | --- |
| `src/lib.rs` DB path constants/re-exports | `pycodex/state/__init__.py` |
| `src/runtime.rs` runtime DB path helpers | `pycodex/state/__init__.py` |
| `src/model/thread_goal.rs` thread goal model/status surface | `pycodex/state/__init__.py` |

This package currently exposes dependency-light model and path surfaces needed
by `codex-core` parity work. SQLite-backed runtime stores, migrations, and
backfill orchestration remain separate contracts.

