# CLI output-schema real smoke

## Scope

- Added an end-to-end local HTTP CLI smoke for `codex exec --output-schema`.
- The smoke covers the user-facing path from a schema file through:
  - CLI parsing.
  - Local HTTP request construction.
  - Shell-tool execution.
  - Follow-up Responses request construction.
  - Final assistant output rendering.

## Upstream navigation

- Used the upstream knowledge graph to stay on the CLI/execution path.
- Relevant Rust source/test files checked:
  - `codex-rs/cli/src/main.rs`
  - `codex-rs/core/tests/suite/exec.rs`
  - `codex-rs/core/tests/suite/cli_stream.rs`
  - `codex-rs/core/tests/suite/apply_patch_cli.rs`

Rust CLI accepts `exec resume ... --output-schema ...` after the resume subcommand and stores the flag on the exec command. The core runtime then carries the loaded schema into Responses request `text.format`.

## Python changes

- Added `TopLevelCliParserTests.test_main_exec_local_http_output_schema_smoke_reaches_followup_request`.
- The test runs `main(["exec", "--output-schema", <schema>, "--dangerously-bypass-approvals-and-sandbox", ...])` against fake local HTTP responses.
- It asserts both the initial and follow-up request bodies contain:
  - `text.format.type == "json_schema"`
  - `text.format.name == "codex_output_schema"`
  - `text.format.strict == True`
  - the exact schema loaded from disk.
- Added the smoke to `tests/test_cli_local_http_smoke_suite.py`, raising the core suite from 21 to 22 tests.

## Validation

```powershell
python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py
python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_output_schema_smoke_reaches_followup_request
python -m unittest tests.test_cli_local_http_smoke_suite
python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_passes_output_schema_to_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_passes_output_schema tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer tests.test_core_turn_request.TurnRequestTests.test_build_turn_responses_request_infers_non_strict_schema_for_guardian_reviewer tests.test_core_http_transport.HttpTransportTests.test_run_user_turn_http_sampling_infers_guardian_output_schema_non_strict
```

Results:

- New smoke: 1 test passed.
- Core local HTTP CLI smoke suite: 22 tests passed in about 1.5 seconds.
- Focused lower-level output-schema checks: 5 tests passed.

One attempted validation used an outdated runtime test name and a pytest-style `tests/test_core_client.py` test in an environment without pytest. The corrected standard-library unittest command above passed.

## Follow-up

- This protects the common local HTTP `exec --output-schema` path. It does not expand into app-server or remote-control schema transport, which remain outside the current core runtime slice.
