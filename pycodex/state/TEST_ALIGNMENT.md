# codex-state test alignment

This ledger records module-scoped Rust behavior contracts for `codex-state`
that have Python parity evidence.

`codex-state` functional module work is complete. The full state parity suite
passed on 2026-06-17 with `143 passed`, so this package is promoted to strict
`complete` status in `CRATE_COMPLETION_STATUS.md`.

## complete

### `src/audit.rs` read-only state database audit rows

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/audit.rs`
- Python module: `pycodex/state/audit.py`
- Python status file: `pycodex/state/AUDIT_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines `ThreadStateAuditRow` and an async read-only SQLite
  query that selects `id`, `rollout_path`, `archived`, `source`, and
  `model_provider` from `threads` without creating, migrating, or repairing the
  DB. Python mirrors the row shape, read-only SQLite open mode, selected
  columns, integer-to-bool `archived` conversion, and async API shape.
- Validation: formal parity tests added in `tests/test_state_audit_rs.py`;
  `python -m pytest tests/test_state_audit_rs.py -q` passed with `4 passed`
  on 2026-06-17. `python -m py_compile pycodex/state/audit.py
  pycodex/state/__init__.py tests/test_state_audit_rs.py` also passed.

### `src/extract.rs` rollout item to thread metadata mutation

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/extract.rs`
- Python module: `pycodex/state/extract.py`
- Python status file: `pycodex/state/EXTRACT_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust applies only session metadata, turn context, token count, user
  message, and thread-goal events to `ThreadMetadata`; response items and
  compacted items are no-ops. Python mirrors the in-place mutation contract,
  default-provider fill, CWD precedence, user-message prefix stripping,
  image-only placeholder, preview/title rules, token count clamping, and
  `rollout_item_affects_thread_metadata` predicate.
- Validation: formal parity tests added in `tests/test_state_extract_rs.py`;
  `python -m pytest tests/test_state_extract_rs.py -q` passed with
  `11 passed` on 2026-06-17. `python -m py_compile pycodex/state/extract.py
  pycodex/state/__init__.py tests/test_state_extract_rs.py` also passed.

### `src/lib.rs` crate-root constants and current re-export surface

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/lib.rs`
- Python module: `pycodex/state/__init__.py`
- Python status file: `pycodex/state/LIB_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `lib.rs` owns DB filename constants, the
  `CODEX_SQLITE_HOME` override variable name, DB telemetry metric names, and
  crate-root re-exports. Python mirrors these constants and re-exports the
  state model/path surfaces that have module-level parity evidence. Runtime
  store/telemetry/audit/extract re-exported behavior remains owned by separate
  modules.
- Validation: formal parity tests added in `tests/test_state_lib_rs.py`;
  `python -m pytest tests/test_state_lib_rs.py -q` passed with `3 passed` on
  2026-06-17. `python -m py_compile pycodex/state/__init__.py
  tests/test_state_lib_rs.py` also passed.

### `src/runtime.rs` runtime DB aggregation and `StateRuntime` facade

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime.rs`
- Python module: `pycodex/state/state_runtime.py`
- Python status file: `pycodex/state/RUNTIME_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `runtime.rs` owns the four DB specs, runtime DB path listing,
  SQLite open options, runtime `StateRuntime` aggregation, store accessors,
  backfill singleton initialization, thread updated-at high-water loading,
  logs startup maintenance, memory-data clearing from a SQLite home, and
  read-only SQLite integrity checks. Python mirrors those runtime aggregation
  and helper surfaces with standard-library SQLite connections and the already
  ported runtime child stores. Runtime opens now apply the same upstream Rust
  SQL migration directories referenced by `pycodex.state.migrations` when this
  checkout is available, recording applied versions in `_sqlx_migrations` and
  preserving Rust's runtime `ignore_missing` compatibility behavior.
- Validation: compile/import only during this module pass:
  `python -m py_compile pycodex/state/state_runtime.py pycodex/state/__init__.py`
  and temporary empty-`codex_home` SQLite migration/init/path/backfill/
  integrity smoke passed on 2026-06-17. Formal parity tests:
  `python -m pytest tests/test_state_runtime_rs.py -q` passed on 2026-06-17
  with `4 passed`, covering empty-home runtime migration/init, newer applied
  migration tolerance, read-only SQLite integrity checks, and memory-data
  clearing.

