# pycodex.utils.template

Python counterpart for the Rust `codex-utils-template` crate.

## Rust Counterpart

```text
Rust crate: codex-utils-template
Rust path: codex/codex-rs/utils/template
Cargo role: strict string templating for prompt and text assets
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/utils/template/__init__.py` | crate public surface and inline tests |
| `README.md` | `pycodex/utils/template/README.md` | supported syntax and strictness policy |

## Alignment Unit

The acceptance unit is a module-scoped behavior contract:

```text
utils.template.parse_segments
utils.template.literal_delimiter_escapes
utils.template.placeholder_inventory
utils.template.strict_render_values
utils.template.error_wrapping
utils.template.byte_offset_errors
```

## Current Status

Status: module_completed_with_focused_validation.

The Python implementation preserves Rust's strict syntax:

```text
{{ name }} placeholder interpolation
{{{{ literal {{
}}}} literal }}
```

Parsing fails for empty, nested, unmatched, and unterminated placeholders.
Rendering fails for missing, extra, and duplicate values. Error messages and
parse offsets are aligned to Rust's byte-indexed `Display` behavior.

## Test Sources

Primary Python parity tests:

```text
tests/test_utils_template.py
```

Rust source/test anchors:

```text
codex/codex-rs/utils/template/src/lib.rs
codex/codex-rs/utils/template/README.md
```

## Stop Rule

This module contract is complete once `tests/test_utils_template.py` passes.
Do not replace existing domain-specific render helpers unless a future module
slice confirms they should use this strict template crate.
