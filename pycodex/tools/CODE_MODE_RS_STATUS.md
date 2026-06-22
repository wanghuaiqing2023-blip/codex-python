# codex-tools src/code_mode.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/code_mode.rs`
Rust tests: `codex/codex-rs/tools/src/code_mode_tests.rs`
Python module: `pycodex/tools/code_mode.py`
Python tests: `tests/test_core_code_mode.py`

## Behavior contract

`src/code_mode.rs` owns the `codex-tools` bridge between top-level tool specs
and `codex-code-mode` nested tool definitions:

- `augment_tool_spec_for_code_mode`.
- `tool_spec_to_code_mode_tool_definition`.
- `collect_code_mode_tool_definitions`.
- `collect_code_mode_exec_prompt_tool_definitions`.
- `code_mode_name_for_tool_name`.

## Python alignment

`pycodex.tools.code_mode` mirrors the Rust module boundary while reusing the
existing code-mode runtime dataclasses and augmentation helpers. It preserves
Rust's function/freeform/namespace conversion, unsupported hosted-tool skips,
sorted de-duplication by code-mode name, exec/wait nested-tool filtering, and
namespace name joining rule.

The lower-level `codex-code-mode` crate behavior remains owned by
`pycodex.code_mode` and `pycodex.core.tools.code_mode`; this module only owns
the `codex-tools/src/code_mode.rs` adapter layer.

## Evidence

Existing Python coverage in `tests/test_core_code_mode.py` exercises the
adapter behavior for function and freeform augmentation, nested tool conversion,
collection sorting/de-duplication, unsupported variant skips, and namespace
name handling.

Focused validation is deferred by the current crate automation rule until
`codex-tools` functional module code is complete.
