# 2026-06-02 default session write_stdin loop

## Upstream slice

- Confirmed `codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs`.
- The Rust handler reads `session_id`, `chars`, `yield_time_ms`, and `max_output_tokens`, calls `session.services.unified_exec_manager.write_stdin(...)`, emits a terminal interaction for non-empty stdin, and lets a final poll observe the original exec command completion.

## Python slice

- Added `call_id` to `ExecCommandRequest` and now preserve the original `exec_command` call id in `UnifiedExecProcessManager` live process entries.
- The default session tool loop can now run a model-level sequence of:
  1. `exec_command` with `tty=true`
  2. `write_stdin` using the returned session id
  3. final assistant response after the tool output is recorded
- Added a default-session turn-runtime test using a temporary Python script to avoid shell quoting dependencies.

## Validation

- `python -m py_compile pycodex/core/unified_exec.py pycodex/core/unified_exec_handler.py tests/test_core_turn_runtime.py`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_session_exec_command_then_write_stdin`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_session_runtime`
- `python -m unittest tests.test_core_tool_router tests.test_exec_local_runtime`

## Known follow-up debt

- The stdlib process manager still approximates Rust PTY behavior. It supports stdin for `tty=true`, but does not yet emulate full terminal semantics.
- The default-session path now has model-level interactive coverage; the next high-value slice is a CLI-level smoke that exercises the same loop through `pycodex exec`.
