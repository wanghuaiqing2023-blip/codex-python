## Unified exec sandbox denied handler output

Slice:

- Upstream graph nodes:
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#handle`
  - `codex-rs/core/src/tools/handlers/unified_exec.rs#post_unified_exec_tool_use_payload`
  - `codex-rs/core/src/tools/runtimes/shell.rs`
- Authoritative Rust behavior:
  - `ExecCommandHandler::handle` treats `UnifiedExecError::SandboxDenied` as terminal command output, not as a normal tool failure.
  - The handler returns `ExecCommandToolOutput` with the captured aggregated output, duration, exit code, generated chunk id, original token count, no live process id, and the original hook command.

Python changes:

- `pycodex/core/unified_exec_handler.py`
  - Added a `UnifiedExecError::SANDBOX_DENIED` branch in the manager-backed exec handler path.
  - Converts protocol `ExecToolCallOutput` into core `ExecCommandToolOutput` so the model receives the sandbox denial output as a successful tool result.
- `tests/test_core_unified_exec_handler.py`
  - Added coverage for manager-raised sandbox denial preserving event call id, generated chunk id, wall time, captured output, exit code, max output tokens, original token count, and hook command.

Validation:

- `python -m py_compile pycodex\core\unified_exec_handler.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_unified_exec_handler.py -q`
  - `34 passed, 2 skipped`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_unified_exec.py tests\test_core_unified_exec_handler.py tests\test_core_exec.py tests\test_core_tool_router.py -q`
  - `149 passed, 2 skipped`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`

Known gaps:

- Deeper platform sandbox execution behavior remains approximate in Python; this slice only aligns the user-visible manager/handler result conversion for sandbox denial on the core unified exec path.
