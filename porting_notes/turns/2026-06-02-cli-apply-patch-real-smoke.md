# CLI local HTTP apply_patch smoke

## Graph-guided slice

- Upstream graph entrypoint: `codex-rs/exec/src/lib.rs#run_exec_session`.
- Apply-patch behavior nodes:
  - `codex-rs/apply-patch/src/invocation.rs#verify_apply_patch_args`
  - `codex-rs/core/src/apply_patch.rs#apply_patch`
  - `codex-rs/core/src/tools/handlers/apply_patch.rs`
  - `codex-rs/core/src/tools/runtimes/apply_patch.rs`
  - `codex-rs/core/src/tools/handlers/shell.rs#run_exec_like`
- Python target slice: `pycodex.cli.parser` dispatches `codex exec` into the
  local HTTP shell-tool loop, and `pycodex.exec.local_runtime` executes
  Responses `custom_tool_call` `apply_patch` payloads through the Python
  apply-patch implementation before sending a follow-up tool output request.

## Progress

- Added a CLI-level smoke test for model-driven `apply_patch`.
- The fake Responses endpoint first returns a `custom_tool_call` named
  `apply_patch`, then a final assistant message.
- The test runs through `main(["exec", ...])`, writes a file in a temporary
  working directory, and verifies that the follow-up request contains a
  `custom_tool_call_output` without a `name` field, matching the Responses
  shape used by the runtime-level parity tests.
- Added a second CLI-level smoke for the common `exec_command` heredoc form:
  the model emits `exec_command` with an `apply_patch <<'PATCH'` body, and the
  Python runtime intercepts it before shell execution, writes the file, and
  sends a successful `function_call_output` follow-up.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_smoke_writes_file_and_followup`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_exec_command_apply_patch_heredoc_smoke`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_smoke_writes_file_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_posts_expected_request tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_passes_output_schema_to_tool_loop`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_smoke_writes_file_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_exec_command_apply_patch_heredoc_smoke tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_posts_expected_request tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_passes_output_schema_to_tool_loop`
- `python -m py_compile tests\test_cli_parser.py`

## Deferred

- CLI-level approval prompt flow for apply_patch in non-bypass modes.
- Full streaming/event parity for file-change begin/completed events.
