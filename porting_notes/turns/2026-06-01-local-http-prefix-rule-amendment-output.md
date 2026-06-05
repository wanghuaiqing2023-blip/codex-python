# Local HTTP Prefix Rule Amendment Output

## Upstream graph slice

- Graph query matched `function:codex-rs/core/src/exec_policy.rs#create_exec_approval_requirement_for_command:272`.
- Related upstream files read:
  - `codex/codex-rs/core/src/tools/handlers/shell.rs`
  - `codex/codex-rs/core/src/exec_policy.rs`

## Rust behavior confirmed

- The shell handler passes tool-call `prefix_rule` into `ExecApprovalRequest`.
- `create_exec_approval_requirement_for_command` derives `proposed_execpolicy_amendment` for approval-required commands when parsing is not complex.
- Heredoc fallback parsing still evaluates policy decisions, but does not auto-derive an amendment.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Local HTTP `approval_required` shell output now calls `create_exec_approval_requirement_for_command`.
  - When Rust-style policy evaluation proposes an amendment, the model-facing output includes:
    - `proposed_execpolicy_amendment: {"command":[...]}`
  - Local shell command strings are wrapped as shell policy commands for parsing, using PowerShell wrapping when an explicit PowerShell shell is requested and `bash -lc` otherwise.

- `tests/test_exec_local_runtime.py`
  - Existing prefix-rule approval output test now asserts the proposed amendment is preserved.
  - Added heredoc coverage to assert complex parsing does not emit an automatic amendment.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_preserves_prefix_rule tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_skips_heredoc_prefix_rule_amendment`
- `python -m unittest tests.test_core_exec_policy tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_output_requires_approval_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_preserves_metadata tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_preserves_prefix_rule tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_skips_heredoc_prefix_rule_amendment tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_unknown_sandbox_permissions_before_execution`
- `python -m unittest tests.test_exec_local_runtime`

## Known gaps

- This only exposes the amendment in the local HTTP helper's model-facing approval output. Full protocol approval-event handling already has amendment data types, but deeper app-server approval flows remain outside this core local-exec slice.
