# 2026-06-06 - canonical migration batch 25: agent and multi-agent handlers

## Purpose

Continue moving existing Python implementation成果 into Rust-aligned coordinates so previous work is preserved without keeping confusing old paths.

## Rust source anchors

- `codex/codex-rs/core/src/tools/handlers/agent_jobs.rs`
- `codex/codex-rs/core/src/tools/handlers/agent_jobs_spec.rs`
- `codex/codex-rs/core/src/tools/handlers/multi_agents.rs`
- `codex/codex-rs/core/src/tools/handlers/multi_agents_common.rs`
- `codex/codex-rs/core/src/tools/handlers/multi_agents_spec.rs`
- `codex/codex-rs/core/src/tools/handlers/multi_agents_v2.rs`

## Python canonical targets

- `pycodex/core/tools/handlers/agent_jobs.py`
- `pycodex/core/tools/handlers/multi_agents_common.py`
- `pycodex/core/tools/handlers/multi_agents_spec.py`
- `pycodex/core/tools/handlers/multi_agents.py`
- `pycodex/core/tools/handlers/multi_agents_v2.py`

## Moved from old paths

- `pycodex/core/agent_jobs.py`
- `pycodex/core/multi_agents_common.py`
- `pycodex/core/multi_agents_spec.py`
- `pycodex/core/multi_agents_v1_handler.py`
- `pycodex/core/multi_agents_v2_handler.py`

## Result

The existing agent job and multi-agent shim/handler implementations are now located under the same conceptual Rust handler coordinate. Old root-level module paths were removed instead of preserved as aliases.

## Validation

- Residual old import search across `pycodex/` and `tests/`: clean.
- Import smoke for the new handler modules: passed.
- Focused adjacent test command:
  - `python -m pytest tests/test_core_agent_jobs.py tests/test_core_multi_agents_common.py tests/test_core_multi_agents_spec.py tests/test_core_multi_agents_v1_handler.py tests/test_core_multi_agents_v2_handler.py tests/test_core_tool_registry.py tests/test_core_spec_plan.py tests/test_core_session_runtime.py`
- Result: `195 passed`.

## Scope note

This is a coordinate consolidation batch, not a deep expansion of multi-agent behavior. Deep multi-agent orchestration remains outside the current core implementation target unless a core runtime path requires a compatibility shim.
