# 2026-06-02 CLI local_shell_call JSON smoke

## Upstream slice

- Continued the core `exec -> Responses item -> command execution event` path.
- The relevant Rust behavior remains `ResponseItem::LocalShellCall` normalization and app-server command execution rendering from:
  - `codex/codex-rs/core/src/context_manager/normalize.rs`
  - `codex/codex-rs/app-server-protocol/src/protocol/item_builders.rs`

## Python change

- Added a CLI-level JSON smoke test for a local HTTP Responses payload containing `local_shell_call` without an explicit output.
- The test verifies that `codex exec --json` emits `command_execution` in-progress/completed items and uses the normalized `aborted` output for the completed item.
- Added the new smoke to `tests/test_cli_local_http_smoke_suite.py`, bringing the core local HTTP CLI smoke suite to 24 tests.

## Validation

- `python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_json_local_shell_call_smoke_outputs_command_execution`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_inserts_missing_output_for_local_shell_call tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_maps_local_shell_call_to_command_execution`

## Known gaps

- This is regression coverage for already-supported timeline rendering. It does not add a new local-shell execution runtime.
