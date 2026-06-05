# Local HTTP command-actions default shell

## Scope

- Tightened local HTTP command execution metadata on the core shell-tool path.
- When a model emits `exec_command` without an explicit shell, Python now derives the command-action argv from the ported default user shell helper instead of hard-coding `bash -lc`.
- This affects user-visible command execution timeline metadata and JSON event `command_actions`; it does not change the subprocess runner path used to execute the command.

## Upstream behavior

- Relevant Rust source:
  - `codex-rs/core/src/shell.rs`
  - `codex-rs/core/src/tools/handlers/shell_tests.rs`
- Rust `Shell::derive_exec_args()` uses:
  - POSIX shells: `<shell> -lc <command>` for login, `<shell> -c <command>` for non-login.
  - PowerShell: `<shell> -Command <command>` for login, `<shell> -NoProfile -Command <command>` for non-login.
  - Cmd: `<shell> /c <command>`.
- Rust `default_user_shell()` selects PowerShell on Windows where available, and the user's/default POSIX shell on Unix-like platforms.

## Python changes

- `pycodex/exec/local_runtime.py`
  - `_shell_command_execution_argv()` now calls `default_user_shell().derive_exec_args(...)` when `LocalHttpShellInvocation.shell` is omitted.
  - Explicit model-provided shells keep the existing handling for PowerShell, Cmd, and POSIX shells.
- `tests/test_exec_local_runtime.py`
  - Added tests proving implicit shell metadata follows the patched default shell helper.
  - Added tests proving explicit shell metadata remains stable.
- `tests/test_core_shell.py`
  - Fixed POSIX shell path expectations to match the existing ported helper's forward-slash normalization on Windows.

## Validation

```powershell
python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py tests\test_core_shell.py
python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_command_execution_argv_uses_default_user_shell tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_command_execution_argv_preserves_explicit_shell tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer tests.test_core_tool_events.ToolEventsTests.test_command_actions_from_argv_uses_shell_command_parser
python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests tests.test_core_shell tests.test_shell_command_parse_command tests.test_core_tool_events.ToolEventsTests.test_command_actions_from_argv_uses_shell_command_parser
python -m unittest tests.test_cli_local_http_smoke_suite
```

Results:

- Focused local HTTP command-action tests: 4 passed.
- Shell/helper/parser related tests: 50 passed.
- Core local HTTP CLI smoke suite: 23 passed.

## Follow-up

- This closes the local HTTP command-action default shell approximation. Full unified-exec process manager parity remains broader work and was intentionally not expanded in this slice.
