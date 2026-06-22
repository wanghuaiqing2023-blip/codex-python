# request_processors/command_exec_processor.rs Status

Rust module: `codex-app-server/src/request_processors/command_exec_processor.rs`

Python module: `pycodex/app_server/request_processors_command_exec_processor.py`

Status: `complete`

## Covered Contract

- Processor construction preserves Rust's injected arg0 paths, config,
  outgoing sender, config manager, environment manager, and command exec manager
  ownership boundary.
- One-off command execution requires a configured local environment before
  building or starting a command.
- Request validation mirrors Rust error messages for empty command, mutually
  exclusive `permissionProfile`/`sandboxPolicy`, terminal size without TTY,
  output cap conflicts, timeout conflicts, and negative timeout values.
- CWD resolution, environment override merging, output cap selection,
  expiration mode, capture policy, and sandbox CWD selection are projected.
- Permission-profile reload delegates to the injected config manager and maps
  reload/disallowed-profile failures to Rust's invalid-request messages.
- Legacy sandbox policy validation delegates to injected permission hooks and
  maps validation failures to Rust's invalid-request messages.
- Managed network proxy startup and exec request construction are injectable
  runtime boundaries with Rust-compatible internal-error text.
- `command_exec_write`, `command_exec_resize`, `command_exec_terminate`, and
  `connection_closed` delegate to `CommandExecManager`.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/command_exec_processor.rs`
- Python parity tests staged in
  `tests/test_app_server_request_processors_command_exec_processor_rs.py`.
- Focused validation completed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_command_exec_processor_rs.py -q`
  -> 13 passed.
- Syntax validation completed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_command_exec_processor.py tests/test_app_server_request_processors_command_exec_processor_rs.py`.

## Known Gaps

- Concrete `codex_core::exec::build_exec_request`, process spawning, real
  sandbox construction, and managed network proxy lifetimes remain injected
  runtime boundaries.
