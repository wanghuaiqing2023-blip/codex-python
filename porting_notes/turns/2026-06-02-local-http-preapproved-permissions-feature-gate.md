# Local HTTP preapproved permissions feature gate

## Scope

Continue the core `exec -> tool dispatch -> shell execution` path by aligning how local HTTP shell
commands use additional permissions that were granted by `request_permissions`.

## Upstream source checked

- Knowledge graph nodes:
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
  - `codex-rs/core/src/tools/handlers/shell/shell_command.rs`
- Rust source confirms:
  - `additional_permissions_allowed` is true when `Feature::ExecPermissionApprovals` is enabled.
  - If permissions are already preapproved by `request_permissions`, they are also allowed only when
    `Feature::RequestPermissionsTool` is enabled.
  - Preapproved permissions skip the pending approval branch and continue through normal exec approval.

## Python changes

- Added `local_http_shell_tool_additional_permissions_allowed`.
- `shell_tool_outputs_from_local_http_exec_result` now computes the Rust-style feature gate after
  checking whether requested permissions are preapproved.
- `local_http_shell_tool_permission_request_error` now rejects preapproved grants when both
  `exec_permission_approvals_enabled` and `request_permissions_tool_enabled` are disabled.
- Added tests for:
  - normal granted additional permissions,
  - request-permissions preapproved grants with `exec_permission_approvals_enabled=False`,
  - disabled feature rejection even when a grant object is present.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- Focused tests:
  - `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_runs_with_granted_additional_permissions tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_runs_with_request_permissions_preapproved_grant tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_granted_permissions_when_feature_disabled tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_applies_granted_request_permissions`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_exec_config_plan tests.test_exec_session`

## Deferred

- This remains a local HTTP/runtime slice. Full app-server feature wiring and non-core transports are still
  out of scope for the active core-runtime push.
