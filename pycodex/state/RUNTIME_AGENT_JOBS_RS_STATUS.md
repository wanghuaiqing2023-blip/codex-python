# codex-state `src/runtime/agent_jobs.rs`

Rust module: `codex/codex-rs/state/src/runtime/agent_jobs.rs`

Python module: `pycodex/state/runtime/agent_jobs.py`

Status: `complete`

## Behavior Contract

- Mirrors the agent job SQLite runtime surface over `agent_jobs` and
  `agent_job_items`.
- Creates jobs and initial items in one transaction with JSON-encoded headers,
  schemas, row payloads, pending status, and epoch-second timestamps.
- Reads jobs/items through the ported `AgentJobRow` and `AgentJobItemRow`
  model conversions.
- Preserves job status updates for running, completed, failed, cancelled, and
  cancellation checks.
- Preserves item transitions for pending/running, running-with-thread,
  requeue-to-pending, thread assignment, reporting results, completion guarded
  by `result_json IS NOT NULL`, failure, and aggregate progress counts.
- Preserves report acceptance requiring the item to be running and assigned to
  the reporting thread.

## Evidence

- Rust source:
  `codex/codex-rs/state/src/runtime/agent_jobs.rs`
- Rust schema:
  `codex/codex-rs/state/migrations/0014_agent_jobs.sql`
  and `0015_agent_jobs_max_runtime_seconds.sql`
- Rust tests:
  `report_agent_job_item_result_completes_item_atomically` and
  `report_agent_job_item_result_rejects_late_reports`

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_runtime_agent_jobs_rs.py -q
# 5 passed

python -m py_compile pycodex\state\runtime\agent_jobs.py pycodex\state\runtime\__init__.py pycodex\state\__init__.py tests\test_state_runtime_agent_jobs_rs.py
```

Coverage includes job creation with initial items, Rust's atomic accepted
result-report completion case, Rust's late-report rejection case, cancellation
state constraints, filtered item listing, progress aggregation, and path-backed
SQLite store reopening.

## Known Gaps

- No known gaps for `src/runtime/agent_jobs.rs`.
- StateRuntime DB opening/migration and broader runtime orchestration remain
  separate module contracts.
