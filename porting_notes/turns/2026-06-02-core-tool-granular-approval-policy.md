# Core Tool Granular Approval Policy

## Scope

Advanced granular approval handling from protocol/session compatibility into the
core tool execution path for `exec_command` and direct `apply_patch`.

## Upstream references

- Graph nodes:
  - `codex-rs/core/src/tools/handlers/shell.rs#run_exec_like`
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#handle`
  - `codex-rs/core/src/tools/handlers/mod.rs#normalize_and_validate_additional_permissions`
  - `codex-rs/protocol/src/protocol.rs#AskForApproval`
  - `codex-rs/protocol/src/protocol.rs#GranularApprovalConfig`
- Rust behavior confirmed from source:
  - Shell and unified exec reject unpreapproved sandbox override requests unless
    `approval_policy` is exactly `AskForApproval::OnRequest`.
  - `normalize_and_validate_additional_permissions` applies the same `OnRequest`
    guard for unpreapproved `with_additional_permissions`.
  - `GranularApprovalConfig.sandbox_approval` controls whether sandbox approval
    prompts are allowed.

## Python changes

- `pycodex/core/handler_utils.py`
  - `normalize_and_validate_additional_permissions` now accepts
    `GranularApprovalConfig` without stringifying it.
  - Preserved string compatibility for existing callers.
  - Granular policies remain non-`OnRequest` for unpreapproved additional
    permission requests, matching Rust's current guard.
- `pycodex/core/unified_exec_handler.py`
  - `_invocation_approval_policy` now returns `GranularApprovalConfig` directly
    when present, so explicit escalation is rejected before process allocation
    instead of failing through enum parsing.
- `pycodex/core/apply_patch.py`
  - `_invocation_approval_policy` now preserves granular values.
  - Read-only/out-of-sandbox patch writes produce `forbidden` when granular
    `sandbox_approval` is disabled.

## Validation

- `python -m unittest tests.test_core_handler_utils.HandlerUtilsTests.test_additional_permissions_rejects_unapproved_granular_policy_like_rust tests.test_core_unified_exec_handler.CoreUnifiedExecHandlerTests.test_exec_command_handler_rejects_escalated_request_when_approval_granular tests.test_core_apply_patch.CoreApplyPatchTests.test_apply_patch_handler_forbids_read_only_policy_when_granular_disallows_sandbox_approval`
  - 3 tests passed.
- `python -m unittest tests.test_core_handler_utils tests.test_core_unified_exec_handler tests.test_core_apply_patch tests.test_core_tool_runtimes tests.test_core_tool_sandboxing tests.test_core_exec_policy`
  - 260 tests passed, 1 skipped.
- `python -m py_compile pycodex\core\handler_utils.py pycodex\core\unified_exec_handler.py pycodex\core\apply_patch.py tests\test_core_handler_utils.py tests\test_core_unified_exec_handler.py tests\test_core_apply_patch.py`
  - Passed.
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite tests.test_exec_local_http_runtime_smoke_suite`
  - 94 tests passed.

## Known gaps

- Non-core display/config surfaces may still render granular approval as a
  generic object.
- Full granular behavior for every approval source, especially app-server/TUI
  surfaces and extension areas, remains deferred until the main core runtime
  path is stable.
