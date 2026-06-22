# codex-tools src/tool_definition.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/tool_definition.rs`
Rust tests: `codex/codex-rs/tools/src/tool_definition_tests.rs`
Python module: `pycodex/tools/tool_definition.py`
Python tests: `tests/test_core_tool_definition.py`

## Behavior contract

Rust `src/tool_definition.rs` owns the generic tool metadata record used by
downstream tool-spec builders:

- `ToolDefinition` stores `name`, `description`, `input_schema`,
  optional `output_schema`, and `defer_loading`;
- `renamed(...)` returns a copy with only the name changed;
- `into_deferred()` clears `output_schema` and marks the definition deferred.

## Python alignment

`pycodex.tools.tool_definition.ToolDefinition` mirrors the Rust data shape and
copy-returning helpers. Python additionally supports mapping round-trips and
defensive deep-copy/type checks so downstream Python code cannot mutate schema
payloads through aliasing.

## Evidence

- Rust source inspected: `codex/codex-rs/tools/src/tool_definition.rs`.
- Rust tests inspected:
  `codex/codex-rs/tools/src/tool_definition_tests.rs`.
- Python implementation inspected: `pycodex/tools/tool_definition.py`.
- Python tests inspected: `tests/test_core_tool_definition.py`.
- Validation deferred by current crate automation rule until `codex-tools`
  functional module code is complete.