### `src/log_db.rs` log sink formatting and bounded flush facade

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/log_db.rs`
- Python module: `pycodex/state/log_db.py`
- Python status file: `pycodex/state/LOG_DB_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines log sink queue defaults/normalization, a process-wide
  `pid:{pid}:{uuid}` identifier, first-match message/thread visitors, span
  contexts for feedback-log body construction, event-to-`LogEntry` conversion,
  drop-new-entry bounded queueing, and flush through `StateRuntime::insert_logs`.
  Python mirrors those data-shaping and explicit flush contracts with a
  standard-library queue facade while documenting the tracing Layer/Tokio ticker
  adaptation as future runtime integration work.
- Validation: formal parity tests passed on 2026-06-17:
  `python -m pytest tests/test_state_log_db_rs.py -q` with `7 passed`, plus
  `python -m py_compile pycodex/state/log_db.py pycodex/state/__init__.py
  tests/test_state_log_db_rs.py`.

### `src/migrations.rs` migration metadata and runtime wrappers

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/migrations.rs`
- Python module: `pycodex/state/migrations.py`
- Python status file: `pycodex/state/MIGRATIONS_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines four embedded migrators and runtime helper functions
  that preserve base migrator configuration while setting `ignore_missing=true`
  for compatibility with databases migrated by newer binaries. Python mirrors
  the migration directory anchors and runtime wrapper semantics with a
  dependency-light `Migrator` value object.
- Validation: compile/import only during this module pass:
  `python -m py_compile pycodex/state/migrations.py pycodex/state/__init__.py`
  and package-root import/runtime-migrator smoke passed on 2026-06-17. Formal
  parity tests: `python -m pytest tests/test_state_migrations_rs.py -q` passed
  on 2026-06-17 with `4 passed`, covering base migration directory anchors,
  runtime wrapper config preservation, type rejection, and helper-to-base
  mapping. Status-correction re-run on 2026-06-17 also passed with `4 passed`,
  plus `python -m py_compile pycodex/state/migrations.py
  pycodex/state/__init__.py tests/test_state_migrations_rs.py`.

### `src/model/agent_job.rs` agent job models and row conversions

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/model/agent_job.rs`
- Python module: `pycodex/state/model/agent_job.py`
- Python status file: `pycodex/state/AGENT_JOB_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines job/item status enums, job and item payloads,
  progress counters, create parameter shapes, and row conversion for persisted
  JSON and epoch-second timestamp fields. Python mirrors the wire strings,
  final-status semantics, row JSON decoding, UTC timestamp conversion, and
  Rust integer-domain checks for `i64`, `u64`, and `usize` fields.
- Validation: compile/import only during this module pass:
  `python -m py_compile pycodex/state/model/agent_job.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py` and package-root
  import/status/row-conversion smoke passed on 2026-06-17. Formal parity
  tests: `python -m pytest tests/test_state_agent_job_model_rs.py -q` passed
  on 2026-06-17 with `8 passed`, covering status parsing/finality, job/item
  row conversion, JSON decode paths, UTC epoch conversion, invalid persisted
  fields, progress counters, create parameter shapes, and Rust integer-domain
  checks. Status-correction re-run on 2026-06-17 also passed with `8 passed`,
  plus `python -m py_compile pycodex/state/model/agent_job.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py
  tests/test_state_agent_job_model_rs.py`.

### `src/model/backfill_state.rs` backfill lifecycle state

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/model/backfill_state.rs`
- Python module: `pycodex/state/model/backfill_state.py`
- Python status file: `pycodex/state/BACKFILL_STATE_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `BackfillStatus` owns the persisted wire strings
  `pending`, `running`, and `complete`, rejects unknown values, and
  `BackfillState::default()` starts pending with no watermark or success
  timestamp. Python mirrors those contracts and the Rust row conversion for
  `status`, `last_watermark`, and epoch-second `last_success_at`.
- Validation: compile/import only during this module pass:
  `python -m py_compile pycodex/state/model/backfill_state.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py` and package-root
  import smoke passed on 2026-06-17. Formal parity tests:
  `python -m pytest tests/test_state_backfill_state_rs.py -q` passed on
  2026-06-17 with `7 passed`, covering status strings/parsing, unknown status
  rejection, default state, row conversion, nullable optional fields, invalid
  field types, and invalid timestamp rejection. Status-correction re-run on
  2026-06-17 also passed with `7 passed`, plus `python -m py_compile
  pycodex/state/model/backfill_state.py pycodex/state/model/__init__.py
  pycodex/state/__init__.py tests/test_state_backfill_state_rs.py`.

