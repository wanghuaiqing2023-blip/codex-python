# codex-tools src/dynamic_tool.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/dynamic_tool.rs`
Rust tests: `codex/codex-rs/tools/src/dynamic_tool_tests.rs`
Python module: `pycodex/tools/dynamic_tool.py`
Python tests: deferred; Rust-derived coverage should mirror
`codex/codex-rs/tools/src/dynamic_tool_tests.rs`

## Behavior contract

`src/dynamic_tool.rs` owns `parse_dynamic_tool`, which converts a protocol
`DynamicToolSpec` into a tools `ToolDefinition` by:

- copying `name` and `description`;
- sanitizing/parsing `input_schema` through `parse_tool_input_schema`;
- setting `output_schema` to `None`;
- preserving `defer_loading`.

## Python alignment

`pycodex.tools.dynamic_tool.parse_dynamic_tool` accepts either a
`DynamicToolSpec` or its mapping shape, uses the `codex-tools` JSON Schema
parser, and returns the canonical `pycodex.tools.ToolDefinition`.

## Evidence

The Rust behavior contract is described by
`codex/codex-rs/tools/src/dynamic_tool_tests.rs`, covering input-schema
sanitization and `defer_loading` preservation. Focused Python test migration is
deferred by the current crate automation rule until `codex-tools` functional
module code is complete.
