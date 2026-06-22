# codex-tools src/json_schema.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/json_schema.rs`
Rust tests: `codex/codex-rs/tools/src/json_schema_tests.rs`
Python module: `pycodex/tools/json_schema.py`
Python tests: deferred; Rust-derived coverage should mirror
`codex/codex-rs/tools/src/json_schema_tests.rs`

## Behavior contract

`src/json_schema.rs` owns the generic tool JSON-Schema subset:

- `JsonSchemaPrimitiveType`, `JsonSchemaType`, `JsonSchema`, and
  `AdditionalProperties`.
- `parse_tool_input_schema` with sanitize, unreachable-definition pruning, and
  large-schema compaction.
- `parse_tool_input_schema_without_compaction` for trusted schema parsing.
- Local `$defs` / `definitions` reference reachability, including percent
  encoded JSON pointers and nested local refs.

## Python alignment

`pycodex.tools.json_schema` implements the Rust-owned schema data model and
normalization pipeline. It preserves boolean-schema lowering, type inference,
`const` to single-value `enum` rewriting, default object/array children,
nullable unions, `anyOf`, schema-valued `additionalProperties`, malformed
definition-table dropping, unreachable definition pruning, singleton-null
rejection, and best-effort large-schema compaction.

## Evidence

The Rust behavior contract is described by
`codex/codex-rs/tools/src/json_schema_tests.rs`. Focused Python test migration
is deferred by the current crate automation rule until `codex-tools` functional
module code is complete.
