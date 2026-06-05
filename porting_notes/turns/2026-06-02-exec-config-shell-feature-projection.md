# Exec config shell feature projection

## Scope

Advance the core `exec -> config -> model request -> tool schema -> tool dispatch` path by
projecting Rust's shell-related config and feature flags into Python's `ExecSessionConfig`.

## Upstream source checked

- Knowledge graph nodes:
  - `codex-rs/core/src/config/mod.rs#Permissions`
  - `codex-rs/core/src/config/mod.rs` config loading around `allow_login_shell`
  - `codex-rs/core/src/tools/spec_plan.rs#add_shell_tools`
  - `codex-rs/core/src/tools/spec_plan.rs#add_core_utility_tools`
- Rust source confirms:
  - `allow_login_shell` defaults to true and comes from config permissions.
  - `exec_command` / shell tool `additional_permissions` is gated by `Feature::ExecPermissionApprovals`.
  - `request_permissions` is gated separately by `Feature::RequestPermissionsTool`.

## Python changes

- `ExecConfigBootstrapPlan` now records:
  - `allow_login_shell`
  - `exec_permission_approvals_enabled`
  - `request_permissions_tool_enabled`
- `build_exec_config_bootstrap_plan` now applies CLI `-c` overrides to the TOML mapping before deriving
  model/provider, user instructions, and shell-related feature flags.
- `exec_session_config_from_bootstrap_plan` and the CLI local HTTP session builder now pass those flags
  into `ExecSessionConfig`.
- Startup-plan mappings now expose the three flags for test/debug visibility.

## Validation

- `python -m py_compile pycodex\exec\config_plan.py pycodex\cli\parser.py tests\test_exec_config_plan.py tests\test_cli_parser.py`
- `python -m unittest tests.test_exec_config_plan`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_reads_config_toml_for_local_http_session_config tests.test_cli_parser.TopLevelCliParserTests.test_feature_toggles_known_features_generate_overrides`
- `python -m unittest tests.test_exec_local_runtime`

Full `python -m unittest tests.test_cli_parser` was also run and still has unrelated existing failures in
app/cloud/doctor/remote-control/app-server parser areas. The targeted exec config and local HTTP tests pass.

## Deferred

- Broader full-config parity remains incomplete. This slice only wires the shell-related config values
  needed by the current local HTTP exec path.
