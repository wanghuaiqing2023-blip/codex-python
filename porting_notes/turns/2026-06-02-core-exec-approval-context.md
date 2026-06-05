# Core exec approval context

## Scope

Advanced the default `codex exec` core route by carrying approval and permission
context into the in-memory session and by enforcing the Rust unified exec
handler's pre-execution permission checks before launching commands.

## Upstream reference

- Graph-selected slice: `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`.
- Supporting Rust helper behavior: `codex-rs/core/src/tools/handlers/mod.rs`.
- Confirmed that upstream validates `require_escalated` and
  `with_additional_permissions` before calling the unified exec manager, applies
  granted turn/session permissions, and rejects fresh sandbox override requests
  unless approval policy is `OnRequest`.

## Python changes

- `pycodex/core/unified_exec_handler.py`
  - Applies granted session/turn permissions before constructing
    `ExecCommandRequest`.
  - Rejects fresh sandbox override requests when the turn approval policy is not
    `on-request`.
  - Normalizes and validates `additional_permissions` with the existing
    stdlib-only helper layer.
  - Keeps lightweight test/session substitutes compatible by treating missing
    grant accessors as no grants.
- `pycodex/exec/local_runtime.py`
  - Added `_in_memory_exec_session()` so default HTTP/core sampling paths carry
    `approval_policy`, `approvals_reviewer`, `permission_profile`,
    file-system sandbox policy, feature flags, workspace roots, request
    permission callback, and granted session permissions from
    `ExecSessionConfig`.

## Validation

- `python -m unittest tests.test_core_unified_exec_handler tests.test_core_turn_runtime tests.test_core_unified_exec`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_passes_exec_approval_policy_to_core_tools tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_core_exec_tool_loop_by_default`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite`
- `python -m py_compile pycodex\core\unified_exec_handler.py pycodex\exec\local_runtime.py tests\test_core_unified_exec_handler.py tests\test_exec_local_runtime.py`

## Known gaps

- Full interactive approval prompting and app-server approval request events are
  still not complete on the Python core route.
- Deep platform sandbox enforcement remains approximated by the current Python
  process manager; this change only preserves the pre-execution user-visible
  policy behavior for common `exec_command` requests.
