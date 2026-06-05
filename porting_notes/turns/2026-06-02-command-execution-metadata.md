# Command Execution Metadata

## Scope

- Continued the core `exec -> tool dispatch -> user-visible events -> final answer` path.
- Expanded Python exec JSON command execution items to preserve Rust/app-server metadata that was already present in the Python protocol layer.

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/app-server-protocol/src/protocol/item_builders.rs#build_command_execution_begin_item`
  - `function:codex-rs/app-server-protocol/src/protocol/item_builders.rs#build_command_execution_end_item`
  - `class:codex-rs/protocol/src/protocol.rs#ExecCommandBeginEvent`
  - `class:codex-rs/protocol/src/protocol.rs#ExecCommandEndEvent`
  - `class:codex-rs/exec/src/exec_events.rs#CommandExecutionItem`
- Rust source read:
  - `codex/codex-rs/app-server-protocol/src/protocol/item_builders.rs`
  - `codex/codex-rs/protocol/src/protocol.rs`

## Rust behavior confirmed

- `CommandExecution` thread items preserve command, cwd, process id, source, parsed command actions, status, aggregated output, exit code, and duration.
- Begin items carry in-progress status and command metadata.
- End items carry final status, aggregated output, exit code, and duration.

## Python changes

- `pycodex/exec/events.py`
  - `command_execution_item` now accepts and emits `cwd`, `process_id`, `source`, `command_actions`, and `duration_ms` when available.
  - Typed `CommandExecutionItem` conversion now preserves those fields in exec JSON output.
- `pycodex/exec/event_processor.py`
  - App-server command execution notifications now preserve the same metadata when converted to exec JSON items.
- `pycodex/exec/local_runtime.py`
  - Local HTTP paired shell timeline items now include cwd/source metadata from the exec config and shell invocation.
  - Session-backed shell outputs can surface process/session id and duration metadata when present in the local output payload.
- `tests/test_exec_event_processor.py` and `tests/test_exec_local_runtime.py`
  - Added assertions for cwd/source/command metadata on typed and local HTTP command execution items.

## Validation

- `python -m py_compile pycodex\exec\events.py pycodex\exec\event_processor.py pycodex\exec\local_runtime.py tests\test_exec_event_processor.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_event_processor tests.test_exec_local_runtime`

## Known gaps

- Parsed command actions remain empty for local HTTP shell calls because the Python local runtime does not yet port Rust's parsed-command classifier for this path.
