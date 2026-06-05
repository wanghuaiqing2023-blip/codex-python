# Local HTTP Configured Exec-Policy Rules

## Upstream graph slice

- Knowledge graph path:
  - `function:codex-rs/exec/src/lib.rs#run_exec_session:564`
  - `function:codex-rs/core/src/exec_policy.rs#create_exec_approval_requirement_for_command:272`
- Rust source read:
  - `codex/codex-rs/exec/src/cli.rs`
  - `codex/codex-rs/core/src/exec_policy.rs`
  - `codex/codex-rs/core/src/tools/handlers/shell.rs`

## Rust behavior confirmed

- `codex exec` normally loads user/project `.rules` files unless `--ignore-rules` is set.
- Shell tool execution evaluates parsed shell commands against exec-policy prefix rules before falling back to heuristics.
- Matched prefix rules are carried as `RuleMatch::PrefixRuleMatch`, and `create_exec_approval_requirement_for_command` uses them for prompt/forbidden decisions, reasons, and amendment suppression.

## Python changes

- `pycodex/cli/parser.py`
  - Added local HTTP exec discovery for default `rules/*.rules` files under `CODEX_HOME/rules` and the selected working directory's `.codex/rules`.
  - Reuses the existing stdlib `execpolicy check` parser and converts parsed prefix rules into `ExecPolicyPrefixRule` values.
  - Wires loaded rules into `ExecSessionConfig.exec_policy_rules` for local HTTP `exec`/`review`/`resume`, and honors `--ignore-rules`.

- `pycodex/core/exec_policy.py`
  - Added `ExecPolicyPrefixRule`.
  - Added `match_exec_policy_rules_for_command()` to match configured prefix rules against Rust-style shell-wrapper commands after shell parsing.
  - Re-exported the new helper and rule type through `pycodex.core`.

- `pycodex/exec/session.py`
  - Added `ExecSessionConfig.exec_policy_rules` as the runtime hook for loaded/configured exec-policy prefix rules.

- `pycodex/exec/local_runtime.py`
  - Local HTTP shell-tool approval checks now pass matched configured prefix rules into `ExecApprovalRequest`.
  - Rule-driven prompt decisions now produce the Rust-style policy reason and suppress auto-generated amendments.

- `tests/test_core_exec_policy.py`
  - Added coverage for matching configured prefix rules against `bash -lc ...` command wrappers and alternatives.

- `tests/test_exec_local_runtime.py`
  - Added coverage that configured prefix prompt rules block local shell execution and surface the configured justification.

- `tests/test_cli_parser.py`
  - Added coverage that local HTTP `exec` loads user/project `.rules` files into the session config.
  - Added coverage that `--ignore-rules` skips default rule discovery.

## Validation

- `python -m py_compile pycodex\core\exec_policy.py pycodex\core\__init__.py pycodex\exec\session.py pycodex\exec\local_runtime.py tests\test_core_exec_policy.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_core_exec_policy.CoreExecPolicyTests.test_match_exec_policy_rules_for_command_matches_shell_wrapped_prefix_rules tests.test_core_exec_policy.CoreExecPolicyTests.test_create_exec_approval_requirement_for_command_honors_prompt_rule_reason tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_applies_configured_exec_policy_prefix_rules`
- `python -m py_compile pycodex\cli\parser.py tests\test_cli_parser.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_loads_default_execpolicy_rules tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_ignore_rules_skips_default_execpolicy_rules`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_runtime_prints_summary_and_final_message tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_loads_default_execpolicy_rules tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_ignore_rules_skips_default_execpolicy_rules tests.test_cli_parser.TopLevelCliParserTests.test_main_review_local_http_runtime_prints_summary_and_final_message`
- `python -m unittest tests.test_core_exec_policy tests.test_exec_local_runtime`
- Full `python -m unittest tests.test_cli_parser` currently fails on unrelated pre-existing/non-core areas in this dirty worktree/environment, including app/cloud/doctor/remote-control/MCP/app-server parser expectations and local app-server connection tests. The new local HTTP exec-policy tests pass in isolation.

## Follow-up debt

- Python now covers the common local default sources, but it does not yet fully mirror Rust's complete `ConfigLayerStack` discovery, trust/requirements overlays, or ancestor project config behavior.
- Host executable declarations are parsed for `execpolicy check`, but local HTTP shell-tool approval currently only forwards prefix rules into the runtime hook.
