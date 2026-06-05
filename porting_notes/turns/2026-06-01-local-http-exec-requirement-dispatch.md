# Local HTTP Exec Requirement Dispatch

## Upstream graph slice

- Knowledge graph node used:
  - `function:codex-rs/core/src/exec_policy.rs#create_exec_approval_requirement_for_command:272`
- Rust source files read:
  - `codex/codex-rs/core/src/tools/handlers/shell.rs`
  - `codex/codex-rs/core/src/tools/orchestrator.rs`
  - `codex/codex-rs/core/src/tools/sandboxing.rs`
  - `codex/codex-rs/core/src/tools/runtimes/shell.rs`
  - `codex/codex-rs/core/src/exec_policy.rs`

## Rust behavior confirmed

- Shell tool calls pass `ExecApprovalRequirement` into the orchestrator.
- `Forbidden` returns a rejected tool error before execution.
- `NeedsApproval` requests approval before execution.
- `Skip` proceeds to the first execution attempt.
- Explicit `with_additional_permissions` / escalation requests remain approval-gated even when the base command is otherwise safe.
- On Windows, Rust also accounts for missing read-only sandbox enforcement; the Python local HTTP helper does not yet implement the same sandbox layer, so this turn only applies pre-execution `forbidden` to commands detected as dangerous.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Shell tool dispatch now computes the local exec-policy requirement before execution.
  - `Forbidden` dangerous commands return a model-facing forbidden output instead of running.
  - `NeedsApproval` returns approval-required output.
  - `Skip` allows normal local execution, aligning `on-failure` and safe `on-request` behavior with Rust's first-attempt flow.
  - Pending `require_escalated` / `with_additional_permissions` requests still force approval under `on-request`.

- `tests/test_exec_local_runtime.py`
  - Added coverage that `approval_policy=never` rejects a dangerous shell command before the runner is called.
  - Added coverage that `approval_policy=on-failure` executes a safe skip requirement.
  - Updated the old approval-required test to use a dangerous command, matching Rust's policy-driven distinction between safe and dangerous commands.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_forbidden_exec_policy_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_on_failure_executes_skip_requirement tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_preserves_metadata tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_session_nonzero_exit_remains_successful_tool_result tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_tool_call_passes_shell_argument`
- `python -m unittest tests.test_core_exec_policy tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_output_requires_approval_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_forbidden_exec_policy_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_on_failure_executes_skip_requirement tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_preserves_metadata tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_preserves_prefix_rule tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_skips_heredoc_prefix_rule_amendment tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_unknown_sandbox_permissions_before_execution`
- `python -m unittest tests.test_exec_local_runtime`

## Follow-up debt

- Full Windows sandbox parity is still not implemented in the local HTTP helper. The current forbidden gate is intentionally limited to dangerous-command detection so normal local exec sessions keep working while still blocking clearly dangerous commands under `approval_policy=never`.
