# 2026-06-06 canonical migration batch 19: remaining core/tools support layer

## Scope

- Continue the Rust-tree-aligned migration of core tool modules.
- This batch covers the remaining shared tool support layer after the public context/registry/router/spec-plan/runtime move.

## Rust anchors

- `codex/codex-rs/core/src/tools/tool_dispatch_trace.rs`
- `codex/codex-rs/core/src/tools/lifecycle.rs`
- `codex/codex-rs/core/src/tools/parallel.rs`
- `codex/codex-rs/core/src/tools/orchestrator.rs`
- `codex/codex-rs/core/src/tools/sandboxing.rs`

## Python canonical coordinates

- `pycodex/core/tools/tool_dispatch_trace.py`
- `pycodex/core/tools/lifecycle.py`
- `pycodex/core/tools/parallel.py`
- `pycodex/core/tools/orchestrator.py`
- `pycodex/core/tools/sandboxing.py`

## Changes

- Moved the old root-level `tool_*` support files into `pycodex/core/tools/`.
- Renamed Python files to match Rust module names where Rust omits the `tool_` prefix:
  - `tool_lifecycle.py` -> `tools/lifecycle.py`
  - `tool_parallel.py` -> `tools/parallel.py`
  - `tool_orchestrator.py` -> `tools/orchestrator.py`
  - `tool_sandboxing.py` -> `tools/sandboxing.py`
- Kept `tool_dispatch_trace.py` name because the Rust source file uses the same name.
- Updated production and focused test imports to canonical coordinates.

## Validation

- Focused suite:
  - `tests/test_core_tool_orchestrator.py`
  - `tests/test_core_tool_parallel.py`
  - `tests/test_core_tool_router.py`
  - `tests/test_core_tool_runtimes.py`
  - `tests/test_core_session_runtime.py`
  - `tests/test_core_stream_events_utils.py`
  - `tests/test_core_shell_handler.py`
  - `tests/test_core_unified_exec_handler.py`
  - `tests/test_core_exec_policy.py`
  - `tests/test_core_apply_patch.py`
- Result:
  - `634 passed`
  - `2 skipped`
- Import smoke:
  - `pycodex.core.tools.tool_dispatch_trace`
  - `pycodex.core.tools.lifecycle`
  - `pycodex.core.tools.parallel`
  - `pycodex.core.tools.orchestrator`
  - `pycodex.core.tools.sandboxing`
  - passed
- Old import residual check:
  - no matches for the moved root module paths.

## Notes

- `pycodex.core` remains the broad public facade, but it now imports these support-layer symbols from canonical tool coordinates.
- `pycodex/sandboxing` remains a compatibility package and now points at `pycodex.core.tools.sandboxing`.
