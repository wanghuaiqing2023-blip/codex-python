# pycodex.state

Canonical Python package for helpers ported from the Rust workspace crate:

- Rust crate: `codex/codex-rs/state`
- Python package: `pycodex/state`

## Completion status

`codex-state` is complete as of 2026-06-17. All tracked Rust module contracts
in this package have Python parity tests, and the full state parity suite
passed with:

```text
python -m pytest <all tests/test_state_*.py files> -q
143 passed
```

The module-level evidence remains in `pycodex/state/TEST_ALIGNMENT.md` and the
per-module `*_RS_STATUS.md` files.

## Module correspondence

| Rust behavior area | Python module |
| --- | --- |
| `src/audit.rs` read-only state DB audit query | `pycodex/state/audit.py` |
| `src/extract.rs` rollout-to-thread-metadata mutation helpers | `pycodex/state/extract.py` |
| `src/lib.rs` DB path constants/re-exports | `pycodex/state/__init__.py` |
| `src/log_db.rs` tracing log entry formatting and bounded sink | `pycodex/state/log_db.py` |
| `src/migrations.rs` migrator metadata/runtime wrapper | `pycodex/state/migrations.py` |
| `src/model/agent_job.rs` agent job model and row conversions | `pycodex/state/model/agent_job.py` |
| `src/model/backfill_state.rs` backfill lifecycle state | `pycodex/state/model/backfill_state.py` |
| `src/model/graph.rs` thread-spawn edge status model | `pycodex/state/model/graph.py` |
| `src/model/log.rs` log row/query/entry models | `pycodex/state/model/log.py` |
| `src/model/memories.rs` memory extraction claim/output models | `pycodex/state/model/memories.py` |
| `src/model/mod.rs` model module aggregation/re-exports | `pycodex/state/model/__init__.py` |
| `src/model/thread_metadata.rs` thread metadata models and row conversion | `pycodex/state/model/thread_metadata.py` |
| `src/paths.rs` file modified time helper | `pycodex/state/paths.py` |
| `src/runtime/agent_jobs.rs` agent job persistence and item state transitions | `pycodex/state/runtime/agent_jobs.py` |
| `src/runtime/remote_control.rs` remote-control enrollment persistence | `pycodex/state/runtime/remote_control.py` |
| `src/runtime/backfill.rs` backfill lifecycle persistence | `pycodex/state/runtime/backfill.py` |
| `src/runtime/goals.rs` thread goal persistence and accounting | `pycodex/state/runtime/goals.py` |
| `src/runtime/logs.rs` log persistence, query, pruning, and feedback export | `pycodex/state/runtime/logs.py` |
| `src/runtime/memories.rs` memory extraction/consolidation SQLite runtime store | `pycodex/state/runtime/memories.py` |
| `src/runtime/test_support.rs` runtime test fixture helpers | `pycodex/state/runtime/test_support.py` |
| `src/runtime/threads.rs` thread metadata persistence, listing, archival, and spawn edges | `pycodex/state/runtime/threads.py` |
| `src/runtime.rs` runtime DB path helpers and `StateRuntime` facade | `pycodex/state/__init__.py`, `pycodex/state/state_runtime.py` |
| `src/telemetry.rs` SQLite telemetry sink and classification helpers | `pycodex/state/telemetry.py` |
| `src/model/thread_goal.rs` thread goal model/status/row conversion | `pycodex/state/model/thread_goal.py` |

This package currently exposes dependency-light model and path surfaces needed
by `codex-core` parity work. Crate-root constants from `src/lib.rs` live in
`pycodex.state`; SQLite-backed runtime stores, migrations, and backfill
orchestration remain separate contracts.

## `src/audit.rs`

`pycodex.state.audit` mirrors the read-only diagnostic query surface:
`ThreadStateAuditRow` and `read_thread_state_audit_rows`. The helper opens an
existing SQLite database in read-only mode, reads persisted thread rows without
creating or migrating the database, and converts the integer `archived` column
to a boolean.

## `src/extract.rs`

`pycodex.state.extract` mirrors the Rust rollout metadata mutation helper
surface. It applies session metadata, turn context, token count, user message,
and thread-goal events to `ThreadMetadata`, preserves the Rust no-op behavior
for response items, and exposes the same image-only preview placeholder and
rollout-item-affects-metadata predicate. File scanning and SQLite persistence
remain owned by runtime modules.

## `src/migrations.rs`

`pycodex.state.migrations` mirrors the Rust migrator metadata and runtime
wrapper behavior. The base migrators point at the four embedded migration
directories, and each runtime migrator returns the same configuration with
`ignore_missing=True`, matching Rust's compatibility behavior for databases
already migrated by a newer binary. Runtime SQL execution is owned by
`pycodex.state.state_runtime`, which applies the upstream SQL files when this
source checkout is available.

