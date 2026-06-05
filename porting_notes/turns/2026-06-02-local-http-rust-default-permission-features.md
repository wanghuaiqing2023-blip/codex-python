# Local HTTP Rust default permission features

## Scope

Continue the core `exec -> config -> model-visible tools -> tool dispatch` path by aligning local HTTP
session defaults with Rust feature defaults.

## Upstream source checked

- Knowledge graph nodes:
  - `codex-rs/core/src/tools/spec_plan.rs#add_shell_tools`
  - `codex-rs/core/src/tools/spec_plan.rs#add_core_utility_tools`
  - `codex-rs/core/src/tools/handlers/mod.rs#normalize_and_validate_additional_permissions`
- Rust source confirms:
  - `allow_login_shell` defaults to true.
  - `Feature::ExecPermissionApprovals` defaults to false.
  - `Feature::RequestPermissionsTool` defaults to false.
  - Without `ExecPermissionApprovals`, `with_additional_permissions` requests fail before approval unless
    permissions were already preapproved through an enabled `RequestPermissionsTool`.

## Python changes

- `ExecSessionConfig` now defaults `exec_permission_approvals_enabled=False`.
- `ExecSessionConfig` now defaults `request_permissions_tool_enabled=False`.
- `LocalHttpShellToolRouter`, `local_http_shell_tool_spec`, and `local_http_shell_tools_built_tools`
  now use those Rust-like defaults when no explicit config is supplied.
- Tests that exercise additional permission approval/request-permissions behavior now enable the relevant
  feature explicitly.
- Local HTTP schema tests now cover:
  - default `exec_command` without `additional_permissions`,
  - explicit `exec_permission_approvals_enabled=True`,
  - explicit `request_permissions_tool_enabled=True`.

## Validation

- `python -m py_compile pycodex\exec\session.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_exec_config_plan tests.test_exec_session`

## Deferred

- This aligns the local HTTP core runtime defaults. Full CLI/app-server parity for unrelated commands remains
  outside this mainline slice.
