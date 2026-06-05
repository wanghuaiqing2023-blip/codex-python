# Unified exec manager allocation order

## Upstream Rust slice

- Graph-selected files:
  - `codex/codex-rs/core/src/session/turn.rs`
  - `codex/codex-rs/core/src/tools/context.rs`
  - `codex/codex-rs/core/src/tools/router.rs`
  - `codex/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
- Rust `ExecCommandHandler::handle` resolves the command, allocates a unified exec process id, then performs
  permission normalization and `apply_patch` interception. Early returns after allocation release the process id.

## Python port progress

- `pycodex/core/unified_exec_handler.py` now follows the Rust manager-path ordering:
  - resolve command and environment
  - allocate manager process id
  - reject disallowed escalated requests with release
  - release after additional permission normalization errors
  - intercept `apply_patch` with release instead of bypassing the manager path
  - release on manager execution errors
- The no-manager stdlib fallback still intercepts `apply_patch` before local subprocess execution, preserving the
  dependency-light local path.

## Validation

- `python -m py_compile pycodex/core/unified_exec_handler.py tests/test_core_unified_exec_handler.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_unified_exec_handler.py -q`
  - `33 passed, 2 skipped`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_tool_router.py tests/test_core_turn_runtime.py -q`
  - `123 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`
