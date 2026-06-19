# codex-tools src/tool_call.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/tool_call.rs`
Rust tests: none in `codex-tools`
Python module: `pycodex/tools/tool_call.py`
Python behavior implementation: `pycodex/core/tools/router.py`
Python tests: `tests/test_core_tool_router.py`

## Behavior contract

`src/tool_call.rs` owns the shared invocation snapshot used by extension tool
runtimes:

- `ConversationHistory::new` stores an immutable response history snapshot and
  `items()` returns that snapshot.
- `ToolCall` carries turn id, call id, tool name, truncation policy,
  conversation history, and `ToolPayload`.
- `ToolCall::function_arguments()` returns function payload arguments verbatim,
  including an empty string.
- Non-function payloads raise `FunctionCallError::Fatal` with
  `tool {tool_name} invoked with incompatible payload`.

## Python alignment

`pycodex.core.tools.router` already implements the shared Python
`ConversationHistory` and `ToolCall` types used by tool dispatch. The new
`pycodex.tools.tool_call` module re-exports those exact types from the
canonical tools-crate package path, avoiding duplicate call classes while
matching Rust ownership.

## Evidence

Existing Python coverage validates the Rust behavior contract:

- `tests/test_core_tool_router.py` covers incompatible payload fatal formatting,
  empty function argument preservation, response item mapping coercion in
  `ConversationHistory`, and `ToolCall` extension context fields.

Focused validation is deferred by the current crate automation rule until
`codex-tools` functional module code is complete.