## `src/lib.rs`

`pycodex.state` mirrors the crate-root DB filename constants, SQLite home
override environment variable, and DB telemetry metric names from Rust
`src/lib.rs`. The package root also re-exports the state model/path surfaces
that have been ported so far. Runtime store types and telemetry functions
remain separate module contracts and are not implemented by this crate-root
surface pass.

## `src/runtime.rs`

`pycodex.state.state_runtime` mirrors the Rust runtime aggregation and DB
opening surface around the already ported runtime child modules. It defines the
four runtime DB specs, opens SQLite connections with WAL/normal sync/busy
timeout/incremental autovacuum pragmas, builds `StateRuntime` with state/logs/
goals/memories connections plus `RuntimeThreadStore`, `RuntimeLogStore`,
`GoalStore`, `MemoryStore`, and `AgentJobStore`, seeds the backfill singleton
row for migrated state DBs, initializes the thread updated-at high-water mark,
runs best-effort log startup maintenance, exposes `codex_home`, supports
memory-data clearing from a SQLite home, and provides read-only SQLite integrity
checks. It also applies the same Rust SQL migration directories referenced by
`pycodex.state.migrations` when this source checkout is available, recording
applied versions in `_sqlx_migrations` and preserving the Rust runtime
`ignore_missing` compatibility behavior.

## `src/log_db.rs`

`pycodex.state.log_db` mirrors the Rust log-sink formatting and queue contract:
queue default normalization, process-stable `pid:{pid}:{uuid}` identifiers,
first-match `message`/`thread_id` visitors, span-root feedback-log formatting,
event-to-`LogEntry` construction, drop-new-entry bounded queueing, and explicit
flush through an `insert_logs` sink. Rust's `tracing_subscriber::Layer` and
Tokio ticker are adapted to a dependency-light Python facade; broader runtime
log-store integration remains a separate module contract.

## `src/model/agent_job.rs`

`pycodex.state.model.agent_job` mirrors the state-crate agent job models and
row conversion contracts: job/item status enums, persisted job and item
payloads, progress counters, create parameter shapes, and JSON/epoch-second
conversion from row-shaped records. The core in-memory agent-job tool handler
is a separate runtime surface and is not expanded by this model pass.

## `src/model/backfill_state.rs`

`pycodex.state.model.backfill_state` mirrors the persisted backfill lifecycle
model: `BackfillStatus` wire strings (`pending`, `running`, `complete`), the
default pending `BackfillState`, row/mapping conversion for `status`,
`last_watermark`, and `last_success_at`, plus Unix epoch seconds to UTC
`datetime` conversion.

## `src/model/graph.rs`

`pycodex.state.model.graph` mirrors `DirectionalThreadSpawnEdgeStatus`, the
snake_case persisted status attached to directional thread-spawn edges. The
Python enum preserves the Rust `AsRefStr`/`Display` wire strings `open` and
`closed`, plus a small parser for callers that need Rust-like `EnumString`
behavior.

## `src/model/log.rs`

`pycodex.state.model.log` mirrors the Rust log model surface: serializable
`LogEntry`, database row-shaped `LogRow`, and defaultable `LogQuery`. The
Python module keeps the data contract independent from SQLite query execution;
`log_db.rs` and runtime log-store behavior remain separate module contracts.

## `src/model/thread_goal.rs`

`pycodex.state.model.thread_goal` mirrors the Rust thread goal status enum,
goal payload, row-shaped storage model, and row-to-domain conversion using
epoch-millisecond UTC timestamps. The package root re-exports these names for
compatibility; the canonical implementation lives under `pycodex.state.model`
to match the Rust module coordinate.

## `src/model/mod.rs`

`pycodex.state.model` mirrors the Rust model aggregation module. It imports
the seven ported model submodules and re-exports their public model types plus
row/timestamp helper surfaces used by neighboring state modules. Runtime
persistence and extraction behavior remain owned by their Rust module
coordinates rather than this package aggregator.

## `src/model/thread_metadata.rs`

`pycodex.state.model.thread_metadata` mirrors the Rust thread metadata model
surface: sort/page anchors, extraction outcome, metadata builder defaults,
row-shaped storage conversion, UTC epoch helpers, lossy reasoning-effort row
parsing, Git field preservation, and Rust's `diff_fields` field list. SQLite
query/upsert behavior and rollout item extraction remain separate module
contracts.

## `src/model/memories.rs`

