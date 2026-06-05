# Exec Shell Tools Output Schema CLI Coverage

Date: 2026-06-02

## Scope

Used the upstream knowledge graph to stay on the common `codex exec` path. The selected Rust source slice was:

- `codex-rs/exec/src/lib.rs::run_exec_session`
- `codex-rs/exec/src/lib.rs::load_output_schema`
- `codex-rs/core/src/client_common.rs::Prompt`

The behavior checked here is the user-facing `codex exec --output-schema ...` path, especially when local HTTP shell-tool looping is enabled.

## Source Behavior

Rust loads `--output-schema` into the `InitialOperation::UserTurn` output schema. Core request construction then carries that schema through `Prompt.output_schema`, including later model turns that still need the final answer constrained by the same schema.

## Python Change

Added CLI-level coverage proving that Python `exec` keeps the parsed output schema on `plan.initial_operation.output_schema` when `PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS=1` routes execution into `run_exec_user_turn_with_shell_tools_http_sampling`.

Runtime-level tests already cover the schema reaching both the initial local HTTP request and the shell-tool follow-up request. This new test protects the CLI-to-runtime handoff.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_passes_output_schema_to_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_default_tool_rounds_are_unbounded`
- `python -m unittest tests.test_exec_run tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_continues_by_default_until_no_tool_calls`
- `python -m py_compile tests\test_cli_parser.py`

## Known Gaps

This is coverage for a core-path contract, not a new runtime feature. Full parity still requires broader live end-to-end validation of `codex exec` against a real or fully simulated Responses stream.
