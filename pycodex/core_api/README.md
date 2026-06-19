# pycodex.core_api

Canonical Python package for the Rust facade crate:

- Rust crate path: `codex/codex-rs/core-api`
- Python package path: `pycodex/core_api`

## Module Correspondence

| Rust module | Python module |
| --- | --- |
| `src/lib.rs` | `pycodex/core_api/__init__.py` |

## Status

Status: complete.

`codex-core-api` is a single-module public facade crate. The Python package
re-exports existing Python counterparts for app-server protocol, arg0, config,
core, exec-server, feature, model-provider, protocol, and absolute-path types.
Where neighboring Rust crates are outside this module boundary and do not yet
have a concrete Python type, `pycodex.core_api` carries an explicit lightweight
facade placeholder so the public API name remains importable without expanding
this turn into those crates.

## Test Sources

Rust source:

```text
codex/codex-rs/core-api/src/lib.rs
```

Python parity tests:

```text
tests/test_core_api_lib_rs.py
```