### `src/model/graph.rs` directional thread-spawn edge status

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/model/graph.rs`
- Python module: `pycodex/state/model/graph.py`
- Python status file: `pycodex/state/GRAPH_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `DirectionalThreadSpawnEdgeStatus` derives
  `AsRefStr`/`Display`/`EnumString` with `snake_case` serialization for `Open`
  and `Closed`. Python mirrors the persisted strings `open` and `closed`, plus
  Rust-like `as_ref()` and `parse()` helpers.
- Validation: compile/import only during this module pass:
  `python -m py_compile pycodex/state/model/graph.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py` and package-root
  import/parse smoke passed on 2026-06-17. Formal parity tests:
  `python -m pytest tests/test_state_graph_rs.py -q` passed on 2026-06-17
  with `4 passed`, covering wire values, `as_ref()`, Rust-like display via
  `str(status)`, accepted parsing, and unknown-value rejection.
  Status-correction re-run on 2026-06-17 also passed with `4 passed`, plus
  `python -m py_compile pycodex/state/model/graph.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py
  tests/test_state_graph_rs.py`.

### `src/model/log.rs` log entry, row, and query models

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/model/log.rs`
- Python module: `pycodex/state/model/log.py`
- Python status file: `pycodex/state/LOG_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines serializable `LogEntry`, row-shaped `LogRow`, and
  defaultable `LogQuery` with optional filters and pagination fields. Python
  mirrors those field names/defaults, validates Rust `i64` domains, and keeps
  `LogQuery.limit` as an optional non-negative integer for Rust `Option<usize>`.
- Validation: compile/import only during this module pass:
  `python -m py_compile pycodex/state/model/log.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py` and package-root
  import/default/row smoke passed on 2026-06-17. Formal parity tests:
  `python -m pytest tests/test_state_log_model_rs.py -q` passed on
  2026-06-17 with `6 passed`, covering `LogEntry` mapping shape, `LogRow`
  mapping conversion, Rust `i64`/string bounds, `LogQuery` defaults, sequence
  normalization, `Option<usize>` limit validation, and bool field validation.
  Status-correction re-run on 2026-06-17 also passed with `6 passed`, plus
  `python -m py_compile pycodex/state/model/log.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py
  tests/test_state_log_model_rs.py`.

### `src/model/thread_goal.rs` thread goal model and row conversion

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/model/thread_goal.rs`
- Python module: `pycodex/state/model/thread_goal.py`
- Python status file: `pycodex/state/THREAD_GOAL_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines thread goal status wire strings, active/terminal
  predicates, domain model fields, row-shaped storage data, and row-to-domain
  conversion using epoch-millisecond timestamps. Python consolidates the prior
  package-root model into the Rust-coordinate model module, preserves package
  root re-exports, and mirrors status parsing, predicates, row conversion, and
  timestamp normalization.
- Validation: formal parity tests added in
  `tests/test_state_thread_goal_model_rs.py`; `python -m pytest
  tests/test_state_thread_goal_model_rs.py -q` passed with `7 passed` on
  2026-06-17. `python -m py_compile pycodex/state/model/thread_goal.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py
  tests/test_state_thread_goal_model_rs.py` also passed. Status-correction
  re-run on 2026-06-17 also passed with `7 passed`.

### `src/model/thread_metadata.rs` thread metadata model and row conversion

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/model/thread_metadata.rs`
- Python module: `pycodex/state/model/thread_metadata.py`
- Python status file: `pycodex/state/THREAD_METADATA_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines thread list sorting/page anchors, extraction outcome,
  canonical thread metadata, metadata builder defaults, row-shaped storage
  conversion, epoch second/millisecond helpers, Git-field preservation, field
  diffing, and backfill counters. Python mirrors those model contracts, keeps
  unknown persisted reasoning-effort strings lossy as `None`, preserves Rust's
  legacy second-precision conversion for old millisecond columns, and mirrors
  the Rust `diff_fields` omission of `thread_source`.
- Validation: formal parity tests added in
  `tests/test_state_thread_metadata_model_rs.py`; `python -m pytest
  tests/test_state_thread_metadata_model_rs.py -q` passed with `9 passed` on
  2026-06-17. `python -m py_compile pycodex/state/model/thread_metadata.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py
  tests/test_state_thread_metadata_model_rs.py` also passed. Status-correction
  re-run on 2026-06-17 also passed with `9 passed`.

