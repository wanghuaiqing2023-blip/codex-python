# 2026-06-02 default session unified exec manager

## Upstream slice

- Used the upstream graph to stay on the core tool-dispatch path:
  - `core/src/tools/parallel.rs`
  - `core/src/tools/router.rs`
  - `core/src/tools/handlers/unified_exec/exec_command.rs`
  - `core/src/unified_exec/process_manager.rs`
- This slice is part of the common `model response -> tool dispatch -> exec manager -> tool output -> follow-up request` loop.

## Python slice

- Added default `services.unified_exec_manager` to `InMemoryCodexSession`.
- The default in-memory core session now naturally supplies `UnifiedExecProcessManager` to `ExecCommandHandler` through `ToolInvocation.session`.
- Added a turn-runtime test that simulates a model `exec_command` call, executes a real local command through the default session manager, records the tool output, and sends it into the follow-up model request.

## Validation

- `python -m py_compile pycodex/core/session_runtime.py tests/test_core_turn_runtime.py`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_session_exec_command_uses_unified_exec_manager`
- `python -m unittest tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_unified_exec tests.test_core_unified_exec_handler`
- `python -m unittest tests.test_core_tool_router tests.test_exec_local_runtime`

## Known follow-up debt

- The in-memory manager remains a stdlib local-process approximation; full Rust sandbox, PTY, and network-denial handling are not complete.
- `write_stdin` is covered at manager/handler level, but the default-session turn loop still needs a model-level two-step `exec_command` then `write_stdin` test.
