# pycodex.utils.output_truncation

Python counterpart for the Rust `codex-utils-output-truncation` crate.

## Rust Counterpart

```text
Rust crate: codex-utils-output-truncation
Rust path: codex/codex-rs/utils/output-truncation
Cargo role: truncating tool/function output with TruncationPolicy
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/utils/output_truncation/__init__.py` | crate public surface |
| `src/truncate_tests.rs` | `tests/test_utils_output_truncation.py` | Rust-derived parity tests |

## Alignment Unit

The acceptance unit is a module-scoped behavior contract:

```text
utils.output_truncation.formatted_text
utils.output_truncation.raw_text
utils.output_truncation.content_items_formatted
utils.output_truncation.content_items_budgeted
utils.output_truncation.byte_count_token_conversion
```

## Current Status

Status: module_completed_with_focused_validation.

The Python package preserves Rust behavior for byte/token truncation policy
dispatch, formatted total-line prefixes, UTF-8-safe middle truncation through
`pycodex.utils.string`, content-item text merging, image/encrypted-content
preservation, omitted text-item summaries, and `i64` byte-count token
conversion clamping for non-positive values.

`pycodex.core.tools.context` keeps its existing public helper names but now
imports these pure functions from this Rust-aligned utility package.

## Test Sources

Primary Python parity tests:

```text
tests/test_utils_output_truncation.py
tests/test_core_tool_context.py
```

Rust source/test anchors:

```text
codex/codex-rs/utils/output-truncation/src/lib.rs
codex/codex-rs/utils/output-truncation/src/truncate_tests.rs
```

## Stop Rule

This module contract is complete once the direct utility tests and the core tool
context tests pass. Runtime-specific output rendering, MCP response conversion,
and exec command response shaping remain owned by their existing core modules.
