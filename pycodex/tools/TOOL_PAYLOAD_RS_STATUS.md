# codex-tools src/tool_payload.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/tool_payload.rs`
Rust tests: none in `codex-tools`
Python module: `pycodex/tools/tool_payload.py`
Python behavior implementation: `pycodex/core/tools/context.py`
Python tests: `tests/test_core_tool_context.py`, `tests/test_core_tool_router.py`

## Behavior contract

`src/tool_payload.rs` owns the canonical payload shapes accepted by
model-visible tool runtimes:

- `Function { arguments: String }`
- `ToolSearch { arguments: SearchToolCallParams }`
- `Custom { input: String }`
- `log_payload()`, which returns function arguments, tool-search query text, or
  custom input for telemetry/logging previews.

## Python alignment

`pycodex.core.tools.context.ToolPayload` already implements the shared payload
type used by tool dispatch. The new `pycodex.tools.tool_payload` module
re-exports that same type from the canonical tools-crate package path, avoiding
duplicate payload classes while matching Rust ownership.

## Evidence

Existing Python coverage validates the Rust behavior contract:

- `tests/test_core_tool_context.py` covers `ToolPayload.function`,
  `ToolPayload.tool_search`, `ToolPayload.custom`, shape validation, and
  `log_payload()` for all three Rust variants.
- `tests/test_core_tool_router.py` covers construction of function,
  tool-search, and custom payloads from response items and downstream runtime
  use.

Focused validation is deferred by the current crate automation rule until
`codex-tools` functional module code is complete.
