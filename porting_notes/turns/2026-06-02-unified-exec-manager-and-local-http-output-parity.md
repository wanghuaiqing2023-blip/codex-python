# Unified exec manager and local HTTP output parity

## Upstream graph/source slice

- Graph-selected core path:
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#handle`
  - `codex-rs/core/src/exec_policy.rs#create_exec_approval_requirement_for_command`
  - `codex-rs/exec/src/event_processor_with_jsonl_output.rs`
- Confirmed from Rust source:
  - `exec_command` resolves the command and sends an `ExecCommandRequest` through the unified exec process manager.
  - heredoc-derived command prefixes may participate in policy evaluation, but auto-derived exec policy amendments are disabled when complex parsing was required.
  - JSON exec output emits completed thread items for tool outputs and final assistant messages.

## Python changes

- Added `ExecCommandRequest` in `pycodex.core.unified_exec_handler`.
- When a session exposes `services.unified_exec_manager.exec_command`, `ExecCommandHandler` now delegates the resolved command request to that manager, preserving the stdlib subprocess fallback when no manager is available.
- Apply-patch interception from `exec_command` now uses a zero wall time like the Rust handler's intercepted apply-patch path.
- Local HTTP approval output now suppresses `proposed_execpolicy_amendment` for heredoc/herestring commands while still showing the requested `prefix_rule`.
- Local HTTP JSON event emission now preserves named read-only `function_call_output` items as `mcp_tool_call` timeline items, while still dropping unnamed orphan function/custom outputs.

## Validation

- `python -m py_compile pycodex/core/unified_exec_handler.py pycodex/core/__init__.py tests/test_core_unified_exec_handler.py`
- `python -m py_compile pycodex/exec/local_runtime.py`
- `python -m unittest tests.test_core_unified_exec_handler`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_unified_exec_handler tests.test_core_tool_router tests.test_exec_local_runtime`

Known gaps:

- The Python unified exec manager remains a lightweight compatibility surface; deeper Rust process-manager parity is still broader core runtime work.
