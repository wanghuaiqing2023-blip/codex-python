# Local HTTP shell tool spec config flags

## Scope

Continue the core `exec -> model request -> tool dispatch -> final answer` path by making the
local HTTP `exec_command` tool schema follow the same feature/config gates as upstream Rust Codex.

## Upstream source checked

- Knowledge graph nodes:
  - `codex-rs/core/src/tools/spec_plan.rs#add_shell_tools`
  - `codex-rs/core/src/tools/handlers/shell_spec.rs#create_exec_command_tool`
  - `codex-rs/core/src/tools/handlers/shell_spec.rs#create_approval_parameters`
- Rust source confirms:
  - `allow_login_shell` comes from `turn_context.config.permissions.allow_login_shell`.
  - `additional_permissions` is included only when `Feature::ExecPermissionApprovals` is enabled.
  - `request_permissions` is registered only when `Feature::RequestPermissionsTool` is enabled.
  - `allow_login_shell` defaults to true in config loading.

## Python changes

- Added `allow_login_shell` and `exec_permission_approvals_enabled` to `ExecSessionConfig`.
- Added `request_permissions_tool_enabled` to `ExecSessionConfig`.
- Threaded those fields into `local_http_shell_tools_built_tools(..., config=...)`.
- `LocalHttpShellToolRouter` now generates the fallback `exec_command` schema with those flags.
- `LocalHttpShellToolRouter` now hides its fallback `request_permissions` tool when configured off.
- `run_exec_user_turn_with_shell_tools_http_sampling` now passes its session config into the shell tool wrapper.

Defaults intentionally preserve the current local HTTP behavior while allowing callers/tests to
exercise Rust-like disabled states.

## Validation

- `python -m py_compile pycodex\exec\session.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime`

## Deferred

- Broader config TOML feature parsing remains outside this slice. The runtime now has the correct
contract boundary for the local HTTP core path once those config values are loaded.
