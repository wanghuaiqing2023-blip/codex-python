# Local HTTP Unbounded Tool Follow-Up

## Upstream graph slice

- Knowledge graph path:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:1698`
- Rust source read:
  - `codex/codex-rs/core/src/session/turn.rs`

## Rust behavior confirmed

- `run_turn` repeats sampling while the model or pending input needs follow-up.
- Tool calls mark `needs_follow_up`, and `response.completed` with `end_turn == false` also keeps the turn loop alive.
- There is no default one-tool-round cutoff in the common Rust turn loop.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Changed `local_http_exec_max_tool_rounds()` to default to `None`, meaning no fixed local HTTP shell-tool round cap unless the environment overrides it.
  - Changed `run_exec_user_turn_with_shell_tools_http_sampling()` to accept `max_tool_rounds=None` and continue until no tool outputs are produced.
  - Kept `PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS=<non-negative integer>` as an explicit local guard or test override.

- `tests/test_exec_local_runtime.py`
  - Added coverage that the local HTTP shell-tool loop continues through two tool-call rounds by default and stops when the model returns a final answer.
  - Updated max-tool-round environment coverage for the new Rust-like default.

- `tests/test_cli_parser.py`
  - Added coverage that CLI local HTTP shell-tools mode passes `None` for `max_tool_rounds` when no environment cap is configured.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_continues_by_default_until_no_tool_calls tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_max_tool_rounds_env tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_default_tool_rounds_are_unbounded`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_default_tool_rounds_are_unbounded tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_passes_tool_loop_options tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_rejects_invalid_max_rounds`

## Follow-up debt

- Python still lacks Rust's full mid-turn compaction and pending user-input drain behavior around very long follow-up chains.
- The local HTTP helper keeps the explicit environment cap as an operational escape hatch, even though Rust's main loop has no default fixed round limit.
