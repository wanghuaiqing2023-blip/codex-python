# pycodex.response_debug_context

Canonical Python package for the Rust crate:

- Rust crate path: `codex/codex-rs/response-debug-context`
- Python package path: `pycodex/response_debug_context`

## Module Correspondence

| Rust module | Python module |
| --- | --- |
| `src/lib.rs` | `pycodex/response_debug_context/__init__.py` |

## Status

Status: complete.

The package mirrors the Rust response debug helper surface: extracting request
ids, Cloudflare ray ids, authorization errors, and base64-encoded authorization
error codes from HTTP transport errors, plus stable body-free telemetry error
messages.

## Test Sources

Rust source and tests:

```text
codex/codex-rs/response-debug-context/src/lib.rs
```

Python parity tests:

```text
tests/test_response_debug_context_lib_rs.py
```
