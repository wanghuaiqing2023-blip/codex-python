# Tool emitter command actions

## Upstream Rust slice

- Graph-selected files:
  - `codex/codex-rs/core/src/tools/events.rs`
  - `codex/codex-rs/core/src/session/turn.rs`
  - `codex/codex-rs/core/src/tools/router.rs`
- Rust `ToolEmitter::shell` and `ToolEmitter::unified_exec` call `parse_command(command)` during construction,
  so exec begin/end events naturally include parsed command actions for app-server/user-visible command execution
  items.

## Python port progress

- `pycodex/core/tool_events.py` now parses command actions by default for `ToolEmitter.shell(...)` and
  `ToolEmitter.unified_exec(...)`.
- Explicit `parsed_cmd` arguments still override the default parser, preserving tests and injected fixtures.
- This improves common command UI parity for read/search/list command actions without adding third-party
  dependencies.

## Validation

- `python -m py_compile pycodex/core/tool_events.py tests/test_core_tool_events.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_tool_events.py tests/test_shell_command_parse_command.py -q`
  - `30 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_tool_router.py tests/test_core_turn_runtime.py -q`
  - `123 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`
