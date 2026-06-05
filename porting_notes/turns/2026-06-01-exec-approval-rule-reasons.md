# Exec Approval Rule Reasons

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/core/src/exec_policy.rs#derive_prompt_reason:929`
  - `function:codex-rs/core/src/session/mod.rs#request_command_approval:1947`
  - `class:codex-rs/protocol/src/approvals.rs#ExecApprovalRequestEvent:218`
- Rust files read:
  - `codex/codex-rs/core/src/exec_policy.rs`
  - `codex/codex-rs/core/src/session/mod.rs`
  - `codex/codex-rs/protocol/src/approvals.rs`

## Rust behavior confirmed

- `derive_prompt_reason` only returns a reason when a prompt decision came from an exec-policy prefix rule.
- The most specific prompt prefix wins.
- Prompt rules with a justification render:
  - `` `{command}` requires approval: {justification}``
- Prompt rules without a justification render:
  - `` `{command}` requires approval by policy``
- `request_command_approval` carries this reason into `ExecApprovalRequestEvent.reason`.

## Python changes

- `pycodex/core/exec_policy.py`
  - Added `derive_prompt_reason` and `derive_forbidden_reason`.
  - `create_exec_approval_requirement_for_command` now includes policy-rule decisions in the final requirement decision instead of using only unmatched-command fallback decisions.
  - `NeedsApproval` now carries the prompt reason when a matched prompt rule caused the approval.
  - `Forbidden` now prefers matched forbidden-rule justifications when available.

- `pycodex/core/__init__.py`
  - Re-exported the new reason helpers.

- `pycodex/exec/local_runtime.py`
  - Local HTTP approval-required shell output now includes `reason: ...` when the requirement carries one.

- `tests/test_core_exec_policy.py`
  - Added prompt-rule and forbidden-rule reason coverage.

- `tests/test_exec_local_runtime.py`
  - Added local HTTP approval output coverage for requirement reasons.

## Validation

- `python -m py_compile pycodex\core\exec_policy.py pycodex\core\__init__.py pycodex\exec\local_runtime.py tests\test_core_exec_policy.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_core_exec_policy.CoreExecPolicyTests.test_create_exec_approval_requirement_for_command_honors_prompt_rule_reason tests.test_core_exec_policy.CoreExecPolicyTests.test_create_exec_approval_requirement_for_command_honors_forbidden_rule_reason tests.test_core_exec_policy.CoreExecPolicyTests.test_create_exec_approval_requirement_for_command_proposes_requested_prefix_rule tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_shell_tool_approval_output_includes_requirement_reason`
- `python -m unittest tests.test_core_exec_policy`
- `python -m unittest tests.test_exec_local_runtime`

## Known gaps

- The Python local HTTP helper still does not load and evaluate persistent exec-policy files on its own. This turn improves the shared requirement helper and output plumbing so rule reasons are preserved wherever matched rule data is available.
