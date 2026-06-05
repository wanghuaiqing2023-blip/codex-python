# 2026-06-01 Exec Policy Prefix Rule Amendment

## Graph-Guided Slice

- Continued the core `exec -> tool dispatch -> approval/safety -> shell execution` path.
- Used the upstream graph to focus on high-impact exec-policy nodes:
  - `codex/codex-rs/core/src/exec_policy.rs`
  - `codex/codex-rs/execpolicy/src/policy.rs`

## Upstream Behavior

- Rust derives a proposed `ExecPolicyAmendment` from a model-supplied `prefix_rule` only when:
  - the prefix exists and is not empty;
  - it is not an exact match for broad banned suggestions such as `python -c`, shell wrappers, PowerShell wrappers, `sudo`, `node -e`, etc.;
  - no existing policy rule already matched;
  - adding that prefix would approve all command candidates.
- Exact banned prefixes are rejected, but more specific longer prefixes like `python -c "print('hi')"` may still be proposed.

## Python Work

- Added `derive_requested_execpolicy_amendment_from_prefix_rule`.
- Added `prefix_rule_would_approve_all_commands`.
- Added `ExecApprovalRequest` and `create_exec_approval_requirement_for_command`, covering the common no-policy-rule path that parses shell wrappers, evaluates unmatched-command heuristics, applies the requested `prefix_rule`, and returns the `ExecApprovalRequirement` shape consumed by tool runtimes.
- Added the Rust banned-prefix list as `BANNED_PREFIX_SUGGESTIONS`.
- Exported the new helpers through `pycodex.core`.
- Added focused coverage in `tests/test_core_exec_policy.py`.
- Fixed a missing `Any` import in `tests/test_core_tool_sandboxing.py` that blocked the related regression set.

## Validation

- `python -m unittest tests.test_core_exec_policy`
- `python -m unittest tests.test_core_exec_policy tests.test_core_tool_sandboxing tests.test_core_tool_runtimes`
- `python -m unittest tests.test_core_exec_policy tests.test_core_tool_sandboxing tests.test_core_tool_runtimes tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_output_preserves_prefix_rule`
- `python -m py_compile pycodex\core\exec_policy.py pycodex\core\__init__.py tests\test_core_exec_policy.py`

## Deferred

- This slice adds and validates the Rust-compatible amendment derivation and common approval-requirement aggregation boundary. A later slice should wire this helper into the full shell/unified-exec approval event path wherever the Python runtime has enough session policy context.