`pycodex.state.model.memories` mirrors the Rust memory extraction model
surface: `Stage1Output`, stage-1 and phase-2 claim outcomes, claimed job
payloads, and startup claim parameters. The SQLite-backed memory store remains
out of scope for this module; stage-1 claim payloads can now use the ported
`ThreadMetadata` model surface where callers need a typed thread payload.

## `src/runtime/agent_jobs.rs`

`pycodex.state.runtime.agent_jobs` mirrors the Rust agent-job SQLite store:
job creation with initial item rows, job reads, item listing/reads, job status
updates, cancellation checks, item running/requeue/thread assignment, result
reporting, guarded completion, failure transitions, and aggregate progress
counts. It stays independent from `StateRuntime` initialization and migration
ownership, which are tracked separately.

## `src/paths.rs`

`pycodex.state.paths` mirrors the Rust async `file_modified_time_utc` helper:
it reads filesystem metadata for a path, converts the modified timestamp to a
UTC-aware `datetime`, and returns `None` when metadata or timestamp extraction
fails.

## `src/runtime/remote_control.rs`

`pycodex.state.runtime.remote_control` mirrors the Rust remote-control
enrollment persistence helpers. It uses the same composite lookup key, stores a
missing app-server client name as the empty-string key, converts that key back
to `None` on read, performs conflict-targeted upserts, and returns affected row
counts from delete. Full runtime initialization and migrations remain separate
module contracts.

## `src/runtime/backfill.rs`

`pycodex.state.runtime.backfill` mirrors the Rust singleton backfill-state
runtime helpers. It ensures row `id = 1`, reads through the ported
`BackfillState` model, preserves running/checkpoint/complete state transitions,
keeps completion watermark updates nullable through `COALESCE`, and implements
the Rust stale-lease claim gate for rollout metadata backfill ownership.
Runtime initialization and broader store orchestration remain separate module
contracts.

## `src/runtime/goals.rs`

`pycodex.state.runtime.goals` mirrors the Rust `GoalStore` surface over the
independent goals database. It supports get/replace/insert/update/delete,
optimistic goal-id checks, active pause and usage-limit transitions, and usage
accounting modes that preserve Rust's budget-limit status transitions. The
Python `GoalUpdate` keeps a sentinel for Rust's `Option<Option<i64>>`
`token_budget` field so callers can distinguish "do not change" from "clear
the budget".

## `src/runtime/logs.rs`

`pycodex.state.runtime.logs` mirrors the Rust logs runtime store over an
existing migrated logs table. It persists `LogEntry` batches, computes retained
byte estimates, prunes newest-first per thread/process/threadless-null
partition, deletes logs before the startup retention cutoff, applies Rust's
`LogQuery` filters, formats feedback log lines, merges thread rows with
threadless rows from the latest process for feedback export, and returns `0`
for empty `max_log_id` results. Logs DB schema creation and migration remain
owned by the migration/runtime initialization modules.

## `src/runtime/memories.rs`

`pycodex.state.runtime.memories` mirrors the Rust memory extraction runtime
store over existing migrated memories/state databases. It clears memory data,
records stage-1 usage, claims startup/stage-1 jobs, marks stage-1 success or
failure, stores and hydrates stage-1 outputs through enabled thread metadata,
selects phase-2 inputs, prunes stale unselected outputs, marks polluted memory
mode, deletes per-thread memory, and manages the singleton global phase-2 job
lease/success/failure lifecycle. The store implements persistence and selection
state only; model generation and filesystem consolidation remain callers'
responsibility, matching the Rust boundary.

## `src/runtime/test_support.rs`

`pycodex.state.runtime.test_support` mirrors the Rust test-only helper module:
`unique_temp_dir` returns a prefixed temp path with timestamp and UUID
components, and `test_thread_metadata` returns the same fixed `ThreadMetadata`
fixture used by Rust runtime tests. It remains a test-support surface and does
not expand runtime store behavior.

## `src/runtime/threads.rs`

`pycodex.state.runtime.threads` mirrors the Rust thread runtime store over an
existing migrated state database. It reads and upserts thread metadata, keeps
millisecond `updated_at` allocation monotonic for hot writes, lists/paginates
visible threads with Rust-style filters and anchors, updates title/preview/Git
fields/memory mode, archives and unarchives rows, and maintains directional
thread-spawn edges including child/descendant path lookup. Memory and goal
cleanup on delete remain optional neighboring-store hooks rather than an
implementation of the separate memory runtime module.

## `src/telemetry.rs`

`pycodex.state.telemetry` mirrors the SQLite telemetry helper surface: a
process-wide install-once telemetry sink, startup/fallback recording helpers,
DB kind labels, outcome tags, and SQLite primary/extended result code
classification. It intentionally keeps delivery best-effort and independent
from database behavior, matching the Rust module contract.
