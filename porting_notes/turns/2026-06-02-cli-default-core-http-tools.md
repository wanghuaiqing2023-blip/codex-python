# 2026-06-02 - CLI default core HTTP tools

## Upstream slice

- Continued from the graph-selected `codex-rs/exec/src/lib.rs#run_exec_session` path.
- The relevant Rust behavior is that `exec` sends a user turn into the core runtime, then lets the core event/tool loop drive tool execution and follow-up model requests.

## Python changes

- Changed `local_http_exec_shell_tools_enabled()` so the legacy local HTTP shell-loop runs only when `PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS=1` is set.
- The default local HTTP CLI exec path now selects `run_exec_user_turn_http_sampling`, which uses `run_user_turn_http_sampling_from_session` and the core runtime tool router.
- Kept the legacy `run_exec_user_turn_with_shell_tools_http_sampling` path available behind the explicit environment flag for compatibility while the core route matures.
- Added runtime coverage proving `run_exec_user_turn_http_sampling` can receive an HTTP `exec_command` tool call, execute it through the core router, send `function_call_output` in the next HTTP request, and finish with a final assistant message.
- Added CLI coverage proving default local HTTP exec uses the core HTTP runner, while explicit `PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS=1` still selects the legacy shell-loop.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_core_exec_tool_loop_by_default tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_core_sampling_runs_default_exec_tool_loop tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tools_default_disabled_with_explicit_enable`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_default_uses_core_http_sampling tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_explicit_tool_rounds_are_unbounded tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_core_exec_tool_loop_by_default`
- `python -m py_compile pycodex\exec\local_runtime.py pycodex\cli\parser.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite`
- `git diff --check -- pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`

The focused local HTTP smoke run completed 80 tests successfully.

## Known gaps

- A broad `tests.test_exec_local_runtime tests.test_cli_parser` run still has unrelated failures in app/cloud/doctor/remote-control/proxy/MCP areas in the current worktree. Those are outside the active core exec slice and were not treated as evidence against the default core exec path.
- The default path still depends on the local HTTP Responses transport for real model calls; deeper app-server parity remains deferred.
