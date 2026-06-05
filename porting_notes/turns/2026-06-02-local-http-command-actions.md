# Local HTTP Command Actions

## Scope

- Continued the core `exec -> tool dispatch -> user-visible events -> final answer` path.
- Filled the local HTTP `command_execution.command_actions` gap left after adding command execution metadata.

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/shell-command/src/parse_command.rs#parse_command`
  - `class:codex-rs/protocol/src/parse_command.rs#ParsedCommand`
  - `class:codex-rs/app-server-protocol/src/protocol/v2/item.rs#CommandAction`
  - `function:codex-rs/app-server-protocol/src/protocol/v2/item.rs#from_core_with_cwd`
  - `function:codex-rs/app-server-protocol/src/protocol/item_builders.rs#build_command_execution_begin_item`
- Rust source read:
  - `codex/codex-rs/app-server-protocol/src/protocol/v2/item.rs`
  - `codex/codex-rs/app-server-protocol/src/protocol/item_builders.rs`

## Rust behavior confirmed

- Command execution items derive `command_actions` by parsing the shell argv with `parse_command`.
- Parsed commands are converted with cwd-aware `CommandAction::from_core_with_cwd`.
- Read actions get cwd-joined paths; list/search/unknown actions preserve their parsed command payloads.

## Python changes

- `pycodex/core/tool_events.py`
  - Added `command_actions_from_argv()` as a small public wrapper around the existing Python parse-command port and command-action conversion logic.
- `pycodex/core/__init__.py`
  - Re-exported `command_actions_from_argv`.
- `pycodex/exec/local_runtime.py`
  - Local HTTP paired shell `command_execution` items now populate `command_actions` using the same parser/converter path.
  - Default local shell display uses the existing `bash -lc <command>` argv approximation already used by local approval messaging.
- `tests/test_core_tool_events.py`
  - Added direct coverage for `cat README.md` -> read action and `rg needle src` -> search action.
- `tests/test_exec_local_runtime.py`
  - Added local HTTP timeline assertions that `pwd` carries an unknown command action on begin/end events.

## Validation

- `python -m py_compile pycodex\core\tool_events.py pycodex\core\__init__.py pycodex\exec\local_runtime.py tests\test_core_tool_events.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_core_tool_events tests.test_exec_local_runtime`

## Known gaps

- Local HTTP still approximates the implicit shell argv as `bash -lc <command>` when the model does not specify a shell. That matches current local approval display, but deeper platform-specific shell selection remains a future parity slice.
