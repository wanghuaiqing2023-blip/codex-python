# `codex-state/src/runtime.rs` alignment status

Status: `complete_candidate`

Rust owner: `codex-state`  
Rust module: `codex/codex-rs/state/src/runtime.rs`  
Python module: `pycodex/state/state_runtime.py`

## Behavior contract

- Defines runtime DB specs for state, logs, goals, and memories, including
  labels, filenames, DB kinds, and open/migrate phase names.
- Provides runtime DB path helpers and `runtime_db_paths` in the same four-DB
  order as Rust.
- Opens SQLite databases with WAL journal mode, normal synchronous mode, a
  busy timeout, and incremental autovacuum preference.
- Builds a `StateRuntime` facade that owns state/logs/goals/memories
  connections and wires the already ported runtime child stores:
  `RuntimeThreadStore`, `RuntimeLogStore`, `GoalStore`, `MemoryStore`, and
  `AgentJobStore`.
- Seeds the singleton backfill row for migrated state DBs and initializes the
  thread updated-at millisecond high-water mark from `threads`.
- Runs best-effort log startup maintenance, exposes the configured Codex home,
  clears memory data from a SQLite home, and performs read-only SQLite
  integrity checks.

## Python adaptation notes

- Python uses standard-library `sqlite3.Connection` objects instead of
  `sqlx::SqlitePool`.
- Runtime SQLite opens apply the same upstream Rust SQL migration directories
  referenced by `pycodex.state.migrations` when this source checkout is
  available, recording applied versions in `_sqlx_migrations` and tolerating
  missing migration directories through Rust's runtime `ignore_missing`
  compatibility setting.
- The module lives at `pycodex/state/state_runtime.py` because
  `pycodex/state/runtime/` is the Python package for Rust `src/runtime/*`
  child modules.

## Validation

- `python -m py_compile pycodex/state/state_runtime.py pycodex/state/__init__.py`
- Temporary empty-`codex_home` SQLite smoke for Rust SQL migration application
  across state/logs/goals/memories DBs, runtime initialization, runtime DB
  paths, backfill singleton seeding, and read-only integrity check.
- `python -m pytest tests/test_state_runtime_rs.py -q` passed on 2026-06-17
  with `4 passed`, covering empty-home runtime migration/init, newer applied
  migration tolerance, read-only SQLite integrity checks, and memory-data
  clearing.

Full `codex-state` tests remain the final crate-promotion gate now that the
functional module work has implementation coverage.
