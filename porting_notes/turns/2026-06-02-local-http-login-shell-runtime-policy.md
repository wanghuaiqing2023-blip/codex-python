# Local HTTP login shell runtime policy

## Scope

Continue the core `exec -> tool-call parsing -> tool dispatch -> command execution` slice by making
the local HTTP shell execution path enforce Rust's `allow_login_shell` runtime behavior, not just
hide the schema field.

## Upstream source checked

- Knowledge graph nodes:
  - `codex-rs/core/src/tools/handlers/unified_exec.rs#get_command`
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
  - `codex-rs/core/src/tools/handlers/shell/shell_command.rs#resolve_use_login_shell`
- Rust source confirms:
  - If `login=true` and `allow_login_shell=false`, the tool returns a model-facing error:
    `login shell is disabled by config; omit \`login\` or set it to false.`
  - If `login` is omitted, the effective login-shell choice defaults to `allow_login_shell`.

## Python changes

- Added `local_http_shell_tool_login_error`.
- Added `local_http_shell_invocation_with_config_login`.
- `shell_tool_outputs_from_local_http_exec_result` now rejects disallowed explicit login shells before
  sandbox/approval/execution handling.
- Omitted `login` is now materialized from `ExecSessionConfig.allow_login_shell` so downstream runner and
  apply-patch command derivation use the same effective value.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- Focused login/tool schema tests:
  - `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_passes_login_argument_to_runner tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_login_when_disabled_by_config tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_resolves_omitted_login_from_config tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_uses_configured_shell_spec_flags`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_exec_config_plan tests.test_exec_session`

## Deferred

- The stdlib subprocess fallback still cannot faithfully construct a real login shell process in every
  platform/shell combination. This slice aligns the safety/error/default behavior visible on the core path.
