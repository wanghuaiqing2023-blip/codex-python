# pycodex.utils.string

Python counterpart for the Rust `codex-utils-string` crate.

## Rust Counterpart

```text
Rust crate: codex-utils-string
Rust path: codex/codex-rs/utils/string
Cargo role: string truncation, ASCII JSON, UUID detection, and tag/path helpers
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/utils/string/__init__.py` | crate public surface and small helpers |
| `src/json.rs` | `pycodex/utils/string/__init__.py` | ASCII-safe JSON serialization |
| `src/truncate.rs` | `pycodex/utils/string/__init__.py` | UTF-8-safe middle truncation and token estimates |
| `src/truncate/tests.rs` | `tests/test_core_string_utils.py` | Rust-derived parity tests |

## Alignment Unit

The acceptance unit is a module-scoped behavior contract:

```text
utils.string.utf8_prefix_truncation
utils.string.middle_split
utils.string.middle_truncate_chars
utils.string.middle_truncate_tokens
utils.string.metric_tag_sanitization
utils.string.uuid_detection
utils.string.markdown_location_suffix
utils.string.ascii_json
```

## Current Status

Status: module_completed_with_focused_validation.

The public Rust surface from `src/lib.rs` has been reviewed against the Python
exports: ASCII JSON serialization, UTF-8 prefix truncation, middle truncation
and approximate token helpers, metric tag sanitization, UUID detection, and
markdown location suffix normalization are covered. Python keeps
`truncate_to_char_boundary` and `_split_string` as local/testing helpers; they
are documented by tests and are not Rust public exports.

## Test Sources

Primary Python parity tests:

```text
tests/test_core_string_utils.py
```

Rust test sources:

```text
codex/codex-rs/utils/string/src/lib.rs
codex/codex-rs/utils/string/src/json.rs
codex/codex-rs/utils/string/src/truncate/tests.rs
```

## Stop Rule

This module contract is complete once `tests/test_core_string_utils.py` passes.
Do not rescan this slice unless a related test fails, Rust source changes, or a
future task explicitly targets this package.
