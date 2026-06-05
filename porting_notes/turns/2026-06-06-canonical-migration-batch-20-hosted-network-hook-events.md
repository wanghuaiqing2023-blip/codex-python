# 2026-06-06 canonical migration batch 20: hosted/network/hook/events tool modules

## Scope

- Continue aligning Python module coordinates with Rust `codex-rs/core/src/tools`.
- This batch covers remaining non-handler tool modules that still lived under `pycodex/core`.

## Rust anchors

- `codex/codex-rs/core/src/tools/hosted_spec.rs`
- `codex/codex-rs/core/src/tools/network_approval.rs`
- `codex/codex-rs/core/src/tools/hook_names.rs`
- `codex/codex-rs/core/src/tools/events.rs`

## Python canonical coordinates

- `pycodex/core/tools/hosted_spec.py`
- `pycodex/core/tools/network_approval.py`
- `pycodex/core/tools/hook_names.py`
- `pycodex/core/tools/events.py`

## Changes

- Moved `pycodex/core/hosted_spec.py` into `pycodex/core/tools/hosted_spec.py`.
- Moved `pycodex/core/network_approval.py` into `pycodex/core/tools/network_approval.py`.
- Moved `pycodex/core/hook_names.py` into `pycodex/core/tools/hook_names.py`.
- Moved `pycodex/core/tool_events.py` into `pycodex/core/tools/events.py`.
- Renamed the Python events file to `events.py` because the Rust source anchor is `tools/events.rs`.
- Updated production and focused test imports.

## Validation

- Focused suite:
  - `tests/test_core_network_approval.py`
  - `tests/test_core_client.py`
  - `tests/test_core_client_common.py`
  - `tests/test_core_apply_patch.py`
  - `tests/test_core_shell_handler.py`
  - `tests/test_core_unified_exec_handler.py`
  - `tests/test_core_tool_parallel.py`
  - `tests/test_core_tool_runtimes.py`
  - `tests/test_core_spec_plan.py`
  - `tests/test_core_session_runtime.py`
- Result:
  - `662 passed`
  - `2 skipped`
- Import smoke:
  - `pycodex.core.tools.hosted_spec`
  - `pycodex.core.tools.network_approval`
  - `pycodex.core.tools.hook_names`
  - `pycodex.core.tools.events`
  - passed
- Old import residual check:
  - no matches for old root module paths.

## Notes

- `pycodex.core` remains the public facade and now re-exports these symbols from canonical tool coordinates.
- This batch did not change behavior; it only moved module coordinates and updated imports.
