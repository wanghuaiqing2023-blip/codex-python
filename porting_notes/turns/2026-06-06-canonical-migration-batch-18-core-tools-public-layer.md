# 2026-06-06 canonical migration batch 18: core/tools public layer

## Scope

- Continue replacing old root-level Python coordinates with Rust-tree-aligned module paths.
- This batch covers the shared tool public layer, not individual handler behavior.

## Rust anchors

- `codex/codex-rs/core/src/tools/context.rs`
- `codex/codex-rs/core/src/tools/registry.rs`
- `codex/codex-rs/core/src/tools/router.rs`
- `codex/codex-rs/core/src/tools/spec_plan.rs`
- `codex/codex-rs/core/src/tools/runtimes/mod.rs`
- `codex/codex-rs/core/src/tools/runtimes/apply_patch.rs`
- `codex/codex-rs/core/src/tools/runtimes/shell.rs`
- `codex/codex-rs/core/src/tools/runtimes/unified_exec.rs`

## Python canonical coordinates

- `pycodex/core/tools/context.py`
- `pycodex/core/tools/registry.py`
- `pycodex/core/tools/router.py`
- `pycodex/core/tools/spec_plan.py`
- `pycodex/core/tools/runtimes/__init__.py`

## Changes

- Moved the old root-level tool public layer files into `pycodex/core/tools/`.
- Updated imports throughout `pycodex/` and focused tests.
- Updated module-object imports in stream event tests from `pycodex.core.tool_router` style to `pycodex.core.tools.router`.
- Kept `pycodex.core` as the public facade, now importing these symbols from canonical coordinates.
- Did not move `pycodex/core/tool_definition.py` in this batch because no direct Rust `core/src/tools/definition.rs` anchor was confirmed.

## Validation

- Focused public-tools suite:
  - `tests/test_core_tool_router.py`
  - `tests/test_core_tool_parallel.py`
  - `tests/test_core_tool_runtimes.py`
  - `tests/test_core_spec_plan.py`
  - `tests/test_core_stream_events_utils.py`
  - `tests/test_core_shell_handler.py`
  - `tests/test_core_unified_exec_handler.py`
  - `tests/test_core_goal_handler.py`
  - `tests/test_core_request_plugin_install.py`
  - `tests/test_core_extension_tools.py`
  - `tests/test_core_http_transport.py`
- Result:
  - `573 passed`
  - `2 skipped`
- Import smoke:
  - `pycodex.core.tools.context`
  - `pycodex.core.tools.registry`
  - `pycodex.core.tools.router`
  - `pycodex.core.tools.runtimes`
  - `pycodex.core.tools.spec_plan`
  - passed
- Old import residual check:
  - no matches for moved root module paths.

## Adjacent risk

- A wider validation run that also included `tests/test_core_turn_runtime.py` and `tests/test_core_session_runtime.py` reported 6 failures.
- The failing assertions are in analytics/config and sandbox/settings projection behavior, not in import resolution or the moved tool public layer.
- These failures should be handled as a separate session/runtime alignment slice rather than expanding this coordinate migration batch.
