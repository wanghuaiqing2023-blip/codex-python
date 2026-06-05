# CLI resume output-schema real smoke

## Scope

- Added a local HTTP CLI smoke for `codex exec resume <thread> --output-schema <path>`.
- The smoke covers the core resumed task path:
  - Resolve an existing rollout thread.
  - Load prior conversation history.
  - Load a JSON schema from disk.
  - Send the resumed turn through local HTTP shell-tool execution.
  - Preserve the schema on both the initial and follow-up Responses requests.
  - Append the final assistant output back to the existing rollout.

## Upstream navigation

- Used the upstream knowledge graph to stay on the CLI/execution path.
- Confirmed relevant upstream CLI behavior in `codex-rs/cli/src/main.rs`, where `exec resume ... --output-schema ...` is accepted and stored on the exec command.
- Related upstream core test areas remain:
  - `codex-rs/core/tests/suite/exec.rs`
  - `codex-rs/core/tests/suite/cli_stream.rs`
  - `codex-rs/core/tests/suite/apply_patch_cli.rs`

## Python changes

- Added `TopLevelCliParserTests.test_main_exec_resume_local_http_output_schema_smoke_reaches_followup_request`.
- The test creates a rollout with prior user and assistant messages, runs:

```powershell
python -m pycodex exec resume <thread> --output-schema schema.json --dangerously-bypass-approvals-and-sandbox "resume with schema"
```

- Fake local HTTP first returns an `exec_command` tool call, then a JSON-shaped final assistant answer.
- The test asserts:
  - Both request bodies contain the loaded schema in `text.format`.
  - Resumed history and the current prompt are present in model input.
  - The tool output reaches the follow-up request.
  - The final assistant output is appended to the original rollout.
- Added the smoke to `tests/test_cli_local_http_smoke_suite.py`, raising the core suite from 22 to 23 tests.

## Validation

```powershell
python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py
python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_output_schema_smoke_reaches_followup_request
python -m unittest tests.test_cli_local_http_smoke_suite
python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_passes_output_schema tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_smoke_runs_command_and_appends_rollout tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_reconstructed_model_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer
```

Results:

- New resume smoke: 1 test passed.
- Core local HTTP CLI smoke suite: 23 tests passed in about 1.9 seconds.
- Focused resume/runtime checks: 5 tests passed.

One attempted validation used the outdated name `test_local_http_resume_runner_uses_rollout_history`; unittest correctly reported the current test as `test_local_http_resume_runner_uses_reconstructed_model_history`. The corrected command above passed.

## Follow-up

- This protects the common resumed local HTTP `exec --output-schema` path. Broader remote/app-server resume schema transport remains outside the active core runtime slice.
