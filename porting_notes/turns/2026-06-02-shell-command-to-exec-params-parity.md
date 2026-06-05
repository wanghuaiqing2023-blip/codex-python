## shell_command to_exec_params parity

Slice:

- Upstream graph nodes:
  - `codex-rs/core/src/tools/handlers/shell/shell_command.rs#to_exec_params`
  - `codex-rs/core/src/tools/handlers/shell/shell_command.rs#resolve_use_login_shell`
  - `codex-rs/core/src/tools/handlers/shell_tests.rs#shell_command_handler_to_exec_params_uses_session_shell_and_turn_context`
- Authoritative Rust behavior:
  - `shell_command` derives argv from the session user shell and the resolved login-shell setting.
  - The working directory is resolved against the turn context.
  - `ExecParams` carries shell-tool capture policy, timeout expiration, environment from `create_env(shell_environment_policy, thread_id)`, turn network, sandbox permissions, Windows sandbox fields, justification, and `arg0: None`.

Python changes:

- `pycodex/core/shell_handler.py`
  - Added `ShellCommandHandler.to_exec_params` as a pure compatibility contract for the legacy `shell_command` path.
  - Added small helpers for session shell lookup, turn cwd resolution, and Windows private desktop extraction.
- `tests/test_core_shell_handler.py`
  - Added coverage for argv, cwd, timeout, capture policy, environment thread id, network, sandbox permissions, Windows sandbox fields, justification, and `arg0`.

Validation:

- `python -m py_compile pycodex\core\shell_handler.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_shell_handler.py -q`
  - `10 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_shell_handler.py tests\test_core_shell_spec.py tests\test_core_shell.py tests\test_core_tool_registry.py tests\test_core_tool_router.py -q`
  - `102 passed, 12 subtests passed`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_unified_exec.py tests\test_core_unified_exec_handler.py tests\test_core_shell_handler.py tests\test_core_exec.py tests\test_core_tool_router.py -q`
  - `160 passed, 2 skipped`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`

Known gaps:

- This slice preserves the pure conversion contract for legacy `shell_command`; full Rust shell runtime execution remains approximated elsewhere by the Python local runtime and unified exec path.