### `src/model/mod.rs` model module aggregation and re-exports

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/model/mod.rs`
- Python module: `pycodex/state/model/__init__.py`
- Python status file: `pycodex/state/MODEL_MOD_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust declares the seven model child modules and re-exports their
  public model surfaces plus crate-private row/timestamp helpers for neighboring
  state modules. Python mirrors this aggregation point with package-level
  imports and `__all__` names for the already ported model modules.
- Validation: formal parity tests added in `tests/test_state_model_mod_rs.py`;
  `python -m pytest tests/test_state_model_mod_rs.py -q` passed with
  `3 passed` on 2026-06-17. `python -m py_compile
  pycodex/state/model/__init__.py pycodex/state/__init__.py
  tests/test_state_model_mod_rs.py` also passed. Status-correction re-run on
  2026-06-17 also passed with `3 passed`.

### `src/model/memories.rs` memory extraction model payloads

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/model/memories.rs`
- Python module: `pycodex/state/model/memories.py`
- Python status file: `pycodex/state/MEMORIES_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines model-only payloads for stage-1 memory output,
  stage-1 claim outcomes, claimed stage-1 jobs, startup claim parameters, and
  phase-2 claim outcomes. Python mirrors those value shapes with frozen
  dataclasses/string enums, UTC datetime normalization, path normalization, and
  `usize`/`i64` field validation while treating neighboring `ThreadMetadata`
  as an interface constraint.
- Validation: formal parity tests added in
  `tests/test_state_memories_model_rs.py`; `python -m pytest
  tests/test_state_memories_model_rs.py -q` passed with `6 passed` on
  2026-06-17. Status-correction re-run on 2026-06-17 also passed with
  `6 passed`. `python -m py_compile pycodex/state/model/memories.py
  pycodex/state/model/__init__.py pycodex/state/__init__.py
  tests/test_state_memories_model_rs.py` also passed.

### `src/runtime/agent_jobs.rs` agent job persistence and item transitions

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime/agent_jobs.rs`
- Python module: `pycodex/state/runtime/agent_jobs.py`
- Python status file: `pycodex/state/RUNTIME_AGENT_JOBS_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `StateRuntime` owns agent job creation, job/item reads, item
  listing, job status updates, cancellation checks, item running/requeue/thread
  assignment, result reporting guarded by assigned reporting thread, guarded
  item completion, failure updates, and aggregate item progress. Python mirrors
  these SQLite contracts through `AgentJobStore`, reusing the ported agent-job
  row/model conversion surfaces.
- Validation: formal parity tests added in
  `tests/test_state_runtime_agent_jobs_rs.py`; `python -m pytest
  tests/test_state_runtime_agent_jobs_rs.py -q` passed with `5 passed` on
  2026-06-17. `python -m py_compile pycodex/state/runtime/agent_jobs.py
  pycodex/state/runtime/__init__.py pycodex/state/__init__.py
  tests/test_state_runtime_agent_jobs_rs.py` also passed.

### `src/paths.rs` file modified time helper

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/paths.rs`
- Python module: `pycodex/state/paths.py`
- Python status file: `pycodex/state/PATHS_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `file_modified_time_utc` awaits filesystem metadata,
  extracts modified time, converts it to UTC, and returns `None` for metadata
  or modified-time failures. Python mirrors this with an async standard-library
  helper using `Path.stat` in a worker thread and UTC-aware `datetime`
  conversion.
- Validation: compile/import only during this module pass:
  `python -m py_compile pycodex/state/paths.py pycodex/state/__init__.py` and
  package-root import smoke passed on 2026-06-17. Formal parity tests:
  `python -m pytest tests/test_state_paths_rs.py -q` passed on 2026-06-17
  with `3 passed`, covering successful UTC timestamp conversion, missing-path
  metadata failure, and generic metadata extraction failure. Status-correction
  re-run on 2026-06-17 also passed with `3 passed`; `python -m py_compile
  pycodex/state/paths.py pycodex/state/__init__.py tests/test_state_paths_rs.py`
  also passed.

### `src/runtime/remote_control.rs` remote-control enrollment persistence

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime/remote_control.rs`
- Python module: `pycodex/state/runtime/remote_control.py`
- Python status file: `pycodex/state/REMOTE_CONTROL_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust persists remote-control enrollments keyed by
  `(websocket_url, account_id, app_server_client_name)`, maps `None` client
  names to an empty-string key, converts that key back to `None`, upserts on
  the composite key, and deletes by the same lookup returning affected rows.
  Python mirrors those contracts against a standard-library SQLite connection
  or database path.
