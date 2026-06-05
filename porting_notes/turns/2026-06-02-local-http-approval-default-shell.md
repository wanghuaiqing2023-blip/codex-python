# Local HTTP approval default shell

## Scope

- Continued the core local HTTP shell-tool path after command-action metadata was moved off the hard-coded `bash -lc` approximation.
- Approval and exec-policy decisions now use the same shell argv derivation as command execution metadata.
- This affects model-facing `approval_required` tool output, exec-policy prefix-rule matching, and forbidden-command checks in the local HTTP helper.

## Upstream behavior

- Relevant Rust source:
  - `codex-rs/core/src/shell.rs`
  - `codex-rs/core/src/tools/handlers/shell.rs`
  - `codex-rs/core/src/tools/handlers/shell/shell_command.rs`
  - `codex-rs/core/src/tools/handlers/unified_exec.rs`
- Rust derives command argv from the active/default shell before applying approval and exec-policy logic.

## Python changes

- `pycodex/exec/local_runtime.py`
  - `_local_http_shell_tool_exec_policy_command()` now reuses `_shell_command_execution_argv()`.
  - This keeps approval/exec-policy rendering aligned with the same default shell helper used by local command execution timeline metadata.
- `tests/test_exec_local_runtime.py`
  - Added coverage proving `_local_http_shell_tool_exec_policy_command()` and `_shell_command_execution_argv()` stay in sync.
  - Updated prefix-rule approval coverage to patch a PowerShell default shell and assert the model-facing reason uses `pwsh.exe -Command ...`.
  - Made the forbidden dangerous-command fixture explicitly use `/bin/bash`, so the test is about bash danger parsing rather than the host default shell.

## Validation

```powershell
python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py
python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tool_exec_policy_command_uses_same_shell_argv tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_command_execution_argv_uses_default_user_shell tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_applies_configured_exec_policy_prefix_rules tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_output_requires_approval_before_execution
python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_forbidden_exec_policy_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_output_requires_approval_before_execution tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tool_exec_policy_command_uses_same_shell_argv tests.test_core_exec_policy
python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_applies_configured_exec_policy_prefix_rules tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_forbidden_exec_policy_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_output_requires_approval_before_execution tests.test_core_shell tests.test_shell_command_parse_command
python -m unittest tests.test_cli_local_http_smoke_suite
```

Results:

- Focused approval/default-shell checks: 4 passed.
- Exec-policy and affected runtime checks: 26 passed.
- Shell/runtime related checks: 53 passed.
- Core local HTTP CLI smoke suite: 23 passed.

## Follow-up

- This keeps the local HTTP non-interactive approval output aligned with the ported shell helper. Full interactive approval UI/app-server approval transport remains outside this core local HTTP slice.
