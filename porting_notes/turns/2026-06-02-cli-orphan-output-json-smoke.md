# 2026-06-02 CLI orphan-output JSON smoke

## Upstream slice

- Continued the core `exec -> Responses item normalization -> user-visible JSON events` path.
- This follows the Rust normalize behavior where orphan function/custom outputs are not kept as visible history entries.

## Python change

- Added a CLI-level JSON smoke for a local HTTP response containing orphan `function_call_output` and `custom_tool_call_output` items plus a final assistant message.
- The test verifies `codex exec --json` hides those orphan outputs and only emits the final `agent_message`.
- Added the smoke to `tests/test_cli_local_http_smoke_suite.py`, increasing the core local HTTP CLI smoke suite to 25 tests.

## Validation

- `python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_json_orphan_tool_outputs_are_hidden`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_drops_orphan_function_and_custom_outputs`
- `python -m unittest tests.test_cli_local_http_smoke_suite`

## Known gaps

- This adds end-to-end regression coverage for function/custom orphan outputs. Tool-search output timeline modeling remains separate from the active command-execution slice.
