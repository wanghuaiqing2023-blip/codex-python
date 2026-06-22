# pycodex.test_binary_support

Canonical Python package for the Rust utility crate:

- Rust crate path: `codex/codex-rs/test-binary-support`
- Python package path: `pycodex/test_binary_support`

## Module Correspondence

| Rust module | Python module |
| --- | --- |
| `lib.rs` | `pycodex/test_binary_support/__init__.py` |

## Status

Status: complete.

`lib.rs` is a single-module crate. The Python implementation preserves the test
binary dispatch mode selection, temporary `CODEX_HOME` setup, arg0 alias
installation delegation, environment restoration, and guard path access.

## Test Sources

Rust source:

```text
codex/codex-rs/test-binary-support/lib.rs
codex/codex-rs/core/tests/suite/mod.rs
codex/codex-rs/exec-server/tests/common/mod.rs
```

Python parity tests:

```text
tests/test_test_binary_support_lib_rs.py
```
