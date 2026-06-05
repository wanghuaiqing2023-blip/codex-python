# CLI approval policy for local HTTP tools

## Graph-guided slice

- Upstream graph nodes used as the approval/safety path:
  - `codex-rs/exec/src/lib.rs#run_exec_session`
  - `codex-rs/core/src/tools/runtimes/apply_patch.rs#start_approval_async`
  - `codex-rs/core/src/tools/runtimes/apply_patch.rs#exec_approval_requirement`
  - `codex-rs/core/tests/suite/approvals.rs#approving_apply_patch_for_session_skips_future_prompts_for_same_file`
- Python target slice:
  - `pycodex.exec.cli.ExecCli`
  - `pycodex.cli.parser._inherit_exec_root_options`
  - `pycodex.exec.config_plan.exec_harness_overrides_from_cli`
  - `pycodex.exec.local_runtime.shell_tool_outputs_from_local_http_exec_result`

## Progress

- Fixed root `--ask-for-approval` inheritance for `codex exec`.
- `ExecCli` now carries the inherited approval policy.
- `exec_harness_overrides_from_cli` now projects the CLI approval policy into
  `ExecSessionConfig` instead of forcing `never`.
- Added CLI-level coverage proving that `--ask-for-approval on-request` blocks
  local HTTP `apply_patch` from writing files and returns a model-visible
  `approval_required` tool output.
- Added CLI-level coverage proving the same inherited approval policy blocks
  local HTTP `exec_command` before shell execution. The blocked command would
  have written a file, and the smoke verifies the file is absent while the
  follow-up request carries a failed `function_call_output` with
  `exit_code: approval_required`.

## Validation

- `python -m unittest tests.test_exec_config_plan.ExecConfigPlanTests.test_exec_harness_overrides_preserves_cli_approval_policy tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_on_request_requires_approval tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_smoke_writes_file_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_exec_command_apply_patch_heredoc_smoke tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tool_on_request_requires_approval`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tool_on_request_requires_approval tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_on_request_requires_approval tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_smoke_writes_file_and_followup tests.test_exec_config_plan.ExecConfigPlanTests.test_exec_harness_overrides_preserves_cli_approval_policy`
- `python -m py_compile pycodex\exec\cli.py pycodex\cli\parser.py pycodex\exec\config_plan.py tests\test_cli_parser.py tests\test_exec_config_plan.py`

## Observed adjacent issue

- `tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details`
  currently returns code 1 in this workspace when run directly, with unrelated
  doctor/update-check resource warnings. This was not part of the local HTTP
  exec approval slice and remains separate follow-up debt.

## Deferred

- Interactive approval UI flow for local HTTP tools.
- Persisted/session-scoped approval grants for CLI-level smoke coverage.
- Explicit user-approved shell command continuation flow beyond the current
  model-visible refusal smoke.
