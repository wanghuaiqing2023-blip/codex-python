# `codex-state/src/model/agent_job.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/model/agent_job.rs`
- Public model anchors:
  - `AgentJobStatus`
  - `AgentJobItemStatus`
  - `AgentJob`
  - `AgentJobItem`
  - `AgentJobProgress`
  - `AgentJobCreateParams`
  - `AgentJobItemCreateParams`
- Internal row anchors:
  - `AgentJobRow`
  - `AgentJobItemRow`

This module owns agent-job value shapes and row-to-model conversion. Runtime
job orchestration, agent control, CSV execution, and persistence stores belong
to neighboring runtime/tool modules and are intentionally outside this pass.

## Python mapping

- Module: `pycodex/state/model/agent_job.py`
- Re-exported through `pycodex/state/model/__init__.py` and
  `pycodex/state/__init__.py`.

The Python port mirrors status wire strings, final-status semantics, job/item
payloads, progress counters, create parameter shapes, JSON string decoding for
row models, epoch-second UTC conversion, and Rust integer-domain checks for
`i64`, `u64`, and `usize` fields.

## Validation

```powershell
python -m py_compile pycodex\state\model\agent_job.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_agent_job_model_rs.py
python -m pytest tests\test_state_agent_job_model_rs.py -q
```

Result on 2026-06-17: `8 passed`. Re-run during status correction also passed:

```text
python -m pytest tests\test_state_agent_job_model_rs.py -q
8 passed

python -m py_compile pycodex\state\model\agent_job.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_agent_job_model_rs.py
```

Formal parity tests cover job/item status wire strings and parsing, final job
status semantics, row-to-domain conversion for job and item rows, JSON decode
paths, UTC epoch-second conversion, invalid persisted status and timestamp
errors, negative `max_runtime_seconds` rejection, progress counters, create
parameter shapes, and Rust integer-domain checks for `i64`, `u64`, and `usize`
fields.

## Remaining crate work

No known gaps for `src/model/agent_job.rs`. `codex-state` remains pending
focused full-crate validation before strict crate-complete promotion.