- Validation: formal parity tests passed on 2026-06-17:
  `python -m pytest tests/test_state_runtime_remote_control_rs.py -q` with
  `5 passed`, plus `python -m py_compile
  pycodex/state/runtime/remote_control.py pycodex/state/runtime/__init__.py
  pycodex/state/__init__.py tests/test_state_runtime_remote_control_rs.py`.

### `src/runtime/backfill.rs` backfill lifecycle persistence

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime/backfill.rs`
- Python module: `pycodex/state/runtime/backfill.py`
- Python status file: `pycodex/state/RUNTIME_BACKFILL_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `StateRuntime` ensures the singleton `backfill_state` row,
  reads through `BackfillState::try_from_row`, claims the backfill worker slot
  unless complete or protected by a non-expired running lease, persists running
  and checkpoint state, and marks completion while preserving the previous
  watermark when no new one is supplied. Python mirrors those SQLite updates
  and row conversion semantics against a standard-library SQLite connection or
  database path.
- Validation: formal parity tests passed on 2026-06-17:
  `python -m pytest tests/test_state_runtime_backfill_rs.py -q` with
  `5 passed`, plus `python -m py_compile pycodex/state/runtime/backfill.py
  pycodex/state/runtime/__init__.py pycodex/state/__init__.py
  tests/test_state_runtime_backfill_rs.py`.

### `src/runtime/goals.rs` thread goal persistence and accounting

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime/goals.rs`
- Python module: `pycodex/state/runtime/goals.py`
- Python status file: `pycodex/state/RUNTIME_GOALS_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `GoalStore` owns thread-goal CRUD, `GoalUpdate`,
  `GoalAccountingMode`, `GoalAccountingOutcome`, active pause/usage-limit
  filters, goal-id optimistic concurrency, immediate budget-limit transitions,
  partial update preservation, and usage accounting across active, completed,
  and stopped goal modes. Python mirrors those contracts against the
  independent `goals_1.sqlite` `thread_goals` schema using a standard-library
  SQLite connection or database path.
- Validation: formal parity tests added in
  `tests/test_state_runtime_goals_rs.py`; `python -m pytest
  tests/test_state_runtime_goals_rs.py -q` passed with `7 passed` on
  2026-06-17. `python -m py_compile pycodex/state/runtime/goals.py
  pycodex/state/runtime/__init__.py pycodex/state/__init__.py
  tests/test_state_runtime_goals_rs.py` also passed.

### `src/runtime/logs.rs` log persistence, query, pruning, and feedback export

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime/logs.rs`
- Python module: `pycodex/state/runtime/logs.py`
- Python status file: `pycodex/state/RUNTIME_LOGS_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `StateRuntime` owns log batch insertion into the dedicated
  logs table, feedback-body fallback from message, estimated retained bytes,
  newest-first partition pruning by thread/process/threadless-null partitions,
  startup retention deletion and passive WAL checkpoint, `LogQuery` filters,
  feedback log line formatting, feedback export merged with latest-process
  threadless rows, and `max_log_id`. Python mirrors these contracts through
  `RuntimeLogStore` against an existing migrated SQLite logs schema.
- Validation: formal parity tests added in
  `tests/test_state_runtime_logs_rs.py`; `python -m pytest
  tests/test_state_runtime_logs_rs.py -q` passed with `7 passed` on
  2026-06-17. `python -m py_compile pycodex/state/runtime/logs.py
  pycodex/state/runtime/__init__.py pycodex/state/__init__.py
  tests/test_state_runtime_logs_rs.py` also passed.

### `src/runtime/memories.rs` memory extraction and consolidation runtime store

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime/memories.rs`
- Python module: `pycodex/state/runtime/memories.py`
- Python status file: `pycodex/state/RUNTIME_MEMORIES_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `MemoryStore` owns the memories DB stage-1 output table and
  memory job rows, plus cross-DB hydration through enabled `threads` rows.
  Python mirrors the runtime store surface for clearing memory data, recording
  usage, startup/stage-1 claiming, stage-1 success/no-output/failure,
  per-thread memory deletion, latest output listing, phase-2 input selection,
  stale-output pruning, polluted memory mode marking, global consolidation
  enqueueing, phase-2 claim/heartbeat/success/failure transitions, selected
  baseline snapshot updates, and retry/cooldown/lease skip outcomes.
- Validation: `python -m pytest tests/test_state_runtime_memories_rs.py -q`
  passed with `8 passed`; `python -m py_compile
  pycodex/state/runtime/memories.py pycodex/state/runtime/__init__.py
  pycodex/state/__init__.py tests/test_state_runtime_memories_rs.py` passed on
  2026-06-17. Formal parity coverage includes stage-1 claim/success/no-output,
  startup filtering, usage/selection/retention, polluted mode enqueueing,
  phase-2 claim/heartbeat/success/failure/cooldown, unowned fallback, and
  clear-all memory data behavior.

### `src/runtime/test_support.rs` runtime test fixture helpers

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime/test_support.rs`
- Python module: `pycodex/state/runtime/test_support.py`
- Python status file: `pycodex/state/RUNTIME_TEST_SUPPORT_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust exposes `unique_temp_dir` and `test_thread_metadata` under
  `#[cfg(test)]`. Python mirrors the prefixed temp path shape and the fixed
  `ThreadMetadata` fixture values: timestamp `1_700_000_000`, rollout path
  under `codex_home`, provider `test-provider`, model `gpt-5`, medium reasoning
  effort, version `0.0.0`, preview/first message `hello`, read-only sandbox,
  on-request approval, zero tokens, and empty optional agent/archive/git fields.
- Validation: formal parity tests added in
  `tests/test_state_runtime_test_support_rs.py`; `python -m pytest
  tests/test_state_runtime_test_support_rs.py -q` passed with `4 passed` on
  2026-06-17. `python -m py_compile
  pycodex/state/runtime/test_support.py pycodex/state/runtime/__init__.py
  pycodex/state/__init__.py tests/test_state_runtime_test_support_rs.py` also
  passed. Status-correction re-run on 2026-06-17 also passed with `4 passed`.

### `src/runtime/threads.rs` thread persistence, listing, archival, and spawn edges

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/runtime/threads.rs`
- Python module: `pycodex/state/runtime/threads.py`
- Python status file: `pycodex/state/RUNTIME_THREADS_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust `StateRuntime` owns thread reads, memory-mode reads/updates,
  preview-if-empty updates, thread-spawn edge upsert/status/child/descendant
  queries, rollout-path/title lookups, thread list pagination/filtering,
  insert/upsert behavior, monotonic `updated_at_ms` allocation, title/touch/Git
  updates, rollout item application, archive/unarchive, and delete. Python
  mirrors those SQLite contracts through `RuntimeThreadStore`, reusing the
  ported thread metadata and graph models while keeping memory/goal cleanup as
  optional neighboring-store hooks.
- Validation: `python -m pytest tests/test_state_runtime_threads_rs.py -q`
  passed with `7 passed`; `python -m py_compile
  pycodex/state/runtime/threads.py pycodex/state/runtime/__init__.py
  pycodex/state/__init__.py tests/test_state_runtime_threads_rs.py` passed on
  2026-06-17. Formal parity coverage includes upsert/insert-if-absent
  preservation, preview-if-empty, title/touch/Git updates, unique
  `updated_at_ms`, legacy seconds fallback, listing filters/search/anchors,
  thread-spawn traversal/path/source helpers, rollout memory-mode restoration,
  archive/unarchive, delete hooks, and preview fallback behavior.

### `src/telemetry.rs` SQLite telemetry helpers

- Rust owner: `codex-state`
- Rust module: `codex/codex-rs/state/src/telemetry.rs`
- Python module: `pycodex/state/telemetry.py`
- Python status file: `pycodex/state/TELEMETRY_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines an install-once process telemetry sink, optional
  override resolution, init/backfill/fallback recording helpers, DB kind labels,
  success/failure outcome tags, and SQLite primary/extended result-code
  classification. Python mirrors those contracts with a `Protocol` sink,
  process-wide lock-protected install, low-cardinality tags, timedelta duration
  recording, and SQLite-like exception code classification.
- Validation: formal parity tests added in `tests/test_state_telemetry_rs.py`;
  `python -m pytest tests/test_state_telemetry_rs.py -q` passed with
  `9 passed` on 2026-06-17. `python -m py_compile
  pycodex/state/telemetry.py pycodex/state/__init__.py
  tests/test_state_telemetry_rs.py` also passed. Status-correction re-run on
  2026-06-17 also passed with `9 passed`.

## Remaining

- No known functional Rust modules remain below `codex-state`; the crate is an
  implementation candidate pending focused full-crate validation and promotion
  to strict `complete`.
